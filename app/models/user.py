"""Authentication models: User and an optional Profile."""
from __future__ import annotations

from datetime import datetime

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from ..extensions import db


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(255), nullable=True)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    last_login_at = db.Column(db.DateTime, nullable=True)

    profile = db.relationship(
        "Profile", back_populates="user", uselist=False,
        cascade="all, delete-orphan",
    )

    # ── Password handling (PBKDF2-SHA256 via werkzeug) ────────────────────────
    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<User {self.username}{' (admin)' if self.is_admin else ''}>"


class Profile(db.Model):
    """Optional per-user profile (display name, region scope, etc.)."""

    __tablename__ = "profiles"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"),
                        unique=True, nullable=False)
    full_name = db.Column(db.String(160), nullable=True)
    region_scope = db.Column(db.String(80), nullable=True)  # restrict a user to a region
    phone = db.Column(db.String(40), nullable=True)

    user = db.relationship("User", back_populates="profile")
