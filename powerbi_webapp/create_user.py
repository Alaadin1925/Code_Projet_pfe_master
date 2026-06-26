"""CLI helper to create/update a webapp user account.

Usage:
    python create_user.py <username> <password> [--admin]
"""
import sys

from app import create_app
from models import User, db


def main():
    if len(sys.argv) < 3:
        print("Usage: python create_user.py <username> <password> [--admin]")
        sys.exit(1)

    username = sys.argv[1]
    password = sys.argv[2]
    is_admin = "--admin" in sys.argv[3:]

    app = create_app(start_background_worker=False)
    with app.app_context():
        user = User.query.filter_by(username=username).first()
        if user is None:
            user = User(username=username, is_admin=is_admin)
            db.session.add(user)
            print(f"Création de l'utilisateur '{username}'...")
        else:
            user.is_admin = is_admin
            print(f"Mise à jour de l'utilisateur '{username}'...")
        user.set_password(password)
        db.session.commit()
        print("OK.")


if __name__ == "__main__":
    main()
