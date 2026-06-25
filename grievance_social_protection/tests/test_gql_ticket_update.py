from types import SimpleNamespace

from django.core.exceptions import PermissionDenied
from django.test import SimpleTestCase
from core.models import MutationLog
from graphene import Schema
from graphene.test import Client
from core.test_helpers import create_test_interactive_user
from grievance_social_protection.apps import TicketConfig
from grievance_social_protection.models import Ticket
from grievance_social_protection.schema import Query, Mutation
from grievance_social_protection.gql_mutations import UpdateTicketMutation
from grievance_social_protection.tests.data import VALID_TICKET_DESCRIPTION
from grievance_social_protection.tests.gql_payloads import gql_mutation_update_ticket
from grievance_social_protection.tests.test_helpers import create_ticket
from core.models.openimis_graphql_test_case import openIMISGraphQLTestCase, BaseTestContext


class UserWithRights:
    def __init__(self, rights):
        self.rights = set(rights)

    def has_perms(self, permissions):
        return any(int(permission) in self.rights for permission in permissions)


class UpdateTicketAuthorizationTestCase(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.gql_client = Client(Schema(query=Query, mutation=Mutation))

    def test_update_ticket_rejects_creator_without_update_permission(self):
        self._assert_update_authorization_error({127000, 127001})

    def test_update_ticket_rejects_view_only_user(self):
        self._assert_update_authorization_error({127000})

    def test_update_ticket_allows_user_with_update_permission(self):
        UpdateTicketMutation._authorize_update(
            UserWithRights({127002}),
            title="Authorized update",
            status=Ticket.TicketStatus.IN_PROGRESS,
        )

    def test_update_ticket_permission_fails_closed_when_config_is_empty(self):
        configured_permissions = TicketConfig.gql_mutation_update_tickets_perms
        TicketConfig.gql_mutation_update_tickets_perms = []
        try:
            with self.assertRaises(PermissionDenied):
                UpdateTicketMutation._authorize_update(UserWithRights(set()))
            UpdateTicketMutation._authorize_update(UserWithRights({127002}))
        finally:
            TicketConfig.gql_mutation_update_tickets_perms = configured_permissions

    def _assert_update_authorization_error(self, rights):
        payload = gql_mutation_update_ticket % (
            "00000000-0000-0000-0000-000000000000",
            "Default",
            "Unauthorized update",
            "2,5",
            "Medium",
            "2024-11-20",
            "Channel A",
            "Default",
            "OPEN",
            "unauthorized-update",
        )
        context = SimpleNamespace(user=UserWithRights(rights))

        result = self.gql_client.execute(payload, context=context)

        self.assertIn("errors", result)
        self.assertIn("authorized", result["errors"][0]["message"].lower())
        self.assertIsNone(result["data"]["updateTicket"])


class GQLTicketUpdateTestCase(openIMISGraphQLTestCase):


    user = None

    category = None
    title = None
    resolution = None
    priority = None
    dateOfIncident = None
    channel = None
    flags = None
    status = None
    existing_ticket = None

    @classmethod
    def setUpClass(cls):
        super(GQLTicketUpdateTestCase, cls).setUpClass()
        cls.user = create_test_interactive_user(username='user_authorized', roles=[7])
        cls.existing_ticket = create_ticket(cls.user)

        gql_schema = Schema(
            query=Query,
            mutation=Mutation
        )

        cls.category = "Default"
        cls.title = "TestMutationUpdate"
        cls.resolution = "2,5"
        cls.priority = "Medium"
        cls.date_of_incident = "2024-11-20"
        cls.channel = "Channel A"
        cls.flags = "Default"
        cls.status = "OPEN"

        cls.gql_client = Client(gql_schema)
        cls.gql_context = BaseTestContext(cls.user)

    def test_update_ticket_success(self):
        mutation_id = "99g453h5g92h04xc66"
        payload = gql_mutation_update_ticket % (
            self.existing_ticket.id,
            self.category,
            self.title,
            self.resolution,
            self.priority,
            self.date_of_incident,
            self.channel,
            self.flags,
            self.status,
            mutation_id
        )

        _ = self.gql_client.execute(payload, context=self.gql_context.get_request())
        mutation_log = MutationLog.objects.get(client_mutation_id=mutation_id)
        self.assertFalse(mutation_log.error)
        ticket = Ticket.objects.get(id=self.existing_ticket.id)
        self.assertEquals(ticket.title, self.title)
        self.assertEquals(ticket.category, self.category)
        self.assertEquals(ticket.resolution, self.resolution)
        self.assertEquals(ticket.priority, self.priority)
        self.assertEquals(str(ticket.date_of_incident), self.date_of_incident)
        self.assertEquals(ticket.flags, self.flags)
        self.assertEquals(ticket.status, self.status)

    def test_update_ticket_accepts_unchanged_consent(self):
        mutation_id = "99g453h5g92h04consent3"
        payload = """
        mutation updateTicket {
          updateTicket(input: {
            id: "%s",
            category: "%s",
            consentGiven: false,
            clientMutationId: "%s"
          }) {
            clientMutationId
          }
        }
        """ % (
            self.existing_ticket.id,
            self.existing_ticket.category,
            mutation_id,
        )

        _ = self.gql_client.execute(payload, context=self.gql_context.get_request())
        mutation_log = MutationLog.objects.get(client_mutation_id=mutation_id)
        self.assertFalse(mutation_log.error)
        ticket = Ticket.objects.get(id=self.existing_ticket.id)
        self.assertFalse(ticket.consent_given)

    def test_update_ticket_rejects_consent_change(self):
        mutation_id = "99g453h5g92h04consent4"
        payload = """
        mutation updateTicket {
          updateTicket(input: {
            id: "%s",
            category: "%s",
            consentGiven: true,
            clientMutationId: "%s"
          }) {
            clientMutationId
          }
        }
        """ % (
            self.existing_ticket.id,
            self.existing_ticket.category,
            mutation_id,
        )

        _ = self.gql_client.execute(payload, context=self.gql_context.get_request())
        mutation_log = MutationLog.objects.get(client_mutation_id=mutation_id)
        self.assertTrue(mutation_log.error)
        self.assertIn("Consent cannot be changed after submission.", mutation_log.error)
        ticket = Ticket.objects.get(id=self.existing_ticket.id)
        self.assertFalse(ticket.consent_given)

    def test_update_ticket_false_invalid_resolution_format(self):
        mutation_id = "65g453h4g92h04yf43"
        payload = gql_mutation_update_ticket % (
            self.existing_ticket.id,
            self.category,
            self.title,
            "kjdslkdjslk",
            self.priority,
            self.date_of_incident,
            self.channel,
            self.flags,
            self.status,
            mutation_id
        )

        _ = self.gql_client.execute(payload, context=self.gql_context.get_request())
        mutation_log = MutationLog.objects.get(client_mutation_id=mutation_id)
        self.assertTrue(mutation_log.error)
        ticket = Ticket.objects.get(id=self.existing_ticket.id)
        self.assertNotEquals(ticket.title, self.title)

    def test_update_ticket_false_invalid_resolution_day_format(self):
        mutation_id = "65g453h4g92h0zx54"
        payload = gql_mutation_update_ticket % (
            self.existing_ticket.id,
            self.category,
            self.title,
            "99,3",
            self.priority,
            self.date_of_incident,
            self.channel,
            self.flags,
            self.status,
            mutation_id
        )

        _ = self.gql_client.execute(payload, context=self.gql_context.get_request())
        mutation_log = MutationLog.objects.get(client_mutation_id=mutation_id)
        self.assertTrue(mutation_log.error)
        ticket = Ticket.objects.get(id=self.existing_ticket.id)
        self.assertNotEquals(ticket.title, self.title)

    def test_update_ticket_false_invalid_resolution_hour_format(self):
        mutation_id = "65g453h4g92h04wl32"
        payload = gql_mutation_update_ticket % (
            self.existing_ticket.id,
            self.category,
            self.title,
            "4,66",
            self.priority,
            self.date_of_incident,
            self.channel,
            self.flags,
            self.status,
            mutation_id
        )

        _ = self.gql_client.execute(payload, context=self.gql_context.get_request())
        mutation_log = MutationLog.objects.get(client_mutation_id=mutation_id)
        self.assertTrue(mutation_log.error)
        ticket = Ticket.objects.get(id=self.existing_ticket.id)
        self.assertNotEquals(ticket.title, self.title)

    def test_update_ticket_rejects_description_change(self):
        mutation_id = "65g453h4g92h04desc"
        changed_description = " ".join([f"changed{i}" for i in range(1, 46)])
        payload = """
        mutation updateTicket {
          updateTicket(input: {
            id: "%s",
            category: "%s",
            description: "%s",
            clientMutationId: "%s"
          }) {
            clientMutationId
          }
        }
        """ % (
            self.existing_ticket.id,
            self.existing_ticket.category,
            changed_description,
            mutation_id,
        )

        _ = self.gql_client.execute(payload, context=self.gql_context.get_request())
        mutation_log = MutationLog.objects.get(client_mutation_id=mutation_id)
        self.assertTrue(mutation_log.error)
        self.assertIn("Description cannot be changed after submission.", mutation_log.error)
        ticket = Ticket.objects.get(id=self.existing_ticket.id)
        self.assertEqual(ticket.description, VALID_TICKET_DESCRIPTION)
