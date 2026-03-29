from flask import Flask, request, send_file, render_template_string
from PIL import Image
import io, json, zipfile, os

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024


HTML = """
<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Image Splitter</title>

<style>
body {
    font-family: Arial;
    background:#f5f5f5;
    margin:0;
    padding:0;
}

.container {
    max-width: 600px;
    margin:auto;
    padding:15px;
    text-align:center;
}

canvas {
    width:100%;
    touch-action:none;
    border:1px solid #ccc;
    margin:20px 0;
}

button, input, select {
    width:95%;
    padding:10px;
    margin:6px 0;
    font-size:16px;
}
</style>
</head>

<body>

<div class="container">

<h2>Image Splitter</h2>

<input type="file" id="file">

<select id="viewMode" onchange="changeView()">
<option value="mobile">Mobile View</option>
<option value="desktop">Desktop View</option>
</select>

<input type="number" id="hCount" placeholder="Horizontal splits (e.g 6)">
<button onclick="createHorizontal()">Create Horizontal</button>

<input type="number" id="vCount" placeholder="Vertical splits (e.g 2)">
<button onclick="createVertical()">Create Vertical</button>

<hr>

<button onclick="addLine('h')">+ Horizontal Line</button>
<button onclick="addLine('v')">+ Vertical Line</button>
<button onclick="clearLines()">Clear Lines</button>

<hr>

<button onclick="download()">Download ZIP</button>

<canvas id="canvas"></canvas>

</div>

<script>
let canvas = document.getElementById("canvas");
let ctx = canvas.getContext("2d");

let img=null, lines=[], dragging=null;

// ===== LOAD IMAGE =====
document.getElementById("file").onchange = e => {
    let file=e.target.files[0];
    let reader=new FileReader();

    reader.onload=function(){
        img=new Image();
        img.onload=function(){
            canvas.width=img.width;
            canvas.height=img.height;
            lines=[];
            draw();
        }
        img.src=reader.result;
    }
    reader.readAsDataURL(file);
}

// ===== VIEW MODE FIX =====
function changeView(){
    let mode=document.getElementById("viewMode").value;
    let container=document.querySelector(".container");

    if(mode==="desktop"){
        container.style.maxWidth="1000px";
    } else {
        container.style.maxWidth="600px";
    }
}

// ===== NUMBER SPLIT =====
function createHorizontal(){
    let n=parseInt(hCount.value);
    if(!img||!n) return;

    lines=lines.filter(l=>l.type!='h');

    let gap=img.height/n;
    for(let i=1;i<n;i++){
        lines.push({type:'h',pos:i*gap});
    }
    draw();
}

function createVertical(){
    let n=parseInt(vCount.value);
    if(!img||!n) return;

    lines=lines.filter(l=>l.type!='v');

    let gap=img.width/n;
    for(let i=1;i<n;i++){
        lines.push({type:'v',pos:i*gap});
    }
    draw();
}

// ===== MANUAL =====
function addLine(t){
    if(!img) return;

    if(t=='h') lines.push({type:'h',pos:img.height/2});
    else lines.push({type:'v',pos:img.width/2});

    draw();
}

function clearLines(){
    lines=[];
    draw();
}

// ===== DRAW =====
function draw(){
    if(!img) return;

    ctx.clearRect(0,0,canvas.width,canvas.height);
    ctx.drawImage(img,0,0);

    ctx.strokeStyle="black";
    ctx.setLineDash([10,5]);

    for(let l of lines){
        ctx.beginPath();
        if(l.type=='h'){
            ctx.moveTo(0,l.pos);
            ctx.lineTo(canvas.width,l.pos);
        } else {
            ctx.moveTo(l.pos,0);
            ctx.lineTo(l.pos,canvas.height);
        }
        ctx.stroke();
    }
}

// ===== POSITION =====
function getPos(e){
    let r=canvas.getBoundingClientRect();

    let sx=canvas.width/r.width;
    let sy=canvas.height/r.height;

    let x=e.touches?(e.touches[0].clientX-r.left)*sx:(e.clientX-r.left)*sx;
    let y=e.touches?(e.touches[0].clientY-r.top)*sy:(e.clientY-r.top)*sy;

    return {x,y};
}

// ===== DRAG FIX (SCROLL + DRAG) =====
canvas.addEventListener("mousedown", start);
canvas.addEventListener("mousemove", move);
canvas.addEventListener("mouseup", end);

canvas.addEventListener("touchstart", start, { passive:false });
canvas.addEventListener("touchmove", move, { passive:false });
canvas.addEventListener("touchend", end);

function start(e){
    let p=getPos(e);
    dragging=null;

    for(let l of lines){
        if(l.type=='h' && Math.abs(p.y-l.pos)<15){
            dragging=l;
            break;
        }
        if(l.type=='v' && Math.abs(p.x-l.pos)<15){
            dragging=l;
            break;
        }
    }

    if(dragging) e.preventDefault();
}

function move(e){
    if(!dragging) return;

    e.preventDefault();

    let p=getPos(e);

    if(dragging.type=='h') dragging.pos=p.y;
    else dragging.pos=p.x;

    draw();
}

function end(){
    dragging=null;
}

// ===== DOWNLOAD =====
function download(){
    if(!img || lines.length===0){
        alert("Add lines first!");
        return;
    }

    let form=new FormData();
    form.append("image", file.files[0]);
    form.append("lines", JSON.stringify(lines));

    fetch(window.location.origin+"/split",{
        method:"POST",
        body:form
    })
    .then(r=>{
        if(!r.ok) throw new Error("Error");
        return r.blob();
    })
    .then(blob=>{
        let url=URL.createObjectURL(blob);
        let a=document.createElement("a");
        a.href=url;
        a.download="split.zip";
        a.click();
    })
    .catch(err=>alert("Download failed"));
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
    file = request.files.get("image")
    if not file:
        return "No image", 400

    lines = json.loads(request.form.get("lines", "[]"))

    img = Image.open(file.stream)
    w, h = img.size

    xs = [0] + sorted([int(l['pos']) for l in lines if l['type']=='v']) + [w]
    ys = [0] + sorted([int(l['pos']) for l in lines if l['type']=='h']) + [h]

    zip_io = io.BytesIO()

    with zipfile.ZipFile(zip_io, "w") as z:
        c = 1
        for i in range(len(ys)-1):
            for j in range(len(xs)-1):
                crop = img.crop((xs[j], ys[i], xs[j+1], ys[i+1]))
                b = io.BytesIO()
                crop.save(b, format="PNG")
                z.writestr(f"piece_{c}.png", b.getvalue())
                c += 1

    zip_io.seek(0)
    return send_file(zip_io, as_attachment=True, download_name="split.zip")

# Render fix
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
