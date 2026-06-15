from types import SimpleNamespace
from unittest.mock import patch

from django.core.exceptions import PermissionDenied
from django.test import SimpleTestCase
from graphene import Schema
from graphene.test import Client

from core.gql.gql_mutations.base_mutation import BaseMutation
from grievance_social_protection.gql_mutations import (
    CloseTicketMutation,
    CreateCommentMutation,
    CreateTicketMutation,
    ReopenTicketMutation,
    ResolveGrievanceByCommentMutation,
    UpdateTicketMutation,
)
from grievance_social_protection.gql_queries import check_ticket_perms
from grievance_social_protection.models import Ticket
from grievance_social_protection.schema import Mutation, Query


class UserWithRights:
    def __init__(self, *rights):
        self.rights = {int(right) for right in rights}

    def has_perms(self, permissions):
        return all(int(permission) in self.rights for permission in permissions)


class GQLTicketPermissionTestCase(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.gql_client = Client(Schema(query=Query, mutation=Mutation))

    def test_creator_cannot_invoke_update_actions(self):
        creator = UserWithRights(127000, 127001)

        CreateTicketMutation._authorize_create(
            creator,
            status=Ticket.TicketStatus.OPEN,
        )
        with self.assertRaises(PermissionDenied):
            CreateTicketMutation._authorize_create(
                creator,
                status=Ticket.TicketStatus.CLOSED,
            )
        self._assert_graphql_denied(creator, self._update_ticket())
        self._assert_graphql_denied(creator, self._reopen_ticket())
        self._assert_graphql_denied(creator, self._close_ticket())

    def test_view_only_user_cannot_invoke_any_action(self):
        view_only = UserWithRights(127000)

        self._assert_graphql_denied(view_only, self._update_ticket())
        self._assert_graphql_denied(view_only, self._create_comment())
        self._assert_graphql_denied(view_only, self._resolve_comment())
        self._assert_graphql_denied(view_only, self._reopen_ticket())
        self._assert_graphql_denied(view_only, self._close_ticket())

    def test_view_only_user_can_list_grievances(self):
        check_ticket_perms(
            SimpleNamespace(
                context=SimpleNamespace(user=UserWithRights(127000)),
            )
        )

    def test_update_only_processor_cannot_bypass_resolve_with_status(self):
        update_only = UserWithRights(127000, 127002)

        UpdateTicketMutation._authorize_update(
            update_only,
            status=Ticket.TicketStatus.IN_PROGRESS,
        )
        with self.assertRaises(PermissionDenied):
            UpdateTicketMutation._authorize_update(
                update_only,
                status=Ticket.TicketStatus.CLOSED,
            )
        with self.assertRaises(PermissionDenied):
            CloseTicketMutation._authorize_close(update_only)

    def test_processor_actions_require_their_specific_rights(self):
        self._assert_authorized(CreateCommentMutation, UserWithRights(127005))
        self._assert_authorized(
            ResolveGrievanceByCommentMutation,
            UserWithRights(127006),
        )
        self._assert_authorized(ReopenTicketMutation, UserWithRights(127002))
        CloseTicketMutation._authorize_close(UserWithRights(127002, 127006))

    def test_view_only_user_cannot_query_comments(self):
        result = self.gql_client.execute(
            """
            query {
              comments(first: 1) {
                edges { node { id } }
              }
            }
            """,
            context=SimpleNamespace(user=UserWithRights(127000)),
        )

        self.assertIn("errors", result)
        self.assertIsNone(result["data"]["comments"])

    def _assert_authorized(self, mutation_class, user):
        info = SimpleNamespace(context=SimpleNamespace(user=user))
        with patch.object(
            BaseMutation,
            "mutate_and_get_payload",
            return_value="authorized",
        ):
            result = mutation_class.mutate_and_get_payload(
                None,
                info,
                id="00000000-0000-0000-0000-000000000000",
                ticket_id="00000000-0000-0000-0000-000000000000",
            )
        self.assertEqual(result, "authorized")

    def _assert_graphql_denied(self, user, payload):
        result = self.gql_client.execute(
            payload,
            context=SimpleNamespace(user=user),
        )
        self.assertIn("errors", result)
        self.assertIn("authorized", result["errors"][0]["message"].lower())

    @staticmethod
    def _update_ticket():
        return """
        mutation {
          updateTicket(input: {
            id: "00000000-0000-0000-0000-000000000000"
            category: "Default"
            title: "Unauthorized update"
            status: OPEN
            clientMutationId: "permission-update"
          }) { clientMutationId }
        }
        """

    @staticmethod
    def _create_comment():
        return """
        mutation {
          createComment(input: {
            ticketId: "00000000-0000-0000-0000-000000000000"
            comment: "Unauthorized comment"
            clientMutationId: "permission-comment"
          }) { clientMutationId }
        }
        """

    @staticmethod
    def _resolve_comment():
        return """
        mutation {
          resolveGrievanceByComment(input: {
            id: "00000000-0000-0000-0000-000000000000"
            clientMutationId: "permission-resolve"
          }) { clientMutationId }
        }
        """

    @staticmethod
    def _reopen_ticket():
        return """
        mutation {
          reopenTicket(input: {
            id: "00000000-0000-0000-0000-000000000000"
            clientMutationId: "permission-reopen"
          }) { clientMutationId }
        }
        """

    @staticmethod
    def _close_ticket():
        return """
        mutation {
          closeTicket(input: {
            id: "00000000-0000-0000-0000-000000000000"
            comment: "Unauthorized close"
            clientMutationId: "permission-close"
          }) { clientMutationId }
        }
        """
