from dataclasses import dataclass

from django.apps import apps
from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError


LOCATION_TYPES = ("R", "D", "W", "V")
LOCATION_INPUT_FIELDS = {
    "region_id": "R",
    "district_id": "D",
    "ward_id": "W",
    "village_id": "V",
}


@dataclass(frozen=True)
class GrievanceLocationScope:
    restricted: bool
    direct_location_ids: tuple
    allowed_location_ids: frozenset


def _underlying_user(user):
    return getattr(user, "_u", None) if user is not None else None


def get_location_scope(user):
    if (
        user is None
        or getattr(user, "is_anonymous", True)
        or getattr(user, "is_superuser", False)
        or not settings.ROW_SECURITY
    ):
        return GrievanceLocationScope(False, (), frozenset())

    from location.apps import LocationConfig
    from location.models import LocationManager, extend_allowed_locations

    if LocationConfig.no_location_check:
        return GrievanceLocationScope(False, (), frozenset())

    location_model = apps.get_model("location", "Location")
    underlying_user = _underlying_user(user)
    if underlying_user is None:
        return GrievanceLocationScope(False, (), frozenset())

    direct_ids = tuple(
        location_model.filter_queryset(
            location_model.objects.filter(
                id__in=LocationManager().get_allowed_ids(underlying_user)
            )
        )
        .order_by("id")
        .values_list("id", flat=True)
    )
    if not direct_ids:
        return GrievanceLocationScope(False, (), frozenset())

    allowed_ids = frozenset(extend_allowed_locations(list(direct_ids), strict=True))
    return GrievanceLocationScope(True, direct_ids, allowed_ids)


def ticket_queryset_for_user(queryset, user):
    scope = get_location_scope(user)
    if not scope.restricted:
        return queryset
    return queryset.filter(event_location_id__in=scope.allowed_location_ids)


def ensure_ticket_access(user, ticket):
    if ticket is None:
        raise ValidationError("Ticket not found")
    if not ticket_queryset_for_user(ticket.__class__.objects.filter(id=ticket.id), user).exists():
        raise PermissionDenied("Ticket is outside the user's permitted location")


def location_chain(location):
    chain = {}
    current = location
    while current is not None:
        chain[current.type] = current
        current = current.parent
    return chain


def location_subtree_ids(location_id):
    if not location_id:
        return set()
    from location.models import extend_allowed_locations

    return set(extend_allowed_locations([int(location_id)], strict=True))


def _load_locations(data):
    Location = apps.get_model("location", "Location")
    requested = {
        field: data.get(field)
        for field in (*LOCATION_INPUT_FIELDS.keys(), "event_location_id")
        if field in data and data.get(field) is not None
    }
    ids = {int(location_id) for location_id in requested.values()}
    locations = {
        location.id: location
        for location in Location.filter_queryset(
            Location.objects.select_related(
                "parent",
                "parent__parent",
                "parent__parent__parent",
            ).filter(id__in=ids)
        )
    }
    if len(locations) != len(ids):
        raise ValidationError("One or more selected locations are invalid or inactive")
    return requested, locations


def _validate_hierarchy(requested, locations):
    selected_by_type = {}
    for field, expected_type in LOCATION_INPUT_FIELDS.items():
        location_id = requested.get(field)
        if location_id is None:
            continue
        location = locations[int(location_id)]
        if location.type != expected_type:
            raise ValidationError(f"{field} does not reference a {expected_type} location")
        selected_by_type[expected_type] = location

    deepest = None
    for location_type in reversed(LOCATION_TYPES):
        if location_type in selected_by_type:
            deepest = selected_by_type[location_type]
            break

    event_location_id = requested.get("event_location_id")
    if event_location_id is not None:
        event_location = locations[int(event_location_id)]
        if event_location.type not in LOCATION_TYPES:
            raise ValidationError("Event location has an unsupported location type")
        if deepest is not None and deepest.id != event_location.id:
            raise ValidationError("Event location does not match the selected hierarchy")
        deepest = event_location

    if deepest is None:
        return None

    actual_chain = location_chain(deepest)
    for location_type, selected in selected_by_type.items():
        if actual_chain.get(location_type) != selected:
            raise ValidationError("Invalid Region, District, Ward, and Village combination")
    return deepest


def normalize_ticket_location(user, data, existing_ticket=None):
    location_keys = set(LOCATION_INPUT_FIELDS) | {"event_location_id"}
    has_location_input = any(key in data for key in location_keys)
    scope = get_location_scope(user)

    if not has_location_input:
        if existing_ticket is not None:
            if scope.restricted:
                if (
                    existing_ticket.event_location_id is None
                    or existing_ticket.event_location_id not in scope.allowed_location_ids
                ):
                    raise PermissionDenied(
                        "Ticket is outside the user's permitted location"
                    )
            return
        if scope.restricted:
            if len(scope.direct_location_ids) != 1:
                raise ValidationError("Location is required for this user")
            data["event_location_id"] = scope.direct_location_ids[0]
        return

    requested, locations = _load_locations(data)
    selected = _validate_hierarchy(requested, locations)

    for field in LOCATION_INPUT_FIELDS:
        data.pop(field, None)

    if scope.restricted and selected is None:
        if len(scope.direct_location_ids) == 1:
            selected = locations.get(scope.direct_location_ids[0])
            if selected is None:
                Location = apps.get_model("location", "Location")
                selected = Location.filter_queryset(
                    Location.objects.filter(id=scope.direct_location_ids[0])
                ).first()
        else:
            raise ValidationError("Location is required for this user")

    if selected is not None and scope.restricted:
        if selected.id not in scope.allowed_location_ids:
            raise PermissionDenied("Selected location is outside the user's permitted location")

    data["event_location_id"] = selected.id if selected is not None else None
