"""Request/response schemas for /api/signup and /api/signup-status."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, EmailStr, Field


class SignupStatus(BaseModel):
    signups_enabled: bool


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class SignupResendRequest(BaseModel):
    email: EmailStr


class SignupResponse(BaseModel):
    state: Literal["confirm_email_sent"]
