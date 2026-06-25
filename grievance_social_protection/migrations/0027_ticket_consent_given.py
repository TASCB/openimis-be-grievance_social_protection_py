from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("grievance_social_protection", "0026_alter_ticket_description_length"),
    ]

    operations = [
        migrations.AddField(
            model_name="ticket",
            name="consent_given",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="historicalticket",
            name="consent_given",
            field=models.BooleanField(default=False),
        ),
    ]
