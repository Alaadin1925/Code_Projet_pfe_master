"""Data-access for users."""
from __future__ import annotations

from ..extensions import db
from ..models import User


def get_by_username(username: str) -> User | None:
    return db.session.query(User).filter(User.username == username).first()


def get_by_id(user_id: int) -> User | None:
    return db.session.get(User, user_id)


def create(username: str, password: str, is_admin: bool = False,
           email: str | None = None) -> User:
    user = User(username=username, is_admin=is_admin, email=email)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return user


def upsert_admin(username: str, password: str) -> tuple[User, bool]:
    """Create or update an admin user. Returns (user, created?)."""
    user = get_by_username(username)
    created = user is None
    if user is None:
        user = User(username=username, is_admin=True)
        db.session.add(user)
    user.is_admin = True
    user.set_password(password)
    db.session.commit()
    return user, created
