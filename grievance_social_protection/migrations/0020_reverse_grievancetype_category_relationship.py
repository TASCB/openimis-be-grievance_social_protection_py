import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        (
            "grievance_social_protection",
            "0019_grievancetype_historicalgrievancetype_and_more",
        ),
    ]

    operations = [
        # 1. Remove unique_together constraint from GrievanceCategory
        migrations.AlterUniqueTogether(
            name="grievancecategory",
            unique_together=set(),
        ),
        # 2. Remove 'type' FK from HistoricalGrievanceCategory
        migrations.RemoveField(
            model_name="historicalgrievancecategory",
            name="type",
        ),
        # 3. Remove 'type' FK from GrievanceCategory
        migrations.RemoveField(
            model_name="grievancecategory",
            name="type",
        ),
        # 4. Add 'category' FK to GrievanceType (nullable for existing rows)
        migrations.AddField(
            model_name="grievancetype",
            name="category",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name="types",
                to="grievance_social_protection.grievancecategory",
            ),
        ),
        # 5. Add 'category' FK to HistoricalGrievanceType
        migrations.AddField(
            model_name="historicalgrievancetype",
            name="category",
            field=models.ForeignKey(
                blank=True,
                db_constraint=False,
                null=True,
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name="+",
                to="grievance_social_protection.grievancecategory",
            ),
        ),
        # 6. Add unique_together constraint on GrievanceType
        migrations.AlterUniqueTogether(
            name="grievancetype",
            unique_together={("category", "name")},
        ),
    ]
