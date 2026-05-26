from django.test import TestCase
from core.models import MutationLog
from graphene import Schema
from graphene.test import Client
from core.test_helpers import create_test_interactive_user
from grievance_social_protection.models import (
    Comment,
    Ticket
)
from grievance_social_protection.schema import Query, Mutation
from grievance_social_protection.tests.gql_payloads import gql_mutation_resolve_ticket_by_comment
from grievance_social_protection.tests.test_helpers import (
    create_ticket,
    create_comment_for_existing_ticket
)
from core.models.openimis_graphql_test_case import openIMISGraphQLTestCase, BaseTestContext


class GQLTicketResolveByCommentTestCase(openIMISGraphQLTestCase):


    user = None

    existing_ticket = None
    existing_comment = None
    status = "CLOSED"

    @classmethod
    def setUpClass(cls):
        super(GQLTicketResolveByCommentTestCase, cls).setUpClass()
        cls.user = create_test_interactive_user(username='user_authorized', roles=[7])
        cls.existing_ticket = create_ticket(cls.user)
        cls.existing_comment = create_comment_for_existing_ticket(cls.user, cls.existing_ticket)

        gql_schema = Schema(
            query=Query,
            mutation=Mutation
        )

        cls.gql_client = Client(gql_schema)
        cls.gql_context = BaseTestContext(cls.user)

    def test_resolve_ticket_by_comment_success(self):
        mutation_id = "99g154h5b92h11sd33"
        payload = gql_mutation_resolve_ticket_by_comment % (
            self.existing_comment.id,
            mutation_id
        )

        _ = self.gql_client.execute(payload, context=self.gql_context.get_request())
        mutation_log = MutationLog.objects.get(client_mutation_id=mutation_id)
        comment = Comment.objects.get(id=self.existing_comment.id)
        ticket = Ticket.objects.get(id=self.existing_ticket.id)
        self.assertFalse(mutation_log.error)
        self.assertEquals(comment.is_resolution, True)
        self.assertEquals(ticket.status, self.status)
        self.assertIn(str(comment.id), ticket.json_ext["comment_ids"])
