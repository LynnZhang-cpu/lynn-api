# app/main.py
import os
from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, File, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="Lynn API", version="0.0.2")

# 如果你有 public 目录（recorder.html/openapi.yml 等）
app.mount("/", StaticFiles(directory="public", html=True), name="public")

# ========= 关键：标准 Bearer 鉴权 =========
security = HTTPBearer()
LYNN_TOKEN = os.getenv("LYNN_API_TOKEN", "abc123XYZ789")  # Render 环境变量优先，没配就用这个

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    if token != LYNN_TOKEN:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    return token

# ========= 你的路由（需要鉴权的加上 Depends(verify_token)）=========

@app.get("/health", tags=["meta"])
def health():
    return {"ok": True, "service": "Lynn", "version": "0.0.2"}

@app.get("/meta", tags=["meta"])
def meta(token: str = Depends(verify_token)):
    return {"api": "lynn", "auth": "ok"}

@app.post("/transcribe", tags=["audio"])
async def transcribe(
    file: UploadFile = File(...),
    token: str = Depends(verify_token),
):
    data = await file.read()
    return {"ok": True, "fileName": file.filename, "size": len(data)}

@app.post("/soap-from-audio", tags=["audio"])
async def soap_from_audio(
    totalGrams: int = Query(110, ge=1),
    weeks: int = Query(1, ge=1),
    file: UploadFile = File(...),
    token: str = Depends(verify_token),
):
    data = await file.read()
    # TODO: 在这里生成 SOAP；先返回占位信息方便你验证
    return {
        "ok": True,
        "fileName": file.filename,
        "size": len(data),
        "totalGrams": totalGrams,
        "weeks": weeks,
    }

@app.post("/soap", tags=["tcm"])
async def soap_from_text(
    body: dict,
    token: str = Depends(verify_token),
):
    # TODO: 用 body 生成 SOAP；先返回占位信息
    return {"ok": True, "input": body}


