from flask import Flask, request, send_file, render_template_string, jsonify, abort
from PIL import Image
import io
import json
import zipfile
import os
import uuid

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024  # 32 MB


# In-memory storage for prepared ZIPs
ZIP_STORE = {}


HTML = """
<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>Image Splitter</title>
<style>
    body { font-family: Arial, sans-serif; background:#f5f5f5; margin:0; }
    .container {
        max-width: 600px;
        margin: auto;
        padding: 15px;
        text-align: center;
    }
    h2 { margin-top: 8px; }
    canvas {
        width: 100%;
        touch-action: none;
        border: 1px solid #ccc;
        margin: 20px 0;
        background: white;
    }
    button, input, select {
        width: 95%;
        padding: 10px;
        margin: 6px 0;
        font-size: 16px;
        box-sizing: border-box;
    }
    .small {
        font-size: 13px;
        color: #666;
        line-height: 1.5;
    }
    .row {
        display: flex;
        gap: 8px;
        width: 95%;
        margin: 0 auto 6px auto;
    }
    .row button {
        width: 50%;
        margin: 0;
    }
    hr {
        margin: 14px 0;
        border: none;
        border-top: 1px solid #ddd;
    }
</style>
</head>
<body>
<div class="container">

<h2>Image Splitter</h2>

<input type="file" id="file" accept="image/*">

<select id="viewMode" onchange="changeView()">
    <option value="mobile">Mobile View</option>
    <option value="desktop">Desktop View</option>
</select>

<input type="number" id="hCount" placeholder="Horizontal splits (e.g. 6)">
<button onclick="createHorizontal()">Create Horizontal</button>

<input type="number" id="vCount" placeholder="Vertical splits (e.g. 2)">
<button onclick="createVertical()">Create Vertical</button>

<hr>

<div class="row">
    <button onclick="addLine('h')">+ Horizontal Line</button>
    <button onclick="addLine('v')">+ Vertical Line</button>
</div>
<button onclick="clearLines()">Clear Lines</button>

<hr>

<input type="text" id="zipName" placeholder="Enter file name (optional)">
<button onclick="download()">Download ZIP</button>
<button onclick="showHistory()">Download History</button>
<button onclick="openDownloads()">Where is my file?</button>

<p class="small">
    Files are usually saved in the <b>Downloads</b> folder.
</p>
<p class="small">
    Tip: touch near a black line and drag it. Touch elsewhere to scroll.
</p>

<canvas id="canvas"></canvas>

</div>

<script>
const canvas = document.getElementById("canvas");
const ctx = canvas.getContext("2d");
const fileInput = document.getElementById("file");
const viewMode = document.getElementById("viewMode");
const hCount = document.getElementById("hCount");
const vCount = document.getElementById("vCount");
const zipNameInput = document.getElementById("zipName");

let img = null;
let lines = [];
let dragging = null;
let history = JSON.parse(localStorage.getItem("downloads") || "[]");

function loadImage(file) {
    if (!file) return;

    const reader = new FileReader();
    reader.onload = function() {
        img = new Image();
        img.onload = function() {
            canvas.width = img.width;
            canvas.height = img.height;
            lines = [];
            draw();
        };
        img.src = reader.result;
    };
    reader.readAsDataURL(file);
}

fileInput.addEventListener("change", (e) => {
    loadImage(e.target.files[0]);
});

function changeView() {
    const mode = viewMode.value;
    const c = document.querySelector(".container");
    if (mode === "desktop") {
        c.style.maxWidth = "1000px";
    } else {
        c.style.maxWidth = "600px";
    }
}

function createHorizontal() {
    const n = parseInt(hCount.value);
    if (!img || !n || n < 1) return;

    lines = lines.filter(l => l.type !== "h");

    const gap = img.height / n;
    for (let i = 1; i < n; i++) {
        lines.push({ type: "h", pos: i * gap });
    }
    draw();
}

function createVertical() {
    const n = parseInt(vCount.value);
    if (!img || !n || n < 1) return;

    lines = lines.filter(l => l.type !== "v");

    const gap = img.width / n;
    for (let i = 1; i < n; i++) {
        lines.push({ type: "v", pos: i * gap });
    }
    draw();
}

function addLine(type) {
    if (!img) return;

    if (type === "h") {
        lines.push({ type: "h", pos: img.height / 2 });
    } else {
        lines.push({ type: "v", pos: img.width / 2 });
    }
    draw();
}

function clearLines() {
    lines = [];
    draw();
}

function draw() {
    if (!img) return;

    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(img, 0, 0);

    ctx.strokeStyle = "black";
    ctx.lineWidth = 2;
    ctx.setLineDash([10, 5]);

    for (const l of lines) {
        ctx.beginPath();
        if (l.type === "h") {
            ctx.moveTo(0, l.pos);
            ctx.lineTo(canvas.width, l.pos);
        } else {
            ctx.moveTo(l.pos, 0);
            ctx.lineTo(l.pos, canvas.height);
        }
        ctx.stroke();
    }

    ctx.setLineDash([]);
}

function getPos(e) {
    const r = canvas.getBoundingClientRect();
    const sx = canvas.width / r.width;
    const sy = canvas.height / r.height;

    let clientX, clientY;
    if (e.touches && e.touches.length > 0) {
        clientX = e.touches[0].clientX;
        clientY = e.touches[0].clientY;
    } else {
        clientX = e.clientX;
        clientY = e.clientY;
    }

    return {
        x: (clientX - r.left) * sx,
        y: (clientY - r.top) * sy
    };
}

canvas.addEventListener("mousedown", start);
canvas.addEventListener("mousemove", move);
canvas.addEventListener("mouseup", end);
canvas.addEventListener("mouseleave", end);

canvas.addEventListener("touchstart", start, { passive: false });
canvas.addEventListener("touchmove", move, { passive: false });
canvas.addEventListener("touchend", end);

function start(e) {
    if (!img) return;

    const p = getPos(e);
    dragging = null;

    for (const l of lines) {
        if (l.type === "h" && Math.abs(p.y - l.pos) < 15) {
            dragging = l;
            break;
        }
        if (l.type === "v" && Math.abs(p.x - l.pos) < 15) {
            dragging = l;
            break;
        }
    }

    if (dragging) {
        e.preventDefault();
    }
}

function move(e) {
    if (!dragging) return;

    e.preventDefault();
    const p = getPos(e);

    if (dragging.type === "h") {
        dragging.pos = Math.max(1, Math.min(img.height - 1, p.y));
    } else {
        dragging.pos = Math.max(1, Math.min(img.width - 1, p.x));
    }

    draw();
}

function end() {
    dragging = null;
}

function saveHistory(name) {
    history.push(name);
    localStorage.setItem("downloads", JSON.stringify(history));
}

function showHistory() {
    alert(history.length ? history.join("\\n") : "No downloads yet");
}

function openDownloads() {
    alert("Open File Manager > Downloads folder.");
}

async function download() {
    if (!img || lines.length === 0) {
        alert("Add lines first!");
        return;
    }

    let name = zipNameInput.value.trim();
    if (name === "") name = "split_images";
    if (!name.toLowerCase().endsWith(".zip")) name += ".zip";

    const form = new FormData();
    form.append("image", fileInput.files[0]);
    form.append("lines", JSON.stringify(lines));
    form.append("zipName", name);

    try {
        const res = await fetch(window.location.origin + "/prepare", {
            method: "POST",
            body: form
        });

        if (!res.ok) {
            const text = await res.text();
            alert("Could not prepare download: " + text);
            return;
        }

        const data = await res.json();
        saveHistory(data.filename);

        // Open a real download URL instead of blob download
        window.location.href = window.location.origin + "/download/" + data.token;
    } catch (err) {
        alert("Download failed.");
    }
}
</script>

</body>
</html>
"""


@app.route("/")
def home():
    return render_template_string(HTML)


@app.route("/prepare", methods=["POST"])
def prepare():
    file = request.files.get("image")
    if not file:
        return "No image uploaded", 400

    lines = json.loads(request.form.get("lines", "[]"))
    zip_name = request.form.get("zipName", "split_images.zip").strip()

    if not zip_name:
        zip_name = "split_images.zip"
    if not zip_name.lower().endswith(".zip"):
        zip_name += ".zip"

    try:
        img = Image.open(file.stream).convert("RGB")
    except Exception:
        return "Invalid image", 400

    w, h = img.size

    xs = [0] + sorted([int(l["pos"]) for l in lines if l.get("type") == "v"]) + [w]
    ys = [0] + sorted([int(l["pos"]) for l in lines if l.get("type") == "h"]) + [h]

    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        count = 1
        for i in range(len(ys) - 1):
            for j in range(len(xs) - 1):
                left, top = xs[j], ys[i]
                right, bottom = xs[j + 1], ys[i + 1]
                if right <= left or bottom <= top:
                    continue

                crop = img.crop((left, top, right, bottom))
                img_bytes = io.BytesIO()
                crop.save(img_bytes, format="PNG")
                zf.writestr(f"piece_{count}.png", img_bytes.getvalue())
                count += 1

    zip_buffer.seek(0)

    token = str(uuid.uuid4())
    ZIP_STORE[token] = {
        "data": zip_buffer.getvalue(),
        "filename": zip_name
    }

    return jsonify({"token": token, "filename": zip_name})


@app.route("/download/<token>", methods=["GET"])
def download(token):
    item = ZIP_STORE.get(token)
    if not item:
        abort(404)

    buffer = io.BytesIO(item["data"])
    buffer.seek(0)

    response = send_file(
        buffer,
        mimetype="application/zip",
        as_attachment=True,
        download_name=item["filename"]
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
