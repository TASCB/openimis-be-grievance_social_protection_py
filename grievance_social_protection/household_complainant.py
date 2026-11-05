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
