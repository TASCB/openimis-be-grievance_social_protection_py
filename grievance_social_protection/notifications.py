import logging

from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)


def notify_assignment(ticket, assignee):
    """Send an email to `assignee` informing them they were assigned to `ticket`.

    Failures are logged and swallowed — email delivery must never block a mutation.
    """
    email = getattr(assignee, "email", None)
    if not email:
        logger.info("Skipping grievance assignment email: user %s has no email", getattr(assignee, "id", None))
        return

    subject = f"[Grievance {ticket.code or ticket.id}] You have been assigned"
    body = (
        f"Hello {assignee.username or ''},\n\n"
        f"You have been assigned to grievance ticket {ticket.code or ticket.id}.\n\n"
        f"Title: {ticket.title or '(no title)'}\n"
        f"Category: {ticket.category or '-'}\n"
        f"Priority: {ticket.priority or '-'}\n"
        f"Status: {ticket.status}\n"
        f"Due date: {ticket.due_date or '-'}\n\n"
        f"Description:\n{ticket.description or '-'}\n"
    )
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", None) or "no-reply@openimis.local"

    try:
        send_mail(subject, body, from_email, [email], fail_silently=False)
    except Exception:
        logger.exception("Failed to send grievance assignment email to %s", email)
