from copy import deepcopy
from uuid import uuid4

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase, override_settings

from core.test_helpers import create_test_interactive_user, create_test_officer
from location.test_helpers import assign_user_districts, create_test_village

from grievance_social_protection.location_scope import (
    get_location_scope,
    location_subtree_ids,
    normalize_ticket_location,
    ticket_queryset_for_user,
)
from grievance_social_protection.models import Ticket
from grievance_social_protection.services import TicketService
from grievance_social_protection.tests.data import service_add_ticket_payload


@override_settings(ROW_SECURITY=True)
class TicketLocationTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        suffix = uuid4().hex[:8].upper()
        cls.village_a = create_test_village(
            {"code": f"VA-{suffix}", "name": f"Village A {suffix}"}
        )
        cls.village_b = create_test_village(
            {"code": f"VB-{suffix}", "name": f"Village B {suffix}"}
        )
        cls.ward_a = cls.village_a.parent
        cls.district_a = cls.ward_a.parent
        cls.region_a = cls.district_a.parent
        cls.district_b = cls.village_b.parent.parent
        cls.unassigned_user = create_test_interactive_user(
            username=f"location-open-{suffix}",
            roles=[7],
        )

        cls.district_user = create_test_interactive_user(
            username=f"location-district-{suffix}",
            roles=[7],
        )
        assign_user_districts(cls.district_user, [cls.district_a.code])

        officer_username = f"lv{suffix[:6]}"
        create_test_officer(
            custom_props={"code": officer_username, "has_login": True},
            villages=[cls.village_a],
        )
        cls.village_user = create_test_interactive_user(
            username=officer_username,
            roles=[7],
        )

    def _ticket(self, title, location, user=None):
        ticket = Ticket(
            **{
                **service_add_ticket_payload,
                "title": title,
                "code": f"GRS{uuid4().int % 100000000:08}",
                "event_location": location,
            }
        )
        ticket.save(user=user or self.unassigned_user)
        return ticket

    def test_unassigned_user_can_create_without_location(self):
        payload = deepcopy(service_add_ticket_payload)
        result = TicketService(self.unassigned_user).create(payload)

        self.assertTrue(result["success"], result)
        ticket = Ticket.objects.get(uuid=result["data"]["uuid"])
        self.assertIsNone(ticket.event_location_id)

    def test_unassigned_user_can_create_with_selected_village(self):
        payload = {
            **deepcopy(service_add_ticket_payload),
            "region_id": self.region_a.id,
            "district_id": self.district_a.id,
            "ward_id": self.ward_a.id,
            "village_id": self.village_a.id,
            "event_location_id": self.village_a.id,
        }
        result = TicketService(self.unassigned_user).create(payload)

        self.assertTrue(result["success"], result)
        ticket = Ticket.objects.get(uuid=result["data"]["uuid"])
        self.assertEqual(ticket.event_location, self.village_a)

    def test_invalid_location_hierarchy_is_rejected(self):
        payload = {
            "region_id": self.region_a.id,
            "district_id": self.district_b.id,
            "village_id": self.village_a.id,
            "event_location_id": self.village_a.id,
        }

        with self.assertRaises(ValidationError):
            normalize_ticket_location(self.unassigned_user, payload)

    def test_village_assignment_is_detected_and_applied(self):
        scope = get_location_scope(self.village_user)
        self.assertTrue(scope.restricted)
        self.assertEqual(scope.direct_location_ids, (self.village_a.id,))

        payload = deepcopy(service_add_ticket_payload)
        result = TicketService(self.village_user).create(payload)

        self.assertTrue(result["success"], result)
        ticket = Ticket.objects.get(uuid=result["data"]["uuid"])
        self.assertEqual(ticket.event_location, self.village_a)

    def test_assigned_user_cannot_create_outside_scope(self):
        payload = {
            **deepcopy(service_add_ticket_payload),
            "event_location_id": self.village_b.id,
            "village_id": self.village_b.id,
        }

        with self.assertRaises(PermissionDenied):
            TicketService(self.village_user).create(payload)

    def test_assigned_user_only_sees_grievances_in_scope(self):
        allowed = self._ticket("Allowed grievance", self.village_a)
        self._ticket("Outside grievance", self.village_b)
        self._ticket("Locationless grievance", None)

        visible = ticket_queryset_for_user(Ticket.objects.all(), self.village_user)

        self.assertEqual(list(visible), [allowed])

    def test_district_user_can_edit_to_an_allowed_descendant(self):
        ticket = self._ticket("Editable grievance", self.district_a)
        payload = {
            "event_location_id": self.village_a.id,
            "region_id": self.region_a.id,
            "district_id": self.district_a.id,
            "ward_id": self.ward_a.id,
            "village_id": self.village_a.id,
        }

        normalize_ticket_location(
            self.district_user,
            payload,
            existing_ticket=ticket,
        )
        ticket.event_location_id = payload["event_location_id"]
        ticket.save(user=self.district_user)

        ticket.refresh_from_db()
        self.assertEqual(ticket.event_location, self.village_a)

    def test_location_filters_include_descendant_grievances(self):
        self._ticket("Village A grievance", self.village_a)
        self._ticket("Village B grievance", self.village_b)

        region_ids = location_subtree_ids(self.region_a.id)
        district_ids = location_subtree_ids(self.district_a.id)
        ward_ids = location_subtree_ids(self.ward_a.id)
        village_ids = location_subtree_ids(self.village_a.id)

        self.assertEqual(
            Ticket.objects.filter(event_location_id__in=region_ids).count(),
            1,
        )
        self.assertEqual(
            Ticket.objects.filter(event_location_id__in=district_ids).count(),
            1,
        )
        self.assertEqual(
            Ticket.objects.filter(event_location_id__in=ward_ids).count(),
            1,
        )
        self.assertEqual(
            Ticket.objects.filter(event_location_id__in=village_ids).count(),
            1,
        )
