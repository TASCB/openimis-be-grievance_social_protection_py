import re

from django.core.exceptions import ValidationError
from django.core.validators import EmailValidator
from django.utils.translation import gettext as _
from django.contrib.contenttypes.models import ContentType

from core.models import User
from core.validation import BaseModelValidation, ObjectExistsValidationMixin
from grievance_social_protection.models import Ticket, Comment


EXTERNAL_REPORTER_TYPES = {
    "external",
    "externalreporter",
    "external_reporter",
    "external reporter",
}
DESCRIPTION_MIN_WORDS = 45
DESCRIPTION_MAX_WORDS = 150


class TicketValidation(BaseModelValidation):
    OBJECT_TYPE = Ticket

    @classmethod
    def validate_create(cls, user, **data):
        errors = []

        unique_code_errors = validate_ticket_unique_code(data)
        for error in unique_code_errors:
            errors.append(ValidationError(error, code='unique_code_error'))

        description_errors = validate_ticket_description_word_count(data)
        for error in description_errors:
            errors.append(ValidationError(error, code="description_word_count_error"))

        if errors:
            raise ValidationError(errors)

        super().validate_create(user, **data)

    @classmethod
    def validate_update(cls, user, **data):
        errors = []

        unique_code_errors = validate_ticket_unique_code(data)
        for error in unique_code_errors:
            errors.append(ValidationError(error, code='unique_code_error'))

        description_errors = validate_ticket_description_unchanged(data)
        for error in description_errors:
            errors.append(ValidationError(error, code="description_immutable_error"))

        consent_errors = validate_ticket_consent_unchanged(data)
        for error in consent_errors:
            errors.append(ValidationError(error, code="consent_immutable_error"))

        if errors:
            raise ValidationError(errors)

        super().validate_update(user, **data)


class CommentValidation(ObjectExistsValidationMixin):
    OBJECT_TYPE = Comment

    @classmethod
    def validate_create(cls, user, **data):
        errors = [
            *validate_ticket_exists(data),
        ]
        if errors:
            raise ValidationError(errors)

    @classmethod
    def validate_resolve_grievance_by_comment(cls, user, **data):
        errors = []
        comment_id = data.get("id")
        if comment_id:
            cls.validate_object_exists(comment_id)
        else:
            errors.extend(validate_ticket_exists(data))
            if not (data.get("comment") or "").strip():
                errors.append({"message": _("Closing comment is required")})
        if errors:
            raise ValidationError(errors)


def validate_ticket_exists(data):
    ticket_id = data.get('ticket_id')
    if not Ticket.objects.filter(id=ticket_id).exists():
        return [{"message": _("validations.CommentValidation.validate_ticket_exists") % {"ticket_id": ticket_id}}]
    return []


def validate_resolution(data):
    """
    Validates that `value` is in the format '{days},{hours}'
    where days are in the range <0, 99) and hours are in the range <0, 24).
    """
    resolution = data.get('resolution')
    if not resolution:
        return None

    pattern = r"^(?P<days>[0-9]{1,2}),(?P<hours>[0-9]{1,2})$"
    match = re.match(pattern, resolution)
    if not match:
        return {"message": _("validations.TicketValidation.validate_resolution.invalid_format")}
    else:
        days = int(match.group("days"))
        hours = int(match.group("hours"))

        if not (0 <= days < 99):
            return {"message": _("validations.TicketValidation.validate_resolution.invalid_day_value")}
        if not (0 <= hours < 24):
            return {"message": _("validations.TicketValidation.validate_resolution.invalid_hour_value")}

    return None


def validate_commenter_exists(data):
    commenter_type = data.get('commenter_type')
    commenter_id = data.get('commenter_id')
    model_class = commenter_type.model_class()

    if not model_class.objects.filter(id=commenter_id).exists():
        return [{"message": _("validations.CommentValidation.validate_commenter_exists")}]

    return []


def validate_commenter_associated_with_ticket(data):
    commenter_type = data.get('commenter_type')
    commenter_id = data.get('commenter_id')

    model_class = commenter_type.model_class()
    commenter = model_class.objects.get(id=commenter_id)

    if isinstance(commenter, User):
        attending_staff_tickets = Ticket.objects.filter(attending_staff=commenter)
        if attending_staff_tickets.exists():
            return []

    reporter_tickets = Ticket.objects.filter(reporter_type=commenter_type, reporter_id=commenter_id)
    if reporter_tickets.exists():
        return []

    return [{"message": _("validations.CommentValidation.commenter_not_associated_with_ticket")}]


def user_associated_with_ticket(user, ticket_id):
    if not isinstance(user, User) or not ticket_id:
        return False
    return Ticket.objects.filter(
        attending_staff=user,
        id=ticket_id,
    ).exists()


def validate_ticket_unique_code(data):
    code = data.get('code')
    ticket_id = data.get('id')

    if not code:
        return []

    ticket_queryset = Ticket.objects.filter(code=code)
    if ticket_id:
        ticket_queryset.exclude(id=ticket_id)
    if ticket_queryset.exists():
        return [{"message": _("validations.TicketValidation.validate_ticket_unique_code") % {"code": code}}]
    return []


def description_word_count(description):
    return len(str(description or "").strip().split())


def validate_ticket_description_word_count(data):
    word_count = description_word_count(data.get("description"))
    if word_count < DESCRIPTION_MIN_WORDS:
        return [{"message": _("Description must contain at least 45 words.")}]
    if word_count > DESCRIPTION_MAX_WORDS:
        return [{"message": _("Description must not exceed 150 words.")}]
    return []


def validate_ticket_description_unchanged(data):
    if "description" not in data or not data.get("id"):
        return []

    ticket = Ticket.objects.filter(id=data.get("id")).only("description").first()
    if ticket is None:
        return []

    if (ticket.description or "") != (data.get("description") or ""):
        return [{"message": _("Description cannot be changed after submission.")}]
    return []


def validate_ticket_consent_unchanged(data):
    if "consent_given" not in data or not data.get("id"):
        return []

    ticket = Ticket.objects.filter(id=data.get("id")).only("consent_given").first()
    if ticket is None:
        return []

    if data.get("consent_given") is None:
        return [{"message": _("Consent cannot be changed after submission.")}]

    if bool(ticket.consent_given) != bool(data.get("consent_given")):
        return [{"message": _("Consent cannot be changed after submission.")}]
    return []


def is_external_reporter_type(reporter_type):
    if reporter_type is None:
        return False
    return str(reporter_type).strip().lower().replace("-", " ") in EXTERNAL_REPORTER_TYPES


def validate_external_reporter(data):
    errors = []
    required_fields = [
        ("external_reporter_first_name", _("First Name is required")),
        ("external_reporter_last_name", _("Last Name is required")),
        ("external_reporter_phone", _("Phone Number is required")),
    ]

    for field, message in required_fields:
        value = data.get(field)
        if not str(value or "").strip():
            errors.append({"message": message})

    phone = str(data.get("external_reporter_phone") or "").strip()
    if phone and not _is_usable_phone(phone):
        errors.append({
            "message": _(
                "Phone Number must contain 7 to 15 digits and may include a leading +, spaces, hyphens, dots, or parentheses"
            )
        })

    email = str(data.get("external_reporter_email") or "").strip()
    if email:
        try:
            EmailValidator()(email)
        except ValidationError:
            errors.append({"message": _("Email Address must be a valid email address")})

    if errors:
        raise ValidationError(errors)


def _is_usable_phone(phone):
    if not re.match(r"^\+?[0-9][0-9\s().-]*$", phone):
        return False
    digits = re.sub(r"\D", "", phone)
    if not 7 <= len(digits) <= 15:
        return False
    if len(set(digits)) == 1:
        return False
    return True


def validate_reporter(data):
    reporter_type = data.get("reporter_type")
    reporter_id = data.get("reporter_id")

    if reporter_type and reporter_id:
        if reporter_type not in ["User", "Individual"]:
            return [{"message": _("validations.TicketValidation.invalid_reporter_type")}]

        try:
            content_type = ContentType.objects.get(model=reporter_type.lower())
        except Exception:
            return [{"message": _("validations.TicketValidation.reporter_type_invalid")}]

        try:
            content_type.get_object_for_this_type(id=reporter_id)
        except Exception:
            return [{"message": _("validations.TicketValidation.reporter_not_found")}]

        return []

    error_messages = []
    if not reporter_type:
        error_messages.append({"message": _("validations.TicketValidation.reporter_type_required")})
    if not reporter_id:
        error_messages.append({"message": _("validations.TicketValidation.reporter_id_required")})

    return error_messages
