import graphene
from core.gql.gql_mutations.base_mutation import (
    BaseHistoryModelCreateMutationMixin,
    BaseMutation,
    BaseHistoryModelUpdateMutationMixin,
    BaseHistoryModelDeleteMutationMixin,
)
from core.schema import OpenIMISMutation
from .models import (
    Ticket,
    TicketMutation,
    Comment,
    GrievanceCategory,
    GrievanceType,
    GrievanceChannel,
)
from django.core.exceptions import ValidationError, PermissionDenied
from .apps import TicketConfig
from django.utils.translation import gettext_lazy as _
from .services import (
    TicketService,
    CommentService,
    GrievanceCategoryService,
    GrievanceTypeService,
    GrievanceChannelService,
)
from .validations import user_associated_with_ticket
from .location_scope import ensure_ticket_access


TERMINAL_TICKET_STATUSES = {
    Ticket.TicketStatus.RESOLVED,
    Ticket.TicketStatus.CLOSED,
}


def _context_user(info):
    return getattr(getattr(info, "context", None), "user", None)


def _require_permission(user, field):
    if user is None or not user.has_perms(TicketConfig.permissions(field)):
        raise PermissionDenied(_("unauthorized"))


def _require_comment_access(user, ticket_id):
    _require_ticket_access(user, ticket_id)
    if user is not None and user.has_perms(
        TicketConfig.permissions("gql_mutation_create_comment_perms")
    ):
        return
    if user_associated_with_ticket(user, ticket_id):
        return
    raise PermissionDenied(_("unauthorized"))


def _require_ticket_access(user, ticket_id):
    ticket = Ticket.objects.filter(id=ticket_id).first()
    ensure_ticket_access(user, ticket)
    return ticket


class CreateTicketInputType(OpenIMISMutation.Input):
    class TicketStatusEnum(graphene.Enum):
        RECEIVED = Ticket.TicketStatus.RECEIVED
        OPEN = Ticket.TicketStatus.OPEN
        IN_PROGRESS = Ticket.TicketStatus.IN_PROGRESS
        RESOLVED = Ticket.TicketStatus.RESOLVED
        CLOSED = Ticket.TicketStatus.CLOSED

    key = graphene.String(required=False)
    title = graphene.String(required=False)
    description = graphene.String(required=False)
    reporter_type = graphene.String(required=False, max_lenght=255)
    reporter_id = graphene.String(required=False, max_lenght=255)
    attending_staff_id = graphene.UUID(required=False)
    date_of_incident = graphene.Date(required=False)
    status = graphene.Field(TicketStatusEnum, required=False)
    priority = graphene.String(required=False)
    due_date = graphene.Date(required=False)
    category = graphene.String(required=True)
    flags = graphene.String(required=False)
    channel = graphene.String(required=False)
    consent_given = graphene.Boolean(required=False)
    json_ext = graphene.types.json.JSONString(required=False)
    resolution = graphene.String(required=False)
    event_location_id = graphene.Int(required=False)
    region_id = graphene.Int(required=False)
    district_id = graphene.Int(required=False)
    ward_id = graphene.Int(required=False)
    village_id = graphene.Int(required=False)
    external_reporter_first_name = graphene.String(required=False)
    external_reporter_last_name = graphene.String(required=False)
    external_reporter_phone = graphene.String(required=False)
    external_reporter_email = graphene.String(required=False)
    external_reporter_location_id = graphene.Int(required=False)
    external_reporter_region_id = graphene.Int(required=False)
    external_reporter_district_id = graphene.Int(required=False)
    external_reporter_ward_id = graphene.Int(required=False)
    external_reporter_village_id = graphene.Int(required=False)


class UpdateTicketInputType(CreateTicketInputType):
    id = graphene.UUID(required=True)


class ResolveGrievanceByCommentInputType(OpenIMISMutation.Input):
    id = graphene.UUID(required=True)


class CloseTicketInputType(OpenIMISMutation.Input):
    id = graphene.UUID(required=True)
    title = graphene.String(required=False)
    description = graphene.String(required=False)
    attending_staff_id = graphene.UUID(required=False)
    date_of_incident = graphene.Date(required=False)
    priority = graphene.String(required=False)
    due_date = graphene.Date(required=False)
    category = graphene.String(required=False)
    flags = graphene.String(required=False)
    channel = graphene.String(required=False)
    resolution = graphene.String(required=False)
    event_location_id = graphene.Int(required=False)
    region_id = graphene.Int(required=False)
    district_id = graphene.Int(required=False)
    ward_id = graphene.Int(required=False)
    village_id = graphene.Int(required=False)
    commenter_type = graphene.String(required=False, max_lenght=255)
    commenter_id = graphene.String(required=False, max_lenght=255)
    comment = graphene.String(required=True)


class CreateCommentInputType(OpenIMISMutation.Input):
    ticket_id = graphene.UUID(required=True)
    commenter_type = graphene.String(required=False, max_lenght=255)
    commenter_id = graphene.String(required=False, max_lenght=255)
    comment = graphene.String(required=True)


class CreateTicketMutation(BaseHistoryModelCreateMutationMixin, BaseMutation):
    _mutation_class = "CreateTicketMutation"
    _mutation_module = "grievance_social_protection"
    _model = Ticket

    @classmethod
    def _authorize_create(cls, user, **data):
        _require_permission(user, "gql_mutation_create_tickets_perms")
        if data.get("status") in TERMINAL_TICKET_STATUSES:
            _require_permission(user, "gql_mutation_resolve_grievance_perms")

    @classmethod
    def mutate_and_get_payload(cls, root, info, **data):
        cls._authorize_create(_context_user(info), **data)
        return super().mutate_and_get_payload(root, info, **data)

    @classmethod
    def _validate_mutation(cls, user, **data):
        super()._validate_mutation(user, **data)
        cls._authorize_create(user, **data)

    @classmethod
    def _mutate(cls, user, **data):
        client_mutation_id = data.pop("client_mutation_id")
        if "client_mutation_label" in data:
            data.pop("client_mutation_label")

        service = TicketService(user)
        response = service.create(data)
        if not response["success"]:
            return response
        if client_mutation_id:
            ticket_id = response["data"]["id"]
            ticket = Ticket.objects.get(id=ticket_id)
            TicketMutation.object_mutated(
                user, client_mutation_id=client_mutation_id, ticket=ticket
            )

        return None

    class Input(CreateTicketInputType):
        pass


class UpdateTicketMutation(BaseHistoryModelUpdateMutationMixin, BaseMutation):
    _mutation_class = "UpdateTicketMutation"
    _mutation_module = "grievance_social_protection"
    _model = Ticket

    @classmethod
    def _authorize_update(cls, user, **data):
        _require_permission(user, "gql_mutation_update_tickets_perms")
        if data.get("id"):
            _require_ticket_access(user, data["id"])
        if data.get("status") in TERMINAL_TICKET_STATUSES:
            _require_permission(user, "gql_mutation_resolve_grievance_perms")

    @classmethod
    def mutate_and_get_payload(cls, root, info, **data):
        cls._authorize_update(_context_user(info), **data)
        return super().mutate_and_get_payload(root, info, **data)

    @classmethod
    def _validate_mutation(cls, user, **data):
        super()._validate_mutation(user, **data)
        cls._authorize_update(user, **data)

    @classmethod
    def _mutate(cls, user, **data):
        client_mutation_id = data.pop("client_mutation_id")
        if "client_mutation_label" in data:
            data.pop("client_mutation_label")

        service = TicketService(user)
        response = service.update(data)
        if not response["success"]:
            return response
        if client_mutation_id:
            ticket_id = response["data"]["id"]
            ticket = Ticket.objects.get(id=ticket_id)
            TicketMutation.object_mutated(
                user, client_mutation_id=client_mutation_id, ticket=ticket
            )
        return None

    class Input(UpdateTicketInputType):
        pass


class DeleteTicketMutation(BaseHistoryModelDeleteMutationMixin, BaseMutation):
    _mutation_class = "DeleteTicketMutation"
    _mutation_module = "grievance_social_protection"
    _model = Ticket

    @classmethod
    def _validate_mutation(cls, user, **data):
        super()._validate_mutation(user, **data)
        _require_permission(user, "gql_mutation_delete_tickets_perms")
        for ticket_id in data.get("ids", []):
            _require_ticket_access(user, ticket_id)

    class Input(OpenIMISMutation.Input):
        ids = graphene.List(graphene.UUID)


class CreateCommentMutation(BaseHistoryModelCreateMutationMixin, BaseMutation):
    _mutation_class = "CreateCommentMutation"
    _mutation_module = "grievance_social_protection"
    _model = Comment

    @classmethod
    def mutate_and_get_payload(cls, root, info, **data):
        _require_comment_access(_context_user(info), data.get("ticket_id"))
        return super().mutate_and_get_payload(root, info, **data)

    @classmethod
    def _validate_mutation(cls, user, **data):
        super()._validate_mutation(user, **data)
        _require_comment_access(user, data.get("ticket_id"))

    @classmethod
    def _mutate(cls, user, **data):
        if "client_mutation_id" in data:
            data.pop("client_mutation_id")
        if "client_mutation_label" in data:
            data.pop("client_mutation_label")

        if "commenter_type" in data:
            data["commenter_type"] = data.get("commenter_type", "").lower()
        service = CommentService(user)
        response = service.create(data)

        if not response["success"]:
            return response
        return None

    class Input(CreateCommentInputType):
        pass


class ResolveGrievanceByCommentMutation(
    BaseHistoryModelUpdateMutationMixin, BaseMutation
):
    _mutation_class = "ResolveGrievanceByCommentMutation"
    _mutation_module = "grievance_social_protection"
    _model = Comment

    @classmethod
    def mutate_and_get_payload(cls, root, info, **data):
        _require_permission(
            _context_user(info),
            "gql_mutation_resolve_grievance_perms",
        )
        comment = Comment.objects.filter(id=data.get("id")).select_related("ticket").first()
        if comment is not None:
            ensure_ticket_access(_context_user(info), comment.ticket)
        return super().mutate_and_get_payload(root, info, **data)

    @classmethod
    def _validate_mutation(cls, user, **data):
        super()._validate_mutation(user, **data)
        _require_permission(user, "gql_mutation_resolve_grievance_perms")
        comment = Comment.objects.filter(id=data.get("id")).select_related("ticket").first()
        if comment is not None:
            ensure_ticket_access(user, comment.ticket)

    @classmethod
    def _mutate(cls, user, **data):
        client_mutation_id = data.pop("client_mutation_id")
        if "client_mutation_label" in data:
            data.pop("client_mutation_label")

        service = CommentService(user)
        response = service.resolve_grievance_by_comment(data)
        if client_mutation_id:
            comment_id = data.get("id")
            ticket = Comment.objects.get(id=comment_id).ticket
            TicketMutation.object_mutated(
                user, client_mutation_id=client_mutation_id, ticket=ticket
            )

        if not response["success"]:
            return response
        return None

    class Input(ResolveGrievanceByCommentInputType):
        pass


class ReopenTicketMutation(BaseHistoryModelUpdateMutationMixin, BaseMutation):
    _mutation_class = "ReopenTicketMutation"
    _mutation_module = "grievance_social_protection"
    _model = Ticket

    @classmethod
    def mutate_and_get_payload(cls, root, info, **data):
        _require_permission(_context_user(info), "gql_mutation_update_tickets_perms")
        _require_ticket_access(_context_user(info), data.get("id"))
        return super().mutate_and_get_payload(root, info, **data)

    @classmethod
    def _validate_mutation(cls, user, **data):
        super()._validate_mutation(user, **data)
        _require_permission(user, "gql_mutation_update_tickets_perms")
        _require_ticket_access(user, data.get("id"))

    @classmethod
    def _mutate(cls, user, **data):
        client_mutation_id = data.pop("client_mutation_id")
        if "client_mutation_label" in data:
            data.pop("client_mutation_label")

        service = TicketService(user)
        response = service.reopen_ticket(data)
        if client_mutation_id:
            ticket_id = data.get("id")
            ticket = Ticket.objects.get(id=ticket_id)
            TicketMutation.object_mutated(
                user, client_mutation_id=client_mutation_id, Ticket=ticket
            )

        if not response["success"]:
            return response
        return None

    class Input(ResolveGrievanceByCommentInputType):
        pass


class CloseTicketMutation(BaseHistoryModelUpdateMutationMixin, BaseMutation):
    _mutation_class = "CloseTicketMutation"
    _mutation_module = "grievance_social_protection"
    _model = Ticket

    @classmethod
    def _authorize_close(cls, user):
        _require_permission(user, "gql_mutation_update_tickets_perms")
        _require_permission(user, "gql_mutation_resolve_grievance_perms")

    @classmethod
    def mutate_and_get_payload(cls, root, info, **data):
        cls._authorize_close(_context_user(info))
        _require_ticket_access(_context_user(info), data.get("id"))
        return super().mutate_and_get_payload(root, info, **data)

    @classmethod
    def _validate_mutation(cls, user, **data):
        super()._validate_mutation(user, **data)
        cls._authorize_close(user)
        _require_ticket_access(user, data.get("id"))

    @classmethod
    def _mutate(cls, user, **data):
        client_mutation_id = data.pop("client_mutation_id")
        if "client_mutation_label" in data:
            data.pop("client_mutation_label")
        if "commenter_type" in data and data["commenter_type"]:
            data["commenter_type"] = data.get("commenter_type", "").lower()

        service = TicketService(user)
        response = service.close_ticket(data)
        if client_mutation_id:
            ticket_id = data.get("id")
            ticket = Ticket.objects.get(id=ticket_id)
            TicketMutation.object_mutated(
                user, client_mutation_id=client_mutation_id, ticket=ticket
            )

        if not response["success"]:
            return response
        return None

    class Input(CloseTicketInputType):
        pass


# ── GrievanceCategory mutations ──────────────────────────────────────────────

class GrievanceCategoryInputType(OpenIMISMutation.Input):
    id = graphene.String(required=False)
    code = graphene.String(required=False)
    name = graphene.String(required=True)
    timeline = graphene.Int(required=False)
    is_active = graphene.Boolean(required=False, default_value=True)


class CreateGrievanceCategoryMutation(BaseHistoryModelCreateMutationMixin, BaseMutation):
    _mutation_class = "CreateGrievanceCategoryMutation"
    _mutation_module = "grievance_social_protection"
    _model = GrievanceCategory

    @classmethod
    def _validate_mutation(cls, user, **data):
        super()._validate_mutation(user, **data)
        _require_permission(user, "gql_mutation_create_tickets_perms")

    @classmethod
    def _mutate(cls, user, **data):
        data.pop("client_mutation_id", None)
        data.pop("client_mutation_label", None)
        service = GrievanceCategoryService(user)
        response = service.create(data)
        if not response["success"]:
            return response
        return None

    class Input(GrievanceCategoryInputType):
        pass


class UpdateGrievanceCategoryMutation(BaseHistoryModelUpdateMutationMixin, BaseMutation):
    _mutation_class = "UpdateGrievanceCategoryMutation"
    _mutation_module = "grievance_social_protection"
    _model = GrievanceCategory

    @classmethod
    def _validate_mutation(cls, user, **data):
        super()._validate_mutation(user, **data)
        _require_permission(user, "gql_mutation_update_tickets_perms")

    @classmethod
    def _mutate(cls, user, **data):
        data.pop("client_mutation_id", None)
        data.pop("client_mutation_label", None)
        service = GrievanceCategoryService(user)
        response = service.update(data)
        if not response["success"]:
            return response
        return None

    class Input(GrievanceCategoryInputType):
        id = graphene.String(required=True)


class DeleteGrievanceCategoryMutation(BaseHistoryModelDeleteMutationMixin, BaseMutation):
    _mutation_class = "DeleteGrievanceCategoryMutation"
    _mutation_module = "grievance_social_protection"
    _model = GrievanceCategory

    @classmethod
    def _validate_mutation(cls, user, **data):
        super()._validate_mutation(user, **data)
        _require_permission(user, "gql_mutation_delete_tickets_perms")
        for cat_id in data.get("ids", []):
            if GrievanceType.objects.filter(category_id=cat_id, is_deleted=False).exists():
                raise ValidationError(
                    "Cannot delete a category that has associated types. "
                    "Delete or reassign the types first."
                )

    class Input(OpenIMISMutation.Input):
        ids = graphene.List(graphene.UUID)


# ── GrievanceType mutations ───────────────────────────────────────────────────

class GrievanceTypeInputType(OpenIMISMutation.Input):
    id = graphene.String(required=False)
    code = graphene.String(required=False)
    name = graphene.String(required=True)
    is_active = graphene.Boolean(required=False, default_value=True)
    category_id = graphene.String(required=False)


class CreateGrievanceTypeMutation(BaseHistoryModelCreateMutationMixin, BaseMutation):
    _mutation_class = "CreateGrievanceTypeMutation"
    _mutation_module = "grievance_social_protection"
    _model = GrievanceType

    @classmethod
    def _validate_mutation(cls, user, **data):
        super()._validate_mutation(user, **data)
        _require_permission(user, "gql_mutation_create_tickets_perms")

    @classmethod
    def _mutate(cls, user, **data):
        data.pop("client_mutation_id", None)
        data.pop("client_mutation_label", None)
        service = GrievanceTypeService(user)
        response = service.create(data)
        if not response["success"]:
            return response
        return None

    class Input(GrievanceTypeInputType):
        pass


class UpdateGrievanceTypeMutation(BaseHistoryModelUpdateMutationMixin, BaseMutation):
    _mutation_class = "UpdateGrievanceTypeMutation"
    _mutation_module = "grievance_social_protection"
    _model = GrievanceType

    @classmethod
    def _validate_mutation(cls, user, **data):
        super()._validate_mutation(user, **data)
        _require_permission(user, "gql_mutation_update_tickets_perms")

    @classmethod
    def _mutate(cls, user, **data):
        data.pop("client_mutation_id", None)
        data.pop("client_mutation_label", None)
        service = GrievanceTypeService(user)
        response = service.update(data)
        if not response["success"]:
            return response
        return None

    class Input(GrievanceTypeInputType):
        id = graphene.String(required=True)


class DeleteGrievanceTypeMutation(BaseHistoryModelDeleteMutationMixin, BaseMutation):
    _mutation_class = "DeleteGrievanceTypeMutation"
    _mutation_module = "grievance_social_protection"
    _model = GrievanceType

    @classmethod
    def _validate_mutation(cls, user, **data):
        super()._validate_mutation(user, **data)
        _require_permission(user, "gql_mutation_delete_tickets_perms")

    class Input(OpenIMISMutation.Input):
        ids = graphene.List(graphene.UUID)


# ── GrievanceChannel mutations ────────────────────────────────────────────────

class GrievanceChannelInputType(OpenIMISMutation.Input):
    id = graphene.String(required=False)
    code = graphene.String(required=False)
    name = graphene.String(required=True)
    is_active = graphene.Boolean(required=False, default_value=True)


class CreateGrievanceChannelMutation(BaseHistoryModelCreateMutationMixin, BaseMutation):
    _mutation_class = "CreateGrievanceChannelMutation"
    _mutation_module = "grievance_social_protection"
    _model = GrievanceChannel

    @classmethod
    def _validate_mutation(cls, user, **data):
        super()._validate_mutation(user, **data)
        _require_permission(user, "gql_mutation_create_tickets_perms")

    @classmethod
    def _mutate(cls, user, **data):
        data.pop("client_mutation_id", None)
        data.pop("client_mutation_label", None)
        service = GrievanceChannelService(user)
        response = service.create(data)
        if not response["success"]:
            return response
        return None

    class Input(GrievanceChannelInputType):
        pass


class UpdateGrievanceChannelMutation(BaseHistoryModelUpdateMutationMixin, BaseMutation):
    _mutation_class = "UpdateGrievanceChannelMutation"
    _mutation_module = "grievance_social_protection"
    _model = GrievanceChannel

    @classmethod
    def _validate_mutation(cls, user, **data):
        super()._validate_mutation(user, **data)
        _require_permission(user, "gql_mutation_update_tickets_perms")

    @classmethod
    def _mutate(cls, user, **data):
        data.pop("client_mutation_id", None)
        data.pop("client_mutation_label", None)
        service = GrievanceChannelService(user)
        response = service.update(data)
        if not response["success"]:
            return response
        return None

    class Input(GrievanceChannelInputType):
        id = graphene.String(required=True)


class DeleteGrievanceChannelMutation(BaseHistoryModelDeleteMutationMixin, BaseMutation):
    _mutation_class = "DeleteGrievanceChannelMutation"
    _mutation_module = "grievance_social_protection"
    _model = GrievanceChannel

    @classmethod
    def _validate_mutation(cls, user, **data):
        super()._validate_mutation(user, **data)
        _require_permission(user, "gql_mutation_delete_tickets_perms")

    class Input(OpenIMISMutation.Input):
        ids = graphene.List(graphene.UUID)


# class CreateTicketAttachmentMutation(OpenIMISMutation):
#     _mutation_module = "grievance_social_protection"
#     _mutation_class = "CreateTicketAttachmentMutation"
#
#     class Input(AttachmentInputType):
#         pass
#
#     @classmethod
#     def async_mutate(cls, user, **data):
#         ticket = None
#         try:
#             if user.is_anonymous or not user.has_perms(TicketConfig.gql_mutation_update_tickets_perms):
#                 raise PermissionDenied(_("unauthorized"))
#             if "client_mutation_id" in data:
#                 data.pop('client_mutation_id')
#             if "client_mutation_label" in data:
#                 data.pop('client_mutation_label')
#             ticket_uuid = data.pop('ticket_uuid')
#             queryset = Ticket.objects.filter(*filter_validity())
#             ticket = queryset.filter(uuid=ticket_uuid).first()
#             if not ticket:
#                 raise PermissionDenied(_("unathorized"))
#             create_attachment(ticket.id, data)
#             return None
#         except Exception as exc:
#             return [{
#                 'message': _("ticket.mutation.failed_to_attach_document"),
#                 'detail': str(exc)}]


# class UpdateTicketAttachmentMutation(OpenIMISMutation):
#     _mutation_module = "grievance_social_protection"
#     _mutation_class = "UpdateTicketAttachmentMutation"
#
#     class Input(BaseAttachmentInputType):
#         pass
#
#     @classmethod
#     def async_mutate(cls, user, **data):
#
#         try:
#             if not user.has_perms(TicketConfig.gql_mutation_update_tickets_perms):
#                 raise PermissionDenied(_("unauthorized"))
#             # get ticketattachment uuid
#             ticketattachment_uuid = data.pop('uuid')
#             queryset = TicketAttachment.objects.filter(*filter_validity())
#             if ticketattachment_uuid:
#                 # fetch ticketattachment uuid
#                 ticketattachment = queryset.filter(uuid=ticketattachment_uuid).first()
#                 [setattr(ticketattachment, key, data[key]) for key in data]
#             else:
#                 # raise an error if uuid is not valid or does not exist
#                 raise PermissionDenied(_("unauthorized"))
#             # saves update dta
#             ticketattachment.save()
#             return None
#         except Exception as exc:
#             return [{
#
#                 'message': _("ticket.mutation.failed_to_attach_document"),
#                 'detail': str(exc)}]

# class BaseAttachment:
#     id = graphene.String(required=False, read_only=True)
#     uuid = graphene.String(required=False)
#     filename = graphene.String(required=False)
#     mime_type = graphene.String(required=False)
#     url = graphene.String(required=False)
#     date = graphene.Date(required=False)


# class BaseAttachmentInputType(BaseAttachment, OpenIMISMutation.Input):
#     """
#     Ticket attachment (without the document), used on its own
#     """
#     ticket_uuid = graphene.String(required=False)
#
#
# class Attachment(BaseAttachment):
#     document = graphene.String(required=False)


# class TicketAttachmentInputType(Attachment, InputObjectType):
#     """
#     Ticket attachment, used nested in claim object
#     """
#     pass


# class AttachmentInputType(Attachment, OpenIMISMutation.Input):
#     """
#     Ticket attachment, used on its own
#     """
#     ticket_uuid = graphene.String(required=False)


# def create_file(date, ticket_id, document):
#     date_iso = date.isoformat()
#     root = TicketConfig.tickets_attachments_root_path
#     file_dir = '%s/%s/%s/%s' % (
#         date_iso[0:4],
#         date_iso[5:7],
#         date_iso[8:10],
#         ticket_id
#     )
#
#     file_path = '%s/%s' % (file_dir, uuid.uuid4())
#     pathlib.Path('%s/%s' % (root, file_dir)).mkdir(parents=True, exist_ok=True)
#     f = open('%s/%s' % (root, file_path), "xb")
#     f.write(base64.b64decode(document))
#     f.close()
#     return file_path
#
#
# def create_attachment(ticket_id, data):
#     if "client_mutation_id" in data:
#         data.pop('client_mutation_id')
#     # Check if client_mutation_label is passed in data
#     if "client_mutation_label" in data:
#         data.pop('client_mutation_label')
#     data['ticket_id'] = ticket_id
#     now = timezone.now()
#     if TicketConfig.tickets_attachments_root_path:
#         data['url'] = create_file(now, ticket_id, data.pop('document'))
#     data['validity_from'] = now
#     attachment = TicketAttachment.objects.create(**data)
#     attachment.save()
#     return attachment
#
#
# def create_attachments(ticket_id, attachments):
#     for attachment in attachments:
#         create_attachment(ticket_id, attachment)
