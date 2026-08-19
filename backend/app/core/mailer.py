"""Sending an e-mail, and refusing loudly when it cannot be sent.

🔴 A FAILED SEND MUST NEVER LOOK LIKE A SENT ONE. This product records `notified_on` on a
capital call, and `LateCall.never_notified` exists so a fund can tell « this investor is
late » from « we never wrote to them ». A mailer that swallowed a failure and let the caller
mark the notice as sent would destroy exactly that distinction: the column would say the
letter went out, the investor would have received nothing, and the fund would chase them for
it. So this module RAISES, and the caller marks nothing.

That is deliberately the opposite of the sister product's choice. Le Comptoir Immo's
`send_email` returns False and carries on, because a receipt that failed to send is an
annoyance. Here the send is the fact being recorded, and a silent failure is a false record.

🔴 NO IDENTITY BORROWED FROM ANOTHER PRODUCT. The SMTP CONNECTION is shared across the
platform - one relay, one credential, rotated in one place. The SENDING IDENTITY never is.
`SMTP_FROM_EMAIL` has no default: an installation that forgets it cannot send, which is the
right failure. A fallback on a sibling's address would put « Le Comptoir Immo » on a fund's
capital call, and the investor would be right to treat it as a phishing attempt.

⚠️ THE RELAY FILTERS BY IP. Brevo refuses with « 525 Unauthorized IP » until the sending
host's address is on its allow-list, and the message says nothing about IPs. When a send
fails from a new host, check that first.
"""

from __future__ import annotations

import logging
from email.message import EmailMessage

import aiosmtplib

from app.config import get_settings
from app.core.i18n import pick

logger = logging.getLogger(__name__)


class MailNotSent(Exception):
    """The letter did not go out, and the caller must not record that it did."""


def is_configured() -> bool:
    """Can this installation send at all?

    Both halves are required: a host with no sender address cannot address a message, and a
    sender address with no host has nowhere to hand it to. Reported as one answer so a
    screen can say « sending is not set up » instead of failing at the click.
    """
    settings = get_settings()
    return bool(settings.SMTP_HOST and settings.SMTP_FROM_EMAIL)


async def send(*, to: str, subject: str, body: str) -> None:
    """Hand one plain-text message to the relay, or raise saying why not.

    ⚠️ PLAIN TEXT, ON PURPOSE. A capital call notice is a legal demand whose whole content
    is a figure, a date and a reference the investor retypes. HTML adds a way for the
    reference to be reflowed, hidden behind a link, or eaten by a client's stripping - and
    the reference is the only thing tying their transfer to the call.
    """
    settings = get_settings()
    if not is_configured():
        raise MailNotSent(
            pick(
                "L'envoi d'e-mail n'est pas configuré sur cette installation : le serveur "
                "SMTP ou l'adresse d'expédition manque. L'avis n'a pas été envoyé, et il "
                "n'est pas enregistré comme envoyé.",
                "E-mail sending is not configured on this installation: the SMTP server or "
                "the sender address is missing. The notice was not sent, and it is not "
                "recorded as sent.",
            )
        )
    if not (to or "").strip():
        raise MailNotSent(
            pick(
                "Ce destinataire n'a pas d'adresse e-mail enregistrée : l'avis ne peut pas "
                "lui être envoyé.",
                "This recipient has no e-mail address on record: the notice cannot be sent "
                "to them.",
            )
        )

    message = EmailMessage()
    message["From"] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>"
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)

    try:
        await aiosmtplib.send(
            message,
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=settings.SMTP_USER or None,
            password=settings.SMTP_PASSWORD or None,
            start_tls=settings.SMTP_TLS,
        )
    except Exception as exc:  # noqa: BLE001 - every failure is the same fact: not sent
        logger.error("SMTP refused the notice to %s: %s", to, exc)
        raise MailNotSent(
            pick(
                f"Le serveur d'envoi a refusé le message : {exc}. L'avis n'a pas été "
                f"envoyé, et il n'est pas enregistré comme envoyé.",
                f"The sending server refused the message: {exc}. The notice was not sent, "
                f"and it is not recorded as sent.",
            )
        ) from exc


__all__ = ["MailNotSent", "is_configured", "send"]
