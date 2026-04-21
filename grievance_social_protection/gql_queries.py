import graphene
from graphene import ObjectType
from graphene_django import DjangoObjectType
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied
from django.utils.translation import gettext as _
from core.gql_queries import UserGQLType
from .apps import TicketConfig
from .models import Ticket, Comment, TicketAttachment
from core import prefix_filterset, ExtendedConnection, filter_validity
from .util import model_obj_to_json
from .validations import user_associated_with_ticket
from .models import GrievanceType, GrievanceCategory, GrievanceChannel


def check_ticket_perms(info):
    if not info.context.user.has_perms(TicketConfig.gql_query_tickets_perms):
        raise PermissionDenied(_("unauthorized"))


def check_comment_perms(info):
    user = info.context.user
    if not (
        user_associated_with_ticket(user)
        or user.has_perms(TicketConfig.gql_query_comments_perms)
    ):
        raise PermissionDenied(_("Unauthorized"))


class TicketGQLType(DjangoObjectType):
    # TODO on resolve check filters and remove anonymized so user can't fetch ticket using last_name if not visible
    client_mutation_id = graphene.String()
    reporter = graphene.JSONString()
    reporter_type = graphene.Int()
    reporter_type_name = graphene.String()
    is_history = graphene.Boolean()

    reporter_first_name = graphene.String()
    reporter_last_name = graphene.String()
    reporter_dob = graphene.String()

    @staticmethod
    def resolve_reporter_type(root, info):
        check_ticket_perms(info)
        return root.reporter_type.id if root.reporter_type else None

    @staticmethod
    def resolve_reporter_type_name(root, info):
        check_ticket_perms(info)
        return root.reporter_type.name if root.reporter_type else None

    @staticmethod
    def resolve_reporter(root, info):
        check_ticket_perms(info)
        return model_obj_to_json(root.reporter) if root.reporter else None

    @staticmethod
    def resolve_is_history(root, info):
        check_ticket_perms(info)
        return not root.version == Ticket.objects.get(id=root.id).version

    @staticmethod
    def resolve_reporter_first_name(root, info):
        check_ticket_perms(info)
        if root.reporter_type:
            content_type = ContentType.objects.get_for_model(
                root.reporter_type.model_class()
            )
            if content_type:
                model_object = content_type.get_object_for_this_type(
                    pk=root.reporter_id
                )
                if model_object:
                    if root.reporter_type.name == "individual":
                        return model_object.first_name
                    elif root.reporter_type.name == "beneficiary":
                        return model_object.individual.first_name
                    elif root.reporter_type.name == "user":
                        return None
        return None

    @staticmethod
    def resolve_reporter_last_name(root, info):
        check_ticket_perms(info)
        if root.reporter_type:
            content_type = ContentType.objects.get_for_model(
                root.reporter_type.model_class()
            )
            if content_type:
                model_object = content_type.get_object_for_this_type(
                    pk=root.reporter_id
                )
                if model_object:
                    if root.reporter_type.name == "individual":
                        return model_object.last_name
                    elif root.reporter_type.name == "beneficiary":
                        return model_object.individual.last_name
                    elif root.reporter_type.name == "user":
                        return None
        return None

    @staticmethod
    def resolve_reporter_dob(root, info):
        check_ticket_perms(info)
        if root.reporter_type:
            content_type = ContentType.objects.get_for_model(
                root.reporter_type.model_class()
            )
            if content_type:
                model_object = content_type.get_object_for_this_type(
                    pk=root.reporter_id
                )
                if model_object:
                    if root.reporter_type.name == "individual":
                        return model_object.dob
                    elif root.reporter_type.name == "beneficiary":
                        return model_object.individual.dob
                    elif root.reporter_type.name == "user":
                        return None
        return None

    class Meta:
        model = Ticket
        interfaces = (graphene.relay.Node,)
        filter_fields = {
            "id": ["exact", "isnull"],
            "version": ["exact"],
            "key": ["exact", "istartswith", "icontains", "iexact"],
            "code": ["exact", "istartswith", "icontains", "iexact"],
            "title": ["exact", "istartswith", "icontains", "iexact"],
            "description": ["exact", "istartswith", "icontains", "iexact"],
            "status": ["exact", "istartswith", "icontains", "iexact"],
            "priority": ["exact", "istartswith", "icontains", "iexact"],
            "category": ["exact", "istartswith", "icontains", "iexact"],
            "flags": ["exact", "istartswith", "icontains", "iexact"],
            "channel": ["exact", "istartswith", "icontains", "iexact"],
            "resolution": ["exact", "istartswith", "icontains", "iexact"],
            "reporter_id": ["exact"],
            "due_date": ["exact", "istartswith", "icontains", "iexact"],
            "date_of_incident": ["exact", "istartswith", "icontains", "iexact"],
            "date_created": ["exact", "istartswith", "icontains", "iexact"],
            **prefix_filterset("attending_staff__", UserGQLType._meta.filter_fields),
        }

        connection_class = ExtendedConnection

    def resolve_client_mutation_id(self, info):
        ticket_mutation = (
            self.mutations.select_related("mutation").filter(mutation__status=0).first()
        )
        return ticket_mutation.mutation.client_mutation_id if ticket_mutation else None


class CommentGQLType(DjangoObjectType):
    commenter = graphene.JSONString()
    commenter_type = graphene.Int()
    commenter_type_name = graphene.String()

    commenter_first_name = graphene.String()
    commenter_last_name = graphene.String()
    commenter_dob = graphene.String()

    @staticmethod
    def resolve_commenter_type(root, info):
        check_comment_perms(info)
        return root.commenter_type.id if root.commenter_type else None

    @staticmethod
    def resolve_commenter_type_name(root, info):
        check_comment_perms(info)
        return root.commenter_type.name if root.commenter_type else None

    @staticmethod
    def resolve_commenter(root, info):
        check_comment_perms(info)
        return model_obj_to_json(root.commenter) if root.commenter else None

    @staticmethod
    def resolve_commenter_first_name(root, info):
        check_comment_perms(info)
        if root.commenter_type:
            content_type = ContentType.objects.get_for_model(
                root.commenter_type.model_class()
            )
            if content_type:
                model_object = content_type.get_object_for_this_type(
                    pk=root.commenter_id
                )
                if model_object:
                    if root.commenter_type.name == "individual":
                        return model_object.first_name
                    elif root.commenter_type.name == "beneficiary":
                        return model_object.individual.first_name
                    elif root.commenter_type.name == "user":
                        return None
        return None

    @staticmethod
    def resolve_commenter_last_name(root, info):
        check_comment_perms(info)
        if root.commenter_type:
            content_type = ContentType.objects.get_for_model(
                root.commenter_type.model_class()
            )
            if content_type:
                model_object = content_type.get_object_for_this_type(
                    pk=root.commenter_id
                )
                if model_object:
                    if root.commenter_type.name == "individual":
                        return model_object.last_name
                    elif root.commenter_type.name == "beneficiary":
                        return model_object.individual.last_name
                    elif root.commenter_type.name == "user":
                        return None
        return None

    @staticmethod
    def resolve_commenter_dob(root, info):
        check_comment_perms(info)
        if root.commenter_type:
            content_type = ContentType.objects.get_for_model(
                root.commenter_type.model_class()
            )
            if content_type:
                model_object = content_type.get_object_for_this_type(
                    pk=root.commenter_id
                )
                if model_object:
                    if root.commenter_type.name == "individual":
                        return model_object.dob
                    elif root.commenter_type.name == "beneficiary":
                        return model_object.individual.dob
                    elif root.commenter_type.name == "user":
                        return None
        return None

    class Meta:
        model = Comment
        interfaces = (graphene.relay.Node,)
        filter_fields = {
            "id": ["exact", "isnull"],
            "comment": ["exact", "istartswith", "icontains", "iexact"],
            "date_created": ["exact", "istartswith", "icontains", "iexact"],
            "is_resolution": ["exact"],
            **prefix_filterset("ticket__", TicketGQLType._meta.filter_fields),
        }

        connection_class = ExtendedConnection


class TicketAttachmentGQLType(DjangoObjectType):
    class Meta:
        model = TicketAttachment
        interfaces = (graphene.relay.Node,)
        filter_fields = {
            "id": ["exact"],
            "filename": ["exact", "icontains"],
            "mime_type": ["exact", "icontains"],
            "url": ["exact", "icontains"],
            **prefix_filterset("ticket__", TicketGQLType._meta.filter_fields),
        }
        connection_class = ExtendedConnection

    @classmethod
    def get_queryset(cls, queryset, info):
        queryset = queryset.filter(*filter_validity())
        return queryset


class AttendingStaffRoleGQLType(ObjectType):
    category = graphene.String()
    role_ids = graphene.List(graphene.String)


class ResolutionTimesByCategoryGQLType(ObjectType):
    category = graphene.String()
    resolution_time = graphene.String()


class GrievanceTypeConfigurationGQLType(ObjectType):
    grievance_types = graphene.List(graphene.String)
    grievance_flags = graphene.List(graphene.String)
    grievance_channels = graphene.List(graphene.String)
    grievance_category_staff_roles = graphene.List(AttendingStaffRoleGQLType)
    grievance_default_resolutions_by_category = graphene.List(
        ResolutionTimesByCategoryGQLType
    )

    def resolve_grievance_types(self, info):
        return TicketConfig.grievance_types

    def resolve_grievance_flags(self, info):
        return TicketConfig.grievance_flags

    def resolve_grievance_channels(self, info):
        channels = list(
            GrievanceChannel.objects.filter(is_deleted=False, is_active=True)
            .order_by("name")
            .values_list("name", flat=True)
        )
        return channels or TicketConfig.grievance_channels

    def resolve_grievance_category_staff_roles(self, info):
        category_staff_role_list = []
        for (
            category_key,
            role_ids,
        ) in TicketConfig.default_attending_staff_role_ids.items():
            category_staff_role = AttendingStaffRoleGQLType(
                category=category_key, role_ids=role_ids
            )
            category_staff_role_list.append(category_staff_role)

        return category_staff_role_list

    def resolve_grievance_default_resolutions_by_category(self, info):
        category_resolution_time_list = []
        for category_key, resolution_time in TicketConfig.default_resolution.items():
            category_resolution_time = ResolutionTimesByCategoryGQLType(
                category=category_key, resolution_time=resolution_time
            )
            category_resolution_time_list.append(category_resolution_time)

        return category_resolution_time_list


class GrievanceCategoryGQL(DjangoObjectType):
    types = graphene.List(lambda: GrievanceTypeGQL)

    class Meta:
        model = GrievanceCategory
        interfaces = (graphene.relay.Node,)
        fields = ("id", "code", "name", "is_active")
        filter_fields = {
            "id": ["exact"],
            "code": ["exact", "icontains"],
            "name": ["exact", "icontains"],
            "is_active": ["exact"],
        }
        connection_class = ExtendedConnection

    def resolve_types(self, info):
        return self.types.filter(is_active=True)


class GrievanceTypeGQL(DjangoObjectType):
    category_name = graphene.String()

    class Meta:
        model = GrievanceType
        interfaces = (graphene.relay.Node,)
        fields = ("id", "code", "name", "is_active", "category")
        filter_fields = {
            "id": ["exact"],
            "code": ["exact", "icontains"],
            "name": ["exact", "icontains"],
            "is_active": ["exact"],
            "category__id": ["exact"],
            "category__name": ["exact", "icontains"],
        }
        connection_class = ExtendedConnection

    def resolve_category_name(self, info):
        return self.category.name if self.category else None


class GrievanceChannelGQL(DjangoObjectType):
    class Meta:
        model = GrievanceChannel
        interfaces = (graphene.relay.Node,)
        fields = ("id", "code", "name", "is_active")
        filter_fields = {
            "id": ["exact"],
            "code": ["exact", "icontains"],
            "name": ["exact", "icontains"],
            "is_active": ["exact"],
        }
        connection_class = ExtendedConnection
