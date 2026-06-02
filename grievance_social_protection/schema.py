import graphene
from django.contrib.auth.models import AnonymousUser
from core.schema import OrderedDjangoFilterConnectionField
from core.schema import signal_mutation_module_validate
from django.db.models import Q
import graphene_django_optimizer as gql_optimizer
from core.utils import append_validity_filter
from .apps import MODULE_NAME
from .gql_queries import *
from .gql_mutations import *
from graphql_relay import from_global_id
from django.utils.translation import gettext_lazy as _
from .gql_queries import GrievanceTypeGQL, GrievanceCategoryGQL, GrievanceChannelGQL
from .models import TicketAttachment


class Query(graphene.ObjectType):
    tickets = OrderedDjangoFilterConnectionField(
        TicketGQLType,
        orderBy=graphene.List(of_type=graphene.String),
        show_history=graphene.Boolean(),
        client_mutation_id=graphene.String(),
        ticket_version=graphene.Int(),
    )

    ticketsStr = OrderedDjangoFilterConnectionField(
        TicketGQLType,
        str=graphene.String(),
    )
    ticket_attachments = OrderedDjangoFilterConnectionField(
        TicketAttachmentGQLType,
        orderBy=graphene.List(of_type=graphene.String),
    )

    ticket_details = OrderedDjangoFilterConnectionField(
        TicketGQLType,
        # showHistory=graphene.Boolean(),
        orderBy=graphene.List(of_type=graphene.String),
    )

    grievance_config = graphene.Field(GrievanceTypeConfigurationGQLType)

    comments = OrderedDjangoFilterConnectionField(
        CommentGQLType,
        orderBy=graphene.List(of_type=graphene.String),
    )

    grievance_types = OrderedDjangoFilterConnectionField(
        GrievanceTypeGQL,
        orderBy=graphene.List(of_type=graphene.String),
        category_id=graphene.ID(),
        description="Query all grievance types, optionally filter by category or active status",
    )

    grievance_categories = OrderedDjangoFilterConnectionField(
        GrievanceCategoryGQL,
        orderBy=graphene.List(of_type=graphene.String),
        description="Query all grievance categories, optionally filter by active status",
    )

    grievance_channels = OrderedDjangoFilterConnectionField(
        GrievanceChannelGQL,
        orderBy=graphene.List(of_type=graphene.String),
        description="Query all grievance channels, optionally filter by active status",
    )

    grievance_reports = graphene.List(
        GrievanceReportRowGQLType,
        report=graphene.String(required=True),
        date_from=graphene.Date(),
        date_to=graphene.Date(),
        agent_id=graphene.String(),
        paa_id=graphene.String(),
        description="Aggregated grievance reports with optional date, agent, and PAA filters",
    )

    def resolve_comments(self, info, **kwargs):
        user = info.context.user

        if not (
            user_associated_with_ticket(user)
            or user.has_perms(TicketConfig.gql_query_comments_perms)
        ):
            raise PermissionDenied(_("Unauthorized"))

        return gql_optimizer.query(Comment.objects.all(), info)

    def resolve_ticket_details(self, info, **kwargs):
        if not info.context.user.has_perms(TicketConfig.gql_query_tickets_perms):
            raise PermissionDenied(_("unauthorized"))
        return gql_optimizer.query(
            Ticket.objects.filter(*append_validity_filter(**kwargs))
            .all()
            .order_by(
                "ticket_title",
            ),
            info,
        )

    def resolve_tickets(self, info, **kwargs):
        """
        Extra steps to perform when Scheme is queried
        """
        # Check if user has permission
        if not info.context.user.has_perms(TicketConfig.gql_query_tickets_perms):
            raise PermissionDenied(_("unauthorized"))
        filters = []
        model = Ticket

        client_mutation_id = kwargs.get("client_mutation_id", None)
        if client_mutation_id:
            filters.append(
                Q(mutations__mutation__client_mutation_id=client_mutation_id)
            )

        # Used to specify if user want to see all records including invalid records as history
        show_history = kwargs.get("show_history", False)
        ticket_version = kwargs.get("ticket_version", False)
        if show_history or ticket_version:
            if ticket_version:
                filters.append(Q(version=ticket_version))
            query = model.history.filter(*filters).all().as_instances()
        else:
            query = model.objects.filter(*filters, is_deleted=False).all()

        return gql_optimizer.query(query, info)

    def resolve_ticketsStr(self, info, **kwargs):
        """
        Extra steps to perform when Scheme is queried
        """
        # Check if user has permission
        if not info.context.user.has_perms(TicketConfig.gql_query_tickets_perms):
            raise PermissionDenied(_("unauthorized"))
        filters = []

        # Used to specify if user want to see all records including invalid records as history
        show_history = kwargs.get("show_history", False)
        if not show_history:
            filters += append_validity_filter(**kwargs)

        client_mutation_id = kwargs.get("client_mutation_id", None)
        if client_mutation_id:
            filters.append(
                Q(mutations__mutation__client_mutation_id=client_mutation_id)
            )

        # str = kwargs.get('str')
        # if str is not None:
        #     filters += [Q(code__icontains=str) | Q(name__icontains=str)]

        return gql_optimizer.query(Ticket.objects.filter(*filters).all(), info)

    # def resolve_claim_attachments(self, info, **kwargs):
    #     if not info.context.user.has_perms(TicketConfig.gql_query_tickets_perms):
    #         raise PermissionDenied(_("unauthorized"))

    def resolve_grievance_config(self, info, **kwargs):
        user = info.context.user
        if type(user) is AnonymousUser:
            raise PermissionDenied(_("unauthorized"))
        if not info.context.user.has_perms(TicketConfig.gql_query_tickets_perms):
            raise PermissionDenied(_("unauthorized"))
        return GrievanceTypeConfigurationGQLType()

    def resolve_grievance_types(self, info, category_id=None, is_active=None, **kwargs):
        user = info.context.user
        if not user.has_perms(TicketConfig.gql_query_tickets_perms):
            raise PermissionDenied(_("unauthorized"))
        qs = GrievanceType.objects.select_related("category").all()
        if category_id:
            _type, uuid = from_global_id(category_id)
            qs = qs.filter(category_id=uuid)
        if is_active is not None:
            qs = qs.filter(is_active=is_active)
        return qs

    def resolve_grievance_categories(self, info, is_active=None, **kwargs):
        user = info.context.user
        if not user.has_perms(TicketConfig.gql_query_tickets_perms):
            raise PermissionDenied(_("unauthorized"))
        qs = GrievanceCategory.objects.all()
        if is_active is not None:
            qs = qs.filter(is_active=is_active)
        return qs

    def resolve_ticket_attachments(self, info, **kwargs):
        if not info.context.user.has_perms(TicketConfig.gql_query_tickets_perms):
            raise PermissionDenied(_("unauthorized"))
        from core.utils import filter_validity
        qs = TicketAttachment.objects.filter(*filter_validity())
        return gql_optimizer.query(qs, info)

    def resolve_grievance_channels(self, info, is_active=None, **kwargs):
        user = info.context.user
        if not user.has_perms(TicketConfig.gql_query_tickets_perms):
            raise PermissionDenied(_("unauthorized"))
        qs = GrievanceChannel.objects.all()
        if is_active is not None:
            qs = qs.filter(is_active=is_active)
        return qs

    def resolve_grievance_reports(self, info, **kwargs):
        return resolve_grievance_report_rows(info, **kwargs)


class Mutation(graphene.ObjectType):
    create_Ticket = CreateTicketMutation.Field()
    update_Ticket = UpdateTicketMutation.Field()
    delete_Ticket = DeleteTicketMutation.Field()

    create_comment = CreateCommentMutation.Field()

    resolve_grievance_by_comment = ResolveGrievanceByCommentMutation.Field()
    close_ticket = CloseTicketMutation.Field()
    reopen_ticket = ReopenTicketMutation.Field()

    create_grievance_category = CreateGrievanceCategoryMutation.Field()
    update_grievance_category = UpdateGrievanceCategoryMutation.Field()
    delete_grievance_category = DeleteGrievanceCategoryMutation.Field()

    create_grievance_type = CreateGrievanceTypeMutation.Field()
    update_grievance_type = UpdateGrievanceTypeMutation.Field()
    delete_grievance_type = DeleteGrievanceTypeMutation.Field()

    create_grievance_channel = CreateGrievanceChannelMutation.Field()
    update_grievance_channel = UpdateGrievanceChannelMutation.Field()
    delete_grievance_channel = DeleteGrievanceChannelMutation.Field()

    # create_ticket_attachment = CreateTicketAttachmentMutation.Field()
    # update_ticket_attachment = UpdateTicketAttachmentMutation.Field()


def on_bank_mutation(kwargs, k="uuid"):
    """
    This method is called on signal binding for scheme mutation
    """

    # get uuid from data
    ticket_uuid = kwargs["data"].get("uuid", None)
    if not ticket_uuid:
        return []
    # fetch the scheme object by uuid
    impacted_ticket = Ticket.objects.get(Q(uuid=ticket_uuid))
    # Create a mutation object
    TicketMutation.objects.create(
        Bank=impacted_ticket, mutation_id=kwargs["mutation_log_id"]
    )
    return []


def on_ticket_mutation(**kwargs):
    uuids = kwargs["data"].get("uuids", [])
    if not uuids:
        uuid = kwargs["data"].get("claim_uuid", None)
        uuids = [uuid] if uuid else []
    if not uuids:
        return []
    impacted_tickets = Ticket.objects.filter(uuid__in=uuids).all()
    for ticket in impacted_tickets:
        TicketMutation.objects.create(
            Ticket=ticket, mutation_id=kwargs["mutation_log_id"]
        )
    return []


def bind_signals():
    signal_mutation_module_validate[MODULE_NAME].connect(on_ticket_mutation)
