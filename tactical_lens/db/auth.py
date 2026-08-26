"""
多用户认证与权限
角色：admin | coach | analyst | viewer
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from .connection import get_connection

# 角色定义
ROLES = ("admin", "coach", "analyst", "viewer")

# 权限矩阵：role -> 允许的动作
PERMISSIONS: Dict[str, List[str]] = {
    "admin": [
        "user.manage",
        "org.manage",
        "match.create",
        "match.read",
        "match.update",
        "match.delete",
        "upload.create",
        "report.create",
        "report.read",
        "insight.manage",
    ],
    "coach": [
        "match.create",
        "match.read",
        "match.update",
        "upload.create",
        "report.create",
        "report.read",
        "insight.manage",
    ],
    "analyst": [
        "match.create",
        "match.read",
        "match.update",
        "upload.create",
        "report.create",
        "report.read",
        "insight.manage",
    ],
    "viewer": [
        "match.read",
        "report.read",
    ],
}


def _hash_password(password: str, salt: Optional[str] = None) -> str:
    """轻量哈希（无额外依赖）。生产可换 bcrypt。"""
    if salt is None:
        salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000)
    return f"pbkdf2_sha256${salt}${dk.hex()}"


def _verify_password(password: str, stored: str) -> bool:
    try:
        algo, salt, hexdigest = stored.split("$", 2)
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000)
        return hmac.compare_digest(dk.hex(), hexdigest)
    except Exception:
        return False


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _expires_iso(hours: int = 72) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")


class AuthService:
    """用户注册 / 登录 / 会话 / 权限检查"""

    def ensure_default_admin(self, username: str = "admin", password: str = "admin123") -> None:
        """若无任何用户，创建默认管理员（首次部署用，请尽快改密）"""
        with get_connection() as conn:
            row = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()
            if row and row["c"] > 0:
                return
            uid = str(uuid.uuid4())
            conn.execute(
                """
                INSERT INTO users (id, username, email, password_hash, display_name, role)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (uid, username, None, _hash_password(password), "系统管理员", "admin"),
            )

    def register(
        self,
        username: str,
        password: str,
        role: str = "analyst",
        email: Optional[str] = None,
        display_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        if role not in ROLES:
            raise ValueError(f"无效角色: {role}，可选: {ROLES}")
        if len(password) < 6:
            raise ValueError("密码至少 6 位")
        uid = str(uuid.uuid4())
        with get_connection() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO users (id, username, email, password_hash, display_name, role)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (uid, username.strip(), email, _hash_password(password), display_name or username, role),
                )
            except Exception as e:
                if "UNIQUE" in str(e).upper():
                    raise ValueError("用户名或邮箱已存在") from e
                raise
        return self.get_user(uid)  # type: ignore

    def login(self, username: str, password: str) -> Dict[str, Any]:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE username = ? AND is_active = 1",
                (username.strip(),),
            ).fetchone()
            if not row or not _verify_password(password, row["password_hash"]):
                raise ValueError("用户名或密码错误")
            token = secrets.token_urlsafe(32)
            conn.execute(
                "INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
                (token, row["id"], _expires_iso(72)),
            )
        user = dict(row)
        user.pop("password_hash", None)
        return {"token": token, "user": user}

    def logout(self, token: str) -> None:
        with get_connection() as conn:
            conn.execute("DELETE FROM sessions WHERE token = ?", (token,))

    def get_user_by_token(self, token: str) -> Optional[Dict[str, Any]]:
        if not token:
            return None
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT u.* FROM users u
                JOIN sessions s ON s.user_id = u.id
                WHERE s.token = ? AND s.expires_at > datetime('now') AND u.is_active = 1
                """,
                (token,),
            ).fetchone()
            if not row:
                return None
            user = dict(row)
            user.pop("password_hash", None)
            return user

    def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        with get_connection() as conn:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            if not row:
                return None
            user = dict(row)
            user.pop("password_hash", None)
            return user

    def list_users(self) -> List[Dict[str, Any]]:
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT id, username, email, display_name, role, is_active, created_at FROM users ORDER BY created_at"
            ).fetchall()
            return [dict(r) for r in rows]

    def set_role(self, user_id: str, role: str) -> None:
        if role not in ROLES:
            raise ValueError(f"无效角色: {role}")
        with get_connection() as conn:
            conn.execute(
                "UPDATE users SET role = ?, updated_at = ? WHERE id = ?",
                (role, _now_iso(), user_id),
            )

    def has_permission(self, user: Dict[str, Any], action: str) -> bool:
        role = user.get("role", "viewer")
        return action in PERMISSIONS.get(role, [])

    def require_permission(self, user: Dict[str, Any], action: str) -> None:
        if not self.has_permission(user, action):
            raise PermissionError(f"权限不足：需要 {action}（当前角色 {user.get('role')}）")
