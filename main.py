from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
import os, asyncio
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
queue: asyncio.Queue[str] = asyncio.Queue()

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
            await queue.put(_last_line)
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
