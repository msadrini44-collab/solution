"""Pydantic request/response models for the API."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, EmailStr


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    api_key: str
    email: EmailStr


class DetectResponse(BaseModel):
    scan_id: str
    status: str
    filename: str
    media_type: Optional[str] = None
    # Present immediately when processed synchronously.
    score: Optional[float] = None
    verdict: Optional[str] = None
    breakdown: Optional[List[Dict[str, Any]]] = None
    processing_time_sec: Optional[float] = None
    artifacts: Optional[Dict[str, str]] = None


class ScanSummary(BaseModel):
    scan_id: str
    filename: str
    media_type: str
    status: str
    score: Optional[float] = None
    verdict: Optional[str] = None
    created_at: str


class HistoryResponse(BaseModel):
    scans: List[ScanSummary]
