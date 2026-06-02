from django.utils import timezone
from graphene import Schema
from graphene.test import Client

from core.models.openimis_graphql_test_case import (
    BaseTestContext,
    openIMISGraphQLTestCase,
)
from grievance_social_protection.models import Ticket
from grievance_social_protection.schema import Mutation, Query
from grievance_social_protection.tests.test_helpers import create_test_grievance_user


class GQLGrievanceReportsTestCase(openIMISGraphQLTestCase):
    @classmethod
    def setUpClass(cls):
        super(GQLGrievanceReportsTestCase, cls).setUpClass()
        cls.user = create_test_grievance_user(username="user_grievance_reports")
        cls.gql_client = Client(Schema(query=Query, mutation=Mutation))
        cls.gql_context = BaseTestContext(cls.user)

    def _create_ticket(self, category, channel="Report Channel", status=None):
        ticket = Ticket(
            category=category,
            title=f"{category} ticket",
            resolution="2,0",
            priority="Normal",
            date_of_incident=timezone.localdate(),
            channel=channel,
            flags="Default",
        )
        if status:
            ticket.status = status
        ticket.save(user=self.user)
        return ticket

    def test_category_report_counts_tickets_by_category(self):
        self._create_ticket("Report Category A")
        self._create_ticket("Report Category B")
        today = timezone.localdate().isoformat()

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

    def test_resolution_status_report_groups_received_open_and_closed(self):
        self._create_ticket("Report Status Received")
        self._create_ticket("Report Status Open", status=Ticket.TicketStatus.OPEN)
        self._create_ticket("Report Status Closed", status=Ticket.TicketStatus.CLOSED)
        today = timezone.localdate().isoformat()

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
        rows = {row["status"]: row["count"] for row in response["data"]["grievanceReports"]}
        self.assertEqual(rows["Received"], 1)
        self.assertEqual(rows["Open"], 1)
        self.assertEqual(rows["Closed"], 1)
