from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.staticfiles import StaticFiles
import os, hashlib

app = FastAPI(title="Lynn Minimal", version="0.0.2")

# 读取并裁剪环境变量里的 token（去掉可能的空格/换行）
RAW_API_TOKEN = os.getenv("LYNN_API_TOKEN", "")
API_TOKEN = RAW_API_TOKEN.strip()

def _mask(s: str) -> str:
    if not s:
        return "EMPTY"
    return f"{s[:3]}...{s[-3:]} (len={len(s)}) sha256={hashlib.sha256(s.encode()).hexdigest()[:10]}"

# 启动时打印加载到的 token 摘要（不会泄露明文）
print("[BOOT] loaded LYNN_API_TOKEN:", _mask(API_TOKEN))

def require_auth(authorization: str | None):
    # 只有设置了 token 才做校验
    if API_TOKEN:
        if not authorization or not authorization.lower().startswith("bearer "):
            raise HTTPException(status_code=401, detail="Missing bearer token")
        # 取 Bearer 后面的部分并裁剪空白
        token = authorization.split(" ", 1)[1].strip()
        if token != API_TOKEN:
            raise HTTPException(status_code=403, detail="Invalid token")

@app.get("/health", tags=["meta"])
def health():
    return {"ok": True, "service": "Lynn", "version": "0.0.2"}

@app.get("/meta", tags=["meta"])
def meta(authorization: str | None = Header(default=None)):
    require_auth(authorization)
    return {"api": "lynn", "auth": "ok"}

# 调试1：回显你带过来的 Authorization 头
@app.get("/debug/echo-auth", tags=["debug"])
def echo_auth(request: Request):
    return {"authorization": request.headers.get("authorization")}

# 调试2：显示服务端加载到的 token 摘要（不泄露明文）
@app.get("/debug/token", tags=["debug"])
def debug_token():
    return {"loaded": _mask(API_TOKEN)}

# 公开静态 openapi.yaml
app.mount("/", StaticFiles(directory="public", html=False), name="public")



