"""
SQLAdmin web UI — auto-generated CRUD for all security models.
Mounts at /admin (managed by sqladmin.Admin in app.py).
Login requires valid admin credentials (checked via bcrypt).
"""
from __future__ import annotations

import logging

import bcrypt
from sqladmin import ModelView
from sqladmin.authentication import AuthenticationBackend
from starlette.requests import Request
from wtforms import PasswordField
from wtforms.validators import Optional

from ..security.database import AsyncSessionLocal
from ..security.models import AuditLog, Permission, Role, RolePermission, User
from ..security.rbac import rbac_engine

logger = logging.getLogger(__name__)


class AdminAuth(AuthenticationBackend):
    """Session-cookie-based auth for the SQLAdmin UI."""

    async def login(self, request: Request) -> bool:
        form = await request.form()
        username = form.get("username", "")
        password = form.get("password", "")

        async with AsyncSessionLocal() as session:
            user = await rbac_engine.authenticate_password(session, str(username), str(password))

        if not user:
            return False
        if not user.role or user.role.role_name != "admin":
            logger.warning("Non-admin user '%s' attempted admin UI login", username)
            return False

        # Store user identity in the session (encrypted by SessionMiddleware)
        request.session["admin_user_id"] = user.id
        request.session["admin_username"] = user.username
        return True

    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> bool:
        return "admin_user_id" in request.session


# ---------------------------------------------------------------------------
# ModelView definitions
# ---------------------------------------------------------------------------

class UserAdmin(ModelView, model=User):
    name = "User"
    name_plural = "Users"
    icon = "fa-solid fa-user"

    column_list = [User.id, User.username, User.email, User.status, User.role_id, User.created_at, User.last_login]
    column_searchable_list = [User.username, User.email]
    column_sortable_list = [User.id, User.username, User.created_at]
    form_excluded_columns = [User.password_hash, User.audit_logs]
    form_extra_fields = {"password": PasswordField("Password", validators=[Optional()])}
    can_export = True

    async def on_model_change(self, data: dict, model: User, is_created: bool, request: Request) -> None:
        password = data.pop("password", None) or ""
        if password:
            model.password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        elif is_created:
            model.password_hash = bcrypt.hashpw(b"XXXX", bcrypt.gensalt()).decode()


class RoleAdmin(ModelView, model=Role):
    name = "Role"
    name_plural = "Roles"
    icon = "fa-solid fa-shield"

    column_list = [Role.id, Role.role_name, Role.description]
    column_searchable_list = [Role.role_name]
    can_export = True


class PermissionAdmin(ModelView, model=Permission):
    name = "Permission"
    name_plural = "Permissions"
    icon = "fa-solid fa-key"

    column_list = [Permission.id, Permission.permission_key, Permission.tool_name, Permission.action, Permission.description]
    column_searchable_list = [Permission.permission_key, Permission.tool_name]
    column_sortable_list = [Permission.permission_key, Permission.tool_name]
    can_export = True


class RolePermissionAdmin(ModelView, model=RolePermission):
    name = "Role Permission"
    name_plural = "Role Permissions"
    icon = "fa-solid fa-link"

    column_list = [RolePermission.id, RolePermission.role_id, RolePermission.permission_id]
    can_export = True


class AuditLogAdmin(ModelView, model=AuditLog):
    name = "Audit Log"
    name_plural = "Audit Logs"
    icon = "fa-solid fa-clipboard-list"

    column_list = [
        AuditLog.id, AuditLog.user_id, AuditLog.tool_name, AuditLog.action,
        AuditLog.result_status, AuditLog.timestamp, AuditLog.ip_address,
    ]
    column_sortable_list = [AuditLog.timestamp, AuditLog.tool_name, AuditLog.result_status]
    column_searchable_list = [AuditLog.tool_name]

    # Audit logs are immutable
    can_create = False
    can_edit = False
    can_delete = False
    can_export = True


ALL_VIEWS = [
    UserAdmin,
    RoleAdmin,
    PermissionAdmin,
    RolePermissionAdmin,
    AuditLogAdmin,
]
