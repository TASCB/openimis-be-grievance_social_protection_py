import graphene
from graphene import ObjectType
from graphene_django import DjangoObjectType
from collections import defaultdict
from datetime import timedelta
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied
from django.apps import apps
from django.db.models import (
    Case,
    DateField,
    DateTimeField,
    DurationField,
    ExpressionWrapper,
    F,
    Func,
    IntegerField,
    OuterRef,
    Q,
    Subquery,
    Value,
    When,
)
from django.db.models.functions import Cast, Coalesce
from django.utils import timezone
from django.utils.translation import gettext as _
from core.gql_queries import UserGQLType
from location.gql_queries import LocationGQLType
from .apps import TicketConfig
from .models import Ticket, Comment, TicketAttachment
from core import prefix_filterset, ExtendedConnection, filter_validity
from .util import model_obj_to_json
from .models import GrievanceType, GrievanceCategory, GrievanceChannel
from .location_scope import (
    get_location_scope,
    location_chain,
    ticket_queryset_for_user,
)


REPORT_CATEGORY = "CATEGORY"
REPORT_PAA_WITHOUT_GRIEVANCES = "PAA_WITHOUT_GRIEVANCES"
REPORT_CHANNEL = "CHANNEL"
REPORT_RESOLUTION_STATUS = "RESOLUTION_STATUS"
REPORT_CLOSURE_TIMELINE = "CLOSURE_TIMELINE"
REPORT_CLOSURE_TIMELINE_BY_PAA = "CLOSURE_TIMELINE_BY_PAA"
REPORT_OVERDUE_BY_PAA = "OVERDUE_BY_PAA"
CATEGORY_REPORT_LAST_CATEGORY = "Maswali na Maoni"

PAA_GRIEVANCE_FILTER_WITHOUT = "WITHOUT_GRIEVANCE"
PAA_GRIEVANCE_FILTER_WITH = "WITH_GRIEVANCE"
PAA_GRIEVANCE_FILTER_LESS_THAN = "LESS_THAN"
PAA_GRIEVANCE_FILTER_MORE_THAN = "MORE_THAN"
PAA_GRIEVANCE_FILTERS = {
    PAA_GRIEVANCE_FILTER_WITHOUT,
    PAA_GRIEVANCE_FILTER_WITH,
    PAA_GRIEVANCE_FILTER_LESS_THAN,
    PAA_GRIEVANCE_FILTER_MORE_THAN,
}

CLOSED_STATUSES = [
    Ticket.TicketStatus.CLOSED,
    Ticket.TicketStatus.RESOLVED,
]
OPEN_STATUSES = [
    Ticket.TicketStatus.RECEIVED,
    Ticket.TicketStatus.OPEN,
    Ticket.TicketStatus.IN_PROGRESS,
]

TIMELINE_STATUS_OVERDUE = "OVERDUE"
TIMELINE_STATUS_ON_TIME = "ON_TIME"
TIMELINE_STATUS_RESOLVED_LATE = "RESOLVED_LATE"
TIMELINE_STATUS_NOT_APPLICABLE = "N_A"


class AddDays(Func):
    arity = 2
    output_field = DateField()

    def as_sql(self, compiler, connection, **extra_context):
        date_sql, date_params = compiler.compile(self.source_expressions[0])
        days_sql, days_params = compiler.compile(self.source_expressions[1])
        return f"({date_sql} + {days_sql})", (*date_params, *days_params)

    def as_microsoft(self, compiler, connection, **extra_context):
        date_sql, date_params = compiler.compile(self.source_expressions[0])
        days_sql, days_params = compiler.compile(self.source_expressions[1])
        return (
            f"DATEADD(day, {days_sql}, {date_sql})",
            (*days_params, *date_params),
        )

    def as_mysql(self, compiler, connection, **extra_context):
        date_sql, date_params = compiler.compile(self.source_expressions[0])
        days_sql, days_params = compiler.compile(self.source_expressions[1])
        return (
            f"DATE_ADD({date_sql}, INTERVAL {days_sql} DAY)",
            (*date_params, *days_params),
        )

    def as_sqlite(self, compiler, connection, **extra_context):
        date_sql, date_params = compiler.compile(self.source_expressions[0])
        days_sql, days_params = compiler.compile(self.source_expressions[1])
        return (
            f"DATE({date_sql}, printf('+%d days', {days_sql}))",
            (*date_params, *days_params),
        )


def check_ticket_perms(info):
    if not info.context.user.has_perms(
        TicketConfig.permissions("gql_query_tickets_perms")
    ):
        raise PermissionDenied(_("unauthorized"))


def check_comment_perms(info):
    if not info.context.user.has_perms(
        TicketConfig.permissions("gql_query_comments_perms")
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
    overdue = graphene.Boolean()
    timeline_status = graphene.String()
    time_taken_seconds = graphene.Float()


class GrievanceLocationScopeGQLType(ObjectType):
    restricted = graphene.Boolean(required=True)
    required = graphene.Boolean(required=True)
    assigned_location = graphene.Field(LocationGQLType)
    assigned_locations = graphene.List(LocationGQLType, required=True)
    region = graphene.Field(LocationGQLType)
    district = graphene.Field(LocationGQLType)
    ward = graphene.Field(LocationGQLType)
    village = graphene.Field(LocationGQLType)


def build_grievance_location_scope(user):
    Location = apps.get_model("location", "Location")
    scope = get_location_scope(user)
    assigned_locations = list(
        Location.filter_queryset(
            Location.objects.filter(id__in=scope.direct_location_ids).select_related(
                "parent",
                "parent__parent",
                "parent__parent__parent",
            )
        ).order_by("type", "code")
    )
    assigned_location = assigned_locations[0] if len(assigned_locations) == 1 else None
    chain = location_chain(assigned_location) if assigned_location else {}
    return GrievanceLocationScopeGQLType(
        restricted=scope.restricted,
        required=scope.restricted,
        assigned_location=assigned_location,
        assigned_locations=assigned_locations,
        region=chain.get("R"),
        district=chain.get("D"),
        ward=chain.get("W"),
        village=chain.get("V"),
    )


def grievance_locations_for_user(user, location_type, parent_id=None, search=None):
    Location = apps.get_model("location", "Location")
    scope = get_location_scope(user)
    queryset = Location.filter_queryset(
        Location.objects.filter(type=location_type)
    )

    if scope.restricted:
        visible_ids = set(scope.allowed_location_ids)
        assigned_locations = Location.objects.filter(
            id__in=scope.direct_location_ids
        ).select_related("parent", "parent__parent", "parent__parent__parent")
        for assigned_location in assigned_locations:
            current = assigned_location
            while current is not None:
                visible_ids.add(current.id)
                current = current.parent
        queryset = queryset.filter(id__in=visible_ids)

    if parent_id is not None:
        queryset = queryset.filter(parent_id=parent_id)
    if search:
        queryset = queryset.filter(
            Q(name__icontains=search) | Q(code__icontains=search)
        )
    return queryset.order_by("name")[:100]


def annotate_ticket_metrics(queryset, now=None):
    now = now or timezone.now()
    today = _local_date(now)
    category_timeline = GrievanceCategory.objects.filter(
        name=OuterRef("category"),
        is_deleted=False,
        is_active=True,
        timeline__gt=0,
    ).values("timeline")[:1]
    resolution_closed_at = Comment.objects.filter(
        ticket_id=OuterRef("id"),
        is_resolution=True,
        is_deleted=False,
    ).order_by("-date_created").values("date_created")[:1]

    queryset = queryset.annotate(
        _timeline_days=Subquery(category_timeline, output_field=IntegerField()),
        _resolution_closed_at=Subquery(
            resolution_closed_at,
            output_field=DateTimeField(),
        ),
    )
    queryset = queryset.annotate(
        _expected_resolution_date=Coalesce(
            F("due_date"),
            Case(
                When(
                    _timeline_days__gt=0,
                    then=AddDays(
                        Cast(F("date_created"), output_field=DateField()),
                        F("_timeline_days"),
                    ),
                ),
                default=Value(None),
                output_field=DateField(),
            ),
        ),
        _closed_at=Case(
            When(
                status__in=CLOSED_STATUSES,
                then=Coalesce(F("_resolution_closed_at"), F("date_updated")),
            ),
            default=Value(None),
            output_field=DateTimeField(),
        ),
    )
    queryset = queryset.annotate(
        _time_taken_duration=ExpressionWrapper(
            Coalesce(
                F("_closed_at"),
                Value(now, output_field=DateTimeField()),
            )
            - F("date_created"),
            output_field=DurationField(),
        ),
        _overdue_sort=Case(
            When(
                _expected_resolution_date__lt=today,
                status__in=OPEN_STATUSES,
                then=Value(1),
            ),
            default=Value(0),
            output_field=IntegerField(),
        ),
    )
    return queryset


def _local_date(value):
    if not value:
        return None
    if hasattr(value, "date"):
        if timezone.is_aware(value):
            return timezone.localtime(value).date()
        return value.date()
    return value


def ticket_expected_resolution_date(ticket):
    annotated = getattr(ticket, "_expected_resolution_date", None)
    if annotated:
        return annotated
    if ticket.due_date:
        return ticket.due_date
    timeline = (
        GrievanceCategory.objects.filter(
            name=ticket.category,
            is_deleted=False,
            is_active=True,
            timeline__gt=0,
        )
        .values_list("timeline", flat=True)
        .first()
    )
    created_date = _local_date(ticket.date_created)
    if not timeline or not created_date:
        return None
    return created_date + timedelta(days=timeline)


def ticket_closed_at(ticket):
    if ticket.status not in CLOSED_STATUSES:
        return None
    annotated = getattr(ticket, "_closed_at", None)
    if annotated:
        return annotated
    resolution_comment = _resolution_comment(ticket)
    return resolution_comment.date_created if resolution_comment else ticket.date_updated


def ticket_time_taken_seconds(ticket, now=None):
    annotated = getattr(ticket, "_time_taken_duration", None)
    if annotated is not None:
        return max(annotated.total_seconds(), 0)
    end = ticket_closed_at(ticket) or now or timezone.now()
    if not ticket.date_created or not end:
        return None
    return max((end - ticket.date_created).total_seconds(), 0)


def ticket_timeline_status(ticket, today=None):
    expected_date = ticket_expected_resolution_date(ticket)
    if not expected_date:
        return TIMELINE_STATUS_NOT_APPLICABLE
    today = today or _current_date()
    closed_at = ticket_closed_at(ticket)
    if closed_at and _local_date(closed_at) > expected_date:
        return TIMELINE_STATUS_RESOLVED_LATE
    if ticket.status in OPEN_STATUSES and today > expected_date:
        return TIMELINE_STATUS_OVERDUE
    return TIMELINE_STATUS_ON_TIME


def ticket_is_overdue(ticket, today=None):
    if not ticket_expected_resolution_date(ticket):
        return None
    return ticket_timeline_status(ticket, today) == TIMELINE_STATUS_OVERDUE


def _ticket_base_queryset(user, date_from=None, date_to=None, agent_id=None):
    queryset = Ticket.objects.filter(is_deleted=False).select_related(
        "attending_staff",
        "reporter_type",
        "event_location",
        "event_location__parent",
        "event_location__parent__parent",
        "event_location__parent__parent__parent",
    )
    queryset = ticket_queryset_for_user(queryset, user)
    queryset = annotate_ticket_metrics(queryset)
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
    if ticket.event_location:
        return ticket.event_location
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


def _resolution_status_names():
    return [
        _clean_dimension_name(_("Received")),
        _clean_dimension_name(_("Unresolved")),
        _clean_dimension_name(_("Closed")),
    ]


def _resolution_comment(ticket):
    return (
        Comment.objects.filter(ticket=ticket, is_resolution=True, is_deleted=False)
        .order_by("-date_created")
        .first()
    )


def _overdue_days(due_date, compared_to=None):
    if not due_date:
        return None
    compared_to = compared_to or _current_date()
    compared_to = _local_date(compared_to)
    return max((compared_to - due_date).days, 0)


def _current_date():
    now = timezone.now()
    if timezone.is_aware(now):
        return timezone.localtime(now).date()
    return now.date()


def _model_field_names(model):
    return {field.name for field in model._meta.fields}


def _clean_dimension_name(value):
    value = str(value).strip() if value is not None else ""
    return value or str(_("Unspecified"))


def _unique_names(names):
    unique = []
    seen = set()
    for name in names:
        clean_name = _clean_dimension_name(name)
        if clean_name in seen:
            continue
        unique.append(clean_name)
        seen.add(clean_name)
    return unique


def _configured_dimension_names(model, fallback_names=None):
    field_names = _model_field_names(model)
    queryset = model.objects.all()
    if "is_deleted" in field_names:
        queryset = queryset.filter(is_deleted=False)
    if "is_active" in field_names:
        queryset = queryset.filter(is_active=True)
    if "name" in field_names:
        queryset = queryset.order_by("name")

    names = list(queryset.values_list("name", flat=True))
    if not names and fallback_names:
        names = list(fallback_names)
    return _unique_names(names)


def _ordered_dimension_names(configured_names, counted_names):
    ordered = list(configured_names)
    configured = set(configured_names)
    ordered.extend(sorted(name for name in counted_names if name not in configured))
    return ordered


def _aggregate_counts(tickets, value_getter):
    counters = defaultdict(int)
    for ticket in tickets:
        key = _clean_dimension_name(value_getter(ticket))
        counters[key] += 1
    return counters


def _dimension_rows(report, configured_names, counters, value_field):
    rows = []
    for name in _ordered_dimension_names(configured_names, counters.keys()):
        row = GrievanceReportRowGQLType(
            report=report,
            label=name,
            count=counters.get(name, 0),
        )
        setattr(row, value_field, name)
        rows.append(row)
    return rows


def _category_rows(tickets):
    counters = _aggregate_counts(tickets, lambda ticket: ticket.category)
    configured_names = _configured_dimension_names(
        GrievanceCategory,
        TicketConfig.grievance_types,
    )
    rows = _dimension_rows(REPORT_CATEGORY, configured_names, counters, "category")
    last_category = CATEGORY_REPORT_LAST_CATEGORY.casefold()
    return sorted(
        rows,
        key=lambda row: _clean_dimension_name(row.category).casefold() == last_category,
    )


def _channel_rows(tickets):
    counters = _aggregate_counts(tickets, lambda ticket: ticket.channel)
    configured_names = _configured_dimension_names(
        GrievanceChannel,
        TicketConfig.grievance_channels,
    )
    return _dimension_rows(REPORT_CHANNEL, configured_names, counters, "channel")


def _resolution_status_rows(tickets):
    status_names = _resolution_status_names()
    received, unresolved, closed = status_names
    counters = {
        received: len(tickets),
        unresolved: sum(ticket.status in OPEN_STATUSES for ticket in tickets),
        closed: sum(ticket.status in CLOSED_STATUSES for ticket in tickets),
    }
    return _dimension_rows(
        REPORT_RESOLUTION_STATUS,
        status_names,
        counters,
        "status",
    )


def _closure_timeline_rows(report, tickets):
    rows = []
    for ticket in tickets:
        if ticket.status not in CLOSED_STATUSES:
            continue
        closed_at = ticket_closed_at(ticket)
        expected_resolution_date = ticket_expected_resolution_date(ticket)
        time_taken_seconds = ticket_time_taken_seconds(ticket)
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
                date_closed=closed_at,
                due_date=expected_resolution_date,
                closure_days=(
                    round(time_taken_seconds / 86400, 2)
                    if time_taken_seconds is not None
                    else None
                ),
                overdue_days=_overdue_days(
                    expected_resolution_date,
                    closed_at,
                ),
                overdue=ticket_is_overdue(ticket),
                timeline_status=ticket_timeline_status(ticket),
                time_taken_seconds=time_taken_seconds,
            )
        )
    return rows


def _paa_metric_rows(report, counters, user, paa_id=None):
    rows = []
    seen = set()
    for location in _paa_candidates(user, paa_id):
        location_id = _location_identifier(location)
        location_name = _location_name(location)
        data = counters.get(
            location_id,
            {"name": location_name, "count": 0, "max_overdue_days": 0},
        )
        rows.append(
            GrievanceReportRowGQLType(
                report=report,
                label=location_name,
                paa_id=location_id,
                paa_name=location_name,
                count=data.get("count", 0),
                overdue_days=data.get("max_overdue_days", 0),
            )
        )
        seen.add(location_id)

    extra_rows = [
        (paa_key, data)
        for paa_key, data in counters.items()
        if paa_key not in seen
    ]
    for paa_key, data in sorted(extra_rows, key=lambda item: item[1]["name"]):
        rows.append(
            GrievanceReportRowGQLType(
                report=report,
                label=data["name"],
                paa_id=paa_key,
                paa_name=data["name"],
                count=data.get("count", 0),
                overdue_days=data.get("max_overdue_days", 0),
            )
        )
    return rows


def _filter_paa_grievance_count_rows(
    rows,
    paa_grievance_filter=None,
    grievance_count=None,
):
    count_filter = (
        paa_grievance_filter or PAA_GRIEVANCE_FILTER_WITHOUT
    ).upper()
    if count_filter not in PAA_GRIEVANCE_FILTERS:
        raise ValueError(f"Unsupported PAA grievance filter: {count_filter}")

    threshold = grievance_count if grievance_count is not None else 0
    if threshold < 0:
        raise ValueError("Grievance count must be zero or greater")

    predicates = {
        PAA_GRIEVANCE_FILTER_WITHOUT: lambda count: count == 0,
        PAA_GRIEVANCE_FILTER_WITH: lambda count: count > 0,
        PAA_GRIEVANCE_FILTER_LESS_THAN: lambda count: count < threshold,
        PAA_GRIEVANCE_FILTER_MORE_THAN: lambda count: count > threshold,
    }
    predicate = predicates[count_filter]
    return [row for row in rows if predicate(row.count or 0)]


def _paa_grievance_count_rows(
    tickets,
    user,
    paa_id=None,
    paa_grievance_filter=None,
    grievance_count=None,
):
    counters = {}
    for ticket in tickets:
        ticket_paa_id, ticket_paa_name = _ticket_paa(ticket)
        current = counters.setdefault(
            ticket_paa_id,
            {
                "name": ticket_paa_name,
                "count": 0,
                "max_overdue_days": 0,
            },
        )
        current["count"] += 1
    rows = _paa_metric_rows(
        REPORT_PAA_WITHOUT_GRIEVANCES,
        counters,
        user,
        paa_id,
    )
    return _filter_paa_grievance_count_rows(
        rows,
        paa_grievance_filter,
        grievance_count,
    )


def _overdue_by_paa_rows(tickets, user, paa_id=None):
    today = _current_date()
    counters = {}
    for ticket in tickets:
        if not ticket_is_overdue(ticket, today):
            continue
        ticket_paa_id, ticket_paa_name = _ticket_paa(ticket)
        current = counters.setdefault(
            ticket_paa_id,
            {
                "name": ticket_paa_name,
                "count": 0,
                "max_overdue_days": 0,
            },
        )
        current["count"] += 1
        current["max_overdue_days"] = max(
            current["max_overdue_days"],
            _overdue_days(ticket_expected_resolution_date(ticket), today) or 0,
        )
    return _paa_metric_rows(REPORT_OVERDUE_BY_PAA, counters, user, paa_id)


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

    field_names = _model_field_names(Location)
    if "is_deleted" in field_names:
        queryset = queryset.filter(is_deleted=False)

    if paa_id:
        identifier_filter = Q(id=paa_id)
        if "uuid" in field_names:
            identifier_filter |= Q(uuid=paa_id)
        queryset = queryset.filter(identifier_filter)

    for order_field in ("name", "code", "location_name"):
        if order_field in field_names:
            queryset = queryset.order_by(order_field)
            break

    return list(queryset)


def resolve_grievance_report_rows(
    info,
    report,
    date_from=None,
    date_to=None,
    agent_id=None,
    paa_id=None,
    paa_grievance_filter=None,
    grievance_count=None,
):
    check_ticket_perms(info)
    tickets = list(
        _ticket_base_queryset(info.context.user, date_from, date_to, agent_id)
    )
    if paa_id:
        tickets = [ticket for ticket in tickets if _ticket_matches_paa(ticket, paa_id)]

    if report == REPORT_CATEGORY:
        return _category_rows(tickets)
    if report == REPORT_PAA_WITHOUT_GRIEVANCES:
        return _paa_grievance_count_rows(
            tickets,
            info.context.user,
            paa_id,
            paa_grievance_filter,
            grievance_count,
        )
    if report == REPORT_CHANNEL:
        return _channel_rows(tickets)
    if report == REPORT_RESOLUTION_STATUS:
        return _resolution_status_rows(tickets)
    if report == REPORT_CLOSURE_TIMELINE:
        return _closure_timeline_rows(report, tickets)
    if report == REPORT_CLOSURE_TIMELINE_BY_PAA:
        return _closure_timeline_rows(report, tickets)
    if report == REPORT_OVERDUE_BY_PAA:
        return _overdue_by_paa_rows(tickets, info.context.user, paa_id)

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
    event_location = graphene.Field(LocationGQLType)
    region = graphene.Field(LocationGQLType)
    district = graphene.Field(LocationGQLType)
    ward = graphene.Field(LocationGQLType)
    village = graphene.Field(LocationGQLType)
    expected_resolution_date = graphene.Date()
    closed_at = graphene.DateTime()
    overdue = graphene.Boolean()
    timeline_status = graphene.String()
    time_taken_seconds = graphene.Float()

    @staticmethod
    def _resolve_location_type(root, info, location_type):
        check_ticket_perms(info)
        return location_chain(root.event_location).get(location_type)

    @staticmethod
    def resolve_event_location(root, info):
        check_ticket_perms(info)
        return root.event_location

    @staticmethod
    def resolve_region(root, info):
        return TicketGQLType._resolve_location_type(root, info, "R")

    @staticmethod
    def resolve_district(root, info):
        return TicketGQLType._resolve_location_type(root, info, "D")

    @staticmethod
    def resolve_ward(root, info):
        return TicketGQLType._resolve_location_type(root, info, "W")

    @staticmethod
    def resolve_village(root, info):
        return TicketGQLType._resolve_location_type(root, info, "V")

    @staticmethod
    def resolve_expected_resolution_date(root, info):
        check_ticket_perms(info)
        return ticket_expected_resolution_date(root)

    @staticmethod
    def resolve_closed_at(root, info):
        check_ticket_perms(info)
        return ticket_closed_at(root)

    @staticmethod
    def resolve_overdue(root, info):
        check_ticket_perms(info)
        return ticket_is_overdue(root)

    @staticmethod
    def resolve_timeline_status(root, info):
        check_ticket_perms(info)
        return ticket_timeline_status(root)

    @staticmethod
    def resolve_time_taken_seconds(root, info):
        check_ticket_perms(info)
        return ticket_time_taken_seconds(root)

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
            "event_location": ["exact", "isnull"],
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
