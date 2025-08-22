from __future__ import annotations
import os, secrets, asyncio, tempfile, uuid, datetime
from typing import Optional, Dict, List

from fastapi import FastAPI, Depends, HTTPException, status, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel

API_TOKEN = (os.getenv("LYNN_API_TOKEN") or os.getenv("API_TOKEN") or "").strip()
bearer_scheme = HTTPBearer(auto_error=False)
def auth(creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme)):
    if not API_TOKEN:
        return
    if creds is None or creds.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authenticated")
    client_token = (creds.credentials or "").strip()
    if not secrets.compare_digest(client_token, API_TOKEN):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

from openai import OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or ""
client = OpenAI(api_key=OPENAI_API_KEY)

app = FastAPI(
    title="诊疗分身 · 实时问诊工作流",
    version="1.3.0",
    description="开始问诊 → 实时转写（SSE）→ 结束问诊（返回完整逐字稿）。SOAP 由前端智能体处理。",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class LiveSession:
    def __init__(self):
        self.intake_id: str = str(uuid.uuid4())
        self.started_at: str = datetime.datetime.utcnow().isoformat() + "Z"
        self.tmpfile = tempfile.NamedTemporaryFile(delete=False, suffix=".webm")
        self.filepath = self.tmpfile.name
        self.stopped: bool = False
        self.sse_queues: List[asyncio.Queue[str]] = []
        self.last_text: str = ""
        self.transcribe_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()

    async def broadcast(self, event: str, payload: dict):
        line = "event: " + event + "\n" + "data: " + JSONResponse(content=payload).body.decode("utf-8") + "\n\n"
        for q in list(self.sse_queues):
            try:
                await q.put(line)
            except asyncio.CancelledError:
                pass

SESSIONS: Dict[str, LiveSession] = {}

class LiveStartResponse(BaseModel):
    intakeId: str
    startedAt: str

class LiveStopRequest(BaseModel):
    intakeId: str

class LiveStopResponse(BaseModel):
    intakeId: str
    transcript: str

def transcribe_file_sync(path: str) -> str:
    with open(path, "rb") as f:
        resp = client.audio.transcriptions.create(
            model="whisper-1",
            file=f,
        )
    return getattr(resp, "text", "") or ""

async def transcribe_file(path: str) -> str:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, transcribe_file_sync, path)

async def transcribe_loop(session: LiveSession):
    try:
        while not session.stopped:
            await asyncio.sleep(3)
            txt = await transcribe_file(session.filepath)
            if txt and txt != session.last_text:
                session.last_text = txt
                await session.broadcast("partial", {"intakeId": session.intake_id, "text": txt})
        final_txt = await transcribe_file(session.filepath)
        if final_txt:
            session.last_text = final_txt
        await session.broadcast("final", {"intakeId": session.intake_id, "text": session.last_text})
    except Exception as e:
        await session.broadcast("error", {"intakeId": session.intake_id, "message": str(e)})

@app.get("/health", tags=["meta"])
def health():
    return {"ok": True, "service": "Lynn live", "version": "1.3.0"}

@app.post("/live/start", tags=["live"], response_model=LiveStartResponse, dependencies=[Depends(auth)])
async def start_live():
    session = LiveSession()
    SESSIONS[session.intake_id] = session
    session.transcribe_task = asyncio.create_task(transcribe_loop(session))
    return LiveStartResponse(intakeId=session.intake_id, startedAt=session.started_at)

@app.get("/live/events", tags=["live"], dependencies=[Depends(auth)])
async def sse_events(intakeId: str):
    if intakeId not in SESSIONS:
        raise HTTPException(404, "intakeId not found")
    session = SESSIONS[intakeId]
    q: asyncio.Queue[str] = asyncio.Queue()
    session.sse_queues.append(q)

    async def gen():
        try:
            await q.put(f"event: ready\ndata: {{\"intakeId\":\"{intakeId}\"}}\n\n")
            while True:
                data = await q.get()
                yield data
        except asyncio.CancelledError:
            pass
        finally:
            if q in session.sse_queues:
                session.sse_queues.remove(q)

    return StreamingResponse(gen(), media_type="text/event-stream")

@app.post("/live/audio", tags=["live"], status_code=204, dependencies=[Depends(auth)])
async def upload_live_audio(intakeId: str, request: Request, format: Optional[str] = None):
    if intakeId not in SESSIONS:
        raise HTTPException(404, "intakeId not found")
    session = SESSIONS[intakeId]
    async with session._lock:
        with open(session.filepath, "ab") as w:
            async for chunk in request.stream():
                if not chunk:
                    break
                w.write(chunk)
    return Response(status_code=204)

@app.post("/live/stop", tags=["live"], response_model=LiveStopResponse, dependencies=[Depends(auth)])
async def stop_live(body: LiveStopRequest):
    if body.intakeId not in SESSIONS:
        raise HTTPException(404, "intakeId not found")
    session = SESSIONS[body.intakeId]
    session.stopped = True
    if session.transcribe_task:
        try:
            await asyncio.wait_for(session.transcribe_task, timeout=120)
        except asyncio.TimeoutError:
            pass
    return LiveStopResponse(intakeId=session.intake_id, transcript=session.last_text)
