from django.apps import apps
from django.conf import settings

is_unit_test_env = getattr(settings, "IS_UNIT_TEST_ENV", False)

# Check if the 'opensearch_reports' app is in INSTALLED_APPS
if "opensearch_reports" in apps.app_configs and not is_unit_test_env:
    from opensearch_reports.service import BaseSyncDocument
    from django_opensearch_dsl import fields as opensearch_fields
    from django_opensearch_dsl.registries import registry
    from grievance_social_protection.models import Ticket

    @registry.register_document
    class TicketDocument(BaseSyncDocument):
        DASHBOARD_NAME = "Grievance"

        key = (opensearch_fields.KeywordField(),)
        title = (opensearch_fields.KeywordField(),)

        description = (opensearch_fields.KeywordField(),)
        code = (opensearch_fields.KeywordField(),)
        attending_staff = (opensearch_fields.KeywordField(),)
        status = (opensearch_fields.KeywordField(),)

        category = (opensearch_fields.KeywordField(),)
        flags = (opensearch_fields.KeywordField(),)
        channel = (opensearch_fields.KeywordField(),)
        resolution = (opensearch_fields.KeywordField(),)

        class Index:
            name = "ticket"
            settings = {"number_of_shards": 1, "number_of_replicas": 0}
            auto_refresh = True

        class Django:
            model = Ticket
            fields = [
                "id",
                "key",
                "title",
                "code",
                "description",
                "status",
                "category",
                "flags",
                "channel",
                "resolution",
            ]
            queryset_pagination = 5000
