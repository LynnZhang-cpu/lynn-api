from fastapi import FastAPI, UploadFile, File
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
import os, asyncio, io
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

LOG_PATH = os.path.expanduser(os.getenv("LOG_PATH", "/tmp/sse.log"))

transcript_buffer = []
_last_final = ""
_last_line = ""
_last_time = ""

def _extract_final_text(line: str):
    s = line.strip()
    if "final" not in s:
        return None
    i = s.find("final")
    rest = s[i+5:]
    rest = rest.lstrip(" :\t")
    rest = rest.split("#", 1)[0]
    rest = rest.strip()
    return rest or None

async def _watch_log():
    global _last_final, _last_line, _last_time
    while not os.path.exists(LOG_PATH):
        await asyncio.sleep(0.3)
    with open(LOG_PATH, "r", encoding="utf-8", errors="ignore") as f:
        f.seek(0, os.SEEK_END)
        while True:
            line = f.readline()
            if not line:
                await asyncio.sleep(0.2)
                continue
            _last_line = line.rstrip()
            _last_time = datetime.now().strftime("%H:%M:%S")
            txt = _extract_final_text(line)
            if txt and txt != _last_final:
                transcript_buffer.append(txt)
                _last_final = txt

@app.on_event("startup")
async def _startup():
    asyncio.create_task(_watch_log())

@app.get("/start")
async def start():
    global _last_final
    transcript_buffer.clear()
    _last_final = ""
    return {"status": "listening", "message": "问诊已开始，缓冲区已清空"}

@app.get("/latest", response_class=PlainTextResponse)
async def latest():
    return "\n".join(transcript_buffer)

@app.get("/end", response_class=PlainTextResponse)
async def end():
    global _last_final
    text = "\n".join(transcript_buffer)
    transcript_buffer.clear()
    _last_final = ""
    return text

@app.get("/rebuild", response_class=PlainTextResponse)
async def rebuild():
    global _last_final
    transcript_buffer.clear()
    _last_final = ""
    if not os.path.exists(LOG_PATH):
        return ""
    with open(LOG_PATH, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            txt = _extract_final_text(line)
            if txt and txt != _last_final:
                transcript_buffer.append(txt)
                _last_final = txt
    return "\n".join(transcript_buffer)

@app.get("/debug")
async def debug():
    return {
        "logPath": LOG_PATH,
        "bufferLen": len(transcript_buffer),
        "lastFinal": _last_final,
        "lastLine": _last_line,
        "lastTime": _last_time,
        "logExists": os.path.exists(LOG_PATH),
    }

@app.get("/emit")
async def emit(kind: str = "final", text: str = ""):
    if kind == "ready":
        line = "event: ready"
    elif kind == "partial":
        line = f"partial: {text}"
    elif kind == "final":
        line = f"final: {text}"
    else:
        return {"ok": False, "error": "bad kind"}
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    return {"ok": True, "wrote": line}

html_mic = """
<!doctype html><html><head><meta charset="utf-8">
<title>语音转写</title><meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial;padding:16px;background:#0b1020;color:#e6e9ef}
h1{margin:0 0 12px;font-size:18px}
#log{white-space:pre-wrap;background:#0f172a;border-radius:12px;padding:12px;line-height:1.5;min-height:40vh;border:1px solid #223}
button{padding:10px 16px;border-radius:10px;border:0;margin-right:8px;cursor:pointer}
#start{background:#22c55e;color:#111}#stop{background:#ef4444;color:#fff}
</style></head><body>
<h1>实时语音转写</h1>
<div style="margin-bottom:10px;">
<button id="start">开始</button><button id="stop" disabled>停止</button>
</div>
<div id="log"></div>
<script>
let rec; const log=document.getElementById('log');
const startBtn=document.getElementById('start'); const stopBtn=document.getElementById('stop');
function append(t){log.textContent += t + "\\n"; log.scrollTop=log.scrollHeight;}
async function startRec(){
  const stream = await navigator.mediaDevices.getUserMedia({audio:true});
  rec = new MediaRecorder(stream, {mimeType: 'audio/webm;codecs=opus'});
  rec.ondataavailable = async (e)=>{
    if(e.data && e.data.size>0){
      const fd = new FormData(); fd.append('file', e.data, 'chunk.webm');
      try{
        const r = await fetch('/stt', {method:'POST', body: fd});
        const text = await r.text(); if(text && text.trim()) append(text.trim());
      }catch(err){console.error(err);}
    }
  };
  rec.start(2000); startBtn.disabled=true; stopBtn.disabled=false;
}
function stopRec(){ if(rec && rec.state!=='inactive'){rec.stop();} startBtn.disabled=false; stopBtn.disabled=true; }
startBtn.onclick=startRec; stopBtn.onclick=stopRec;
</script></body></html>
"""

@app.get("/mic", response_class=HTMLResponse)
async def mic():
    return HTMLResponse(html_mic)

@app.post("/stt", response_class=PlainTextResponse)
async def stt(file: UploadFile = File(...)):
    import io, os
    # 检查依赖与密钥
    try:
        from openai import OpenAI
    except Exception as e:
        return f"ERROR: openai lib not installed: {e}"
    if not os.getenv("OPENAI_API_KEY"):
        return "ERROR: OPENAI_API_KEY missing"

    data = await file.read()
    bio = io.BytesIO(data)
    try:
        client = OpenAI()
        resp = client.audio.transcriptions.create(
            model="gpt-4o-mini-transcribe",  # 或 whisper-1
            file=("chunk.webm", bio, file.content_type or "audio/webm")
        )
        text = (resp.text or "").strip()
    except Exception as e:
        return f"ERROR: {e}"

    if text:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"final: {text}\n")
    return text


