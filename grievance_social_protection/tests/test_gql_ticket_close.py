from uuid import uuid4

from core.models import MutationLog
from core.models.openimis_graphql_test_case import (
    BaseTestContext,
    openIMISGraphQLTestCase,
)
from core.test_helpers import create_test_interactive_user
from graphene import Schema
from graphene.test import Client

from grievance_social_protection.models import Comment, Ticket
from grievance_social_protection.schema import Mutation, Query
from grievance_social_protection.tests.gql_payloads import (
    gql_mutation_close_ticket,
    gql_mutation_close_ticket_by_user,
)
from grievance_social_protection.tests.test_helpers import create_ticket


class GQLTicketCloseTestCase(openIMISGraphQLTestCase):
    user = None

    category = "Default"
    title = "Closed Ticket Title"
    resolution = "2,5"
    priority = "Medium"
    date_of_incident = "2024-11-20"
    channel = "Channel A"
    flags = "Default"
    closing_comment = "Closing comment saved with the ticket."

    @classmethod
    def setUpClass(cls):
        super(GQLTicketCloseTestCase, cls).setUpClass()
        cls.user = create_test_interactive_user(username="user_authorized", roles=[7])

        gql_schema = Schema(query=Query, mutation=Mutation)
        cls.gql_client = Client(gql_schema)
        cls.gql_context = BaseTestContext(cls.user)

    def test_close_ticket_saves_comment_and_ticket_state(self):
        ticket = create_ticket(self.user)
        mutation_id = str(uuid4())
        payload = gql_mutation_close_ticket % (
            ticket.id,
            self.category,
            self.title,
            self.resolution,
            self.priority,
            self.date_of_incident,
            self.channel,
            self.flags,
            self.closing_comment,
            mutation_id,
        )

        _ = self.gql_client.execute(payload, context=self.gql_context.get_request())

        mutation_log = MutationLog.objects.get(client_mutation_id=mutation_id)
        ticket = Ticket.objects.get(id=ticket.id)
        comment = Comment.objects.get(ticket_id=ticket.id, is_resolution=True)

        self.assertFalse(mutation_log.error)
        self.assertEqual(ticket.status, Ticket.TicketStatus.CLOSED)
        self.assertEqual(ticket.title, self.title)
        self.assertEqual(ticket.category, self.category)
        self.assertEqual(ticket.resolution, self.resolution)
        self.assertEqual(ticket.priority, self.priority)
        self.assertEqual(str(ticket.date_of_incident), self.date_of_incident)
        self.assertEqual(ticket.flags, self.flags)
        self.assertEqual(comment.comment, self.closing_comment)
        self.assertIn(str(comment.id), ticket.json_ext["comment_ids"])

    def test_close_ticket_uses_authenticated_user_when_user_commenter_id_is_not_uuid(self):
        ticket = create_ticket(self.user)
        mutation_id = str(uuid4())
        closing_comment = "Closing comment saved for the authenticated user."
        payload = gql_mutation_close_ticket_by_user % (
            ticket.id,
            self.category,
            self.title,
            self.resolution,
            self.priority,
            self.date_of_incident,
            self.channel,
            self.flags,
            "1",
            closing_comment,
            mutation_id,
        )

        _ = self.gql_client.execute(payload, context=self.gql_context.get_request())

        mutation_log = MutationLog.objects.get(client_mutation_id=mutation_id)
        ticket = Ticket.objects.get(id=ticket.id)
        comment = Comment.objects.get(ticket_id=ticket.id, is_resolution=True)

        self.assertFalse(mutation_log.error)
        self.assertEqual(ticket.status, Ticket.TicketStatus.CLOSED)
        self.assertEqual(comment.commenter_id, str(self.user.id))
        self.assertEqual(comment.comment, closing_comment)
