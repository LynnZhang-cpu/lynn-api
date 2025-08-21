# app/main.py
from fastapi import FastAPI, HTTPException, Header, UploadFile, File, Depends
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import os, tempfile, shutil

app = FastAPI(title="Lynn API", version="0.0.2")

# --------- 简单鉴权 ----------
API_TOKEN = os.getenv("LYNN_API_TOKEN")

def # 新增/调整 import
from fastapi import FastAPI, HTTPException, Depends, Header, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.staticfiles import StaticFiles
import os

app = FastAPI(title="Lynn API", version="0.0.2")

# 从环境变量读取 Token
API_TOKEN = os.getenv("LYNN_API_TOKEN")

# ✅ 声明 Bearer 安全方案（Swagger 会据此显示 Authorize 按钮）
bearer_scheme = HTTPBearer(auto_error=False)

def require_auth(
    credentials: HTTPAuthorizationCredentials = Security(bearer_scheme)
):
    """
    统一校验请求头 Authorization: Bearer <token>
    并与环境变量 LYNN_API_TOKEN 对比。
    """
    if not API_TOKEN:
        # 未配置服务端 Token，直接放行（或按需改为 500）
        return

    # credentials 可能为 None（未携带 Authorization）
    token = credentials.credentials if credentials else None
    if not token:
        raise HTTPException(status_code=401, detail="Missing bearer token")

    if token != API_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid token")


# --------- 调试：列出所有已注册路由 ----------
@app.get("/__routes", tags=["debug"])
def dump_routes():
    out = []
    for r in app.router.routes:
        methods = getattr(r, "methods", None)
        path = getattr(r, "path", None)
        if methods and path:
            out.append({"path": path, "methods": list(methods)})
    return out

# --------- meta ----------
@app.get("/health", tags=["meta"])
def health():
    return {"ok": True, "service": "Lynn", "version": "0.0.2"}

@app.get("/meta", tags=["meta"])
def meta(_: None = Depends(require_auth)):
    return {"api": "lynn", "auth": "ok"}

# --------- SOAP（JSON 入参）----------
class SoapInput(BaseModel):
    chiefComplaint: str
    symptoms: list[str] = []
    tongue: str | None = None
    pulse: str | None = None
    history: str | None = None
    objective: str | None = None
    assessmentHint: str | None = None
    totalGrams: int = 110
    weeks: int = 1
    preferences: str | None = None

class SoapOutput(BaseModel):
    soapMarkdown: str
    totalGrams: int

@app.post("/soap", tags=["tcm"], response_model=SoapOutput)
@app.post("/soap/", tags=["tcm"], response_model=SoapOutput)   # 支持尾斜杠
def generate_soap(body: SoapInput, _: None = Depends(require_auth)):
    md = f"""# SOAP（示例）
- 主诉：{body.chiefComplaint}
- 症状：{", ".join(body.symptoms)}
- 舌象：{body.tongue or "-"}
- 脉象：{body.pulse or "-"}
- 既往史：{body.history or "-"}
- 客观检查：{body.objective or "-"}
- 诊断提示：{body.assessmentHint or "-"}
- 偏好：{body.preferences or "-"}
"""
    return SoapOutput(soapMarkdown=md, totalGrams=body.totalGrams * body.weeks)

# --------- 音频转写（回声版，确保路由 200）----------
@app.post("/transcribe", tags=["audio"])
@app.post("/transcribe/", tags=["audio"])
async def transcribe(file: UploadFile = File(...), _: None = Depends(require_auth)):
    with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[1]) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name
    return {"ok": True, "route": "/transcribe", "filename": file.filename, "tempFile": tmp_path}

# --------- 音频直出 SOAP（回声版，确保路由 200）----------
@app.post("/soap-from-audio", tags=["audio"])
@app.post("/soap-from-audio/", tags=["audio"])
async def soap_from_audio(
    file: UploadFile = File(...),
    totalGrams: int = 110,
    weeks: int = 1,
    _: None = Depends(require_auth),
):
    with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[1]) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name
    return {
        "ok": True,
        "route": "/soap-from-audio",
        "filename": file.filename,
        "tempFile": tmp_path,
        "totalGrams": totalGrams,
        "weeks": weeks,
        "note": "whisper+LLM pending",
    }

# --------- 静态资源：不要挂在 "/" ----------
app.mount("/public", StaticFiles(directory="public", html=False), name="public")
