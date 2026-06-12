from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from jose import JWTError, jwt
from passlib.context import CryptContext

from .config import get_settings

_pwd = CryptContext(schemes=["argon2"], deprecated="auto")
_settings = get_settings()


def hash_password(plain: str) -> str:
    return _pwd.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _pwd.verify(plain, hashed)
    except Exception:
        return False


def create_access_token(subject: str, expires_minutes: int | None = None,
                        extra: dict[str, Any] | None = None) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=expires_minutes or _settings.jwt_access_minutes
    )
    payload = {"sub": subject, "exp": expire, "type": "access"}
    if extra:
        payload.update(extra)
    return jwt.encode(payload, _settings.jwt_secret, algorithm=_settings.jwt_algorithm)


def create_refresh_token(subject: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=_settings.jwt_refresh_days)
    payload = {"sub": subject, "exp": expire, "type": "refresh"}
    return jwt.encode(payload, _settings.jwt_secret, algorithm=_settings.jwt_algorithm)


def decode_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, _settings.jwt_secret, algorithms=[_settings.jwt_algorithm])
    except JWTError as exc:
        raise ValueError(str(exc)) from exc


def _fernet() -> Fernet:
    key = _settings.key_vault_key
    if not key:
        # Derive a dev-only key from the JWT secret if KEY_VAULT_KEY missing.
        digest = (_settings.jwt_secret * 4).encode()[:32]
        key = base64.urlsafe_b64encode(digest).decode()
    return Fernet(key.encode() if not key.endswith("=") else key.encode())


def encrypt_payload(plain: bytes) -> bytes:
    return _fernet().encrypt(plain)


def decrypt_payload(token: bytes) -> bytes:
    try:
        return _fernet().decrypt(token)
    except InvalidToken as exc:
        raise ValueError("invalid encrypted payload") from exc
