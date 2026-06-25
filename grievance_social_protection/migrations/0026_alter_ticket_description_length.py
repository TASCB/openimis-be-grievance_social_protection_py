from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("grievance_social_protection", "0025_ticket_external_reporter"),
    ]

    operations = [
        migrations.AlterField(
            model_name="ticket",
            name="description",
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="historicalticket",
            name="description",
            field=models.TextField(blank=True, null=True),
        ),
    ]
