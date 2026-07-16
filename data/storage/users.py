import logging
import random
import string
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from sqlalchemy import text
from werkzeug.security import generate_password_hash, check_password_hash

from storage.db import get_conn

logger = logging.getLogger(__name__)


def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    email = (email or "").strip().lower()
    if not email:
        return None
    with get_conn() as conn:
        row = conn.execute(
            text("SELECT * FROM utilisateurs WHERE email = :email LIMIT 1"),
            {"email": email},
        ).fetchone()
        return dict(row._mapping) if row else None


def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    with get_conn() as conn:
        row = conn.execute(
            text("SELECT * FROM utilisateurs WHERE id = :id LIMIT 1"),
            {"id": user_id},
        ).fetchone()
        return dict(row._mapping) if row else None


def create_user(
    nom: str,
    email: str,
    password: str,
    voice_auth: int = 0,
) -> Optional[int]:
    nom      = (nom or "").strip()
    email    = (email or "").strip().lower()
    password = password or ""

    if not nom or not email or not password:
        return None

    password_hash  = generate_password_hash(password)
    voice_auth_val = bool(int(voice_auth)) if str(voice_auth).isdigit() else bool(voice_auth)

    with get_conn() as conn:
        exists = conn.execute(
            text("SELECT id FROM utilisateurs WHERE email = :email LIMIT 1"),
            {"email": email},
        ).fetchone()
        if exists:
            return None

        conn.execute(
            text("""
                INSERT INTO utilisateurs (nom, email, password_hash, voice_auth)
                VALUES (:nom, :email, :password_hash, :voice_auth)
            """),
            {
                "nom":           nom,
                "email":         email,
                "password_hash": password_hash,
                "voice_auth":    voice_auth_val,
            },
        )

        row = conn.execute(
            text("SELECT id FROM utilisateurs WHERE email = :email LIMIT 1"),
            {"email": email},
        ).fetchone()
        return int(row[0]) if row else None


def verify_user_password(user_row: Dict[str, Any], password: str) -> bool:
    if not user_row:
        return False
    return check_password_hash(user_row["password_hash"], password)


def generate_verification_code() -> str:
    return "".join(random.choices(string.digits, k=6))


def set_verification_code(email: str, code: str, expires_minutes: int = 15) -> bool:
    email      = (email or "").strip().lower()
    expires_at = (datetime.utcnow() + timedelta(minutes=expires_minutes)).isoformat()

    with get_conn() as conn:
        result = conn.execute(
            text("""
                UPDATE utilisateurs
                SET verification_code       = :code,
                    verification_expires_at = :expires_at
                WHERE email = :email
            """),
            {"code": code, "expires_at": expires_at, "email": email},
        )
        return result.rowcount > 0


def verify_email_code(email: str, code: str) -> bool:
    email = (email or "").strip().lower()
    code  = (code or "").strip()

    user = get_user_by_email(email)
    if not user:
        return False

    stored_code    = user.get("verification_code")
    expires_at_str = user.get("verification_expires_at")

    if not stored_code or stored_code != code:
        return False

    if expires_at_str:
        try:
            expires_at = datetime.fromisoformat(expires_at_str)
            if datetime.utcnow() > expires_at:
                return False
        except ValueError:
            return False

    with get_conn() as conn:
        conn.execute(
            text("""
                UPDATE utilisateurs
                SET email_verified          = 1,
                    verification_code       = NULL,
                    verification_expires_at = NULL
                WHERE email = :email
            """),
            {"email": email},
        )
    return True


def update_password(email: str, new_password: str) -> bool:
    email = (email or "").strip().lower()
    if not email or not new_password:
        return False

    new_hash = generate_password_hash(new_password)
    with get_conn() as conn:
        result = conn.execute(
            text("""
                UPDATE utilisateurs
                SET password_hash = :hash
                WHERE email = :email
            """),
            {"hash": new_hash, "email": email},
        )
        return result.rowcount > 0
