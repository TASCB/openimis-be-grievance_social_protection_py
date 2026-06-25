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
EXTERNAL_REPORTER_LOCATION_INPUT_FIELDS = {
    "external_reporter_region_id": "R",
    "external_reporter_district_id": "D",
    "external_reporter_ward_id": "W",
    "external_reporter_village_id": "V",
}


@dataclass(frozen=True)
class GrievanceLocationScope:
    restricted: bool
    direct_location_ids: tuple
    allowed_location_ids: frozenset


def _underlying_user(user):
    return getattr(user, "_u", None) if user is not None else None


def _location_checks_disabled():
    from location.apps import LocationConfig

    return LocationConfig.no_location_check


def _user_requires_assigned_location(user):
    if (
        user is None
        or getattr(user, "is_anonymous", True)
        or getattr(user, "is_superuser", False)
        or not settings.ROW_SECURITY
    ):
        return False
    return not _location_checks_disabled()


def _direct_user_location_ids(user):
    if user is None or getattr(user, "is_anonymous", True):
        return ()

    from location.models import LocationManager

    location_model = apps.get_model("location", "Location")
    underlying_user = (
        _underlying_user(user)
        or getattr(user, "i_user", None)
        or user
    )
    if underlying_user is None:
        return ()

    allowed_ids = LocationManager().get_allowed_ids(underlying_user) or []
    if not allowed_ids:
        return ()

    return tuple(
        location_model.filter_queryset(
            location_model.objects.filter(
                id__in=allowed_ids
            )
        )
        .order_by("id")
        .values_list("id", flat=True)
    )


def _expanded_location_ids(location_ids):
    if not location_ids:
        return frozenset()
    from location.models import extend_allowed_locations

    return frozenset(extend_allowed_locations(list(location_ids), strict=True))


def get_location_scope(user):
    if _location_checks_disabled():
        return GrievanceLocationScope(False, (), frozenset())

    direct_ids = _direct_user_location_ids(user)
    allowed_ids = _expanded_location_ids(direct_ids)

    if not _user_requires_assigned_location(user):
        return GrievanceLocationScope(False, direct_ids, allowed_ids)

    if not direct_ids:
        return GrievanceLocationScope(True, (), frozenset())

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


def _load_locations(
    data,
    input_fields=LOCATION_INPUT_FIELDS,
    location_id_field="event_location_id",
):
    Location = apps.get_model("location", "Location")
    requested = {
        field: data.get(field)
        for field in (*input_fields.keys(), location_id_field)
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


def _validate_hierarchy(
    requested,
    locations,
    input_fields=LOCATION_INPUT_FIELDS,
    location_id_field="event_location_id",
    location_label="Event location",
):
    selected_by_type = {}
    for field, expected_type in input_fields.items():
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

    selected_location_id = requested.get(location_id_field)
    if selected_location_id is not None:
        selected_location = locations[int(selected_location_id)]
        if selected_location.type not in LOCATION_TYPES:
            raise ValidationError(f"{location_label} has an unsupported location type")
        if deepest is not None and deepest.id != selected_location.id:
            raise ValidationError(f"{location_label} does not match the selected hierarchy")
        deepest = selected_location

    if deepest is None:
        return None

    actual_chain = location_chain(deepest)
    for location_type, selected in selected_by_type.items():
        if actual_chain.get(location_type) != selected:
            raise ValidationError("Invalid Region, District, Ward, and Village combination")
    return deepest


def normalize_external_reporter_location(data, require_complete=False):
    location_id_field = "external_reporter_location_id"
    location_keys = set(EXTERNAL_REPORTER_LOCATION_INPUT_FIELDS) | {location_id_field}
    has_location_input = any(key in data for key in location_keys)

    if not has_location_input:
        if require_complete:
            raise ValidationError("Reporter location is required")
        return

    requested, locations = _load_locations(
        data,
        EXTERNAL_REPORTER_LOCATION_INPUT_FIELDS,
        location_id_field,
    )
    selected = _validate_hierarchy(
        requested,
        locations,
        EXTERNAL_REPORTER_LOCATION_INPUT_FIELDS,
        location_id_field,
        "Reporter location",
    )

    for field in EXTERNAL_REPORTER_LOCATION_INPUT_FIELDS:
        data.pop(field, None)

    if require_complete and selected is None:
        raise ValidationError("Reporter location is required")
    if require_complete and selected.type != "V":
        raise ValidationError("Reporter village is required")

    data[location_id_field] = selected.id if selected is not None else None


def normalize_ticket_location(user, data, existing_ticket=None):
    location_keys = set(LOCATION_INPUT_FIELDS) | {"event_location_id"}
    has_location_input = any(key in data for key in location_keys)
    scope = get_location_scope(user)

    if (
        existing_ticket is None
        and _user_requires_assigned_location(user)
        and not scope.direct_location_ids
    ):
        raise ValidationError(
            "Current user has no assigned location. Please ask an administrator "
            "to assign a Region, District, Ward, or Village before creating a grievance."
        )

    if existing_ticket is None and len(scope.direct_location_ids) == 1:
        assigned_location_id = scope.direct_location_ids[0]
        if has_location_input:
            requested, locations = _load_locations(data)
            selected = _validate_hierarchy(requested, locations)
            if selected is not None and selected.id != assigned_location_id:
                raise PermissionDenied(
                    "Selected location does not match the user's assigned location"
                )
            for field in LOCATION_INPUT_FIELDS:
                data.pop(field, None)
        data["event_location_id"] = assigned_location_id
        return

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
            raise ValidationError("Location is required for this user")
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
