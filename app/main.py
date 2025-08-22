# 顶部
import os, secrets
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

API_TOKEN = os.getenv("API_TOKEN", "").strip()
bearer_scheme = HTTPBearer(auto_error=False)

def auth(creds: HTTPAuthorizationCredentials = Depends(bearer_scheme)):
    # 若未配置 API_TOKEN，则放行（开发期）
    if not API_TOKEN:
        return
    # 没带授权头
    if creds is None or creds.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authenticated")
    # 去空白后比较
    client_token = (creds.credentials or "").strip()
    if not secrets.compare_digest(client_token, API_TOKEN):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
