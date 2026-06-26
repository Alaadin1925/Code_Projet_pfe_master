"""Optional report emailing via SMTP.

Disabled unless MAIL_ENABLED=true and SMTP credentials are configured in .env.
No credentials are ever hardcoded.
"""
from __future__ import annotations

import os
import smtplib
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from flask import current_app


class MailNotConfigured(RuntimeError):
    pass


def _require_config() -> dict:
    cfg = current_app.config
    if not cfg.get("MAIL_ENABLED"):
        raise MailNotConfigured("Email is disabled (set MAIL_ENABLED=true in .env).")
    if not (cfg.get("MAIL_USERNAME") and cfg.get("MAIL_PASSWORD") and cfg.get("MAIL_FROM")):
        raise MailNotConfigured("SMTP credentials are incomplete in .env.")
    return cfg


def send(recipient: str | None, subject: str, html_body: str,
         attachment_path: str | None = None) -> str:
    """Send an HTML email with an optional file attachment. Returns the recipient."""
    cfg = _require_config()
    recipient = (recipient or cfg.get("MAIL_DEFAULT_RECIPIENT") or "").strip()
    if not recipient:
        raise MailNotConfigured("No recipient (set MAIL_DEFAULT_RECIPIENT or pass one).")

    msg = MIMEMultipart("mixed")
    msg["From"] = cfg["MAIL_FROM"]
    msg["To"] = recipient
    msg["Subject"] = subject
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    if attachment_path and os.path.exists(attachment_path):
        with open(attachment_path, "rb") as fh:
            part = MIMEBase("text", "html")
            part.set_payload(fh.read())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", "attachment",
                        filename=os.path.basename(attachment_path))
        msg.attach(part)

    with smtplib.SMTP_SSL(cfg["MAIL_SMTP_HOST"], cfg["MAIL_SMTP_PORT"]) as server:
        server.login(cfg["MAIL_USERNAME"], cfg["MAIL_PASSWORD"])
        server.sendmail(cfg["MAIL_FROM"], [recipient], msg.as_string())
    return recipient
