import base64
import hashlib
import hmac
import json
import time

from fastapi import HTTPException, Request, Response, status

from app.config import get_settings


def require_login(request: Request) -> str:
    settings = get_settings()
    token = request.cookies.get(settings.auth_cookie_name)
    username = verify_session_token(token)
    if not username:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先登录")
    return username


def login(response: Response, username: str, password: str) -> dict:
    settings = get_settings()
    if not settings.auth_password or not settings.auth_session_secret:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="登录密码或会话密钥未配置")
    if not hmac.compare_digest(username, settings.auth_username):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="账号或密码错误")
    if not hmac.compare_digest(password, settings.auth_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="账号或密码错误")

    token = create_session_token(username)
    response.set_cookie(
        key=settings.auth_cookie_name,
        value=token,
        max_age=settings.auth_session_seconds,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        path="/",
    )
    return {"username": username}


def logout(response: Response) -> dict:
    settings = get_settings()
    response.delete_cookie(key=settings.auth_cookie_name, path="/")
    return {"status": "logged_out"}


def create_session_token(username: str) -> str:
    settings = get_settings()
    payload = {
        "username": username,
        "expires_at": int(time.time()) + settings.auth_session_seconds,
    }
    payload_text = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    payload_part = base64.urlsafe_b64encode(payload_text.encode("utf-8")).decode("ascii")
    signature = sign_payload(payload_part)
    return f"{payload_part}.{signature}"


def verify_session_token(token: str | None) -> str:
    if not token or "." not in token:
        return ""
    payload_part, signature = token.rsplit(".", 1)
    if not hmac.compare_digest(signature, sign_payload(payload_part)):
        return ""
    try:
        payload_text = base64.urlsafe_b64decode(payload_part.encode("ascii")).decode("utf-8")
        payload = json.loads(payload_text)
    except (ValueError, json.JSONDecodeError):
        return ""
    if int(payload.get("expires_at", 0)) < int(time.time()):
        return ""
    return str(payload.get("username") or "")


def sign_payload(payload_part: str) -> str:
    secret = get_settings().auth_session_secret.encode("utf-8")
    digest = hmac.new(secret, payload_part.encode("utf-8"), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
