from uuid import uuid4

from core.models import MutationLog
from core.models.openimis_graphql_test_case import BaseTestContext, openIMISGraphQLTestCase
from core.test_helpers import create_test_interactive_user
from django.core.exceptions import ValidationError
from graphene import Schema
from graphene.test import Client
from location.test_helpers import create_test_village

from grievance_social_protection.models import Ticket
from grievance_social_protection.schema import Mutation, Query
from grievance_social_protection.services import TicketService
from grievance_social_protection.tests.data import service_add_ticket_payload


EXTERNAL_REPORTER_DESCRIPTION = " ".join(
    [f"externaldescription{i}" for i in range(1, 46)]
)


def external_reporter_mutation(
    *,
    mutation_id,
    title,
    region_id,
    district_id,
    ward_id,
    village_id,
    first_name="Asha",
    last_name="Mrope",
    phone="+255 712 345 678",
    email='"asha.mrope@example.org"',
):
    email_line = f"externalReporterEmail: {email}" if email is not None else ""
    return f"""
    mutation createTicket {{
      createTicket(input: {{
        category: "Default",
        title: "{title}",
        description: "{EXTERNAL_REPORTER_DESCRIPTION}",
        resolution: "2,5",
        priority: "Medium",
        dateOfIncident: "2024-11-20",
        channel: "Channel A",
        flags: "Default",
        reporterType: "external",
        externalReporterFirstName: "{first_name}",
        externalReporterLastName: "{last_name}",
        externalReporterPhone: "{phone}",
        {email_line}
        externalReporterRegionId: {region_id},
        externalReporterDistrictId: {district_id},
        externalReporterWardId: {ward_id},
        externalReporterVillageId: {village_id},
        externalReporterLocationId: {village_id},
        clientMutationId: "{mutation_id}"
      }}) {{
        clientMutationId
      }}
    }}
    """


class GQLTicketExternalReporterTestCase(openIMISGraphQLTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        suffix = uuid4().hex[:8].upper()
        cls.user = create_test_interactive_user(
            username=f"external-reporter-{suffix}",
            roles=[7],
        )
        cls.village = create_test_village(
            {"code": f"ER-{suffix}", "name": f"External Reporter Village {suffix}"}
        )
        cls.ward = cls.village.parent
        cls.district = cls.ward.parent
        cls.region = cls.district.parent
        cls.gql_client = Client(Schema(query=Query, mutation=Mutation))
        cls.gql_context = BaseTestContext(cls.user)

    def test_create_external_reporter_with_required_fields(self):
        mutation_id = f"external-create-{uuid4()}"
        title = f"External reporter {uuid4()}"

        self.gql_client.execute(
            external_reporter_mutation(
                mutation_id=mutation_id,
                title=title,
                region_id=self.region.id,
                district_id=self.district.id,
                ward_id=self.ward.id,
                village_id=self.village.id,
            ),
            context=self.gql_context.get_request(),
        )

        mutation_log = MutationLog.objects.get(client_mutation_id=mutation_id)
        self.assertFalse(mutation_log.error)
        ticket = Ticket.objects.get(title=title)
        self.assertIsNone(ticket.reporter_type)
        self.assertIsNone(ticket.reporter_id)
        self.assertEqual(ticket.external_reporter_first_name, "Asha")
        self.assertEqual(ticket.external_reporter_last_name, "Mrope")
        self.assertEqual(ticket.external_reporter_phone, "+255 712 345 678")
        self.assertEqual(ticket.external_reporter_email, "asha.mrope@example.org")
        self.assertEqual(ticket.external_reporter_location, self.village)

    def test_create_external_reporter_without_optional_email(self):
        mutation_id = f"external-no-email-{uuid4()}"
        title = f"External reporter no email {uuid4()}"

        self.gql_client.execute(
            external_reporter_mutation(
                mutation_id=mutation_id,
                title=title,
                region_id=self.region.id,
                district_id=self.district.id,
                ward_id=self.ward.id,
                village_id=self.village.id,
                email=None,
            ),
            context=self.gql_context.get_request(),
        )

        mutation_log = MutationLog.objects.get(client_mutation_id=mutation_id)
        self.assertFalse(mutation_log.error)
        self.assertIsNone(Ticket.objects.get(title=title).external_reporter_email)

    def test_external_reporter_missing_required_fields_is_rejected(self):
        mutation_id = f"external-missing-{uuid4()}"
        title = f"External missing {uuid4()}"

        self.gql_client.execute(
            external_reporter_mutation(
                mutation_id=mutation_id,
                title=title,
                region_id=self.region.id,
                district_id=self.district.id,
                ward_id=self.ward.id,
                village_id=self.village.id,
                first_name="",
            ),
            context=self.gql_context.get_request(),
        )

        mutation_log = MutationLog.objects.get(client_mutation_id=mutation_id)
        self.assertTrue(mutation_log.error)
        self.assertFalse(Ticket.objects.filter(title=title).exists())

    def test_external_reporter_location_hierarchy_is_rejected(self):
        other_village = create_test_village(
            {"code": f"ERB-{uuid4().hex[:8].upper()}", "name": "Other External Village"}
        )
        payload = {
            **service_add_ticket_payload,
            "description": EXTERNAL_REPORTER_DESCRIPTION,
            "reporter_type": "external",
            "external_reporter_first_name": "Asha",
            "external_reporter_last_name": "Mrope",
            "external_reporter_phone": "+255712345678",
            "external_reporter_region_id": self.region.id,
            "external_reporter_district_id": other_village.parent.parent.id,
            "external_reporter_ward_id": self.ward.id,
            "external_reporter_village_id": self.village.id,
            "external_reporter_location_id": self.village.id,
        }

        with self.assertRaises(ValidationError):
            TicketService(self.user).create(payload)

    def test_external_reporter_phone_and_email_are_validated(self):
        payload = {
            **service_add_ticket_payload,
            "description": EXTERNAL_REPORTER_DESCRIPTION,
            "reporter_type": "external",
            "external_reporter_first_name": "Asha",
            "external_reporter_last_name": "Mrope",
            "external_reporter_phone": "1111111",
            "external_reporter_email": "not-an-email",
            "external_reporter_location_id": self.village.id,
        }

        with self.assertRaises(ValidationError):
            TicketService(self.user).create(payload)

    def test_update_external_reporter_details(self):
        ticket = self._create_external_ticket()
        update = {
            "id": ticket.id,
            "reporter_type": "external",
            "external_reporter_first_name": "Neema",
            "external_reporter_last_name": "Mrope",
            "external_reporter_phone": "+255 713 000 111",
            "external_reporter_email": "",
            "external_reporter_region_id": self.region.id,
            "external_reporter_district_id": self.district.id,
            "external_reporter_ward_id": self.ward.id,
            "external_reporter_village_id": self.village.id,
            "external_reporter_location_id": self.village.id,
        }

        result = TicketService(self.user).update(update)

        self.assertTrue(result["success"], result)
        ticket.refresh_from_db()
        self.assertEqual(ticket.external_reporter_first_name, "Neema")
        self.assertEqual(ticket.external_reporter_phone, "+255 713 000 111")
        self.assertIsNone(ticket.external_reporter_email)

    def test_change_none_reporter_to_external_reporter(self):
        result = TicketService(self.user).create({
            **service_add_ticket_payload,
            "description": EXTERNAL_REPORTER_DESCRIPTION,
        })
        self.assertTrue(result["success"], result)
        ticket = Ticket.objects.get(uuid=result["data"]["uuid"])

        result = TicketService(self.user).update({
            "id": ticket.id,
            "reporter_type": "external",
            "external_reporter_first_name": "Asha",
            "external_reporter_last_name": "Mrope",
            "external_reporter_phone": "+255 712 345 678",
            "external_reporter_region_id": self.region.id,
            "external_reporter_district_id": self.district.id,
            "external_reporter_ward_id": self.ward.id,
            "external_reporter_village_id": self.village.id,
            "external_reporter_location_id": self.village.id,
        })

        self.assertTrue(result["success"], result)
        ticket.refresh_from_db()
        self.assertEqual(ticket.external_reporter_first_name, "Asha")
        self.assertEqual(ticket.external_reporter_location, self.village)

    def test_change_external_reporter_to_none_clears_external_fields(self):
        ticket = self._create_external_ticket()

        result = TicketService(self.user).update({
            "id": ticket.id,
            "reporter_type": None,
        })

        self.assertTrue(result["success"], result)
        ticket.refresh_from_db()
        self.assertIsNone(ticket.reporter_type)
        self.assertIsNone(ticket.external_reporter_first_name)
        self.assertIsNone(ticket.external_reporter_location)

    def test_ticket_details_exposes_external_reporter_fields(self):
        ticket = self._create_external_ticket()
        query = f"""
        query {{
          tickets(id: "{ticket.id}") {{
            edges {{
              node {{
                reporterTypeName
                reporterFirstName
                reporterLastName
                externalReporterPhone
                externalReporterEmail
                externalReporterRegion {{ name }}
                externalReporterDistrict {{ name }}
                externalReporterWard {{ name }}
                externalReporterVillage {{ name }}
              }}
            }}
          }}
        }}
        """

        result = self.gql_client.execute(query, context=self.gql_context.get_request())

        self.assertNotIn("errors", result)
        node = result["data"]["tickets"]["edges"][0]["node"]
        self.assertEqual(node["reporterTypeName"], "external")
        self.assertEqual(node["reporterFirstName"], "Asha")
        self.assertEqual(node["reporterLastName"], "Mrope")
        self.assertEqual(node["externalReporterPhone"], "+255 712 345 678")
        self.assertEqual(node["externalReporterEmail"], "asha.mrope@example.org")
        self.assertEqual(node["externalReporterRegion"]["name"], self.region.name)
        self.assertEqual(node["externalReporterDistrict"]["name"], self.district.name)
        self.assertEqual(node["externalReporterWard"]["name"], self.ward.name)
        self.assertEqual(node["externalReporterVillage"]["name"], self.village.name)

    def _create_external_ticket(self):
        payload = {
            **service_add_ticket_payload,
            "description": EXTERNAL_REPORTER_DESCRIPTION,
            "reporter_type": "external",
            "external_reporter_first_name": "Asha",
            "external_reporter_last_name": "Mrope",
            "external_reporter_phone": "+255 712 345 678",
            "external_reporter_email": "asha.mrope@example.org",
            "external_reporter_region_id": self.region.id,
            "external_reporter_district_id": self.district.id,
            "external_reporter_ward_id": self.ward.id,
            "external_reporter_village_id": self.village.id,
            "external_reporter_location_id": self.village.id,
        }
        result = TicketService(self.user).create(payload)
        self.assertTrue(result["success"], result)
        return Ticket.objects.get(uuid=result["data"]["uuid"])
