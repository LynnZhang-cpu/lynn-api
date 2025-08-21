from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.staticfiles import StaticFiles
import os, hashlib
import os
from fastapi import Header, HTTPException, UploadFile, File
from pydantic import BaseModel
from openai import OpenAI

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
# ========= SOAP 生成接口 =========
from pydantic import BaseModel, Field
from typing import List, Optional
import os
from openai import OpenAI

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

class SoapOutput(BaseModel):
    soapMarkdown: str
    totalGrams: int

class TranscribeOutput(BaseModel):
    text: str
    language: str | None = None


class SoapInput(BaseModel):
    # 关键信息（可按需扩展/精简）
    chiefComplaint: str = Field(..., description="主诉/来诊原因")
    symptoms: List[str] = Field(default_factory=list, description="症状列表")
    tongue: Optional[str] = Field(default=None, description="舌象（或描述）")
    pulse: Optional[str] = Field(default=None, description="脉象")
    history: Optional[str] = Field(default=None, description="病史/既往史/过敏史等")
    objective: Optional[str] = Field(default=None, description="客观检查/舌图要点等")
    assessmentHint: Optional[str] = Field(default=None, description="诊断思路提示（可空）")
    totalGrams: Optional[int] = Field(default=110, description="默认总克数 110g")
    weeks: Optional[int] = Field(default=1, description="给药周数，默认 1 周")
    preferences: Optional[str] = Field(default=None, description="患者偏好/忌口/备考")

class SoapOutput(BaseModel):
    soapMarkdown: str
    totalGrams: int

def _build_soap_prompt(payload: SoapInput) -> str:
    return f"""
你是我的中医诊断与处方助手，需严格按照以下固定规则与结构输出内容。

【适用输入】
我会提供患者症状、舌象、脉象、病史和其它临床表现。
若未说明用药周期与总克数，默认配方总克数为 {payload.totalGrams * max(1, payload.weeks)} 克（{payload.totalGrams}g/周 × {max(1, payload.weeks)} 周）。

【输出结构与规则】
① 症状与中医诊断表
- 双列表格：左列=症状，右列=中医诊断与病机（精准术语）。

② 核心治则
- 用“×”分隔（≤7条），主症在前。

③ 处方 + 功效说明
- 按功能模块分组：
  - **主症模块**（≥总方 60%）
  - 兼症模块（如：补气、补血、祛湿、活血、安神……）
- 每味药：药名 + 剂量（g），并简述作用。
- 总克数严格≈{payload.totalGrams * max(1, payload.weeks)} g（不含生姜、红枣）。
- 如滋腻药偏多，自动加健脾化湿药护胃；避免药性冲突；必要时标注先煎/后下/另包。

④ 模块化横向处方表
- 每行：**加粗模块标题** | 药名 克数 | 药名 克数 | …
- 最后一行给出总克数（g），单位统一：g / 枚 / 片。

【患者信息】
- 主诉：{payload.chiefComplaint}
- 症状：{", ".join(payload.symptoms) if payload.symptoms else "未补充"}
- 舌象：{payload.tongue or "未述"}
- 脉象：{payload.pulse or "未述"}
- 病史/客观：{payload.history or "未述"}；{payload.objective or ""}
- 偏好/注意：{payload.preferences or "未述"}
- 诊断思路提示：{payload.assessmentHint or "无"}

请直接输出以上 ①~④ 的完整内容（Markdown），不要额外解释。
    """.strip()

@app.post("/soap", response_model=SoapOutput, tags=["tcm"])
def generate_soap(data: SoapInput, authorization: str | None = Header(default=None)):
    # 复用鉴权
    require_auth(authorization)

    if not OPENAI_API_KEY:
        raise HTTPException(status_code=500, detail="Server OPENAI_API_KEY not set")

    client = OpenAI(api_key=OPENAI_API_KEY)

    prompt = _build_soap_prompt(data)

    try:
        # 使用轻量便宜模型：gpt-4o-mini（仅文本）
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "你是一名资深中医临床医生，输出临床严谨、结构化结果。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
        )
        content = completion.choices[0].message.content
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"OpenAI error: {e}")

    return SoapOutput(soapMarkdown=content, totalGrams=(data.totalGrams or 110) * max(1, data.weeks or 1))
# ========= SOAP 生成接口 =========
from pydantic import BaseModel, Field
from typing import List, Optional
from openai import OpenAI

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

class SoapInput(BaseModel):
    # 你可按需增删这些字段
    chiefComplaint: str = Field(..., description="主诉/来诊原因")
    symptoms: List[str] = Field(default_factory=list, description="症状列表")
    tongue: Optional[str] = Field(default=None, description="舌象")
    pulse: Optional[str] = Field(default=None, description="脉象")
    history: Optional[str] = Field(default=None, description="病史/既往史/过敏史等")
    objective: Optional[str] = Field(default=None, description="客观检查/舌图要点等")
    assessmentHint: Optional[str] = Field(default=None, description="诊断思路提示（可空）")
    totalGrams: Optional[int] = Field(default=110, description="默认每周总克数 110g")
    weeks: Optional[int] = Field(default=1, description="给药周数，默认 1 周")
    preferences: Optional[str] = Field(default=None, description="患者偏好/忌口/备考")

class SoapOutput(BaseModel):
    soapMarkdown: str
    totalGrams: int

def _build_soap_prompt(p: SoapInput) -> str:
    total = (p.totalGrams or 110) * max(1, p.weeks or 1)
    symptoms = "、".join(p.symptoms) if p.symptoms else "未补充"
    return f"""
你是我的中医诊断与处方助手，需严格按照以下固定规则与结构输出内容。

【适用输入】
我会提供患者症状、舌象描述（或照片）、脉象、病史或其他临床表现。
默认配方总量：{p.totalGrams or 110} g/周 × {max(1, p.weeks or 1)} 周 = {total} g（不含生姜、红枣）。

【输出结构与规则】

① 症状与中医诊断表
- 制成双列表格：左列=症状（按患者原话或精简表达），右列=中医诊断与病机（精准术语）。

② 核心治则
- 用“×”分隔（≤7条），主症治则在前，兼症在后。

③ 处方 + 功效说明
- 按模块分组：
  - **主症模块**（≥总方 60%，直指主病机）
  - 兼症模块（按逻辑排序：如补气、补血、祛湿、活血、安神等）
- 模块下逐条列出：药名 + 克数（g），并简述主要作用。
- 总克数需严格≈ {total} g（不含生姜、红枣）。
- 如滋腻药较多，自动加入健脾化湿药护胃；避免药性冲突；必要时写明先煎/后下/另包。

④ 模块化横向处方表
- 每行：**模块标题** | 药名 克数 | 药名 克数 | …
- 表格末尾写总克数（g）。单位统一：克用 g，红枣用“枚”，生姜用“片”。

【患者信息】
- 主诉：{p.chiefComplaint}
- 症状：{symptoms}
- 舌象：{p.tongue or "未述"}
- 脉象：{p.pulse or "未述"}
- 病史：{p.history or "未述"}
- 客观：{p.objective or "未述"}
- 诊断思路提示：{p.assessmentHint or "无"}
- 偏好/注意：{p.preferences or "未述"}

请严格按①~④的结构，以 Markdown 输出，不要额外解释。
    """.strip()

@app.post("/soap", response_model=SoapOutput, tags=["tcm"])
def generate_soap(data: SoapInput, authorization: str | None = Header(default=None)):
    # 身份鉴权（沿用你已有的 Bearer token 逻辑）
    require_auth(authorization)

    if not OPENAI_API_KEY:
        raise HTTPException(status_code=500, detail="Server OPENAI_API_KEY not set")

    client = OpenAI(api_key=OPENAI_API_KEY)
    prompt = _build_soap_prompt(data)

    try:
        # 使用便宜快速的文本模型
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "你是一名资深中医临床医生，输出临床严谨、结构化、可直接入病历的内容。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
        )
        content = completion.choices[0].message.content
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"OpenAI error: {e}")

    total = (data.totalGrams or 110) * max(1, data.weeks or 1)
    return SoapOutput(soapMarkdown=content, totalGrams=total)
from fastapi import UploadFile, File

# 结构同你已有的 SoapOutput
class TranscribeOutput(BaseModel):
    text: str
    language: str | None = None

@app.post("/transcribe", response_model=TranscribeOutput, tags=["audio"])
def transcribe_audio(
    authorization: str | None = Header(default=None),
    file: UploadFile = File(...),
    language: str | None = None,
    prompt: str | None = None,
):
    require_auth(authorization)
    if not OPENAI_API_KEY:
        raise HTTPException(status_code=500, detail="Server OPENAI_API_KEY not set")

    client = OpenAI(api_key=OPENAI_API_KEY)
    try:
        # Whisper-1
        result = client.audio.transcriptions.create(
            model="whisper-1",
            file=file.file,  # FastAPI UploadFile 的类文件对象
            language=language,
            prompt=prompt
        )
        # openai>=1.x 返回对象字段名为 .text（按官方SDK）
        return TranscribeOutput(text=result.text or "", language=language)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Transcription error: {e}")

@app.post("/soap-from-audio", response_model=SoapOutput, tags=["audio"])
def soap_from_audio(
    authorization: str | None = Header(default=None),
    file: UploadFile = File(...),
    totalGrams: int = 110,
    weeks: int = 1,
    assessmentHint: str | None = None,
    preferences: str | None = None,
):
    require_auth(authorization)
    if not OPENAI_API_KEY:
        raise HTTPException(status_code=500, detail="Server OPENAI_API_KEY not set")

    # 1) 先转写
    client = OpenAI(api_key=OPENAI_API_KEY)
    try:
        t = client.audio.transcriptions.create(
            model="whisper-1",
            file=file.file,
            language="zh"
        )
        transcript = t.text or ""
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Transcription error: {e}")

    # 2) 再生成 SOAP（把整段转写当作主诉/症状综合，由模型抽取结构）
    prompt = f"""
你是资深中医师。以下是完整转写的问诊记录，请抽取关键信息并输出标准化 SOAP（Markdown）与分模块处方，遵守我方固定结构与总克数：
- 转写原文：{transcript}
- 诊断思路提示：{assessmentHint or "无"}
- 患者偏好：{preferences or "无"}
- 每周总克数：{totalGrams}g，疗程：{weeks}周
严格执行我方既定的 ①症状与中医诊断表 ②核心治则 ③处方 + 功效说明 ④模块化横向处方表 的格式与约束。
    """.strip()

    try:
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "你是一名临床严谨的中医医生，输出可直接入病历的内容。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
        )
        md = completion.choices[0].message.content
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"OpenAI error: {e}")

    return SoapOutput(soapMarkdown=md, totalGrams=(totalGrams * max(1, weeks)))
from fastapi import UploadFile, File
from pydantic import BaseModel
from openai import OpenAI
import os

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

class SoapOutput(BaseModel):
    soapMarkdown: str
    totalGrams: int

class TranscribeOutput(BaseModel):
    text: str
    language: str | None = None

@app.post("/transcribe", response_model=TranscribeOutput, tags=["audio"])
def transcribe_audio(
    authorization: str | None = Header(default=None),
    file: UploadFile = File(...),
    language: str | None = None,
    prompt: str | None = None,
):
    require_auth(authorization)
    if not OPENAI_API_KEY:
        raise HTTPException(status_code=500, detail="Server OPENAI_API_KEY not set")
    client = OpenAI(api_key=OPENAI_API_KEY)
    try:
        res = client.audio.transcriptions.create(
            model="whisper-1",
            file=file.file,
            language=language,
            prompt=prompt
        )
        return TranscribeOutput(text=res.text or "", language=language)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Transcription error: {e}")

@app.post("/soap-from-audio", response_model=SoapOutput, tags=["audio"])
def soap_from_audio(
    authorization: str | None = Header(default=None),
    file: UploadFile = File(...),
    totalGrams: int = 110,
    weeks: int = 1,
    assessmentHint: str | None = None,
    preferences: str | None = None,
):
    require_auth(authorization)
    if not OPENAI_API_KEY:
        raise HTTPException(status_code=500, detail="Server OPENAI_API_KEY not set")

    client = OpenAI(api_key=OPENAI_API_KEY)
    try:
        t = client.audio.transcriptions.create(model="whisper-1", file=file.file, language="zh")
        transcript = t.text or ""
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Transcription error: {e}")

    user_prompt = f"""
请将这段完整的问诊转写整理为标准化中医 SOAP 与处方（Markdown）：
- 转写原文：{transcript}
- 诊断思路提示：{assessmentHint or "无"}
- 患者偏好：{preferences or "无"}
- 每周总克数：{totalGrams}g，疗程：{weeks}周
严格执行我方既定格式：①症状与中医诊断表 ②核心治则 ③处方+功效说明 ④模块化横向处方表。
    """.strip()

    try:
        comp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "你是一名临床严谨的中医医生，输出可直接入病历。"},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.7,
        )
        md = comp.choices[0].message.content
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"OpenAI error: {e}")

    return SoapOutput(soapMarkdown=md, totalGrams=totalGrams * max(1, weeks))
@app.post("/transcribe", response_model=TranscribeOutput, tags=["audio"])
def transcribe_audio(
    authorization: str | None = Header(default=None),
    file: UploadFile = File(...),
    language: str | None = None,
    prompt: str | None = None,
):
    require_auth(authorization)
    if not OPENAI_API_KEY:
        raise HTTPException(status_code=500, detail="Server OPENAI_API_KEY not set")

    client = OpenAI(api_key=OPENAI_API_KEY)
    try:
        res = client.audio.transcriptions.create(
            model="whisper-1",
            file=file.file,         # FastAPI UploadFile 的类文件对象
            language=language,
            prompt=prompt,
        )
        return TranscribeOutput(text=res.text or "", language=language)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Transcription error: {e}")

@app.post("/soap-from-audio", response_model=SoapOutput, tags=["audio"])
def soap_from_audio(
    authorization: str | None = Header(default=None),
    file: UploadFile = File(...),
    totalGrams: int = 110,
    weeks: int = 1,
    assessmentHint: str | None = None,
    preferences: str | None = None,
):
    require_auth(authorization)
    if not OPENAI_API_KEY:
        raise HTTPException(status_code=500, detail="Server OPENAI_API_KEY not set")

    client = OpenAI(api_key=OPENAI_API_KEY)

    # 1) Whisper 转写
    try:
        t = client.audio.transcriptions.create(
            model="whisper-1",
            file=file.file,
            language="zh"   # 也可不指定，让模型自动识别
        )
        transcript = t.text or ""
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Transcription error: {e}")

    # 2) 生成 SOAP（把整段转写交给模型抽取结构并按你固定模板输出）
    user_prompt = f"""
请将这段完整的问诊转写整理为标准化中医 SOAP 与处方（Markdown）：
- 转写原文：{transcript}
- 诊断思路提示：{assessmentHint or "无"}
- 患者偏好：{preferences or "无"}
- 每周总克数：{totalGrams}g，疗程：{weeks}周
严格执行我方既定格式：①症状与中医诊断表 ②核心治则 ③处方+功效说明 ④模块化横向处方表。
    """.strip()

    try:
        comp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "你是一名临床严谨的中医医生，输出可直接入病历。"},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.7,
        )
        md = comp.choices[0].message.content
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"OpenAI error: {e}")

    return SoapOutput(soapMarkdown=md, totalGrams=totalGrams * max(1, weeks))
# 挂载静态目录，公开 /openapi.yaml 与 /recorder.html
app.mount("/", StaticFiles(directory="public", html=False), name="public")


app.mount("/", StaticFiles(directory="public", html=False), name="public")



