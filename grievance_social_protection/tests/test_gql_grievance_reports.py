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

    def test_paa_summary_groups_grievances_by_region_and_district(self):
        tickets = [
            self._create_ticket("PAA Summary A"),
            self._create_ticket("PAA Summary B"),
            self._create_ticket("PAA Summary C"),
        ]

        with patch(
            "grievance_social_protection.gql_queries._ticket_base_queryset",
            return_value=tickets,
        ), patch(
            "grievance_social_protection.gql_queries._ticket_region_and_paa",
            side_effect=[
                ("Arusha", "arusha-cc", "Arusha CC"),
                ("Arusha", "arusha-cc", "Arusha CC"),
                ("Arusha", "karatu-dc", "Karatu DC"),
            ],
        ):
            response = self.gql_client.execute(
                """
                query {
                  grievanceReports(report: "PAA_SUMMARY") {
                    regionName
                    districtName
                    grievancesFiled
                  }
                }
                """,
                context=self.gql_context.get_request(),
            )

        self.assertNotIn("errors", response)
        self.assertEqual(
            response["data"]["grievanceReports"],
            [
                {
                    "regionName": "Arusha",
                    "districtName": "Arusha CC",
                    "grievancesFiled": 2,
                },
                {
                    "regionName": "Arusha",
                    "districtName": "Karatu DC",
                    "grievancesFiled": 1,
                },
            ],
        )

    def test_status_by_category_uses_legacy_report_columns(self):
        tickets = [
            self._create_ticket("Legacy Status", status=Ticket.TicketStatus.RECEIVED),
            self._create_ticket("Legacy Status", status=Ticket.TicketStatus.IN_PROGRESS),
            self._create_ticket("Legacy Status", status=Ticket.TicketStatus.CLOSED),
            self._create_ticket("Legacy Status", status=Ticket.TicketStatus.RESOLVED),
        ]

        with patch(
            "grievance_social_protection.gql_queries._ticket_base_queryset",
            return_value=tickets,
        ):
            response = self.gql_client.execute(
                """
                query {
                  grievanceReports(report: "STATUS_BY_CATEGORY") {
                    category
                    grievancesFiled
                    openCount
                    assignedCount
                    reassignedCount
                    inProgressCount
                    closedCount
                    escalatedCount
                  }
                }
                """,
                context=self.gql_context.get_request(),
            )

        self.assertNotIn("errors", response)
        row = next(
            row
            for row in response["data"]["grievanceReports"]
            if row["category"] == "Legacy Status"
        )
        self.assertEqual(
            row,
            {
                "category": "Legacy Status",
                "grievancesFiled": 4,
                "openCount": 1,
                "assignedCount": 0,
                "reassignedCount": 0,
                "inProgressCount": 1,
                "closedCount": 2,
                "escalatedCount": 0,
            },
        )

    def test_custom_report_groups_by_paa_category_and_title(self):
        tickets = [
            self._create_ticket("Malipo", status=Ticket.TicketStatus.CLOSED),
            self._create_ticket("Malipo", status=Ticket.TicketStatus.CLOSED),
            self._create_ticket("Malipo", status=Ticket.TicketStatus.IN_PROGRESS),
        ]
        for ticket in tickets:
            ticket.title = "Kukosa malipo"

        with patch(
            "grievance_social_protection.gql_queries._ticket_base_queryset",
            return_value=tickets,
        ), patch(
            "grievance_social_protection.gql_queries._ticket_region_and_paa",
            return_value=("Arusha", "arusha-cc", "Arusha CC"),
        ):
            response = self.gql_client.execute(
                """
                query {
                  grievanceReports(report: "CUSTOM") {
                    districtName
                    category
                    ticketTitle
                    grievancesFiled
                    inProgressCount
                    closedCount
                  }
                }
                """,
                context=self.gql_context.get_request(),
            )

        self.assertNotIn("errors", response)
        self.assertEqual(
            response["data"]["grievanceReports"],
            [
                {
                    "districtName": "Arusha CC",
                    "category": "Malipo",
                    "ticketTitle": "Kukosa malipo",
                    "grievancesFiled": 3,
                    "inProgressCount": 1,
                    "closedCount": 2,
                }
            ],
        )

    def test_summary_report_returns_dashboard_kpis(self):
        today = _today()
        tickets = [
            self._create_ticket(
                "Summary Overdue",
                status=Ticket.TicketStatus.RECEIVED,
                due_date=today - timedelta(days=3),
            ),
            self._create_ticket(
                "Summary Open On Time",
                status=Ticket.TicketStatus.OPEN,
                due_date=today + timedelta(days=3),
            ),
            self._create_ticket(
                "Summary Closed On Time",
                status=Ticket.TicketStatus.CLOSED,
                due_date=today + timedelta(days=3),
            ),
            self._create_ticket(
                "Summary Closed Late",
                status=Ticket.TicketStatus.CLOSED,
                due_date=today - timedelta(days=3),
            ),
            self._create_ticket(
                "Summary No Timeline",
                status=Ticket.TicketStatus.RESOLVED,
            ),
        ]

        with patch(
            "grievance_social_protection.gql_queries._ticket_base_queryset",
            return_value=tickets,
        ), patch(
            "grievance_social_protection.gql_queries._paa_candidates",
            return_value=[SimpleNamespace(uuid="paa-empty", name="PAA Empty")],
        ):
            response = self.gql_client.execute(
                """
                query {
                  grievanceReports(report: "SUMMARY") {
                    grievancesFiled
                    openCount
                    closedCount
                    overdueCount
                    resolvedOnTimeCount
                    resolvedLateCount
                    onTimeRate
                    averageClosureDays
                    paaWithoutGrievancesCount
                  }
                }
                """,
                context=self.gql_context.get_request(),
            )

        self.assertNotIn("errors", response)
        rows = response["data"]["grievanceReports"]
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertIsNotNone(row.pop("averageClosureDays"))
        self.assertEqual(
            row,
            {
                "grievancesFiled": 5,
                "openCount": 2,
                "closedCount": 3,
                "overdueCount": 1,
                "resolvedOnTimeCount": 1,
                "resolvedLateCount": 1,
                "onTimeRate": 50.0,
                "paaWithoutGrievancesCount": 1,
            },
        )

    def test_trend_report_fills_empty_months(self):
        now = timezone.now()
        january = now.replace(year=2026, month=1, day=15, hour=12)
        march = now.replace(year=2026, month=3, day=10, hour=12)
        tickets = [
            self._create_ticket("Trend Jan"),
            self._create_ticket("Trend Jan"),
            self._create_ticket("Trend Mar", status=Ticket.TicketStatus.CLOSED),
        ]
        tickets[0].date_created = january
        tickets[1].date_created = january
        tickets[2].date_created = march
        tickets[2].date_updated = march.replace(day=20)

        with patch(
            "grievance_social_protection.gql_queries._ticket_base_queryset",
            return_value=tickets,
        ):
            response = self.gql_client.execute(
                """
                query {
                  grievanceReports(
                    report: "TREND",
                    dateFrom: "2026-01-01",
                    dateTo: "2026-04-30"
                  ) {
                    period
                    periodStart
                    periodEnd
                    count
                    closedCount
                    resolvedCount
                  }
                }
                """,
                context=self.gql_context.get_request(),
            )

        self.assertNotIn("errors", response)
        rows = response["data"]["grievanceReports"]
        self.assertEqual(
            [(row["period"], row["count"], row["resolvedCount"]) for row in rows],
            [
                ("2026-01", 2, 0),
                ("2026-02", 0, 0),
                ("2026-03", 1, 1),
                ("2026-04", 0, 0),
            ],
        )
        self.assertEqual(rows[1]["periodStart"], "2026-02-01")
        self.assertEqual(rows[1]["periodEnd"], "2026-02-28")
        self.assertEqual(rows[2]["closedCount"], 1)

    def test_trend_period_helpers(self):
        from datetime import date

        from grievance_social_protection.gql_queries import (
            TREND_PERIOD_MONTH,
            TREND_PERIOD_WEEK,
            _next_period_start,
            _period_label,
            _period_start,
        )

        self.assertEqual(
            _next_period_start(date(2025, 12, 1), TREND_PERIOD_MONTH),
            date(2026, 1, 1),
        )
        self.assertEqual(
            _period_start(date(2026, 11, 4), TREND_PERIOD_WEEK),
            date(2026, 11, 2),
        )
        self.assertEqual(_period_label(date(2026, 11, 2), TREND_PERIOD_WEEK), "2026-W45")
        self.assertEqual(_period_label(date(2026, 12, 28), TREND_PERIOD_WEEK), "2026-W53")

    def test_trend_report_rejects_unknown_period(self):
        response = self.gql_client.execute(
            """
            query {
              grievanceReports(report: "TREND", period: "YEAR") {
                period
              }
            }
            """,
            context=self.gql_context.get_request(),
        )

        self.assertIn("errors", response)

    def test_dashboard_returns_requested_sections_from_one_ticket_load(self):
        tickets = [
            self._create_ticket("Dashboard Category"),
            self._create_ticket("Dashboard Category", status=Ticket.TicketStatus.CLOSED),
        ]

        with patch(
            "grievance_social_protection.gql_queries._ticket_base_queryset",
            return_value=tickets,
        ) as base_queryset, patch(
            "grievance_social_protection.gql_queries._paa_candidates",
            return_value=[],
        ):
            response = self.gql_client.execute(
                """
                query {
                  grievanceDashboard(
                    reports: ["SUMMARY", "CATEGORY", "SUMMARY", "TREND"]
                  ) {
                    report
                    rows {
                      category
                      count
                      grievancesFiled
                      closedCount
                    }
                  }
                }
                """,
                context=self.gql_context.get_request(),
            )

        self.assertNotIn("errors", response)
        self.assertEqual(base_queryset.call_count, 1)
        sections = {
            section["report"]: section["rows"]
            for section in response["data"]["grievanceDashboard"]
        }
        self.assertEqual(
            [section["report"] for section in response["data"]["grievanceDashboard"]],
            ["SUMMARY", "CATEGORY", "TREND"],
        )
        self.assertEqual(sections["SUMMARY"][0]["grievancesFiled"], 2)
        self.assertEqual(sections["SUMMARY"][0]["closedCount"], 1)
        category_counts = {row["category"]: row["count"] for row in sections["CATEGORY"]}
        self.assertEqual(category_counts["Dashboard Category"], 2)
        self.assertEqual(sum(row["count"] for row in sections["TREND"]), 2)
