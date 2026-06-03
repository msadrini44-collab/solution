"""
Authentication helpers — JWT issuance/verification, password hashing, API keys.

Password hashing uses PBKDF2-HMAC-SHA256 from the standard library so there are
no native build dependencies. JWTs are signed with python-jose.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import hmac
import os
import secrets
from typing import Optional

from fastapi import Depends, Header, HTTPException, status
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from . import config
from .database import User, get_session

_PBKDF2_ROUNDS = 240_000


# --------------------------------------------------------------------------- #
# Passwords
# --------------------------------------------------------------------------- #
def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ROUNDS)
    return f"pbkdf2_sha256${_PBKDF2_ROUNDS}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, rounds, salt_hex, hash_hex = stored.split("$")
        dk = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt_hex), int(rounds)
        )
        return hmac.compare_digest(dk.hex(), hash_hex)
    except Exception:
        return False


def generate_api_key() -> str:
    return "adf_" + secrets.token_hex(24)


# --------------------------------------------------------------------------- #
# JWT
# --------------------------------------------------------------------------- #
def create_access_token(user: User) -> str:
    expire = _dt.datetime.utcnow() + _dt.timedelta(minutes=config.JWT_EXPIRE_MINUTES)
    payload = {"sub": str(user.id), "email": user.email, "exp": expire}
    return jwt.encode(payload, config.JWT_SECRET, algorithm=config.JWT_ALGORITHM)


def _user_from_token(token: str, db: Session) -> Optional[User]:
    try:
        payload = jwt.decode(token, config.JWT_SECRET, algorithms=[config.JWT_ALGORITHM])
        user_id = int(payload.get("sub"))
    except (JWTError, TypeError, ValueError):
        return None
    return db.get(User, user_id)


# --------------------------------------------------------------------------- #
# FastAPI dependencies
# --------------------------------------------------------------------------- #
def get_current_user(
    authorization: Optional[str] = Header(default=None),
    x_api_key: Optional[str] = Header(default=None),
    db: Session = Depends(get_session),
) -> User:
    """Authenticate via Bearer JWT or X-API-Key header."""
    user: Optional[User] = None

    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        user = _user_from_token(token, db)

    if user is None and x_api_key:
        user = db.query(User).filter(User.api_key == x_api_key).first()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def get_optional_user(
    authorization: Optional[str] = Header(default=None),
    x_api_key: Optional[str] = Header(default=None),
    db: Session = Depends(get_session),
) -> Optional[User]:
    """Like ``get_current_user`` but returns None instead of raising.

    Lets anonymous visitors run a scan (e.g. from the sales-page demo) while
    still associating scans with a user when credentials are supplied.
    """
    try:
        return get_current_user(authorization=authorization, x_api_key=x_api_key, db=db)
    except HTTPException:
        return None
