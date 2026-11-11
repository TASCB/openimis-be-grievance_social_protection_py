from unittest import skipUnless
from uuid import uuid4

from django.apps import apps
from django.core.cache import cache
from django.test import TestCase

from core.test_helpers import LogInHelper
from location.test_helpers import create_test_village

from grievance_social_protection.household_complainant import (
    LEGACY_PROGRAMME, legacy_household_summary, search_legacy_households,
)
from grievance_social_protection.models import Ticket
from grievance_social_protection.services import TicketService
from grievance_social_protection.tests.data import service_add_ticket_payload
from grievance_social_protection.tests.test_helpers import ensure_default_category


@skipUnless(apps.is_installed("legacy_individual"), "legacy registry not installed")
class LegacyHouseholdComplainantTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from legacy_individual.models import (
            LegacyGroup, LegacyGroupIndividual, LegacyImportBatch, LegacyIndividual,
        )
        from location.models import Location, UserDistrict

        cls.admin = LogInHelper().get_or_create_user_api()
        ensure_default_category(cls.admin)
        suffix = uuid4().hex[:6].upper()
        cls.village = create_test_village({"code": f"LG{suffix}", "name": f"Legacy Village {suffix}"})
        cls.district = cls.village.parent.parent
        cls.code = f"9{uuid4().int % 10**13:013d}"

        save = {"username": cls.admin.username}
        batch = LegacyImportBatch(code=f"LGTEST-{suffix}", source_system="PSSN")
        batch.save(**save)
        cls.group = LegacyGroup(code=cls.code, import_batch=batch, location=cls.village,
                                json_ext={"phone_no": "0712000111", "pmt_score": "11.4"})
        cls.group.save(**save)
        head = LegacyIndividual(legacy_code=f"{cls.code}01", import_batch=batch,
                                first_name="Zuhura", last_name="Legacytest", location=cls.village)
        head.save(**save)
        LegacyGroupIndividual(group=cls.group, individual=head, role=LegacyGroupIndividual.Role.HEAD,
                              recipient_type=LegacyGroupIndividual.RecipientType.PRIMARY).save(**save)

        other = Location.objects.filter(type="D", validity_to__isnull=True).exclude(id=cls.district.id).first()
        cls.other_user = LogInHelper().get_or_create_user_api(username=f"lg_other_{suffix}", roles=[])
        UserDistrict.objects.create(user=cls.other_user._u, location=other, audit_user_id=-1)
        cache.delete(f"user_locations_{cls.other_user._u.id}")

    def test_found_by_household_number(self):
        found = search_legacy_households(self.admin, self.code)
        self.assertEqual([h["hhid"] for h in found], [self.code])
        summary = found[0]
        self.assertEqual(summary["head"], "Zuhura Legacytest")
        self.assertEqual(summary["village"], self.village.name)
        self.assertEqual(summary["district"], self.district.name)
        self.assertEqual(summary["members"], 1)
        self.assertEqual(summary["programme"], LEGACY_PROGRAMME)

    def test_found_by_head_name_and_phone(self):
        self.assertIn(self.code, [h["hhid"] for h in search_legacy_households(self.admin, "Legacytest")])
        self.assertIn(self.code, [h["hhid"] for h in search_legacy_households(self.admin, "0712000111")])

    def test_short_search_returns_nothing(self):
        self.assertEqual(search_legacy_households(self.admin, "Zu"), [])

    def test_other_district_cannot_find_it(self):
        self.assertEqual(search_legacy_households(self.other_user, self.code), [])

    def test_ticket_links_to_the_legacy_household(self):
        payload = {**service_add_ticket_payload, "title": "Legacy household complaint",
                   "reporter_type": "legacygroup", "reporter_id": str(self.group.id)}
        result = TicketService(self.admin).create(payload)
        self.assertTrue(result.get("success"), result.get("detail"))
        ticket = Ticket.objects.get(id=result["data"]["id"])
        self.assertEqual(ticket.reporter_type.model, "legacygroup")
        self.assertEqual(ticket.reporter, self.group)
        self.assertEqual(legacy_household_summary(ticket.reporter)["hhid"], self.code)

    def test_reporter_json_leaves_the_record_usable(self):
        from grievance_social_protection.util import model_obj_to_json
        model_obj_to_json(self.group)
        self.assertEqual(legacy_household_summary(self.group)["hhid"], self.code)
