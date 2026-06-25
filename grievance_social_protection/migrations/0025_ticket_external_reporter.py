from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("location", "0019_alter_location_code"),
        ("grievance_social_protection", "0024_ticket_event_location"),
    ]

    operations = [
        migrations.AddField(
            model_name="ticket",
            name="external_reporter_first_name",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="ticket",
            name="external_reporter_last_name",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="ticket",
            name="external_reporter_phone",
            field=models.CharField(blank=True, max_length=50, null=True),
        ),
        migrations.AddField(
            model_name="ticket",
            name="external_reporter_email",
            field=models.EmailField(blank=True, max_length=254, null=True),
        ),
        migrations.AddField(
            model_name="ticket",
            name="external_reporter_location",
            field=models.ForeignKey(
                blank=True,
                db_column="ExternalReporterLocationId",
                null=True,
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name="external_reporter_grievance_tickets",
                to="location.location",
            ),
        ),
        migrations.AddField(
            model_name="historicalticket",
            name="external_reporter_first_name",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="historicalticket",
            name="external_reporter_last_name",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="historicalticket",
            name="external_reporter_phone",
            field=models.CharField(blank=True, max_length=50, null=True),
        ),
        migrations.AddField(
            model_name="historicalticket",
            name="external_reporter_email",
            field=models.EmailField(blank=True, max_length=254, null=True),
        ),
        migrations.AddField(
            model_name="historicalticket",
            name="external_reporter_location",
            field=models.ForeignKey(
                blank=True,
                db_column="ExternalReporterLocationId",
                db_constraint=False,
                null=True,
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name="+",
                to="location.location",
            ),
        ),
    ]
