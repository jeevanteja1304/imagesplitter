# ==============================
# UPDATED IMAGE SPLITTER (BETTER UI + OPTIONS)
# ==============================

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
body { font-family: Arial; text-align: center; background:#f5f5f5; }

.container { max-width: 500px; margin:auto; }

canvas { width:100%; touch-action:none; border:1px solid #ccc; }

button, input, select {
    width:95%; padding:10px; margin:5px; font-size:16px;
}

.mode-btn { background:#007bff; color:white; }

</style>
</head>

<body>
<div class="container">

<h2>Image Splitter</h2>

<input type="file" id="file"><br>

<!-- VIEW MODE -->
<select id="viewMode" onchange="changeView()">
    <option value="mobile">Mobile View</option>
    <option value="desktop">Desktop View</option>
</select>

<!-- NUMBER SPLIT -->
<input type="number" id="hCount" placeholder="Horizontal splits (e.g 6)">
<button onclick="createHorizontal()">Create Horizontal</button>

<input type="number" id="vCount" placeholder="Vertical splits (e.g 2)">
<button onclick="createVertical()">Create Vertical</button>

<hr>

<!-- MANUAL -->
<button onclick="addLine('h')">+ Horizontal Line</button>
<button onclick="addLine('v')">+ Vertical Line</button>
<button onclick="clearLines()">Clear</button>

<hr>

<!-- DOWNLOAD OPTIONS -->
<select id="downloadType">
    <option value="zip">Download ZIP</option>
    <option value="single">Download Individually</option>
</select>

<button class="mode-btn" onclick="download()">Download</button>

<br><br>
<canvas id="canvas"></canvas>

</div>

<script>
let canvas = document.getElementById("canvas");
let ctx = canvas.getContext("2d");

let img=null, lines=[], dragging=null;

// ===== FILE LOAD =====
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

// ===== VIEW MODE =====
function changeView(){
    let mode=document.getElementById("viewMode").value;
    if(mode=="desktop"){
        canvas.style.maxWidth="900px";
    } else {
        canvas.style.maxWidth="500px";
    }
}

// ===== NUMBER SPLIT =====
function createHorizontal(){
    let n=parseInt(hCount.value);
    if(!img||!n) return;
    lines=lines.filter(l=>l.type!='h');
    let gap=img.height/n;
    for(let i=1;i<n;i++) lines.push({type:'h',pos:i*gap});
    draw();
}

function createVertical(){
    let n=parseInt(vCount.value);
    if(!img||!n) return;
    lines=lines.filter(l=>l.type!='v');
    let gap=img.width/n;
    for(let i=1;i<n;i++) lines.push({type:'v',pos:i*gap});
    draw();
}

// ===== MANUAL =====
function addLine(t){
    if(!img) return;
    if(t=='h') lines.push({type:'h',pos:img.height/2});
    else lines.push({type:'v',pos:img.width/2});
    draw();
}

function clearLines(){ lines=[]; draw(); }

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

// ===== DRAG =====
function getPos(e){
    let r=canvas.getBoundingClientRect();
    let sx=canvas.width/r.width;
    let sy=canvas.height/r.height;

    let x=e.touches?(e.touches[0].clientX-r.left)*sx:(e.clientX-r.left)*sx;
    let y=e.touches?(e.touches[0].clientY-r.top)*sy:(e.clientY-r.top)*sy;

    return {x,y};
}

canvas.addEventListener("mousedown",start);
canvas.addEventListener("mousemove",move);
canvas.addEventListener("mouseup",end);
canvas.addEventListener("touchstart",start);
canvas.addEventListener("touchmove",move);
canvas.addEventListener("touchend",end);

function start(e){
    let p=getPos(e);
    for(let l of lines){
        if(l.type=='h' && Math.abs(p.y-l.pos)<20) dragging=l;
        if(l.type=='v' && Math.abs(p.x-l.pos)<20) dragging=l;
    }
}

function move(e){
    if(!dragging) return;
    let p=getPos(e);
    if(dragging.type=='h') dragging.pos=p.y;
    else dragging.pos=p.x;
    draw();
}

function end(){ dragging=null; }

// ===== DOWNLOAD =====
function download(){
    let type=document.getElementById("downloadType").value;

    let form=new FormData();
    form.append("image",file.files[0]);
    form.append("lines",JSON.stringify(lines));

    fetch("/split",{method:"POST",body:form})
    .then(r=>r.blob())
    .then(blob=>{
        let url=URL.createObjectURL(blob);
        let a=document.createElement("a");
        a.href=url;
        a.download=(type=="zip"?"split.zip":"image.png");
        a.click();
    });
}
</script>

</body>
</html>
"""

@app.route("/")
def home(): return render_template_string(HTML)

@app.route("/split", methods=["POST"])
def split():
    file=request.files.get("image")
    lines=json.loads(request.form.get("lines"))

    img=Image.open(file.stream)
    w,h=img.size

    xs=[0]+sorted([int(l['pos']) for l in lines if l['type']=='v'])+[w]
    ys=[0]+sorted([int(l['pos']) for l in lines if l['type']=='h'])+[h]

    zip_io=io.BytesIO()
    with zipfile.ZipFile(zip_io,'w') as z:
        c=1
        for i in range(len(ys)-1):
            for j in range(len(xs)-1):
                crop=img.crop((xs[j],ys[i],xs[j+1],ys[i+1]))
                b=io.BytesIO(); crop.save(b,format="PNG")
                z.writestr(f"piece_{c}.png",b.getvalue()); c+=1

    zip_io.seek(0)
    return send_file(zip_io,as_attachment=True,download_name="split.zip")

if __name__=="__main__":
    port=int(os.environ.get("PORT",10000))
    app.run(host="0.0.0.0",port=port)
