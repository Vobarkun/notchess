size = Math.min(window.innerWidth * 0.92, window.innerHeight * 0.8) + "px"
$(".board-container").css("height", size)
$(".board-container").css("width", size)
$(".container").css("width", size)

const ground = Chessground(document.getElementById("ground1"), {
    movable: {
        color: "both",
        free: false,
    },
    fen: "8/8/8/8/8/8/8/8 w KQkq - 0 1",
    draggable: {
        showGhost: true
    },
    highlight: {
        check: true,
        lastMove: true
    },
    coordinates: false,
    autoCastle: false,
    premovable: {
        enabled: false
    },
    drawable: {
        defaultSnapToValidMove: false
    }
});

var ws = new WebSocket("ws://" + window.location.hostname + "/websocket");

ws.onopen = function() {
    ws.send(JSON.stringify({
        msg_type: 'update_position'
    }));
    window.setInterval(function() {
        ws.send(JSON.stringify({
            msg_type: "hi"
        }))
    }, 5000);
};

ws.onmessage = function(event) {
    var data = $.parseJSON(event.data);
    // console.log(data)

    if (data.msg_type == "move") {
        ground.move(data.orig, data.dest);
    }
    if (data.msg_type == "armies") {
        $("#armies").empty()
        for (army of data.armies) {
            $("#armies").append(`<option value="${army}">${army}</option>`)
        }
    }
    if (data.msg_type == "position" || data.msg_type == "move") {
        ground.set({
            orientation: data.yourColor,
            fen: data.fen,
            check: data.check,
            movable: {
                dests: objToStrMap(data.dests),
                // color: data.yourColor
            },
            turnColor: data.fen.includes('w') ? 'white' : 'black'
        })
        if (data.clearLast) {
            ground.set({ lastMove: [] });
        }
        $("#result").text(data.result)
        if (data.result == "") {
            $("#result").hide()
        } else {
            $("#result").show()
        }
        console.log(data.yourColor)
        $("#nameUs").text(data.yourColor == "white" ? data.names.white : data.names.black)
        $("#nameThem").text(data.yourColor == "white" ? data.names.black : data.names.white)
    }
    if (data.msg_type == "draw") {
        ground.setShapes(data.shapes);
    }
};

function onPlayerMove(ws) {
    return (orig, dest) => {
        ws.send(JSON.stringify({
            msg_type: "move",
            orig: orig,
            dest: dest
        }))
    };
}

function onDraw(ws) {
    return shapes => {
        ws.send(JSON.stringify({
            msg_type: "draw",
            shapes: shapes
        }))
    };
}

ground.set({
    movable: { events: { after: onPlayerMove(ws) } },
    drawable: { onChange: onDraw(ws) }
});

function objToStrMap(obj) {
    let strMap = new Map();
    for (let k of Object.keys(obj)) {
        strMap.set(k, obj[k]);
    }
    return strMap;
}

function newgame() {
    ws.send(JSON.stringify({
        msg_type: "newgame"
    }))
    ground.set({ lastMove: [] })
}


function sendArmy() {
    ws.send(JSON.stringify({
        msg_type: "select_army",
        army: $("#armies").val()
    }))
}

function undo(n) {
    ws.send(JSON.stringify({
        msg_type: "undo",
        n: n
    }))
}