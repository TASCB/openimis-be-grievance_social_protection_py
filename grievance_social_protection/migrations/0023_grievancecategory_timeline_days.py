from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('grievance_social_protection', '0022_ticketattachment_attachmentmutation'),
    ]

    operations = [
        migrations.AddField(
            model_name='grievancecategory',
            name='timeline_days',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='historicalgrievancecategory',
            name='timeline_days',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
    ]
