from types import SimpleNamespace
from unittest.mock import patch

from django.core.exceptions import PermissionDenied
from django.test import SimpleTestCase

from grievance_social_protection.apps import TicketConfig
from grievance_social_protection.gql_mutations import (
    CreateTicketMutation,
    _require_sensitive_closure_approval,
    _require_sensitivity_kept,
)
from grievance_social_protection.models import Ticket
from grievance_social_protection.sensitive_closure import is_sensitive, sensitive_after_update

HANDLER_ID = "11111111-1111-1111-1111-111111111111"
APPROVER_ID = "22222222-2222-2222-2222-222222222222"


class UserWithRights:
    is_authenticated = True

    def __init__(self, *rights, id=None):
        self.id = id
        self.rights = {int(right) for right in rights}

    def has_perms(self, permissions):
        return all(int(permission) in self.rights for permission in permissions)


def ticket(priority="Normal", flags=None, attending_staff_id=HANDLER_ID):
    return SimpleNamespace(priority=priority, flags=flags, attending_staff_id=attending_staff_id)


@patch.object(TicketConfig, "sensitive_closure_priorities", ["Critical", "High"])
@patch.object(TicketConfig, "sensitive_closure_flags", ["GBV", "SEA"])
class SensitiveClosureTestCase(SimpleTestCase):
    officer = UserWithRights(127000, 127002, 127006, id=HANDLER_ID)
    approver = UserWithRights(127000, 127002, 127006, 127007, id=APPROVER_ID)

    def test_sensitivity_comes_from_priority_or_flags(self):
        self.assertTrue(is_sensitive("critical", None))
        self.assertTrue(is_sensitive("Normal", "Flag A, gbv"))
        self.assertFalse(is_sensitive("Normal", "Flag A"))
        self.assertFalse(is_sensitive(None, None))

    def test_update_keeps_stored_values_for_absent_keys(self):
        self.assertTrue(sensitive_after_update(ticket("High"), {"flags": "Flag A"}))
        self.assertFalse(sensitive_after_update(ticket("High"), {"priority": "Low"}))

    def test_ordinary_ticket_needs_no_approval(self):
        _require_sensitive_closure_approval(self.officer, ticket("Normal"))

    def test_officer_cannot_close_sensitive_ticket(self):
        for t in (ticket("High"), ticket("Normal", "SEA")):
            with self.subTest(priority=t.priority, flags=t.flags):
                with self.assertRaises(PermissionDenied):
                    _require_sensitive_closure_approval(self.officer, t)

    def test_approver_closes_sensitive_ticket_handled_by_someone_else(self):
        _require_sensitive_closure_approval(self.approver, ticket("Critical"))

    def test_approver_cannot_close_own_sensitive_ticket(self):
        with self.assertRaises(PermissionDenied):
            _require_sensitive_closure_approval(
                self.approver, ticket("Critical", attending_staff_id=APPROVER_ID)
            )

    def test_downgrade_and_close_in_one_step_is_still_sensitive(self):
        with self.assertRaises(PermissionDenied):
            _require_sensitive_closure_approval(self.officer, ticket("High"), priority="Low")

    def test_raising_to_sensitive_and_closing_needs_approval(self):
        with self.assertRaises(PermissionDenied):
            _require_sensitive_closure_approval(self.officer, ticket("Normal"), priority="High")

    def test_only_approver_may_downgrade_a_sensitive_ticket(self):
        with self.assertRaises(PermissionDenied):
            _require_sensitivity_kept(self.officer, ticket("High"), priority="Normal")
        _require_sensitivity_kept(self.officer, ticket("High"), title="Renamed")
        _require_sensitivity_kept(self.officer, ticket("Normal"), priority="High")
        _require_sensitivity_kept(self.approver, ticket("High"), priority="Normal")

    def test_creating_an_already_closed_sensitive_ticket_needs_approval(self):
        creator = UserWithRights(127001, 127006)
        with self.assertRaises(PermissionDenied):
            CreateTicketMutation._authorize_create(
                creator, status=Ticket.TicketStatus.CLOSED, priority="Critical"
            )
        CreateTicketMutation._authorize_create(
            creator, status=Ticket.TicketStatus.CLOSED, priority="Normal"
        )
