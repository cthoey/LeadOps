from __future__ import annotations

from email.message import EmailMessage
import os
import smtplib

from leadops.config import EmailConfig


def send_email_digest(
    *,
    email_config: EmailConfig,
    subject: str,
    body_text: str,
    body_html: str | None = None,
) -> None:
    if email_config.mode != "smtp":
        raise RuntimeError("Email digest is not configured. Set [email] mode = \"smtp\" first.")
    if not email_config.host:
        raise RuntimeError("Email host is missing.")
    if not email_config.from_addr or not email_config.to_addr:
        raise RuntimeError("Email from_addr and to_addr must both be configured.")

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = email_config.from_addr
    message["To"] = email_config.to_addr
    message.set_content(body_text)
    if body_html:
        message.add_alternative(body_html, subtype="html")

    with smtplib.SMTP(email_config.host, email_config.port, timeout=60) as smtp:
        if email_config.starttls:
            smtp.starttls()
        if email_config.username:
            password = os.environ.get(email_config.password_env, "")
            if not password:
                raise RuntimeError(f"Missing SMTP password in ${email_config.password_env}.")
            smtp.login(email_config.username, password)
        smtp.send_message(message)
