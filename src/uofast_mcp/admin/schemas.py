"""Pydantic request/response schemas for the admin REST API."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


# ---------------------------------------------------------------------------
# Role
# ---------------------------------------------------------------------------

class RoleOut(BaseModel):
    id: int
    role_name: str
    description: str | None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Permission
# ---------------------------------------------------------------------------

class PermissionOut(BaseModel):
    id: int
    permission_key: str
    tool_name: str
    action: str
    description: str | None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------

class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    email: EmailStr | None = None
    password: str = Field(..., min_length=8)
    role_name: str = "readonly"


class UserUpdate(BaseModel):
    email: EmailStr | None = None
    role_name: str | None = None
    status: str | None = Field(None, pattern="^(active|disabled)$")


class UserOut(BaseModel):
    id: int
    username: str
    email: str | None
    status: str
    role: RoleOut
    created_at: datetime
    last_login: datetime | None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Role-Permission assignment
# ---------------------------------------------------------------------------

class AssignPermissionRequest(BaseModel):
    permission_key: str


# ---------------------------------------------------------------------------
# Audit Log
# ---------------------------------------------------------------------------

class AuditLogOut(BaseModel):
    id: int
    user_id: int | None
    tool_name: str
    action: str
    params_summary: str | None
    result_status: str
    error_message: str | None
    timestamp: datetime
    ip_address: str | None

    model_config = {"from_attributes": True}
