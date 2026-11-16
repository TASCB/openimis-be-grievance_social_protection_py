from django.test import TestCase

from core.models import User
from grievance_social_protection.models import GrievanceCategory, GrievanceChannel, GrievanceType
from grievance_social_protection.services import (
    GrievanceCategoryService, GrievanceChannelService, GrievanceTypeService,
)


class SetupCodesTest(TestCase):
    """The backend gives every category, type and channel its code; nobody types one."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.filter(username='Admin').first()

    def next_number(self, model, prefix):
        numbers = [int(code[len(prefix):]) for code in model.objects.values_list('code', flat=True)
                   if code and code.startswith(prefix) and code[len(prefix):].isdigit()]
        return max(numbers, default=0) + 1

    def test_a_new_category_gets_the_next_code(self):
        expected = f'GC{self.next_number(GrievanceCategory, "GC"):03d}'
        result = GrievanceCategoryService(self.user).create({'name': 'T Delays', 'timeline': 7})
        self.assertTrue(result['success'], result)
        self.assertEqual(GrievanceCategory.objects.get(name='T Delays').code, expected)

    def test_the_code_a_client_sends_is_ignored(self):
        expected = f'GCH{self.next_number(GrievanceChannel, "GCH"):03d}'
        result = GrievanceChannelService(self.user).create({'name': 'T Radio call-in', 'code': 'MINE'})
        self.assertTrue(result['success'], result)
        self.assertEqual(GrievanceChannel.objects.get(name='T Radio call-in').code, expected)

    def test_a_code_never_changes(self):
        GrievanceCategoryService(self.user).create({'name': 'T Conduct', 'timeline': 7})
        category = GrievanceCategory.objects.get(name='T Conduct')
        given = category.code
        result = GrievanceCategoryService(self.user).update(
            {'id': str(category.id), 'name': 'T Staff conduct', 'code': 'OTHER'})
        self.assertTrue(result['success'], result)
        category.refresh_from_db()
        self.assertEqual((category.name, category.code), ('T Staff conduct', given))

    def test_types_keep_counting_past_the_highest_code(self):
        expected = f'GT{self.next_number(GrievanceType, "GT"):03d}'
        result = GrievanceTypeService(self.user).create({'name': 'T Late transfer'})
        self.assertTrue(result['success'], result)
        self.assertEqual(GrievanceType.objects.get(name='T Late transfer').code, expected)
