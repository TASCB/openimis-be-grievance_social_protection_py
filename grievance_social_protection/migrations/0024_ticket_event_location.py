from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("location", "0019_alter_location_code"),
        ("grievance_social_protection", "0023_grievancecategory_timeline"),
    ]

    operations = [
        migrations.AddField(
            model_name="ticket",
            name="event_location",
            field=models.ForeignKey(
                blank=True,
                db_column="EventLocationId",
                null=True,
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name="grievance_tickets",
                to="location.location",
            ),
        ),
        migrations.AddField(
            model_name="historicalticket",
            name="event_location",
            field=models.ForeignKey(
                blank=True,
                db_column="EventLocationId",
                db_constraint=False,
                null=True,
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name="+",
                to="location.location",
            ),
        ),
    ]
