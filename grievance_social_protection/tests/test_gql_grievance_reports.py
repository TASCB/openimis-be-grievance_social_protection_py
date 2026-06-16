from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.utils import timezone
from graphene import Schema
from graphene.test import Client

from core.models.openimis_graphql_test_case import (
    BaseTestContext,
    openIMISGraphQLTestCase,
)
from core.test_helpers import create_test_interactive_user
from grievance_social_protection.models import (
    GrievanceCategory,
    GrievanceChannel,
    Ticket,
)
from grievance_social_protection.schema import Mutation, Query


def _today():
    return timezone.now().date()


class GQLGrievanceReportsTestCase(openIMISGraphQLTestCase):
    @classmethod
    def setUpClass(cls):
        super(GQLGrievanceReportsTestCase, cls).setUpClass()
        cls.user = create_test_interactive_user(
            username="user_grievance_reports",
            roles=[7],
        )
        cls.gql_client = Client(Schema(query=Query, mutation=Mutation))
        cls.gql_context = BaseTestContext(cls.user)

    def _create_category(self, name):
        category = GrievanceCategory(
            name=name,
            timeline=0,
            is_active=True,
            user_created=self.user,
            user_updated=self.user,
        )
        category.save(username=self.user.username)
        return category

    def _create_channel(self, name):
        channel = GrievanceChannel(
            name=name,
            is_active=True,
            user_created=self.user,
            user_updated=self.user,
        )
        channel.save(username=self.user.username)
        return channel

    def _create_ticket(self, category, channel="Report Channel", status=None, due_date=None):
        ticket = Ticket(
            category=category,
            title=f"{category} ticket",
            resolution="2,0",
            priority="Normal",
            date_of_incident=_today(),
            channel=channel,
            flags="Default",
            due_date=due_date,
        )
        if status:
            ticket.status = status
        ticket.save(user=self.user)
        return ticket

    def test_category_report_counts_tickets_by_category(self):
        self._create_ticket("Report Category A")
        self._create_ticket("Report Category B")
        today = _today().isoformat()

        response = self.gql_client.execute(
            f"""
            query {{
              grievanceReports(report: "CATEGORY", dateFrom: "{today}", dateTo: "{today}") {{
                category
                count
              }}
            }}
            """,
            context=self.gql_context.get_request(),
        )

        self.assertNotIn("errors", response)
        rows = {row["category"]: row["count"] for row in response["data"]["grievanceReports"]}
        self.assertEqual(rows["Report Category A"], 1)
        self.assertEqual(rows["Report Category B"], 1)

    def test_category_report_includes_configured_categories_without_tickets(self):
        self._create_category("Report Category With Ticket")
        self._create_category("Report Category Without Ticket")
        self._create_ticket("Report Category With Ticket")
        today = _today().isoformat()

        response = self.gql_client.execute(
            f"""
            query {{
              grievanceReports(report: "CATEGORY", dateFrom: "{today}", dateTo: "{today}") {{
                category
                count
              }}
            }}
            """,
            context=self.gql_context.get_request(),
        )

        self.assertNotIn("errors", response)
        rows = {row["category"]: row["count"] for row in response["data"]["grievanceReports"]}
        self.assertEqual(rows["Report Category With Ticket"], 1)
        self.assertEqual(rows["Report Category Without Ticket"], 0)

    def test_category_report_lists_maswali_na_maoni_last(self):
        self._create_category("A Report Category")
        self._create_category("Maswali na Maoni")
        self._create_category("Z Report Category")
        self._create_ticket("ZZ Ticket-only Category")
        today = _today().isoformat()

        response = self.gql_client.execute(
            f"""
            query {{
              grievanceReports(report: "CATEGORY", dateFrom: "{today}", dateTo: "{today}") {{
                category
              }}
            }}
            """,
            context=self.gql_context.get_request(),
        )

        self.assertNotIn("errors", response)
        categories = [
            row["category"] for row in response["data"]["grievanceReports"]
        ]
        self.assertIn("Maswali na Maoni", categories)
        self.assertEqual(categories[-1], "Maswali na Maoni")

    def test_channel_report_includes_configured_channels_without_tickets(self):
        self._create_channel("Report Channel With Ticket")
        self._create_channel("Report Channel Without Ticket")
        self._create_ticket("Report Channel Category", channel="Report Channel With Ticket")
        today = _today().isoformat()

        response = self.gql_client.execute(
            f"""
            query {{
              grievanceReports(report: "CHANNEL", dateFrom: "{today}", dateTo: "{today}") {{
                channel
                count
              }}
            }}
            """,
            context=self.gql_context.get_request(),
        )

        self.assertNotIn("errors", response)
        rows = {row["channel"]: row["count"] for row in response["data"]["grievanceReports"]}
        self.assertEqual(rows["Report Channel With Ticket"], 1)
        self.assertEqual(rows["Report Channel Without Ticket"], 0)

    def test_resolution_status_report_summarizes_status_groups(self):
        self._create_ticket("Report Status Received")
        self._create_ticket("Report Status Open", status=Ticket.TicketStatus.OPEN)
        self._create_ticket("Report Status Closed", status=Ticket.TicketStatus.CLOSED)
        self._create_ticket("Report Status In Progress", status=Ticket.TicketStatus.IN_PROGRESS)
        self._create_ticket("Report Status Resolved", status=Ticket.TicketStatus.RESOLVED)
        today = _today().isoformat()

        response = self.gql_client.execute(
            f"""
            query {{
              grievanceReports(
                report: "RESOLUTION_STATUS",
                dateFrom: "{today}",
                dateTo: "{today}"
              ) {{
                status
                count
              }}
            }}
            """,
            context=self.gql_context.get_request(),
        )

        self.assertNotIn("errors", response)
        report_rows = response["data"]["grievanceReports"]
        self.assertEqual(
            [row["status"] for row in report_rows],
            ["Received", "Unresolved", "Closed"],
        )
        rows = {row["status"]: row["count"] for row in report_rows}
        self.assertEqual(rows["Received"], 5)
        self.assertEqual(rows["Unresolved"], 3)
        self.assertEqual(rows["Closed"], 2)

    def test_resolution_status_report_handles_only_received_grievances(self):
        self._create_ticket("Report Status Only Received")
        today = _today().isoformat()

        response = self.gql_client.execute(
            f"""
            query {{
              grievanceReports(
                report: "RESOLUTION_STATUS",
                dateFrom: "{today}",
                dateTo: "{today}"
              ) {{
                status
                count
              }}
            }}
            """,
            context=self.gql_context.get_request(),
        )

        self.assertNotIn("errors", response)
        report_rows = response["data"]["grievanceReports"]
        self.assertEqual(
            [row["status"] for row in report_rows],
            ["Received", "Unresolved", "Closed"],
        )
        rows = {row["status"]: row["count"] for row in report_rows}
        self.assertEqual(rows["Received"], 1)
        self.assertEqual(rows["Unresolved"], 1)
        self.assertEqual(rows["Closed"], 0)

    def test_paa_report_filters_by_grievance_count(self):
        tickets = [self._create_ticket("PAA One")]
        tickets.extend(self._create_ticket("PAA Three") for _ in range(3))

        paa_locations = [
            SimpleNamespace(uuid="paa-zero", name="PAA Zero"),
            SimpleNamespace(uuid="paa-one", name="PAA One"),
            SimpleNamespace(uuid="paa-three", name="PAA Three"),
        ]

        def ticket_paa(ticket):
            paa_by_category = {
                "PAA One": ("paa-one", "PAA One"),
                "PAA Three": ("paa-three", "PAA Three"),
            }
            return paa_by_category[ticket.category]

        def report_rows(count_filter, grievance_count=None):
            count_argument = (
                f", grievanceCount: {grievance_count}"
                if grievance_count is not None
                else ""
            )
            response = self.gql_client.execute(
                f"""
                query {{
                  grievanceReports(
                    report: "PAA_WITHOUT_GRIEVANCES",
                    paaGrievanceFilter: "{count_filter}"
                    {count_argument}
                  ) {{
                    paaName
                    count
                  }}
                }}
                """,
                context=self.gql_context.get_request(),
            )
            self.assertNotIn("errors", response)
            return {
                row["paaName"]: row["count"]
                for row in response["data"]["grievanceReports"]
            }

        with patch(
            "grievance_social_protection.gql_queries._ticket_base_queryset",
            return_value=tickets,
        ), patch(
            "grievance_social_protection.gql_queries._paa_candidates",
            return_value=paa_locations,
        ), patch(
            "grievance_social_protection.gql_queries._ticket_paa",
            side_effect=ticket_paa,
        ):
            self.assertEqual(
                report_rows("WITHOUT_GRIEVANCE"),
                {"PAA Zero": 0},
            )
            self.assertEqual(
                report_rows("WITH_GRIEVANCE"),
                {"PAA One": 1, "PAA Three": 3},
            )
            self.assertEqual(
                report_rows("LESS_THAN", 2),
                {"PAA Zero": 0, "PAA One": 1},
            )
            self.assertEqual(
                report_rows("MORE_THAN", 1),
                {"PAA Three": 3},
            )

    def test_overdue_by_paa_report_handles_naive_current_datetime(self):
        today = _today()
        self._create_ticket(
            "Report Overdue Category",
            due_date=today - timedelta(days=3),
        )

        response = self.gql_client.execute(
            f"""
            query {{
              grievanceReports(
                report: "OVERDUE_BY_PAA",
                dateFrom: "{today.isoformat()}",
                dateTo: "{today.isoformat()}"
              ) {{
                paaName
                count
                overdueDays
              }}
            }}
            """,
            context=self.gql_context.get_request(),
        )

        self.assertNotIn("errors", response)
        rows = response["data"]["grievanceReports"]
        self.assertTrue(
            any(row["count"] >= 1 and row["overdueDays"] >= 3 for row in rows)
        )
