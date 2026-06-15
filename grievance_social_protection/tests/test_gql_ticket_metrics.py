from datetime import timedelta
from types import SimpleNamespace

from django.utils import timezone
from graphene import Schema
from graphene.test import Client

from core.models.openimis_graphql_test_case import (
    BaseTestContext,
    openIMISGraphQLTestCase,
)
from core.test_helpers import create_test_interactive_user
from grievance_social_protection.models import Comment, GrievanceCategory, Ticket
from grievance_social_protection.schema import Mutation, Query


class UserWithRights:
    is_authenticated = True

    def __init__(self, *rights):
        self.rights = {int(right) for right in rights}

    def has_perms(self, permissions):
        return all(int(permission) in self.rights for permission in permissions)


class GQLTicketMetricsTestCase(openIMISGraphQLTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = create_test_interactive_user(
            username="user_grievance_metrics",
            roles=[7],
        )
        cls.gql_client = Client(Schema(query=Query, mutation=Mutation))
        cls.gql_context = BaseTestContext(cls.user)

    def setUp(self):
        self.now = timezone.now()
        self.today = self.now.date()
        self.timeline_category = self._create_category("Metrics Timeline", 7)
        self.no_timeline_category = self._create_category("Metrics No Timeline", 0)
        self.tickets = {
            "open_on_time": self._create_ticket(
                code="MT-OPEN-OK",
                category=self.timeline_category.name,
                status=Ticket.TicketStatus.OPEN,
                created_at=self.now - timedelta(hours=5),
            ),
            "open_overdue": self._create_ticket(
                code="MT-OPEN-LATE",
                category=self.timeline_category.name,
                status=Ticket.TicketStatus.IN_PROGRESS,
                created_at=self.now - timedelta(days=3, hours=4),
                due_date=self.today - timedelta(days=1),
            ),
            "closed_on_time": self._create_ticket(
                code="MT-CLOSE-OK",
                category=self.timeline_category.name,
                status=Ticket.TicketStatus.CLOSED,
                created_at=self.now - timedelta(days=3),
                due_date=self.today - timedelta(days=1),
                closed_at=self.now - timedelta(days=2),
            ),
            "closed_late": self._create_ticket(
                code="MT-CLOSE-LATE",
                category=self.timeline_category.name,
                status=Ticket.TicketStatus.CLOSED,
                created_at=self.now - timedelta(days=5),
                due_date=self.today - timedelta(days=3),
                closed_at=self.now - timedelta(days=1),
            ),
            "no_timeline": self._create_ticket(
                code="MT-NO-DUE",
                category=self.no_timeline_category.name,
                status=Ticket.TicketStatus.RECEIVED,
                created_at=self.now - timedelta(hours=2),
            ),
            "reopened": self._create_ticket(
                code="MT-REOPENED",
                category=self.timeline_category.name,
                status=Ticket.TicketStatus.OPEN,
                created_at=self.now - timedelta(days=10),
                due_date=self.today - timedelta(days=7),
                prior_closed_at=self.now - timedelta(days=5),
            ),
        }

    def _create_category(self, name, timeline):
        category = GrievanceCategory(
            name=name,
            timeline=timeline,
            is_active=True,
            user_created=self.user,
            user_updated=self.user,
        )
        category.save(username=self.user.username)
        return category

    def _create_ticket(
        self,
        *,
        code,
        category,
        status,
        created_at,
        due_date=None,
        closed_at=None,
        prior_closed_at=None,
    ):
        ticket = Ticket(
            code=code,
            category=category,
            title=f"{code} title",
            status=status,
            due_date=due_date,
            priority="Normal",
            channel="Web",
            flags="Default",
        )
        ticket.save(user=self.user)
        Ticket.objects.filter(id=ticket.id).update(
            date_created=created_at,
            date_updated=closed_at or prior_closed_at or created_at,
        )
        ticket.refresh_from_db()

        comment_date = closed_at or prior_closed_at
        if comment_date:
            comment = Comment(
                ticket=ticket,
                comment=f"{code} resolution",
                is_resolution=bool(closed_at),
            )
            comment.save(user=self.user)
            Comment.objects.filter(id=comment.id).update(date_created=comment_date)
        return ticket

    def _query_ticket(self, code):
        response = self.gql_client.execute(
            f"""
            query {{
              tickets(code: "{code}", first: 1) {{
                edges {{
                  node {{
                    code
                    expectedResolutionDate
                    closedAt
                    overdue
                    timelineStatus
                    timeTakenSeconds
                  }}
                }}
              }}
            }}
            """,
            context=self.gql_context.get_request(),
        )
        self.assertNotIn("errors", response)
        return response["data"]["tickets"]["edges"][0]["node"]

    def test_metrics_cover_open_closed_late_and_missing_timeline(self):
        open_on_time = self._query_ticket("MT-OPEN-OK")
        self.assertFalse(open_on_time["overdue"])
        self.assertEqual(open_on_time["timelineStatus"], "ON_TIME")
        self.assertEqual(
            open_on_time["expectedResolutionDate"],
            (
                self.tickets["open_on_time"].date_created.date()
                + timedelta(days=7)
            ).isoformat(),
        )
        self.assertAlmostEqual(open_on_time["timeTakenSeconds"], 5 * 3600, delta=120)

        open_overdue = self._query_ticket("MT-OPEN-LATE")
        self.assertTrue(open_overdue["overdue"])
        self.assertEqual(open_overdue["timelineStatus"], "OVERDUE")
        self.assertAlmostEqual(
            open_overdue["timeTakenSeconds"],
            (3 * 24 + 4) * 3600,
            delta=120,
        )

        closed_on_time = self._query_ticket("MT-CLOSE-OK")
        self.assertFalse(closed_on_time["overdue"])
        self.assertEqual(closed_on_time["timelineStatus"], "ON_TIME")
        self.assertAlmostEqual(closed_on_time["timeTakenSeconds"], 24 * 3600, delta=5)

        closed_late = self._query_ticket("MT-CLOSE-LATE")
        self.assertFalse(closed_late["overdue"])
        self.assertEqual(closed_late["timelineStatus"], "RESOLVED_LATE")
        self.assertAlmostEqual(closed_late["timeTakenSeconds"], 4 * 24 * 3600, delta=5)

        no_timeline = self._query_ticket("MT-NO-DUE")
        self.assertIsNone(no_timeline["expectedResolutionDate"])
        self.assertIsNone(no_timeline["overdue"])
        self.assertEqual(no_timeline["timelineStatus"], "N_A")
        self.assertAlmostEqual(no_timeline["timeTakenSeconds"], 2 * 3600, delta=120)

    def test_reopened_ticket_uses_current_elapsed_time(self):
        reopened = self._query_ticket("MT-REOPENED")
        self.assertIsNone(reopened["closedAt"])
        self.assertTrue(reopened["overdue"])
        self.assertEqual(reopened["timelineStatus"], "OVERDUE")
        self.assertAlmostEqual(
            reopened["timeTakenSeconds"],
            10 * 24 * 3600,
            delta=120,
        )

    def test_overdue_filter_sorting_and_pagination(self):
        overdue_response = self.gql_client.execute(
            """
            query {
              tickets(overdue: true, first: 20, orderBy: ["-_time_taken_duration"]) {
                totalCount
                edges { node { code overdue timeTakenSeconds } }
              }
            }
            """,
            context=self.gql_context.get_request(),
        )
        self.assertNotIn("errors", overdue_response)
        overdue_rows = overdue_response["data"]["tickets"]["edges"]
        metric_codes = [
            row["node"]["code"]
            for row in overdue_rows
            if row["node"]["code"].startswith("MT-")
        ]
        self.assertEqual(metric_codes[:2], ["MT-REOPENED", "MT-OPEN-LATE"])
        self.assertTrue(all(row["node"]["overdue"] for row in overdue_rows))

        page_response = self.gql_client.execute(
            """
            query {
              tickets(code_Istartswith: "MT-", first: 2, orderBy: ["-_overdue_sort", "code"]) {
                totalCount
                edges { node { code overdue } }
                pageInfo { hasNextPage endCursor }
              }
            }
            """,
            context=self.gql_context.get_request(),
        )
        self.assertNotIn("errors", page_response)
        connection = page_response["data"]["tickets"]
        self.assertEqual(connection["totalCount"], 6)
        self.assertEqual(len(connection["edges"]), 2)
        self.assertTrue(connection["pageInfo"]["hasNextPage"])
        self.assertTrue(all(row["node"]["overdue"] for row in connection["edges"]))

    def test_closure_report_includes_overdue_and_time_taken(self):
        response = self.gql_client.execute(
            """
            query {
              grievanceReports(report: "CLOSURE_TIMELINE") {
                ticketCode
                dueDate
                overdue
                timelineStatus
                timeTakenSeconds
              }
            }
            """,
            context=self.gql_context.get_request(),
        )
        self.assertNotIn("errors", response)
        rows = {
            row["ticketCode"]: row
            for row in response["data"]["grievanceReports"]
            if row["ticketCode"] in {"MT-CLOSE-OK", "MT-CLOSE-LATE"}
        }
        self.assertEqual(rows["MT-CLOSE-OK"]["timelineStatus"], "ON_TIME")
        self.assertFalse(rows["MT-CLOSE-OK"]["overdue"])
        self.assertEqual(rows["MT-CLOSE-LATE"]["timelineStatus"], "RESOLVED_LATE")
        self.assertFalse(rows["MT-CLOSE-LATE"]["overdue"])
        self.assertAlmostEqual(
            rows["MT-CLOSE-LATE"]["timeTakenSeconds"],
            4 * 24 * 3600,
            delta=5,
        )

    def test_metrics_follow_ticket_query_permissions(self):
        response = self.gql_client.execute(
            """
            query {
              tickets(first: 1) {
                edges { node { code overdue timelineStatus timeTakenSeconds } }
              }
            }
            """,
            context=SimpleNamespace(user=UserWithRights()),
        )
        self.assertIn("errors", response)
