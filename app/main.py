from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.staticfiles import StaticFiles
import os, hashlib

app = FastAPI(title="Lynn Minimal", version="0.0.1")

API_TOKEN = os.getenv("LYNN_API_TOKEN", "")

def _mask(s: str) -> str:
    if not s:
        return "EMPTY"
    return f"{s[:3]}...{s[-3:]} (len={len(s)}) sha256={hashlib.sha256(s.encode()).hexdigest()[:10]}"

# 启动时打印已加载 Token 的安全摘要（不泄露明文）
print("[BOOT] loaded LYNN_API_TOKEN:", _mask(API_TOKEN))

def require_auth(authorization: str | None):
    if API_TOKEN:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Missing bearer token")
        token = authorization.split(" ", 1)[1]
        if token != API_TOKEN:
            raise HTTPException(status_code=403, detail="Invalid token")

@app.get("/health", tags=["meta"])
def health():
    return {"ok": True, "service": "Lynn", "version": "0.0.1"}

@app.get("/meta", tags=["meta"])
def meta(authorization: str | None = Header(default=None)):
    require_auth(authorization)
    return {"api": "lynn", "auth": "ok"}

# 调试：回显你带过来的 Authorization 头
@app.get("/debug/echo-auth", tags=["debug"])
def echo_auth(request: Request):
    return {"authorization": request.headers.get("authorization")}

# 公开 /openapi.yaml
app.mount("/", StaticFiles(directory="public", html=False), name="public")

