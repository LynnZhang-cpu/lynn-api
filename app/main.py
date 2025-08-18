from fastapi import FastAPI, Header, HTTPException
from fastapi.staticfiles import StaticFiles
import os

app = FastAPI(title="Lynn Minimal", version="0.0.1")

API_TOKEN = os.getenv("LYNN_API_TOKEN")  # 在 Render 上设置

def require_auth(authorization: str | None):
    if API_TOKEN:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Missing bearer token")
        token = authorization.split(" ", 1)[1]
        if token != API_TOKEN:
            raise HTTPException(status_code=403, detail="Invalid token")

@app.get("/health", tags=["meta"])
def health():
    return {"ok": True, "service": "lynn", "version": "0.0.1"}

@app.get("/meta", tags=["meta"])
def meta(authorization: str | None = Header(default=None)):
    require_auth(authorization)
    return {"api": "lynn", "auth": "ok"}

# 挂载静态目录，公开 /openapi.yaml
app.mount("/", StaticFiles(directory="public", html=False), name="public")
