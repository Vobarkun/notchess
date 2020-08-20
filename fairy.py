import collections
import itertools
from copy import copy, deepcopy
from enum import Enum
import math
import random

from timeit import default_timer as timer

startingFen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"

def symmetrize(offset, offset2 = None):
    if offset2 is None:
        i, j = offset
    else:
        i = int(offset)
        j = int(offset2)
    return list(set([(i, j), (i, -j), (-i, j), (-i, -j), 
            (j, i), (j, -i), (-j, i), (-j, -i)]))

def leftright(offsets):
    return list(set(offsets + [(-o[0], o[1]) for o in offsets]))

def topbottom(offsets):
    return list(set(offsets + [(o[0], -o[1]) for o in offsets]))

def tb(i, j):
    return topbottom([(i, j)])

def lr(i, j):
    return leftright([(i, j)])

def lrtb(i, j):
    return leftright(topbottom([(i, j)]))

def rank(n, color):
    if color == Color.white:
        return n - 1
    return 8 - n

def distance(sq1, sq2):
    diff = sq2 - sq1
    return max(abs(diff[0]), abs(diff[1]))

def epoffset(color):
    return (0, -1) if color == Color.white else (0, 1)

class Color(Enum):
    white = "w"
    black = "b"
    empty = " "
    wall = "-"

    def opp(self):
        if self == Color.white:
            return Color.black
        if self == Color.black:
            return Color.white
        return self

    def orientOffset(self, offset):
        if self == Color.black:
            return (offset[0], -offset[1])
        return offset


class Square():
    ranks = ["1", "2", "3", "4", "5", "6", "7", "8"]
    files = ["a", "b", "c", "d", "e", "f", "g", "h"]
    names = [f + r for f in ["a", "b", "c", "d", "e", "f", "g", "h"]
                   for r in ["1", "2", "3", "4", "5", "6", "7", "8"]] 
          
    def __init__(self, f, r = None):
        if type(f) is str:
            r = int(f[1]) - 1
            f = ord(f[0]) - ord("a")
        if type(f) is tuple:
            f, r = f
        if type(f) is Square:
            r = f.r
            f = f.f
        self.f = f
        self.r = r

    def coords(self):
        return (self.f, self.r)

    def __str__(self):
        try:
            return Square.files[self.f] + Square.ranks[self.r]
        except IndexError:
            return str(self.f + 1) + str(self.r + 1) 

    def __add__(self, f, r = None):
        if r is None:
            f, r = f
        return Square(self.f + f, self.r + r)

    def __eq__(self, other):
        if type(other) is not Square: return False
        return self.r == other.r and self.f == other.f

    def __sub__(self, other):
        if type(other) is Square:
            return (self.f - other.f, self.r - other.r)
        else:
            return Square(self.f - other[0], self.r - other[1])


class MoveGen:
    @staticmethod
    def base(self, orig, board, nrec = 0, dest = None, translate = True, attack = True, enpassant = False):
        if dest is None:
            return
        if board[dest].color == self.color.opp() and attack:
            yield Move(orig, dest, capture = True)
        elif board[dest].isempty():
            if enpassant and attack and board.epsquare == dest:
                yield Move(orig, dest, capture = dest + epoffset(self.color))
            elif translate:
                yield Move(orig, dest)

    @staticmethod
    def jump(offsets, translate = True, attack = True, enpassant = False, cylindrical = False):
        def generator(self, orig, board, nrec = 0):
            for offset in offsets:
                offset = self.color.orientOffset(offset)
                dest = orig + offset
                if cylindrical:
                    dest.f %= 8
                yield from MoveGen.base(self, orig, board, nrec, dest, translate, attack, enpassant)
        return generator

    @staticmethod
    def slide(offsets, translate = True, attack = True, enpassant = False, dist = 100, mod = 1, rem = 0, cylindrical = False, spacious = False, njumps = 0):
        def generator(self, orig, board, nrec = 0):
            for offset in offsets:
                jumpsleft = njumps
                offset = self.color.orientOffset(offset)
                dest = orig
                for i in range(1, dist + 1):
                    dest += offset
                    if cylindrical:
                        dest.f %= 8
                    if not (spacious and board[dest + offset].color in [Color.white, Color.black]) or jumpsleft <= 0 and i % mod == rem:
                        yield from MoveGen.base(self, orig, board, nrec, dest, translate, attack, enpassant)
                    if not board[dest].isempty():
                        if jumpsleft <= 0:
                            break
                        jumpsleft -= 1
        return generator

    @staticmethod
    def hop(offsets, translate = True, attack = True, enpassant = False, chain = True, short = False):
        def generator(self, orig, board, nrec = 0):
            for offset in offsets:
                offset = self.color.orientOffset(offset)
                capture = orig + offset
                captures = []
                gcd = math.gcd(*offset) if short else 1
                dest = capture + (offset[0] // gcd, offset[1] // gcd)
                while board.inbounds(dest):
                    if not board[dest].isempty() or board[capture].isempty():
                        if enpassant and board.epsquare == capture:
                            epoffset = (0, -1) if self.color == Color.white else (0, 1)
                            captures.append(capture + epoffset)
                            yield Move(orig, dest, capture = captures)
                        else:
                            break
                    if translate and board[capture].color == self.color:
                        yield Move(orig, dest, capture = captures)
                    if attack and board[capture].color == self.color.opp():
                        captures.append(capture)
                        yield Move(orig, dest, capture = captures)
                    capture = dest + offset
                    dest = capture + (offset[0] // gcd, offset[1] // gcd)
                    if not chain:
                        break
        return generator

    @staticmethod
    def bigpawn(offsets = [(0, 1)]):
        def generator(self, orig, board, nrec = 0):
            for offset in offsets:
                if self.color == Color.black:
                    offset = (offset[0], -offset[1])
                if orig.r in [1, 6]:
                    epsquare = orig + offset
                    if board[epsquare].isempty():
                        dest = orig + offset + offset
                        if board[dest].isempty():
                            yield Move(orig, dest)
        return generator

    @staticmethod
    def castle(name = "R"):
        def generator(self, orig, board, nrec = 0):
            if nrec > 0:
                return
            if self.nmoves == 0:
                for square in board.squares():
                    target = board[square]
                    if target.name.upper() in name.upper() and target.color == self.color:
                        if target.nmoves == 0:
                            offset = square - orig
                            gcd = math.gcd(*offset)
                            offset = (offset[0] // gcd, offset[1] // gcd)
                            destR = orig + offset
                            if board[destR].isempty() or destR == orig or destR == square:
                                dest = orig + offset + offset
                                if board[dest].isempty() or dest == square:
                                    yield Move(orig, dest, path = [orig, destR], sideeffects = [Move(square, destR, isfree = True)])
        return generator

    @staticmethod
    def powercastle(name = "RNBQP"):
        def generator(self, orig, board, nrec = 0):
            for square in board.squares():
                target = board[square]
                if target.name.upper() in name.upper() and target.color == self.color and square != orig:
                    offset = square - orig
                    gcd = math.gcd(*offset)
                    offset = (offset[0] // gcd, offset[1] // gcd)
                    destR = orig + offset
                    if board[destR].isempty() or destR == orig or destR == square:
                        dest = orig + offset + offset
                        if board[dest].isempty() or dest == square:
                            yield Move(orig, dest, sideeffects = [Move(square, destR, isfree = True)])
        return generator

    @staticmethod
    def powerhop(translate = True, attack = True, enpassant = False):
        def generator(self, orig, board, nrec = 0):
            for square in board.squares():
                target = board[square]
                if not target.isempty() and not square == orig:
                    offset = square - orig
                    gcd = math.gcd(*offset)
                    dest = orig + offset + (offset[0] // gcd, offset[1] // gcd)
                    yield from MoveGen.base(self, orig, board, nrec, dest, translate, attack, enpassant)
        return generator

    @staticmethod
    def swap(name):
        def generator(self, orig, board, nrec = 0):
            for dest in board.squares():
                target = board[dest]
                if target.name.upper() == name.upper() and target.color == self.color and not target.name == self.name:
                    yield Move(orig, dest, sideeffects = Move(dest, orig, isfree = True))
        return generator

    @staticmethod
    def compose(gen1, gen2):
        def generator(self, orig, board, nrec = 0):
            for g1 in gen1 if type(gen1) is list else [gen1]:
                for g2 in gen2 if type(gen2) is list else [gen2]:
                    for move2 in g2(self, orig, board):
                        yield move2
                        if not move2.capture:
                            for move1 in g1(self, move2.dest, board):
                                yield move1 * move2
        return generator

    @staticmethod
    def support(d, gen, name = "RNBQKP"):
        def generator(self, orig, board, nrec = 0):
            for square in board.squares():
                if board[square].color == self.color and distance(square, orig) <= d and square != orig and board[square].name.upper() in name:
                    yield from gen(board[square], square, board)
        return generator

    @staticmethod
    def student(d, enemies = True):
        def generator(self, orig, board, nrec = 0):
            if nrec > 0:
                return
            for square in board.squares():
                if distance(square, orig) <= d and board[square].name != self.name:
                    if board[square].color == self.color or enemies: 
                        for gen in board[square].moveGenerators:
                            yield from gen(self, orig, board, nrec = nrec + 1)
        return generator

    @staticmethod
    def inverseCapture(gen):
        def generator(self, orig, board, nrec = 0):
            if nrec == 0:
                for square in board.squares():
                    if board[square].color == self.color.opp():
                        flag = False
                        for g in board[square].moveGenerators:
                            for move in g(self, orig, board, nrec = nrec + 1):
                                if move.dest == square:
                                    yield move
                                    break
                            else:
                                continue
                            break
            for g in gen if type(gen) is list else [gen]:
                for move in g(self, orig, board, nrec):
                    if not move.capture or nrec > 0:
                        yield move
        return generator

    @staticmethod
    def halfling(gen):
        def generator(self, orig, board, nrec = 0):
            for g in gen if type(gen) is list else [gen]:
                for move in g(self, orig, board, nrec):
                    if (move.dest.r >= (move.orig.r - 1) / 2 and 
                        move.dest.f >= (move.orig.f - 1) / 2 and 
                        move.dest.r <= move.orig.r + (8 - move.orig.r) / 2 and 
                        move.dest.f <= move.orig.f + (8 - move.orig.f) / 2):
                        yield move
        return generator

class Effects:
    @staticmethod
    def enpassant(self, move, board):
        if distance(move.dest, move.orig) >= 2:
            board.epsquare = move.dest + ((0, -1) if self.color == Color.white else (0, 1))

    @staticmethod
    def promote(self, move, board):
        if move.dest.r == rank(8, self.color):
            board[move.dest] = deepcopy(board.pieces["Q" if self.color is Color.white else "q"])

    @staticmethod
    def rifle(self, move, board):
        if move.capture:
            board[move.orig] = board[move.dest]
            board[move.dest] = Piece.empty()


class Piece:
    def __init__(self, color=Color.white, name = "", movegen = None, onmove = None, isking = False):
        if movegen is None:
            movegen = []
        if onmove is None:
            onmove = []
        self.moveGenerators = movegen if type(movegen) is list else [movegen] 
        self.color = color
        self.name = name
        self.isking = isking
        self.nmoves = 0
        self.onmove = onmove if type(onmove) is list else [onmove]

    @classmethod
    def empty(cls):
        return cls(Color.empty, " ", [])
    
    @classmethod
    def wall(cls):
        return cls(Color.wall, "-", [])

    def generateMoves(self, square, board, nrec = 0):
        for generator in self.moveGenerators:
            yield from generator(self, square, board, nrec)

    def onMove(self, square, board):
        for f in self.onmove:
            f(self, square, board)        

    def isempty(self):
        return self.color == Color.empty

    def __str__(self):
        if self.color == Color.white: 
            return self.name.upper()
        else: 
            return self.name.lower()

    def __deepcopy__(self, memo):
        c = Piece(self.color, self.name, self.moveGenerators, self.onmove, self.isking)
        c.nmoves = self.nmoves
        return c

    @classmethod
    def defaults(cls):
        return {
            "R": cls(Color.white, "R", [
                MoveGen.slide(symmetrize(1, 0))
            ]),
            "N": cls(Color.white, "N", [
                MoveGen.jump(symmetrize(2, 1))
            ]),
            "B": cls(Color.white, "B", [
                MoveGen.slide(symmetrize(1, 1))
            ]),
            "Q": cls(Color.white, "Q", [
                MoveGen.slide(symmetrize(1, 1) + symmetrize(1, 0))
            ]),
            "K": cls(Color.white, "K", [
                MoveGen.jump(symmetrize(1, 1) + symmetrize(1, 0)),
                MoveGen.castle("R")
            ], isking = True),
            "P": cls(Color.white, "P", [
                MoveGen.jump([(0, 1)], attack = False),
                MoveGen.jump([(1, 1), (-1, 1)], translate = False, enpassant = True),
                MoveGen.bigpawn()
            ], onmove = [Effects.enpassant, Effects.promote]),
            " ": cls.empty()
        }

ferz = [MoveGen.jump(symmetrize(1, 1))]
alfil = [MoveGen.jump(symmetrize(2, 2))]
alfilSlider = [MoveGen.slide(symmetrize(2, 2))]
wazir = [MoveGen.jump(symmetrize(1, 0))]
dabbaba = [MoveGen.jump(symmetrize(2, 0))]
dabbabaSlider = [MoveGen.slide(symmetrize(2, 0))]
king = [MoveGen.jump(symmetrize(1, 1) + symmetrize(1, 0))]
bishop = [MoveGen.slide(symmetrize(1, 1))]
rook = [MoveGen.slide(symmetrize(1, 0))]
shortrook = [MoveGen.slide(symmetrize(1, 0), dist = 4)]
knight = [MoveGen.jump(symmetrize(2, 1))]
knightrider = [MoveGen.slide(symmetrize(2, 1))]
trebuchet = [MoveGen.jump(symmetrize(3, 0))]
barc = [MoveGen.jump(leftright([(2, 1), (1, -2)]))]
barcSlider = [MoveGen.slide(leftright([(2, 1), (1, -2)]))]
crab = [MoveGen.jump(leftright([(1, 2), (2, -1)]))]
crabSlider = [MoveGen.slide(leftright([(1, 2), (2, -1)]))]

armies = {
    "Fabulous Fides": {
        "R": rook,
        "N": knight,
        "B": bishop,
        "Q": bishop + rook
    },
    "Colorbound Clobberers": {
        "R": bishop + dabbaba,
        "N": wazir + alfil,
        "B": ferz + alfil + dabbaba,
        "Q": bishop + knight
    },
    "Nutty Knights": {
        "R": [MoveGen.slide([(1,0), (0,1), (-1,0)]), MoveGen.jump([(-1,-1), (0, -1), (1, -1)])],
        "N": [MoveGen.jump(leftright(topbottom([(1, 2), (1, 1)])))],
        "B": [MoveGen.jump(leftright([(2, 1), (1, 2), (1, 0), (1, -1), (0, -1)]))],
        "Q": [MoveGen.slide([(1,0), (0,1), (-1,0)]), MoveGen.jump(leftright([(2, 1), (1, 1), (1, 2), (1, -1), (0, -1)]))]
    },
    "Remarkable Rookies": {
        "R": shortrook,
        "N": wazir + dabbaba,
        "B": ferz + dabbaba + trebuchet,
        "Q": rook + knight
    },
    "Amazon Army": {
        "R": shortrook,
        "Q": knight + rook + bishop
    },
    "Forward Fides": {
        "R": [MoveGen.slide([(1,0), (0,1), (-1,0)]), MoveGen.jump([(-1,-1), (0, -1), (1, -1)])],
        "N": [MoveGen.jump(leftright([(2,1), (1, 2)])), MoveGen.slide([(-1, -1), (1, -1)])],
        "B": [MoveGen.jump(leftright([(2,-1), (1, -2)])), MoveGen.slide([(-1, 1), (1, 1)])],
        "Q": [MoveGen.jump(leftright([(2,-1), (1, -2), (1, -1), (0, -1)])), MoveGen.slide(leftright([(1, 0), (1, 1), (0, 1)]))]
    }, 
    "Avian Airforce": {
        "R": wazir + dabbabaSlider,
        "N": [MoveGen.jump(leftright([(1, 2), (1, 0), (0, 1), (0, -1)])), MoveGen.slide([(-2, -2), (2, -2)])],
        "B": ferz + alfilSlider,
        "Q": wazir + dabbabaSlider + ferz + alfilSlider
    },
    "Pizza Kings": {
        "R": [MoveGen.jump(leftright([(2, 2), (2, 0), (1, 1), (1, -1), (0, 1), (0, -1)]))],
        "N": [MoveGen.jump(leftright([(1, 2), (3, 1), (1, -1), (1, -2)]))],
        "B": [MoveGen.jump(topbottom(leftright([(0, 3), (1, 2), (1, 1), (1, 0)])))],
        "Q": king + alfil + dabbaba + [MoveGen.jump([(1, 2), (-1, 2)])]
    },
    "Meticulous Mashers": {
        "R": shortrook + ferz,
        "N": [MoveGen.jump(leftright(topbottom([(1, 2), (1, 1)])))],
        "B": bishop + [MoveGen.slide(symmetrize(1, 0), dist = 2, mod = 2)],
        "Q": rook + [MoveGen.slide(symmetrize(2, 1), dist = 2)]
    },
    "Seeping Switchers": {
        "R": [MoveGen.compose(MoveGen.slide([(2*o[0], 2*o[1])]), MoveGen.jump([o])) for o in symmetrize(1, 0)],
        "N": wazir + knight,
        "B": [MoveGen.compose(MoveGen.slide([(x*1, y*1)]), MoveGen.jump([(2*x, y), (x, 2*y)])) for x in [-1, 1] for y in [-1, 1]],
        "Q": [MoveGen.compose(MoveGen.slide([(2*o[0], 2*o[1])]), MoveGen.jump([o])) for o in symmetrize(1, 0) + symmetrize(1, 1)]
    },
    "Cylindrical Cinders": {
        "R": [MoveGen.jump(symmetrize(1, 0) + symmetrize(2, 2), cylindrical = True)],
        "N": [MoveGen.jump(symmetrize(2, 1), cylindrical = True)],
        "B": [MoveGen.slide(symmetrize(1, 1), cylindrical = True)],
        "Q": [MoveGen.jump(symmetrize(2, 1), cylindrical = True), MoveGen.slide(symmetrize(1, 0), cylindrical = True)]
    },
    "Spacious Cannoneers": {
        "R": [MoveGen.slide(symmetrize(1, 0), spacious = True, njumps = 1)],
        "N": wazir + [MoveGen.jump(lrtb(1, 2))],
        "B": [MoveGen.slide(symmetrize(1, 1), spacious = True, njumps = 1)],
        "Q": [MoveGen.slide(symmetrize(1, 0) + symmetrize(1, 1), spacious = True, njumps = 1)]
    },
    "Halflings": {
        "R": [MoveGen.halfling(rook + knightrider)],
        "N": [MoveGen.halfling(knightrider)],
        "B": dabbaba + [MoveGen.halfling(bishop)],
        "Q": [MoveGen.halfling(rook + bishop + knightrider)]
    },
    "DemiRifle": {
        "R": Piece(movegen = wazir + [MoveGen.jump([(0, 2)])], onmove = [Effects.rifle]),
        "N": Piece(movegen = [MoveGen.jump(leftright([(1, 2), ((2, -1))]))], onmove = [Effects.rifle]),
        "B": Piece(movegen = [MoveGen.jump(leftright([(1, -1), ((2, 2))]))], onmove = [Effects.rifle]),
        "Q": Piece(movegen = wazir + [MoveGen.jump([(0, 2)])] + [MoveGen.jump(leftright([(1, -1), ((2, 2))]))], onmove = [Effects.rifle]),
    },
    "Double Moves": {
        "R": [MoveGen.compose(rook, rook)],
        "N": [MoveGen.compose(knight, knight)],
        "B": [MoveGen.compose(bishop, bishop)],
        "Q": [MoveGen.compose(rook + bishop, rook + bishop)]
    },
    "Berolina": {
        "P": [MoveGen.jump([(1, 1), (-1, 1)], attack = False), MoveGen.jump([(0, 1)], translate = False, enpassant = True), MoveGen.bigpawn([(1, 1), (-1, 1)])]
    },
    "Support": {
        "R": king + [MoveGen.support(1, MoveGen.slide(symmetrize(1, 0)), name = "P")],
        "N": king + [MoveGen.support(1, MoveGen.jump(symmetrize(2, 1)), name = "P")],
        "B": king + [MoveGen.support(1, MoveGen.slide(symmetrize(1, 1)), name = "P")],
        "Q": king + [MoveGen.support(1, MoveGen.slide(symmetrize(1, 0) + symmetrize(1, 1)), name = "P")]
    },
    "Inverse Capture": {
        "R": [MoveGen.inverseCapture(rook)],
        "N": [MoveGen.inverseCapture(knight)],
        "B": [MoveGen.inverseCapture(bishop)],
        "Q": [MoveGen.inverseCapture(bishop + rook)],
        "K": Piece(Color.white, "K", [
            MoveGen.inverseCapture(MoveGen.jump(symmetrize(1, 1) + symmetrize(1, 0))),
            MoveGen.castle("R")
        ], isking = True)
    }
}

def generateArmy(name, color = Color.white):
    pieces = Piece.defaults()
    army = armies[name]
    for key in army:
        name = key if color == Color.white else key.lower()
        if type(army[key]) is Piece:
            pieces[key] = deepcopy(army[key])
            pieces[key].name = name
            pieces[key].color = color
        else:
            pieces[key] = Piece(color = color, name = name, movegen = army[key], onmove = pieces[key].onmove, isking = pieces[key].isking)
    if color == Color.black:
        pieces = {k.lower(): v for k, v in pieces.items()}
    return pieces


addons = [
    MoveGen.swap("P")
]

class Move:
    def __init__(self, orig, dest, capture = [], path = [], sideeffects = [], isfree = False):
        self.orig = orig
        self.dest = dest
        if type(capture) is bool:
            capture = [dest] if capture else []
        self.capture = capture
        self.sideeffects = sideeffects if type(sideeffects) is list else [sideeffects]
        self.isfree = isfree
        self.path = path

    def __str__(self):
        return str(self.orig) + ("x" if self.capture else "") + str(self.dest)

    def __bool__(self):
        return True

    def __mul__(self, move):
        return Move(move.orig, self.dest, capture = self.capture + move.capture, path = self.path + move.path, sideeffects = self.sideeffects + move.sideeffects, isfree = self.isfree and move.isfree)

    def captures(self):
        if self.capture:
            yield self.dest
            if type(self.capture) is Square:
                yield self.capture
            if type(self.capture) is list:
                yield from self.capture

    @classmethod
    def fromstring(cls, string):
        return cls(Square(string[0:2]), Square(string[-2:]), capture = "x" in string)


class Board:
    def __init__(self, fen = startingFen, pieces = Piece.defaults()):
        self.board = [[Piece.empty() for i in range(8)] for j in range(8)]
        self.activeColor = Color.white
        self.castling = {Color.white: [True, True], Color.black: [True, True]}
        self.epsquare = None
        self.halfmove = 0
        self.move = 1
        self.pattern = ""
        self.pieces = pieces
        self.loadFen(fen)
        self.whiteArmy = "Fabulous Fides"
        self.blackArmy = "Fabulous Fides"
        self.history = [self.getFen()]
    
    @classmethod
    def fromArmy(cls, white = None, black = None):
        if white is None:
            white = random.choice(list(armies.keys()))
        if black is None:
            black = random.choice(list(armies.keys()))
        piecesWhite = generateArmy(white, Color.white)
        piecesBlack = generateArmy(black, Color.black)
        pieces = {
            **piecesWhite, 
            **piecesBlack
        }
        board = cls(pieces = pieces) 
        board.whiteArmy = white
        board.blackArmy = black
        return board
  
    def __getitem__(self, square: Square):
        if self.inbounds(square):
            return self.board[square.r][square.f]
        return Piece.wall()

    def __setitem__(self, square: Square, value: Piece):
        if self.inbounds(square):
            self.board[square.r][square.f] = value

    def inbounds(self, square):
        if square.r < 0 or square.r > 7 or square.f < 0 or square.f > 7:
            return False
        return True

    def __iter__(self):
        return ((sq, self[sq]) for sq in self.squares())

    def squares(self):
        for i in range(8):
            for j in range(8):
                yield Square(i, j)

    def generateMoves(self, color = None, orig = None):
        if color is None:
            color = self.activeColor
        for move in self.generatePseudolegalMoves(color = color, orig = orig):
            for square in move.path:
                c = deepcopy(self)
                c[square] = c[move.orig]
                if square != move.orig:
                    c[move.orig] = Piece.empty()
                if c.isCheck(color = color.opp()):
                    break
            else:
                after = self.after(move)
                after.isCheck()
                if not after.isCheck():
                    yield move


    def generatePseudolegalMoves(self, color = None, orig = None):
        if color is None:
            color = self.activeColor
        for square in self.squares() if orig is None else [orig]:
            if self[square].color == color:
                yield from self[square].generateMoves(square, self)

    def generateMoveDict(self):
        dests = collections.defaultdict(list)
        for move in self.generateMoves():
            dests[str(move.orig)].append(str(move.dest))
        return dests

    def isattacked(self, square, color = None):
        if color is None:
            color = self.activeColor
        for move in self.generatePseudolegalMoves(color):
            if any(dest == square for dest in move.captures()):
                return True
        return False

    def makeMove(self, orig, dest):
        orig = Square(orig)
        dest = Square(dest)
        best = Move(orig, dest)
        for move in self.generateMoves(orig = orig):
            if move.orig == orig and move.dest == dest and len(move.sideeffects) >= len(best.sideeffects):
                if move.capture or not best.capture:
                    best = move
        self.execute(best)
        return best

    def execute(self, move):
        piece = self[move.orig]
        self[move.orig] = Piece.empty()

        for sideeffect in move.sideeffects:
            self.execute(sideeffect)

        if type(move.capture) in [Square, list]:
            for s in [move.capture] if type(move.capture) is Square else move.capture:
                self[s] = Piece.empty()
         
        self[move.dest] = piece
        piece.nmoves += 1
                
        piece.onMove(move, self)
    
        if not move.isfree:
            self.epsquare = None
            self.halfmove += 1
            if self.activeColor == "b":
                self.move += 1
            self.activeColor = self.activeColor.opp()
            self.pushHistory()
        

    def goto(self, halfmove):
        self.halfmove = halfmove
        self.loadFen(self.history[self.halfmove])
    
    def undo(self, n = 1):
        self.halfmove = min(len(self.history) - 1, max(0, self.halfmove - n))
        self.loadFen(self.history[self.halfmove])
    
    def redo(self, n = 1):
        self.undo(-n)

    def pushHistory(self):
        if self.halfmove < len(self.history):
            self.history = self.history[0:self.halfmove]
        self.history.append(self.getFen())

    def after(self, move):
        c = deepcopy(self)
        c.execute(move)
        return c

    def isCheck(self, color = None):
        if color is None:
            color = self.activeColor
        for sq in self.squares():
            if self[sq].color == color.opp() and self[sq].isking:
                if self.isattacked(sq, color):
                    return True
        return False
    
    def result(self):
        for _ in self.generateMoves(self.activeColor):
            break
        else:
            if self.isCheck(self.activeColor.opp()):
                return "1-0" if self.activeColor == Color.black else "0-1"
            return "½-½"
        return ""

    def loadFen(self, fen):
        position, active, castling, enpassant, halfmove, move = fen.split()

        for i in range(1, 9):
            position = position.replace(str(i), i * " ")
        rows = reversed(position.split("/"))
        
        for i, r in enumerate(rows):
            for j, p in enumerate(r):
                c = deepcopy(self.pieces[p])
                if p.islower():
                    c.color = Color.black
                self[Square(j,i)] = c
        self.activeColor = Color.white if active == "w" else Color.black
        self.castling = {Color.white: ["K" in castling, "Q" in castling], Color.black: ["k" in castling, "q" in castling]}
        self.epsquare = (Square(enpassant) if enpassant in Square.names else None)
        self.halfmove = int(halfmove)
        self.move = int(move)

    def getFen(self):
        rows = [8 * [" "] for i in range(8)]
        for square in self.squares():
            rows[square.r][square.f] = str(self[square])
        position = "/".join(reversed(["".join(r) for r in rows]))
        for i in range(8, 0, -1):
            position = position.replace(i * " ", str(i))

        active = self.activeColor.value
        castling = "".join(["K" * self.castling[Color.white][0], "Q" * self.castling[Color.white][1], "k" * self.castling[Color.black][0], "q" * self.castling[Color.black][1]])

        enpassant = str(self.epsquare) if self.epsquare else "-"
        halfmove = str(self.halfmove)
        move = str(self.move)

        return " ".join([position, active, castling, enpassant, halfmove, move])

    def kriegspielFen(self, color):
        rows = [8 * [" "] for i in range(8)]
        for square in self.squares():
            if self.isattacked(square, color) or self[square].color == color:
                rows[square.r][square.f] = str(self[square])
        position = "/".join(reversed(["".join(r) for r in rows]))
        for i in range(8, 0, -1):
            position = position.replace(i * " ", str(i))

        active = self.activeColor.value
        castling = "".join(["K" * self.castling[Color.white][0], "Q" * self.castling[Color.white][1], "k" * self.castling[Color.black][0], "q" * self.castling[Color.black][1]])

        enpassant = str(self.epsquare) if self.epsquare else "-"
        halfmove = str(self.halfmove)
        move = str(self.move)

        return " ".join([position, active, castling, enpassant, halfmove, move])

    def reset(self):
        self.loadFen(startingFen)

    def __str__(self):
        s = ""
        for r in range(8):
            for f in range(8):
                s += str(self[Square(f,7-r)])
            s += "\n"
        return s[:-1]


