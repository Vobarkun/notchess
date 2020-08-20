import json
from collections.abc import Iterable

from gevent import monkey
monkey.patch_all()

from flask import Flask, render_template
from flask_assets import Environment, Bundle
from werkzeug.debug import DebuggedApplication

from geventwebsocket import WebSocketServer, WebSocketApplication, Resource

flask_app = Flask(__name__)
flask_app.debug = True
assets = Environment(flask_app)
assets.debug = True

import fairy

def dataDictionary(board, msgtype = "position"):
    return {
        "fen": board.getFen(),
        "dests": board.generateMoveDict(),
        "check": board.isCheck(board.activeColor.opp()),
        "result": board.result(),
        "names": {"white": board.whiteArmy, "black": board.blackArmy}
    }

class ChessApplication(WebSocketApplication):
    board = fairy.Board.fromArmy()
    nPlayers = {
        fairy.Color.white: 0,
        fairy.Color.black: 0
    }


    def __init__(self, ws):
        super().__init__(ws)

    def on_open(self):
        client = self.ws.handler.active_client

        nw = ChessApplication.nPlayers[fairy.Color.white]
        nb = ChessApplication.nPlayers[fairy.Color.black]

        color = fairy.Color.white if nw <= nb else fairy.Color.black
        client.color = color
        ChessApplication.nPlayers[color] += 1

        client.army = "Fabulous Fides"
        client.wantsNewGame = False

        print(color.name + " connected")

    def on_message(self, message):
        client = self.ws.handler.active_client
        if message is None:
            return
        message = json.loads(message)
        if message["msg_type"] == "hi":
            return
        print(message["msg_type"])
        if message["msg_type"] == "move":
            if self.board[fairy.Square(message["orig"])].color == self.board.activeColor:
                start = fairy.timer()
                move = self.board.makeMove(message["orig"], message["dest"])
                self.broadcast_move(move)
                print(move, fairy.timer() - start)
        elif message["msg_type"] == "update_position":
            self.update_position(client)
        elif message["msg_type"] == "undo":
            ChessApplication.board.undo(message["n"])
            self.broadcast_position(clearLast = True)
        elif message["msg_type"] == "select_army":
            client.army = message["army"]
        elif message["msg_type"] == "newgame":
            client.wantsNewGame = True
            if all([c.wantsNewGame for c in self.clients()]):
                self.flipBoard()
                armies = {"white": ChessApplication.board.whiteArmy, "black": ChessApplication.board.blackArmy}
                for c in self.clients():
                    armies[c.color.name] = c.army
                ChessApplication.board = fairy.Board.fromArmy(armies["white"], armies["black"])
                self.broadcast({"msg_type": "newgame"})
                self.broadcast_position(clearLast = True)
                for c in self.clients():
                    c.wantsNewGame = False
        else:
            self.broadcast(message)

    def flipBoard(self):
        for client in self.clients():
            client.color = client.color.opp()

    def broadcast_move(self, move):
        data = dataDictionary(ChessApplication.board)
        for client in self.clients():
            client.ws.send(json.dumps({
                "msg_type": "move",
                "orig": str(move.orig),
                "dest": str(move.dest),
                "yourColor": client.color.name,
                **data,
                # "fen": ChessApplication.board.kriegspielFen(client.color)
            }))

    def update_position(self, client):
        data = dataDictionary(ChessApplication.board)
        client.ws.send(json.dumps({
            "msg_type": "position",
            "yourColor": client.color.name,
            **data,
            # "fen": ChessApplication.board.kriegspielFen(client.color)
        }))
        client.ws.send(json.dumps({
            "msg_type": "armies",
            "armies": list(fairy.armies.keys())
        }))

    def broadcast(self, data, clients = None):
        if clients is None:
            clients = self.clients()
        elif not isinstance(clients, Iterable):
            clients = [clients]
        j = json.dumps(data)
        for client in clients:
            client.ws.send(j)


    def broadcast_position(self, clearLast = False):
        data = dataDictionary(ChessApplication.board)
        for client in self.clients():
            client.ws.send(json.dumps({
            "msg_type": "position",
            "yourColor": client.color.name,
            "clearLast": clearLast,
            **data,
            # "fen": ChessApplication.board.kriegspielFen(client.color)
        }))

    def on_close(self, reason):
        print(self.ws.handler.active_client.color.name + " disconnected")
        ChessApplication.nPlayers[self.ws.handler.active_client.color] -= 1

    def clients(self):
        return self.ws.handler.server.clients.values()

@flask_app.route('/')
def index():
    return render_template('index.html')

WebSocketServer(
    ('localhost', 8000),

    Resource([
        ('^/websocket', ChessApplication),
        ('^/.*', DebuggedApplication(flask_app))
    ]),

    debug=False
).serve_forever()