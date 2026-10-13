from grievance_social_protection.models import (
    Comment,
    GrievanceCategory,
    Ticket
)
from grievance_social_protection.tests.data import service_add_ticket_payload


def ensure_default_category(user):
    category = GrievanceCategory.objects.filter(name="Default", is_deleted=False).first()
    if category is None:
        category = GrievanceCategory(name="Default", is_active=True, user_created=user, user_updated=user)
        category.save(username=user.username)
    return category


def create_ticket(user):
    ticket = Ticket(**service_add_ticket_payload)
    ticket.save(user=user)
    return ticket


def create_comment_for_existing_ticket(user, ticket, resolved=False):
    comment = Comment(**{
        "ticket_id": ticket.id,
        "comment": "awesome comment",
        "is_resolution": True if resolved else False
    })
    comment.save(user=user)
    if resolved:
        ticket.status = 'CLOSED'
        ticket.save(user=user)
    return comment
