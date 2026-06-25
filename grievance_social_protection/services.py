from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db.models import Max
from django.db import transaction
from core import TimeUtils
from core.services import BaseService
from core.signals import register_service_signal
from core.services.utils import (
    check_authentication as check_authentication,
    output_exception,
    model_representation,
    output_result_success,
)
from grievance_social_protection.models import (
    Ticket,
    Comment,
    GrievanceCategory,
    GrievanceType,
    GrievanceChannel,
)
from grievance_social_protection.validations import (
    TicketValidation,
    CommentValidation,
    is_external_reporter_type,
    validate_external_reporter,
    validate_resolution,
)
from grievance_social_protection.location_scope import (
    ensure_ticket_access,
    normalize_external_reporter_location,
    normalize_ticket_location,
)


class TicketService(BaseService):
    OBJECT_TYPE = Ticket
    EXTERNAL_REPORTER_FIELDS = {
        "external_reporter_first_name",
        "external_reporter_last_name",
        "external_reporter_phone",
        "external_reporter_email",
        "external_reporter_location_id",
    }
    EXTERNAL_REPORTER_LOCATION_INPUT_FIELDS = {
        "external_reporter_region_id",
        "external_reporter_district_id",
        "external_reporter_ward_id",
        "external_reporter_village_id",
    }

    def __init__(self, user, validation_class=TicketValidation):
        super().__init__(user, validation_class)

    @register_service_signal("ticket_service.create")
    def create(self, obj_data):
        if obj_data.get("consent_given") is None:
            obj_data["consent_given"] = False
        self._normalize_reporter(obj_data)
        normalize_ticket_location(self.user, obj_data)
        self._generate_code(obj_data)
        resolution_error = validate_resolution(obj_data)
        if resolution_error:
            raise ValidationError(resolution_error)
        return super().create(obj_data)

    @register_service_signal("ticket_service.update")
    def update(self, obj_data):
        self._normalize_reporter(obj_data)
        ticket = Ticket.objects.filter(id=obj_data.get("id")).first()
        ensure_ticket_access(self.user, ticket)
        normalize_ticket_location(self.user, obj_data, existing_ticket=ticket)
        resolution_error = validate_resolution(obj_data)
        if resolution_error:
            raise ValidationError(resolution_error)
        return super().update(obj_data)

    @register_service_signal("ticket_service.delete")
    def delete(self, obj_data):
        return super().delete(obj_data)

    @register_service_signal("ticket_service.close_ticket")
    @check_authentication
    def close_ticket(self, obj_data):
        try:
            with transaction.atomic():
                ticket_id = obj_data.get("id")
                ticket = Ticket.objects.filter(id=ticket_id).first()
                if not ticket:
                    raise ValidationError("Ticket not found")
                ensure_ticket_access(self.user, ticket)

                ticket_update_data = {
                    key: value
                    for key, value in obj_data.items()
                    if key
                    in {
                        "title",
                        "attending_staff_id",
                        "date_of_incident",
                        "priority",
                        "due_date",
                        "category",
                        "flags",
                        "channel",
                        "resolution",
                    }
                }
                location_input = {
                    key: obj_data[key]
                    for key in (
                        "event_location_id",
                        "region_id",
                        "district_id",
                        "ward_id",
                        "village_id",
                    )
                    if key in obj_data
                }
                if location_input:
                    normalize_ticket_location(
                        self.user,
                        location_input,
                        existing_ticket=ticket,
                    )
                    ticket_update_data["event_location_id"] = location_input[
                        "event_location_id"
                    ]

                resolution_error = validate_resolution(ticket_update_data)
                if resolution_error:
                    raise ValidationError(resolution_error)
                if ticket_update_data:
                    self.validation_class.validate_update(
                        self.user, id=ticket_id, **ticket_update_data
                    )
                    ticket.update(data=ticket_update_data, user=self.user, save=False)

                comment_text = (obj_data.get("comment") or "").strip()
                if not comment_text:
                    raise ValidationError("Closing comment is required")

                comment_payload = {"ticket_id": ticket_id, "comment": comment_text}
                if obj_data.get("commenter_type"):
                    comment_payload["commenter_type"] = obj_data.get("commenter_type")
                if obj_data.get("commenter_id"):
                    comment_payload["commenter_id"] = obj_data.get("commenter_id")
                if comment_payload.get("commenter_type") == "user":
                    comment_payload["commenter_id"] = str(self.user.id)

                comment_service = CommentService(self.user)
                comment_service._get_content_type(comment_payload)
                comment_service.validation_class.validate_create(
                    self.user, **comment_payload
                )

                comment = Comment(
                    ticket=ticket,
                    comment=comment_text,
                    commenter_type=comment_payload.get("commenter_type"),
                    commenter_id=comment_payload.get("commenter_id"),
                    is_resolution=True,
                )
                comment.save(username=self.user.username)

                comment_service._append_comment_id(ticket, comment.id)
                ticket.status = Ticket.TicketStatus.CLOSED
                ticket.save(username=self.user.username)
                return {
                    "success": True,
                    "message": "Ok",
                    "detail": "close_ticket",
                }
        except Exception as exc:
            return output_exception(
                model_name=self.OBJECT_TYPE.__name__,
                method="close_ticket",
                exception=exc,
            )

    @register_service_signal("ticket_service.reopen_ticket")
    @check_authentication
    def reopen_ticket(self, obj_data):
        try:
            with transaction.atomic():
                self.validation_class.validate_update(self.user, **obj_data)
                ticket_id = obj_data.get("id")
                ticket = Ticket.objects.filter(id=ticket_id).first()
                ensure_ticket_access(self.user, ticket)
                ticket.status = Ticket.TicketStatus.OPEN
                self._check_if_comment_resolution(ticket_id)
                ticket.save(username=self.user.username)
                return {
                    "success": True,
                    "message": "Ok",
                    "detail": "reopen_ticket",
                }
        except Exception as exc:
            return output_exception(
                model_name=self.OBJECT_TYPE.__name__,
                method="reopen_ticket",
                exception=exc,
            )

    @transaction.atomic
    def _check_if_comment_resolution(self, ticket_id):
        comment_queryset = Comment.objects.filter(
            ticket_id=ticket_id, is_resolution=True
        )
        if comment_queryset.exists():
            comment = comment_queryset.first()
            comment.is_resolution = False
            comment.save(username=self.user.username)

    def _normalize_reporter(self, obj_data):
        if "reporter_type" not in obj_data:
            return

        reporter_type = obj_data.get("reporter_type")
        if is_external_reporter_type(reporter_type):
            obj_data["reporter_type"] = None
            obj_data["reporter_id"] = None
            self._clean_external_reporter_strings(obj_data)
            validate_external_reporter(obj_data)
            normalize_external_reporter_location(obj_data, require_complete=True)
            return

        if not reporter_type:
            obj_data["reporter_type"] = None
            obj_data["reporter_id"] = None
            self._clear_external_reporter(obj_data)
            return

        content_type = ContentType.objects.get(model=reporter_type.lower())
        obj_data["reporter_type"] = content_type
        self._clear_external_reporter(obj_data)

    def _clear_external_reporter(self, obj_data):
        for field in self.EXTERNAL_REPORTER_FIELDS:
            obj_data[field] = None
        for field in self.EXTERNAL_REPORTER_LOCATION_INPUT_FIELDS:
            obj_data.pop(field, None)

    @staticmethod
    def _clean_external_reporter_strings(obj_data):
        for field in (
            "external_reporter_first_name",
            "external_reporter_last_name",
            "external_reporter_phone",
            "external_reporter_email",
        ):
            if field in obj_data and obj_data[field] is not None:
                obj_data[field] = str(obj_data[field]).strip() or None

    def _generate_code(self, obj_data):
        if not obj_data.get("code"):
            last_ticket_code = (
                Ticket.objects.filter(code__startswith="GRS")
                .aggregate(Max("code"))
                .get("code__max")
            )
            if last_ticket_code is None:
                last_ticket_code_numeric = 0
            else:
                last_ticket_code_numeric = int(last_ticket_code[3:])

            new_ticket_code = f"GRS{last_ticket_code_numeric + 1:08}"
            obj_data["code"] = new_ticket_code


class CommentService:
    OBJECT_TYPE = Comment

    def __init__(self, user, validation_class=CommentValidation):
        self.user = user
        self.validation_class = validation_class

    @register_service_signal("comment_service.create")
    @check_authentication
    def create(self, obj_data):
        try:
            with transaction.atomic():
                self._get_content_type(obj_data)
                ticket_id = obj_data.get("ticket_id")
                self.validation_class.validate_create(self.user, **obj_data)

                comment_obj = self.OBJECT_TYPE(**obj_data)
                response_data = self.save_instance(comment_obj)
                self._update_ticket_comment_ids(ticket_id, response_data["data"]["id"])

                return response_data

        except Exception as exc:
            return output_exception(
                model_name=self.OBJECT_TYPE.__name__, method="create", exception=exc
            )

    @transaction.atomic
    def _update_ticket_comment_ids(self, ticket_id, comment_id):
        ticket = Ticket.objects.filter(id=ticket_id).first()
        if ticket:
            self._append_comment_id(ticket, comment_id)
            ticket.save(username=self.user.username)

    def _append_comment_id(self, ticket, comment_id):
        json_ext = ticket.json_ext or {}
        comment_ids = list(json_ext.get("comment_ids", []))
        comment_id = str(comment_id)
        if comment_id not in comment_ids:
            comment_ids.append(comment_id)
        json_ext["comment_ids"] = comment_ids
        ticket.json_ext = json_ext

    @register_service_signal("comment_service.resolve_grievance_by_comment")
    @check_authentication
    def resolve_grievance_by_comment(self, obj_data):
        try:
            with transaction.atomic():
                self.validation_class.validate_resolve_grievance_by_comment(
                    self.user, **obj_data
                )
                comment = Comment.objects.filter(id=obj_data.get("id")).first()
                ticket = comment.ticket
                ticket.status = Ticket.TicketStatus.CLOSED
                self._append_comment_id(ticket, comment.id)
                if not comment.is_resolution:
                    comment.is_resolution = True
                    comment.save(username=self.user.username)
                ticket.save(username=self.user.username)
                return {
                    "success": True,
                    "message": "Ok",
                    "detail": "resolve_grievance_by_comment",
                }
        except Exception as exc:
            return output_exception(
                model_name=self.OBJECT_TYPE.__name__,
                method="resolve_grievance_by_comment",
                exception=exc,
            )

    def save_instance(self, obj_):
        obj_.save(username=self.user.username)
        dict_repr = model_representation(obj_)
        return output_result_success(dict_representation=dict_repr)

    def _get_content_type(self, obj_data):
        if "commenter_type" in obj_data:
            content_type = ContentType.objects.get(
                model=obj_data["commenter_type"].lower()
            )
            obj_data["commenter_type"] = content_type


class GrievanceCategoryService(BaseService):
    OBJECT_TYPE = GrievanceCategory

    def __init__(self, user):
        super().__init__(user)

    def _adjust_create_payload(self, payload_data):
        payload_data["user_created"] = self.user
        payload_data["user_updated"] = self.user
        payload_data["date_created"] = TimeUtils.now()
        payload_data["date_updated"] = TimeUtils.now()
        return payload_data

    def _adjust_update_payload(self, payload_data):
        payload_data["user_updated"] = self.user
        payload_data["date_updated"] = TimeUtils.now()
        return super()._adjust_update_payload(payload_data)

    def save_instance(self, obj_):
        obj_.save(username=self.user.username)
        dict_repr = model_representation(obj_)
        return output_result_success(dict_representation=dict_repr)


class GrievanceTypeService(BaseService):
    OBJECT_TYPE = GrievanceType

    def __init__(self, user):
        super().__init__(user)

    def _adjust_create_payload(self, payload_data):
        payload_data["user_created"] = self.user
        payload_data["user_updated"] = self.user
        payload_data["date_created"] = TimeUtils.now()
        payload_data["date_updated"] = TimeUtils.now()
        return payload_data

    def _adjust_update_payload(self, payload_data):
        payload_data["user_updated"] = self.user
        payload_data["date_updated"] = TimeUtils.now()
        return super()._adjust_update_payload(payload_data)

    def save_instance(self, obj_):
        obj_.save(username=self.user.username)
        dict_repr = model_representation(obj_)
        return output_result_success(dict_representation=dict_repr)


class GrievanceChannelService(BaseService):
    OBJECT_TYPE = GrievanceChannel

    def __init__(self, user):
        super().__init__(user)

    def _adjust_create_payload(self, payload_data):
        payload_data["user_created"] = self.user
        payload_data["user_updated"] = self.user
        payload_data["date_created"] = TimeUtils.now()
        payload_data["date_updated"] = TimeUtils.now()
        return payload_data

    def _adjust_update_payload(self, payload_data):
        payload_data["user_updated"] = self.user
        payload_data["date_updated"] = TimeUtils.now()
        return super()._adjust_update_payload(payload_data)

    def save_instance(self, obj_):
        obj_.save(username=self.user.username)
        dict_repr = model_representation(obj_)
        return output_result_success(dict_representation=dict_repr)
