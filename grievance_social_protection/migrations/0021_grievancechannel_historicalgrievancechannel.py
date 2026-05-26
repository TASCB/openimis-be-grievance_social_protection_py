import core.fields
import core.utils
import datetime
import dirtyfields.dirtyfields
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import simple_history.models
import uuid


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        (
            "grievance_social_protection",
            "0020_reverse_grievancetype_category_relationship",
        ),
    ]

    operations = [
        migrations.CreateModel(
            name="HistoricalGrievanceChannel",
            fields=[
                ("id", models.UUIDField(db_index=True, default=uuid.uuid4, editable=False)),
                ("is_deleted", models.BooleanField(db_column="isDeleted", default=False)),
                ("json_ext", models.JSONField(blank=True, db_column="Json_ext", null=True)),
                ("date_created", core.fields.DateTimeField(db_column="DateCreated", default=datetime.datetime.now, null=True)),
                ("date_updated", core.fields.DateTimeField(db_column="DateUpdated", default=datetime.datetime.now, null=True)),
                ("version", models.IntegerField(default=1)),
                ("date_valid_from", core.fields.DateTimeField(db_column="DateValidFrom", default=datetime.datetime.now)),
                ("date_valid_to", core.fields.DateTimeField(blank=True, db_column="DateValidTo", null=True)),
                ("replacement_uuid", models.UUIDField(blank=True, db_column="ReplacementUUID", null=True)),
                ("code", models.CharField(blank=True, max_length=50, null=True)),
                ("name", models.CharField(db_index=True, max_length=255)),
                ("is_active", models.BooleanField(default=True)),
                ("history_id", models.AutoField(primary_key=True, serialize=False)),
                ("history_date", models.DateTimeField(db_index=True)),
                ("history_change_reason", models.CharField(max_length=100, null=True)),
                ("history_type", models.CharField(choices=[("+", "Created"), ("~", "Changed"), ("-", "Deleted")], max_length=1)),
                ("history_user", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("user_created", models.ForeignKey(blank=True, db_column="UserCreatedUUID", db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("user_updated", models.ForeignKey(blank=True, db_column="UserUpdatedUUID", db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name="+", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "historical grievance channel",
                "verbose_name_plural": "historical grievance channels",
                "ordering": ("-history_date", "-history_id"),
                "get_latest_by": ("history_date", "history_id"),
            },
            bases=(simple_history.models.HistoricalChanges, models.Model),
        ),
        migrations.CreateModel(
            name="GrievanceChannel",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("is_deleted", models.BooleanField(db_column="isDeleted", default=False)),
                ("json_ext", models.JSONField(blank=True, db_column="Json_ext", null=True)),
                ("date_created", core.fields.DateTimeField(db_column="DateCreated", default=datetime.datetime.now, null=True)),
                ("date_updated", core.fields.DateTimeField(db_column="DateUpdated", default=datetime.datetime.now, null=True)),
                ("version", models.IntegerField(default=1)),
                ("date_valid_from", core.fields.DateTimeField(db_column="DateValidFrom", default=datetime.datetime.now)),
                ("date_valid_to", core.fields.DateTimeField(blank=True, db_column="DateValidTo", null=True)),
                ("replacement_uuid", models.UUIDField(blank=True, db_column="ReplacementUUID", null=True)),
                ("code", models.CharField(blank=True, max_length=50, null=True)),
                ("name", models.CharField(max_length=255, unique=True)),
                ("is_active", models.BooleanField(default=True)),
                ("user_created", models.ForeignKey(db_column="UserCreatedUUID", on_delete=django.db.models.deletion.DO_NOTHING, related_name="%(class)s_user_created", to=settings.AUTH_USER_MODEL)),
                ("user_updated", models.ForeignKey(db_column="UserUpdatedUUID", on_delete=django.db.models.deletion.DO_NOTHING, related_name="%(class)s_user_updated", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "db_table": "grievance_GrievanceChannel",
            },
            bases=(dirtyfields.dirtyfields.DirtyFieldsMixin, core.utils.CachedModelMixin, models.Model),
        ),
    ]
