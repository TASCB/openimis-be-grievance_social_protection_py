"""Which tickets count as sensitive for closure (RBAC gap G2).

A ticket is sensitive when its priority is in ``sensitive_closure_priorities`` or any of its
comma-separated flags is in ``sensitive_closure_flags``. Closing one needs the extra
``gql_mutation_approve_sensitive_closure_perms`` right, and its attending staff may not close it.
"""
from .apps import TicketConfig

_UNSET = object()


def _flag_set(flags):
    return {flag.strip().lower() for flag in str(flags or "").split(",") if flag.strip()}


def is_sensitive(priority=None, flags=None):
    priorities = {str(p).strip().lower() for p in TicketConfig.sensitive_closure_priorities}
    if priority and str(priority).strip().lower() in priorities:
        return True
    sensitive_flags = {str(f).strip().lower() for f in TicketConfig.sensitive_closure_flags}
    return bool(_flag_set(flags) & sensitive_flags)


def ticket_is_sensitive(ticket):
    return ticket is not None and is_sensitive(ticket.priority, ticket.flags)


def sensitive_after_update(ticket, data):
    """Sensitivity once ``data`` (mutation input) is applied; absent keys keep the stored value."""
    priority = data.get("priority", _UNSET)
    flags = data.get("flags", _UNSET)
    return is_sensitive(
        getattr(ticket, "priority", None) if priority is _UNSET else priority,
        getattr(ticket, "flags", None) if flags is _UNSET else flags,
    )
