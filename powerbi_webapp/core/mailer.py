"""SMTP email sending for region reports."""
import os
import smtplib
from datetime import datetime
from email import encoders
from email.mime.base import MIMEBase
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from . import config as cfg
from .html_builder import build_email_html


def send_region_email(filename, html_filename, slicers, tables,
                       timestamp, recipient, region, logo_b64, has_logo,
                       kpis=None, section_labels=None):
    """Send the region report email.

    `filename` is an optional screenshot path embedded inline (cid:report_img);
    when None or missing, the screenshot block is simply omitted from the email.
    """
    email_html = build_email_html(filename, slicers, tables, timestamp,
                                   has_logo, logo_b64, kpis, section_labels)

    has_screenshot = bool(filename) and os.path.exists(filename)
    if not has_screenshot:
        email_html = email_html.replace(
            '<div style="margin-bottom:32px;">\n'
            f'      <div style="background:{cfg.C_NAVY};color:#fff;padding:10px 16px;font-size:13px;\n'
            f'                   font-weight:700;border-radius:6px 6px 0 0;">\n'
            '        Aperçu du tableau de bord Power BI</div>\n'
            '      <img src="cid:report_img" style="width:100%;display:block;border:1px solid #D5E1F5;\n'
            '               border-top:none;border-radius:0 0 6px 6px;">\n'
            '    </div>\n',
            ''
        )

    msg = MIMEMultipart("related")
    msg["From"] = cfg.EMAIL_FROM
    msg["To"] = recipient
    msg["Subject"] = (
        f"[La Poste Tunisienne] Rapport National — "
        f"{region} — "
        f"{datetime.strptime(timestamp, '%Y-%m-%d %H:%M').strftime('%d/%m/%Y')}"
    )
    msg.attach(MIMEText(email_html, "html", "utf-8"))

    if has_screenshot:
        with open(filename, "rb") as f:
            img = MIMEImage(f.read())
        img.add_header("Content-ID", "<report_img>")
        img.add_header("Content-Disposition", "inline", filename=os.path.basename(filename))
        msg.attach(img)

    if html_filename and os.path.exists(html_filename):
        with open(html_filename, "rb") as f:
            att = MIMEBase("text", "html")
            att.set_payload(f.read())
        encoders.encode_base64(att)
        att.add_header("Content-Disposition", "attachment",
                       filename=os.path.basename(html_filename))
        msg.attach(att)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(cfg.EMAIL_FROM, cfg.EMAIL_PASSWORD)
        server.sendmail(cfg.EMAIL_FROM, [recipient], msg.as_string())
