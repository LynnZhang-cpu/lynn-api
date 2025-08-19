from fastapi import FastAPI, Header, HTTPException
from fastapi.staticfiles import StaticFiles
import os

app = FastAPI(title="Lynn Minimal", version="0.0.1")

# 从环境变量读取 Token
API_TOKEN = os.getenv("LYNN_API_TOKEN")

def require_auth(authorization: str | None):
    """检查请求头里的 Bearer Token"""
    if API_TOKEN:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Missing bearer token")
        token = authorization.split(" ", 1)[1]  # 提取 Bearer 后面的部分
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
