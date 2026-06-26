# Security notes

## 🔴 Action required — rotate the leaked Gmail credential

The **previous** code (`powerbi_webapp/core/config.py`, now removed) contained a
hardcoded Gmail **App Password** committed to the public GitHub repository:

```
EMAIL_FROM     = "aalabouzid2002@gmail.com"
EMAIL_PASSWORD = "nwsj xmwh jvxz rspv"      # <-- leaked, must be revoked
SECRET_KEY     = "change-me-in-production-please"
```

Removing the file from the working tree does **not** remove it from git history.
You must:

1. **Revoke the App Password** now: Google Account → Security → *App passwords* →
   delete `nwsj xmwh jvxz rspv`.
2. Generate a **new** App Password and put it in `.env` (`MAIL_PASSWORD=…`) only.
3. Change the account password if you suspect misuse.
4. (Optional) Purge it from git history with `git filter-repo` / BFG before making
   the repo public again.

## How secrets are handled now

- **Nothing secret is hardcoded.** All secrets/paths/credentials come from `.env`
  (loaded via `python-dotenv`). `.env` is git-ignored; `.env.example` documents the keys.
- `SECRET_KEY` is **required** — the app refuses to start without it (no insecure default).
- **Passwords** are hashed with `werkzeug.security.generate_password_hash`
  (PBKDF2-HMAC-SHA256, per-user salt). Plaintext passwords are never stored.
- **Sessions/cookies**: `HttpOnly`, `SameSite=Lax`, configurable `Secure` flag
  (`SESSION_COOKIE_SECURE=true` behind HTTPS), bounded lifetime.
- **CSRF**: all POST forms are protected by Flask-WTF `CSRFProtect`.
- **Path traversal**: report downloads are restricted to a bare filename inside
  `REPORTS_DIR`.
- **SQL injection**: all DB access goes through SQLAlchemy (parameterized).
- **Least privilege (recommended)**: create a dedicated SQL login for the app with
  rights only on the `lp_national` database instead of using `sa`.
- **PII**: sender fields (name, address, phone) are mostly blank in the source and
  are stored verbatim; restrict DB access accordingly. Consider dropping them if
  not needed for reporting.
