import smtplib
import logging
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logger = logging.getLogger(__name__)


def _get_smtp_config() -> dict:
    return {
        "host":     os.getenv("SMTP_HOST", "smtp.gmail.com"),
        "port":     int(os.getenv("SMTP_PORT", "587")),
        "user":     os.getenv("SMTP_USER", ""),
        "password": os.getenv("SMTP_PASSWORD", ""),
        "from":     os.getenv("SMTP_FROM", os.getenv("SMTP_USER", "")),
    }


def _send(to_email: str, subject: str, html_body: str, text_body: str) -> bool:
    cfg = _get_smtp_config()

    if not cfg["user"] or not cfg["password"]:
        logger.warning("SMTP non configure — email non envoye.")
        logger.info("--- EMAIL DEBUG ---")
        logger.info("A       : %s", to_email)
        logger.info("Sujet   : %s", subject)
        logger.info("Contenu : %s", text_body)
        logger.info("-------------------")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = cfg["from"]
    msg["To"]      = to_email

    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html",  "utf-8"))

    try:
        with smtplib.SMTP(cfg["host"], cfg["port"], timeout=10) as server:
            server.ehlo()
            server.starttls()
            server.login(cfg["user"], cfg["password"])
            server.sendmail(cfg["from"], to_email, msg.as_string())
        logger.info("Email envoye a %s", to_email)
        return True
    except Exception as exc:
        logger.error("Erreur envoi email a %s : %s", to_email, exc)
        return False


def send_verification_code(to_email: str, code: str) -> bool:
    subject = "Votre code de verification Scorpius"

    text_body = (
        f"Bonjour,\n\n"
        f"Votre code de verification Scorpius est : {code}\n\n"
        f"Ce code expire dans 15 minutes.\n\n"
        f"Si vous n avez pas cree de compte, ignorez cet email.\n\n"
        f"Scorpius"
    )

    html_body = f"""
    <div style="font-family:sans-serif; max-width:480px; margin:auto;">
        <h2 style="color:#e05c00;">Scorpius</h2>
        <p>Votre code de verification est :</p>
        <div style="
            font-size: 2.5rem;
            font-weight: bold;
            letter-spacing: 0.4rem;
            color: #e05c00;
            padding: 1rem;
            background: #1a1a2e;
            border-radius: 8px;
            text-align: center;
        ">
            {code}
        </div>
        <p style="color:#888; font-size:0.85rem;">
            Ce code expire dans <strong>15 minutes</strong>.<br>
            Si vous n avez pas cree de compte, ignorez cet email.
        </p>
    </div>
    """

    return _send(to_email, subject, html_body, text_body)


def send_password_reset_link(to_email: str, reset_url: str) -> bool:
    subject = "Reinitialisation de votre mot de passe Scorpius"

    text_body = (
        f"Bonjour,\n\n"
        f"Cliquez sur ce lien pour reinitialiser votre mot de passe :\n"
        f"{reset_url}\n\n"
        f"Ce lien expire dans 1 heure.\n\n"
        f"Si vous n avez pas demande de reinitialisation, ignorez cet email.\n\n"
        f"Scorpius"
    )

    html_body = f"""
    <div style="font-family:sans-serif; max-width:480px; margin:auto;">
        <h2 style="color:#e05c00;">Scorpius</h2>
        <p>Vous avez demande a reinitialiser votre mot de passe.</p>
        <a href="{reset_url}" style="
            display: inline-block;
            margin: 1rem 0;
            padding: 0.75rem 1.5rem;
            background: #e05c00;
            color: white;
            border-radius: 6px;
            text-decoration: none;
            font-weight: bold;
        ">
            Reinitialiser mon mot de passe
        </a>
        <p style="color:#888; font-size:0.85rem;">
            Ce lien expire dans <strong>1 heure</strong>.<br>
            Si vous n etes pas a l origine de cette demande, ignorez cet email.
        </p>
        <p style="color:#555; font-size:0.8rem; word-break:break-all;">
            Lien : {reset_url}
        </p>
    </div>
    """

    return _send(to_email, subject, html_body, text_body)
