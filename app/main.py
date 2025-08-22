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
import os
import hashlib
from fastapi import FastAPI, Header, HTTPException, Depends, UploadFile, File, Query
from fastapi.openapi.utils import get_openapi

app = FastAPI(title="Lynn API", version="0.0.2")

# 读取并清洗环境变量
API_TOKEN: str = (os.getenv("LYNN_API_TOKEN") or "").strip()

def verify_token(authorization: str | None = Header(default=None)):
    """Bearer 鉴权：去空格、忽略大小写前缀"""
    if not API_TOKEN:
        # 没配置 Token 就不做校验（开发模式）
        return ""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    # 取出 Bearer 后面的部分并去首尾空格
    token = authorization.split(" ", 1)[1].strip()
    if token != API_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid token")
    return token

# ===== 临时诊断路由（排查完可删） =====
@app.get("/debug/token", tags=["debug"])
def debug_token():
    masked = (API_TOKEN[:3] + "..." + API_TOKEN[-3:]) if API_TOKEN else ""
    digest = hashlib.sha256(API_TOKEN.encode()).hexdigest() if API_TOKEN else ""
    return {"loaded": masked, "len": len(API_TOKEN), "sha256": digest}

@app.get("/debug/echo-auth", tags=["debug"])
def debug_echo_auth(authorization: str | None = Header(default=None)):
    # 看看服务端到底收到了什么 Authorization
    return {"authorization": authorization}

# 其余已有路由省略……
# /meta 用 Depends(verify_token)
# /transcribe、/soap-from-audio 用 Depends(verify_token)

# ---- OpenAPI 安全方案（确保右上角出现 Authorize） ----
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(title="Lynn API", version="0.0.2", routes=app.routes)
    schema.setdefault("components", {}).setdefault("securitySchemes", {})["bearerAuth"] = {
        "type": "apiKey",
        "in": "header",
        "name": "Authorization",
        "description": "输入纯 token（不要写 Bearer），例如：abc123XYZ789",
    }
    for path in schema.get("paths", {}).values():
        for method in path.values():
            # 需要鉴权的路由才加；/health 保持匿名
            if method.get("operationId") not in {"health_health_get"}:
                method.setdefault("security", []).append({"bearerAuth": []})
    app.openapi_schema = schema
    return schema

app.openapi = custom_openapi




