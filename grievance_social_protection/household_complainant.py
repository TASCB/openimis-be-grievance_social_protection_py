"""Household (GroupBeneficiary) complainants, shown as HHID + representative or head."""
import uuid

from django.db.models import Exists, OuterRef, Q

from individual.models import Group, GroupIndividual

GROUP_BENEFICIARY_TYPE = "groupbeneficiary"


def _member_name(member):
    if not member:
        return None
    ind = member.individual
    return " ".join(p for p in (ind.first_name, ind.last_name) if p) or None


def household_summary(group):
    members = (GroupIndividual.objects
               .filter(group=group, is_deleted=False)
               .filter(Q(role=GroupIndividual.Role.HEAD)
                       | Q(recipient_type=GroupIndividual.RecipientType.PRIMARY))
               .select_related("individual"))
    rep = next((m for m in members if m.recipient_type == GroupIndividual.RecipientType.PRIMARY), None)
    head = next((m for m in members if m.role == GroupIndividual.Role.HEAD), None)
    ext = group.json_ext or {}
    return {
        "hhid": group.code,
        "representative": _member_name(rep) or ext.get("primary_recipient"),
        "head": _member_name(head) or ext.get("head"),
    }


def _plain_id(value):
    try:
        uuid.UUID(str(value))
        return value
    except ValueError:
        from graphql_relay import from_global_id
        return from_global_id(value)[1]


def search_household_beneficiaries(user, benefit_plan_id, search=None, limit=20):
    from social_protection.models import GroupBeneficiary

    benefit_plan_id = _plain_id(benefit_plan_id)

    groups = Group.get_queryset(None, user).filter(is_deleted=False)
    qs = (GroupBeneficiary.objects
          .filter(benefit_plan_id=benefit_plan_id, is_deleted=False, group__in=groups)
          .select_related("group"))
    for term in (search or "").split():
        named = GroupIndividual.objects.filter(
            group_id=OuterRef("group_id"), is_deleted=False,
        ).filter(
            Q(role=GroupIndividual.Role.HEAD) | Q(recipient_type=GroupIndividual.RecipientType.PRIMARY)
        ).filter(Q(individual__first_name__icontains=term) | Q(individual__last_name__icontains=term))
        qs = qs.filter(Q(group__code__icontains=term) | Exists(named))
    return [
        {"id": gb.id, **household_summary(gb.group)}
        for gb in qs.order_by("group__code")[:limit]
    ]


LEGACY_HOUSEHOLD_TYPE = "legacygroup"
LEGACY_PROGRAMME = "PSSN I & II"
LEGACY_SEARCH_MIN_LENGTH = 3


def legacy_registry_installed():
    from django.apps import apps
    return apps.is_installed("legacy_individual")


def _legacy_member_name(membership):
    if not membership:
        return None
    ind = membership.individual
    return " ".join(p for p in (ind.first_name, ind.middle_name, ind.last_name) if p) or None


def _ancestor(location, loc_type):
    while location is not None and location.type != loc_type:
        location = location.parent
    return location


def legacy_household_summary(group):
    from legacy_individual.models import LegacyGroupIndividual

    memberships = list(LegacyGroupIndividual.objects
                       .filter(group=group, is_deleted=False)
                       .select_related("individual"))
    head = next((m for m in memberships if m.role == LegacyGroupIndividual.Role.HEAD), None)
    rep = next((m for m in memberships
                if m.recipient_type == LegacyGroupIndividual.RecipientType.PRIMARY), None)
    ext = group.json_ext or {}
    head_ext = ext.get("head") or {}
    head_from_household = " ".join(
        p for p in (head_ext.get("first_name"), head_ext.get("middle_name"), head_ext.get("last_name")) if p)
    village = group.location
    district = _ancestor(village, "D")
    return {
        "id": str(group.id),
        "hhid": group.code,
        "head": _legacy_member_name(head) or head_from_household or None,
        "representative": _legacy_member_name(rep),
        "village": village.name if village else None,
        "district": district.name if district else None,
        "members": len(memberships),
        "phone": ext.get("phone_no"),
        "pmt_score": ext.get("pmt_score"),
        "programme": LEGACY_PROGRAMME,
    }


def search_legacy_households(user, search=None, limit=20):
    if not legacy_registry_installed():
        return []
    search = (search or "").strip()
    if len(search) < LEGACY_SEARCH_MIN_LENGTH:
        return []
    from location.models import LocationManager
    from legacy_individual.models import LegacyGroup, LegacyGroupIndividual

    qs = LegacyGroup.objects.filter(is_deleted=False)
    if not getattr(user, "is_imis_admin", False):
        interactive = getattr(user, "_u", user)
        qs = qs.filter(LocationManager().build_user_location_filter_query(interactive, prefix="location"))
    for term in search.split():
        named_groups = (LegacyGroupIndividual.objects
                        .filter(is_deleted=False)
                        .filter(Q(role=LegacyGroupIndividual.Role.HEAD)
                                | Q(recipient_type=LegacyGroupIndividual.RecipientType.PRIMARY))
                        .filter(Q(individual__first_name__icontains=term)
                                | Q(individual__last_name__icontains=term))
                        .values("group_id"))
        qs = qs.filter(Q(code__istartswith=term) | Q(json_ext__phone_no=term) | Q(id__in=named_groups))
    return [legacy_household_summary(g) for g in qs.select_related("location").order_by("code")[:limit]]
