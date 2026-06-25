from core.models import MutationLog
from graphene import Schema
from graphene.test import Client
from core.test_helpers import create_test_interactive_user
from grievance_social_protection.models import Ticket
from grievance_social_protection.schema import Query, Mutation
from grievance_social_protection.tests.data import VALID_TICKET_DESCRIPTION
from grievance_social_protection.tests.gql_payloads import gql_mutation_create_ticket
from core.models.openimis_graphql_test_case import openIMISGraphQLTestCase, BaseTestContext


class GQLTicketCreateTestCase(openIMISGraphQLTestCase):


    user = None

    category = None
    title = None
    resolution = None
    priority = None
    dateOfIncident = None
    channel = None
    flags = None

    @classmethod
    def setUpClass(cls):
        super(GQLTicketCreateTestCase, cls).setUpClass()
        cls.user = create_test_interactive_user(username='user_authorized', roles=[7])

        gql_schema = Schema(
            query=Query,
            mutation=Mutation
        )

        cls.category = "Default"
        cls.title = "TestMutationCreate"
        cls.resolution = "2,5"
        cls.priority = "Medium"
        cls.date_of_incident = "2024-11-20"
        cls.channel = "Channel A"
        cls.flags = "Default"

        cls.gql_client = Client(gql_schema)
        cls.gql_context = BaseTestContext(cls.user)

    def test_create_ticket_success(self):
        mutation_id = "99g453h5g92h04gh88"
        payload = gql_mutation_create_ticket % (
            self.category,
            self.title,
            VALID_TICKET_DESCRIPTION,
            self.resolution,
            self.priority,
            self.date_of_incident,
            self.channel,
            self.flags,
            mutation_id
        )

        _ = self.gql_client.execute(payload, context=self.gql_context.get_request())
        mutation_log = MutationLog.objects.get(client_mutation_id=mutation_id)
        self.assertFalse(mutation_log.error)
        tickets = Ticket.objects.filter(title=self.title)
        self.assertEquals(tickets.count(), 1)
        ticket = tickets.first()
        self.assertEquals(ticket.title, self.title)
        self.assertEquals(ticket.category, self.category)
        self.assertEquals(ticket.resolution, self.resolution)
        self.assertEquals(ticket.priority, self.priority)
        self.assertEquals(str(ticket.date_of_incident), self.date_of_incident)
        self.assertEquals(ticket.flags, self.flags)
        self.assertFalse(ticket.consent_given)

    def test_create_ticket_with_consent_checked(self):
        mutation_id = "99g453h5g92h04consent1"
        title = f"{self.title} Consent Given"
        payload = """
        mutation createTicket {
          createTicket(input: {
            category: "%s",
            title: "%s",
            description: "%s",
            resolution: "%s",
            priority: "%s",
            dateOfIncident: "%s",
            channel: "%s",
            flags: "%s",
            consentGiven: true,
            clientMutationId: "%s"
          }) {
            clientMutationId
          }
        }
        """ % (
            self.category,
            title,
            VALID_TICKET_DESCRIPTION,
            self.resolution,
            self.priority,
            self.date_of_incident,
            self.channel,
            self.flags,
            mutation_id,
        )

        _ = self.gql_client.execute(payload, context=self.gql_context.get_request())
        mutation_log = MutationLog.objects.get(client_mutation_id=mutation_id)
        self.assertFalse(mutation_log.error)
        ticket = Ticket.objects.get(title=title)
        self.assertTrue(ticket.consent_given)

        query = """
        query {
          tickets(clientMutationId: "%s", first: 1) {
            edges {
              node {
                consentGiven
              }
            }
          }
        }
        """ % mutation_id
        result = self.gql_client.execute(query, context=self.gql_context.get_request())
        self.assertTrue(result["data"]["tickets"]["edges"][0]["node"]["consentGiven"])

    def test_create_ticket_with_consent_unchecked(self):
        mutation_id = "99g453h5g92h04consent2"
        title = f"{self.title} Consent Not Given"
        payload = """
        mutation createTicket {
          createTicket(input: {
            category: "%s",
            title: "%s",
            description: "%s",
            resolution: "%s",
            priority: "%s",
            dateOfIncident: "%s",
            channel: "%s",
            flags: "%s",
            consentGiven: false,
            clientMutationId: "%s"
          }) {
            clientMutationId
          }
        }
        """ % (
            self.category,
            title,
            VALID_TICKET_DESCRIPTION,
            self.resolution,
            self.priority,
            self.date_of_incident,
            self.channel,
            self.flags,
            mutation_id,
        )

        _ = self.gql_client.execute(payload, context=self.gql_context.get_request())
        mutation_log = MutationLog.objects.get(client_mutation_id=mutation_id)
        self.assertFalse(mutation_log.error)
        ticket = Ticket.objects.get(title=title)
        self.assertFalse(ticket.consent_given)

        query = """
        query {
          tickets(clientMutationId: "%s", first: 1) {
            edges {
              node {
                consentGiven
              }
            }
          }
        }
        """ % mutation_id
        result = self.gql_client.execute(query, context=self.gql_context.get_request())
        self.assertFalse(result["data"]["tickets"]["edges"][0]["node"]["consentGiven"])

    def test_create_ticket_false_invalid_resolution_format(self):
        mutation_id = "65g453h4g92h04gh98"
        payload = gql_mutation_create_ticket % (
            self.category,
            self.title,
            VALID_TICKET_DESCRIPTION,
            "kjdslkdjslk",
            self.priority,
            self.date_of_incident,
            self.channel,
            self.flags,
            mutation_id
        )

        _ = self.gql_client.execute(payload, context=self.gql_context.get_request())
        mutation_log = MutationLog.objects.get(client_mutation_id=mutation_id)
        self.assertTrue(mutation_log.error)
        tickets = Ticket.objects.filter(title=self.title)
        self.assertEquals(tickets.count(), 0)

    def test_create_ticket_false_invalid_resolution_day_format(self):
        mutation_id = "62g453h4g92h04gh90"
        payload = gql_mutation_create_ticket % (
            self.category,
            self.title,
            VALID_TICKET_DESCRIPTION,
            "99,3",
            self.priority,
            self.date_of_incident,
            self.channel,
            self.flags,
            mutation_id
        )

        _ = self.gql_client.execute(payload, context=self.gql_context.get_request())
        mutation_log = MutationLog.objects.get(client_mutation_id=mutation_id)
        self.assertTrue(mutation_log.error)
        tickets = Ticket.objects.filter(title=self.title)
        self.assertEquals(tickets.count(), 0)

    def test_create_ticket_false_invalid_resolution_hour_format(self):
        mutation_id = "15g453h4g92h04gh92"
        payload = gql_mutation_create_ticket % (
            self.category,
            self.title,
            VALID_TICKET_DESCRIPTION,
            "4,66",
            self.priority,
            self.date_of_incident,
            self.channel,
            self.flags,
            mutation_id
        )

        _ = self.gql_client.execute(payload, context=self.gql_context.get_request())
        mutation_log = MutationLog.objects.get(client_mutation_id=mutation_id)
        self.assertTrue(mutation_log.error)
        tickets = Ticket.objects.filter(title=self.title)
        self.assertEquals(tickets.count(), 0)

    def test_create_ticket_false_description_below_minimum(self):
        mutation_id = "15g453h4g92h04desc1"
        payload = gql_mutation_create_ticket % (
            self.category,
            self.title,
            " ".join([f"word{i}" for i in range(1, 45)]),
            self.resolution,
            self.priority,
            self.date_of_incident,
            self.channel,
            self.flags,
            mutation_id
        )

        _ = self.gql_client.execute(payload, context=self.gql_context.get_request())
        mutation_log = MutationLog.objects.get(client_mutation_id=mutation_id)
        self.assertTrue(mutation_log.error)
        self.assertIn("Description must contain at least 45 words.", mutation_log.error)

    def test_create_ticket_allows_description_at_minimum(self):
        mutation_id = "15g453h4g92h04desc2"
        payload = gql_mutation_create_ticket % (
            self.category,
            f"{self.title} Description Minimum",
            " ".join([f"word{i}" for i in range(1, 46)]),
            self.resolution,
            self.priority,
            self.date_of_incident,
            self.channel,
            self.flags,
            mutation_id
        )

        _ = self.gql_client.execute(payload, context=self.gql_context.get_request())
        mutation_log = MutationLog.objects.get(client_mutation_id=mutation_id)
        self.assertFalse(mutation_log.error)

    def test_create_ticket_allows_description_between_limits(self):
        mutation_id = "15g453h4g92h04desc3"
        payload = gql_mutation_create_ticket % (
            self.category,
            f"{self.title} Description Between",
            " ".join([f"word{i}" for i in range(1, 91)]),
            self.resolution,
            self.priority,
            self.date_of_incident,
            self.channel,
            self.flags,
            mutation_id
        )

        _ = self.gql_client.execute(payload, context=self.gql_context.get_request())
        mutation_log = MutationLog.objects.get(client_mutation_id=mutation_id)
        self.assertFalse(mutation_log.error)

    def test_create_ticket_allows_description_at_maximum(self):
        mutation_id = "15g453h4g92h04desc4"
        payload = gql_mutation_create_ticket % (
            self.category,
            f"{self.title} Description Maximum",
            " ".join([f"word{i}" for i in range(1, 151)]),
            self.resolution,
            self.priority,
            self.date_of_incident,
            self.channel,
            self.flags,
            mutation_id
        )

        _ = self.gql_client.execute(payload, context=self.gql_context.get_request())
        mutation_log = MutationLog.objects.get(client_mutation_id=mutation_id)
        self.assertFalse(mutation_log.error)

    def test_create_ticket_false_description_above_maximum(self):
        mutation_id = "15g453h4g92h04desc5"
        payload = gql_mutation_create_ticket % (
            self.category,
            self.title,
            " ".join([f"word{i}" for i in range(1, 152)]),
            self.resolution,
            self.priority,
            self.date_of_incident,
            self.channel,
            self.flags,
            mutation_id
        )

        _ = self.gql_client.execute(payload, context=self.gql_context.get_request())
        mutation_log = MutationLog.objects.get(client_mutation_id=mutation_id)
        self.assertTrue(mutation_log.error)
        self.assertIn("Description must not exceed 150 words.", mutation_log.error)
