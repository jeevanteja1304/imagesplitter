from flask import Flask, request, send_file, render_template_string
from PIL import Image
import io, json, zipfile

app = Flask(__name__)

HTML = """
<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Image Splitter</title>

<style>
body {
    font-family: Arial;
    text-align: center;
    background: #f5f5f5;
}

canvas {
    width: 100%;
    max-width: 500px;
    touch-action: none;
    border: 1px solid #ccc;
}

button, input {
    width: 90%;
    padding: 10px;
    margin: 5px;
    font-size: 16px;
}
</style>
</head>

<body>

<h2>Image Splitter</h2>

<input type="file" id="file"><br>

<input type="number" id="hCount" placeholder="Horizontal splits (e.g 6)">
<button onclick="createHorizontal()">Create Horizontal Splits</button>

<input type="number" id="vCount" placeholder="Vertical splits (e.g 2)">
<button onclick="createVertical()">Create Vertical Splits</button>

<hr>

<button onclick="addLine('h')">Add Horizontal Line</button>
<button onclick="addLine('v')">Add Vertical Line</button>
<button onclick="clearLines()">Clear Lines</button>

<hr>

<button onclick="download()">Download ZIP</button>

<br><br>
<canvas id="canvas"></canvas>

<script>
let canvas = document.getElementById("canvas");
let ctx = canvas.getContext("2d");

let img = null;
let lines = [];
let dragging = null;

document.getElementById("file").onchange = e => {
    let file = e.target.files[0];
    let reader = new FileReader();

    reader.onload = function() {
        img = new Image();
        img.onload = function() {
            canvas.width = img.width;
            canvas.height = img.height;
            lines = [];
            draw();
        }
        img.src = reader.result;
    }

    reader.readAsDataURL(file);
}

function createHorizontal() {
    let n = parseInt(document.getElementById("hCount").value);
    if (!img || !n) return;

    lines = lines.filter(l => l.type !== 'h');

    let gap = img.height / n;
    for (let i = 1; i < n; i++) {
        lines.push({type:'h', pos: i * gap});
    }
    draw();
}

function createVertical() {
    let n = parseInt(document.getElementById("vCount").value);
    if (!img || !n) return;

    lines = lines.filter(l => l.type !== 'v');

    let gap = img.width / n;
    for (let i = 1; i < n; i++) {
        lines.push({type:'v', pos: i * gap});
    }
    draw();
}

function addLine(type) {
    if (!img) return;

    if (type === 'h') {
        lines.push({type:'h', pos: img.height/2});
    } else {
        lines.push({type:'v', pos: img.width/2});
    }
    draw();
}

function clearLines() {
    lines = [];
    draw();
}

function draw() {
    if (!img) return;

    ctx.clearRect(0,0,canvas.width,canvas.height);
    ctx.drawImage(img,0,0);

    ctx.strokeStyle = "black";
    ctx.setLineDash([10,5]);

    for (let l of lines) {
        ctx.beginPath();
        if (l.type === 'h') {
            ctx.moveTo(0, l.pos);
            ctx.lineTo(canvas.width, l.pos);
        } else {
            ctx.moveTo(l.pos, 0);
            ctx.lineTo(l.pos, canvas.height);
        }
        ctx.stroke();
    }
}

function getPos(e) {
    let rect = canvas.getBoundingClientRect();

    let scaleX = canvas.width / rect.width;
    let scaleY = canvas.height / rect.height;

    let x, y;

    if (e.touches) {
        x = (e.touches[0].clientX - rect.left) * scaleX;
        y = (e.touches[0].clientY - rect.top) * scaleY;
    } else {
        x = (e.clientX - rect.left) * scaleX;
        y = (e.clientY - rect.top) * scaleY;
    }

    return {x, y};
}

canvas.addEventListener("mousedown", start);
canvas.addEventListener("mousemove", move);
canvas.addEventListener("mouseup", end);

canvas.addEventListener("touchstart", start);
canvas.addEventListener("touchmove", move);
canvas.addEventListener("touchend", end);

function start(e) {
    let p = getPos(e);

    for (let l of lines) {
        if (l.type === 'h' && Math.abs(p.y - l.pos) < 20) {
            dragging = l;
            break;
        }
        if (l.type === 'v' && Math.abs(p.x - l.pos) < 20) {
            dragging = l;
            break;
        }
    }
}

function move(e) {
    if (!dragging) return;

    let p = getPos(e);

    if (dragging.type === 'h') {
        dragging.pos = p.y;
    } else {
        dragging.pos = p.x;
    }

    draw();
}

function end() {
    dragging = null;
}

function download() {
    if (!img || lines.length === 0) {
        alert("Add lines first!");
        return;
    }

    let form = new FormData();
    form.append("image", document.getElementById("file").files[0]);
    form.append("lines", JSON.stringify(lines));

    fetch("/split", {
        method: "POST",
        body: form
    })
    .then(res => res.blob())
    .then(blob => {
        let url = URL.createObjectURL(blob);
        let a = document.createElement("a");
        a.href = url;
        a.download = "split.zip";
        a.click();
    });
}
</script>

</body>
</html>
"""

@app.route("/")
def home():
    return render_template_string(HTML)

@app.route("/split", methods=["POST"])
def split():
    file = request.files["image"]
    lines = json.loads(request.form["lines"])

    img = Image.open(file.stream)
    w, h = img.size

    verticals = [0]
    horizontals = [0]

    for l in lines:
        if l["type"] == "v":
            verticals.append(int(l["pos"]))
        else:
            horizontals.append(int(l["pos"]))

    verticals.append(w)
    horizontals.append(h)

    verticals = sorted(verticals)
    horizontals = sorted(horizontals)

    zip_io = io.BytesIO()

    with zipfile.ZipFile(zip_io, "w") as z:
        count = 1
        for i in range(len(horizontals)-1):
            for j in range(len(verticals)-1):
                crop = img.crop((
                    verticals[j],
                    horizontals[i],
                    verticals[j+1],
                    horizontals[i+1]
                ))

                img_bytes = io.BytesIO()
                crop.save(img_bytes, format="PNG")

                z.writestr(f"piece_{count}.png", img_bytes.getvalue())
                count += 1

    zip_io.seek(0)
    return send_file(zip_io, as_attachment=True, download_name="split.zip")

# ✅ THIS IS THE ONLY CHANGE FOR RENDER
if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
