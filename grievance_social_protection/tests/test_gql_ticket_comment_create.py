from django.apps import apps
from django.test import TestCase

from graphene import Schema
from graphene.test import Client
from core.datetimes.ad_datetime import datetime
from core.models import Language, MutationLog, Role, RoleRight
from core.test_helpers import create_test_interactive_user
from grievance_social_protection.models import Comment
from grievance_social_protection.schema import Query, Mutation
from grievance_social_protection.tests.gql_payloads import (
    gql_mutation_create_comment,
    gql_mutation_create_comment_anonymous_user
)
from grievance_social_protection.tests.test_helpers import create_ticket
from core.models.openimis_graphql_test_case import openIMISGraphQLTestCase, BaseTestContext
from uuid import uuid4

class GQLTicketCommentCreateTestCase(openIMISGraphQLTestCase):


    user = None

    comment = None
    individual = None
    type = None
    existing_ticket = None

    @classmethod
    def setUpClass(cls):
        super(GQLTicketCommentCreateTestCase, cls).setUpClass()
        cls.__ensure_core_test_seed_data()
        cls.user = create_test_interactive_user(username='user_authorized', roles=[7])
        cls.existing_ticket = create_ticket(cls.user)

        gql_schema = Schema(
            query=Query,
            mutation=Mutation
        )

        cls.comment = "This is an awesome test comment!"
        cls.individual = cls.__create_individual()
        cls.type = "individual"

        cls.gql_client = Client(gql_schema)
        cls.gql_context = BaseTestContext(cls.user)

    def test_create_comment_individual_success(self):
        mutation_id = str(uuid4())
        payload = gql_mutation_create_comment % (
            self.comment,
            self.existing_ticket.id,
            self.individual.id,
            self.type,
            mutation_id
        )

        _ = self.gql_client.execute(payload, context=self.gql_context.get_request())
        mutation_log = MutationLog.objects.get(client_mutation_id=mutation_id)
        self.assertFalse(mutation_log.error)
        comment = Comment.objects.get(ticket_id=self.existing_ticket.id)
        self.assertEquals(comment.ticket.id, self.existing_ticket.id)
        self.assertEquals(comment.comment, self.comment)
        self.assertEquals(comment.commenter_id, str(self.individual.id))
        self.assertEquals(comment.is_resolution, False)
        self.assertIn(self.type, str(comment.commenter_type))

    def test_create_comment_anonymous_user_success(self):
        mutation_id = str(uuid4())
        payload = gql_mutation_create_comment_anonymous_user % (
            self.comment,
            self.existing_ticket.id,
            mutation_id
        )

        _ = self.gql_client.execute(payload, context=self.gql_context.get_request())
        mutation_log = MutationLog.objects.get(client_mutation_id=mutation_id)
        self.assertFalse(mutation_log.error)
        comment = Comment.objects.get(ticket_id=self.existing_ticket.id)
        self.assertEquals(comment.ticket.id, self.existing_ticket.id)
        self.assertEquals(comment.comment, self.comment)
        self.assertEquals(comment.commenter_id, None)
        self.assertEquals(comment.is_resolution, False)
        self.assertEquals(comment.commenter_type, None)

    def test_create_comment_assigned_user_without_permission_succeeds(self):
        assigned_user = self.__create_user_without_grievance_comment_permissions()
        assigned_ticket = self.__create_ticket_assigned_to(assigned_user)
        mutation_id = str(uuid4())
        payload = gql_mutation_create_comment_anonymous_user % (
            self.comment,
            assigned_ticket.id,
            mutation_id
        )

        response = self.gql_client.execute(
            payload,
            context=BaseTestContext(assigned_user).get_request(),
        )
        self.assertFalse(response.get("errors"))
        mutation_log = MutationLog.objects.get(client_mutation_id=mutation_id)
        self.assertFalse(mutation_log.error)
        self.assertTrue(Comment.objects.filter(ticket_id=assigned_ticket.id).exists())

    def test_create_comment_assigned_user_cannot_comment_on_another_ticket(self):
        assigned_user = self.__create_user_without_grievance_comment_permissions()
        self.__create_ticket_assigned_to(assigned_user)
        other_ticket = create_ticket(self.user)

        mutation_id = str(uuid4())
        payload = gql_mutation_create_comment_anonymous_user % (
            self.comment,
            other_ticket.id,
            mutation_id
        )

        response = self.gql_client.execute(
            payload,
            context=BaseTestContext(assigned_user).get_request(),
        )
        self.assertIn("unauthorized", response["errors"][0]["message"].lower())
        self.assertFalse(
            MutationLog.objects.filter(client_mutation_id=mutation_id).exists()
        )
        self.assertFalse(Comment.objects.filter(ticket_id=other_ticket.id).exists())

    def test_create_comment_unassigned_user_without_permission_is_unauthorized(self):
        unassigned_user = self.__create_user_without_grievance_comment_permissions()
        other_ticket = create_ticket(self.user)
        mutation_id = str(uuid4())
        payload = gql_mutation_create_comment_anonymous_user % (
            self.comment,
            other_ticket.id,
            mutation_id
        )

        response = self.gql_client.execute(
            payload,
            context=BaseTestContext(unassigned_user).get_request(),
        )
        self.assertIn("unauthorized", response["errors"][0]["message"].lower())
        self.assertFalse(
            MutationLog.objects.filter(client_mutation_id=mutation_id).exists()
        )
        self.assertFalse(Comment.objects.filter(ticket_id=other_ticket.id).exists())

    def test_query_comments_assigned_user_without_permission_is_denied(self):
        assigned_user = self.__create_user_without_grievance_comment_permissions()
        assigned_ticket = self.__create_ticket_assigned_to(assigned_user)
        own_comment = Comment(
            ticket=assigned_ticket,
            comment=f"Assigned ticket comment {uuid4()}",
        )
        own_comment.save(user=self.user)

        payload = """
        query {
          comments(first: 20) {
            edges {
              node {
                id
                comment
              }
            }
          }
        }
        """

        response = self.gql_client.execute(
            payload,
            context=BaseTestContext(assigned_user).get_request(),
        )
        self.assertTrue(response.get("errors"))
        self.assertIsNone(response["data"]["comments"])

    @classmethod
    def __create_individual(cls):
        individual_model = apps.get_model('individual', 'Individual')

        add_individual_payload = {
            'first_name': 'TestFN',
            'last_name': 'TestLN',
            'dob': datetime.now(),
            'json_ext': {
                'key': 'value',
                'key2': 'value2'
            }
        }

        object_data = {
            **add_individual_payload
        }

        individual = individual_model(**object_data)
        individual.save(username=cls.user.username)

        return individual

    def __create_user_without_grievance_comment_permissions(self):
        role = Role.objects.create(
            name=f"No comment {uuid4()}",
            is_blocked=False,
            is_system=False,
            audit_user_id=self.user.id_for_audit,
        )
        return create_test_interactive_user(
            username=f"u_{uuid4().hex[:20]}",
            roles=[role.id],
        )

    def __create_ticket_assigned_to(self, user):
        ticket = create_ticket(self.user)
        ticket.attending_staff = user
        ticket.save(user=self.user)
        return ticket

    @classmethod
    def __ensure_core_test_seed_data(cls):
        Language.objects.get_or_create(
            code="en",
            defaults={
                "name": "English",
                "sort_order": 1,
            },
        )
        role, _ = Role.objects.get_or_create(
            id=7,
            defaults={
                "name": "Grievance test role",
                "is_blocked": False,
                "is_system": False,
                "audit_user_id": -1,
            },
        )
        for right_id in (127004, 127005):
            RoleRight.objects.get_or_create(
                role=role,
                right_id=right_id,
                defaults={"audit_user_id": -1},
            )
