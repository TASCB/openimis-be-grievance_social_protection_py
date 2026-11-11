from types import SimpleNamespace

from django.test import TestCase

from grievance_social_protection.gql_queries import (
    REPORT_STATUS_BY_TYPE, _build_report_rows, reporter_kind_filter,
)
from grievance_social_protection.models import Ticket


def _ticket(category, title, status):
    return SimpleNamespace(category=category, title=title, status=status)


class StatusByTypeReportTests(TestCase):
    def test_counts_each_type_by_status(self):
        tickets = [
            _ticket("Malipo", "Payment not received", "RECEIVED"),
            _ticket("Malipo", "Payment not received", "CLOSED"),
            _ticket("Malipo", "Wrong amount", "IN_PROGRESS"),
            _ticket("Huduma", "Payment not received", "RECEIVED"),
        ]
        rows = {(r.category, r.label): r for r in _build_report_rows(REPORT_STATUS_BY_TYPE, tickets, None)}
        row = rows[("Malipo", "Payment not received")]
        self.assertEqual((row.count, row.open_count, row.closed_count), (2, 1, 1))
        self.assertEqual(rows[("Malipo", "Wrong amount")].in_progress_count, 1)
        self.assertEqual(rows[("Huduma", "Payment not received")].count, 1)

    def test_rows_are_sorted_by_category_then_type(self):
        tickets = [_ticket("B", "z", "OPEN"), _ticket("A", "y", "OPEN"), _ticket("A", "x", "OPEN")]
        keys = [(r.category, r.label) for r in _build_report_rows(REPORT_STATUS_BY_TYPE, tickets, None)
                if r.count]
        self.assertEqual(keys, [("A", "x"), ("A", "y"), ("B", "z")])

    def test_reporter_kind_filter_targets_the_reporter_models(self):
        sql = str(Ticket.objects.filter(reporter_kind_filter("legacygroup")).query)
        self.assertIn("legacygroup", sql)
        sql = str(Ticket.objects.filter(reporter_kind_filter("beneficiary")).query)
        self.assertIn("groupbeneficiary", sql)
