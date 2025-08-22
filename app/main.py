# app/main.py
import os
from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, File, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="Lynn API", version="0.0.2")

# 建议不要 mount 到 "/"，避免覆盖 /docs 和 /openapi.json
app.mount("/public", StaticFiles(directory="public", html=True), name="public")

# === 标准 Bearer 鉴权 ===
security = HTTPBearer()
LYNN_TOKEN = os.getenv("LYNN_API_TOKEN", "abc123XYZ789")

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    if token != LYNN_TOKEN:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    return token

@app.get("/health", tags=["meta"])
def health():
    return {"ok": True, "service": "Lynn", "version": "0.0.2"}

@app.get("/meta", tags=["meta"])
def meta(token: str = Depends(verify_token)):
    return {"api": "lynn", "auth": "ok"}

@app.post("/transcribe", tags=["audio"])
async def transcribe(file: UploadFile = File(...), token: str = Depends(verify_token)):
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
    return {
        "ok": True,
        "fileName": file.filename,
        "size": len(data),
        "totalGrams": totalGrams,
        "weeks": weeks,
    }

@app.post("/soap", tags=["tcm"])
async def soap_from_text(body: dict, token: str = Depends(verify_token)):
    return {"ok": True, "input": body}



