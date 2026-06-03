import graphene
from graphene import ObjectType
from graphene_django import DjangoObjectType
from collections import defaultdict
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied
from django.apps import apps
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext as _
from core.gql_queries import UserGQLType
from .apps import TicketConfig
from .models import Ticket, Comment, TicketAttachment
from core import prefix_filterset, ExtendedConnection, filter_validity
from .util import model_obj_to_json
from .validations import user_associated_with_ticket
from .models import GrievanceType, GrievanceCategory, GrievanceChannel


REPORT_CATEGORY = "CATEGORY"
REPORT_PAA_WITHOUT_GRIEVANCES = "PAA_WITHOUT_GRIEVANCES"
REPORT_CHANNEL = "CHANNEL"
REPORT_RESOLUTION_STATUS = "RESOLUTION_STATUS"
REPORT_CLOSURE_TIMELINE = "CLOSURE_TIMELINE"
REPORT_CLOSURE_TIMELINE_BY_PAA = "CLOSURE_TIMELINE_BY_PAA"
REPORT_OVERDUE_BY_PAA = "OVERDUE_BY_PAA"

CLOSED_STATUSES = [
    Ticket.TicketStatus.CLOSED,
    Ticket.TicketStatus.RESOLVED,
]


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


class GrievanceReportRowGQLType(ObjectType):
    report = graphene.String()
    label = graphene.String()
    count = graphene.Int()
    category = graphene.String()
    channel = graphene.String()
    status = graphene.String()
    paa_id = graphene.String()
    paa_name = graphene.String()
    agent_id = graphene.String()
    agent_name = graphene.String()
    ticket_id = graphene.String()
    ticket_code = graphene.String()
    ticket_title = graphene.String()
    date_received = graphene.DateTime()
    date_closed = graphene.DateTime()
    due_date = graphene.Date()
    closure_days = graphene.Float()
    overdue_days = graphene.Int()


def _ticket_base_queryset(date_from=None, date_to=None, agent_id=None):
    queryset = Ticket.objects.filter(is_deleted=False).select_related(
        "attending_staff", "reporter_type"
    )
    if date_from:
        queryset = queryset.filter(date_created__date__gte=date_from)
    if date_to:
        queryset = queryset.filter(date_created__date__lte=date_to)
    if agent_id:
        queryset = queryset.filter(attending_staff_id=agent_id)
    return queryset


def _location_identifier(location):
    if not location:
        return None
    return str(getattr(location, "uuid", None) or getattr(location, "id", ""))


def _location_name(location):
    if not location:
        return None
    for attr in ("name", "code", "location_name"):
        value = getattr(location, attr, None)
        if value:
            return str(value)
    return str(location)


def _reporter_location(ticket):
    reporter = ticket.reporter
    if not reporter:
        return None
    candidates = [
        reporter,
        getattr(reporter, "individual", None),
        getattr(reporter, "group", None),
    ]
    for candidate in candidates:
        location = getattr(candidate, "location", None)
        if location:
            return location
    return None


def _ticket_paa(ticket):
    location = _reporter_location(ticket)
    if not location:
        return "unassigned", _("Unassigned")
    return _location_identifier(location), _location_name(location)


def _ticket_matches_paa(ticket, paa_id):
    if not paa_id:
        return True
    ticket_paa_id, _ = _ticket_paa(ticket)
    location = _reporter_location(ticket)
    possible_values = {str(ticket_paa_id)}
    if location:
        possible_values.add(str(getattr(location, "id", "")))
        possible_values.add(str(getattr(location, "uuid", "")))
    return str(paa_id) in possible_values


def _agent_name(ticket):
    user = ticket.attending_staff
    if not user:
        return None
    return getattr(user, "username", None) or str(user)


def _resolution_status(status):
    if status == Ticket.TicketStatus.RECEIVED:
        return _("Received")
    if status in CLOSED_STATUSES:
        return _("Closed")
    return _("Open")


def _resolution_comment(ticket):
    return (
        Comment.objects.filter(ticket=ticket, is_resolution=True, is_deleted=False)
        .order_by("date_created")
        .first()
    )


def _closure_days(ticket, resolution_comment):
    if not resolution_comment or not ticket.date_created:
        return None
    delta = resolution_comment.date_created - ticket.date_created
    return round(delta.total_seconds() / 86400, 2)


def _overdue_days(due_date, compared_to=None):
    if not due_date:
        return None
    compared_to = compared_to or timezone.localdate()
    if hasattr(compared_to, "date"):
        compared_to = compared_to.date()
    return max((compared_to - due_date).days, 0)


def _aggregate_rows(report, tickets, value_getter):
    counters = defaultdict(int)
    for ticket in tickets:
        key = value_getter(ticket) or _("Unspecified")
        counters[key] += 1
    return [
        GrievanceReportRowGQLType(report=report, label=key, count=count)
        for key, count in sorted(counters.items(), key=lambda item: str(item[0]))
    ]


def _category_rows(tickets):
    rows = _aggregate_rows(REPORT_CATEGORY, tickets, lambda ticket: ticket.category)
    for row in rows:
        row.category = row.label
    return rows


def _channel_rows(tickets):
    rows = _aggregate_rows(REPORT_CHANNEL, tickets, lambda ticket: ticket.channel)
    for row in rows:
        row.channel = row.label
    return rows


def _resolution_status_rows(tickets):
    rows = _aggregate_rows(
        REPORT_RESOLUTION_STATUS,
        tickets,
        lambda ticket: _resolution_status(ticket.status),
    )
    for row in rows:
        row.status = row.label
    return rows


def _closure_timeline_rows(report, tickets):
    rows = []
    for ticket in tickets:
        if ticket.status not in CLOSED_STATUSES:
            continue
        resolution_comment = _resolution_comment(ticket)
        paa_id, paa_name = _ticket_paa(ticket)
        rows.append(
            GrievanceReportRowGQLType(
                report=report,
                label=ticket.code or ticket.title,
                category=ticket.category,
                status=ticket.status,
                paa_id=paa_id,
                paa_name=paa_name,
                agent_id=str(ticket.attending_staff_id) if ticket.attending_staff_id else None,
                agent_name=_agent_name(ticket),
                ticket_id=str(ticket.id),
                ticket_code=ticket.code,
                ticket_title=ticket.title,
                date_received=ticket.date_created,
                date_closed=resolution_comment.date_created if resolution_comment else None,
                due_date=ticket.due_date,
                closure_days=_closure_days(ticket, resolution_comment),
                overdue_days=_overdue_days(
                    ticket.due_date,
                    resolution_comment.date_created if resolution_comment else None,
                ),
            )
        )
    return rows


def _overdue_by_paa_rows(tickets):
    today = timezone.localdate()
    counters = {}
    for ticket in tickets:
        if not ticket.due_date or ticket.due_date >= today or ticket.status in CLOSED_STATUSES:
            continue
        paa_id, paa_name = _ticket_paa(ticket)
        current = counters.setdefault(
            paa_id,
            {
                "name": paa_name,
                "count": 0,
                "max_overdue_days": 0,
            },
        )
        current["count"] += 1
        current["max_overdue_days"] = max(
            current["max_overdue_days"],
            _overdue_days(ticket.due_date, today) or 0,
        )
    return [
        GrievanceReportRowGQLType(
            report=REPORT_OVERDUE_BY_PAA,
            label=data["name"],
            paa_id=paa_id,
            paa_name=data["name"],
            count=data["count"],
            overdue_days=data["max_overdue_days"],
        )
        for paa_id, data in sorted(counters.items(), key=lambda item: item[1]["name"])
    ]


def _paa_candidates(user, paa_id=None):
    try:
        Location = apps.get_model("location", "Location")
    except LookupError:
        return []

    queryset = Location.objects.all()
    if hasattr(Location, "get_queryset"):
        queryset = Location.get_queryset(queryset, user)
    if hasattr(Location, "filter_queryset"):
        queryset = Location.filter_queryset(queryset)
    elif hasattr(Location, "is_deleted"):
        queryset = queryset.filter(is_deleted=False)

    if paa_id:
        identifier_filter = Q(id=paa_id)
        if any(field.name == "uuid" for field in Location._meta.fields):
            identifier_filter |= Q(uuid=paa_id)
        queryset = queryset.filter(identifier_filter)

    return list(queryset)


def _paa_without_grievance_rows(tickets, user, paa_id=None):
    ticket_paa_ids = {_ticket_paa(ticket)[0] for ticket in tickets}
    rows = []
    for location in _paa_candidates(user, paa_id):
        location_id = _location_identifier(location)
        if location_id in ticket_paa_ids:
            continue
        rows.append(
            GrievanceReportRowGQLType(
                report=REPORT_PAA_WITHOUT_GRIEVANCES,
                label=_location_name(location),
                count=0,
                paa_id=location_id,
                paa_name=_location_name(location),
            )
        )
    return rows


def resolve_grievance_report_rows(
    info,
    report,
    date_from=None,
    date_to=None,
    agent_id=None,
    paa_id=None,
):
    check_ticket_perms(info)
    tickets = list(_ticket_base_queryset(date_from, date_to, agent_id))
    if paa_id and report != REPORT_PAA_WITHOUT_GRIEVANCES:
        tickets = [ticket for ticket in tickets if _ticket_matches_paa(ticket, paa_id)]

    if report == REPORT_CATEGORY:
        return _category_rows(tickets)
    if report == REPORT_PAA_WITHOUT_GRIEVANCES:
        return _paa_without_grievance_rows(tickets, info.context.user, paa_id)
    if report == REPORT_CHANNEL:
        return _channel_rows(tickets)
    if report == REPORT_RESOLUTION_STATUS:
        return _resolution_status_rows(tickets)
    if report == REPORT_CLOSURE_TIMELINE:
        return _closure_timeline_rows(report, tickets)
    if report == REPORT_CLOSURE_TIMELINE_BY_PAA:
        return _closure_timeline_rows(report, tickets)
    if report == REPORT_OVERDUE_BY_PAA:
        return _overdue_by_paa_rows(tickets)

    return []


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
        fields = ("id", "code", "name", "timeline", "is_active")
        filter_fields = {
            "id": ["exact"],
            "code": ["exact", "icontains"],
            "name": ["exact", "icontains"],
            "timeline": ["exact"],
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
