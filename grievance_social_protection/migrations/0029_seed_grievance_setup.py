from django.db import migrations

from grievance_social_protection.seed_data import seed_missing


def seed(apps, schema_editor):
    """Every database gets the starting categories, types and channels; existing ones are left alone."""
    from grievance_social_protection.apps import TicketConfig

    User = apps.get_model('core', 'User')
    user = User.objects.filter(username='Admin').first() or User.objects.order_by('id').first()
    if user is None:
        # nobody to record as the author yet; `manage.py seed_grievances` adds them later
        return
    added = seed_missing(
        apps.get_model('grievance_social_protection', 'GrievanceCategory'),
        apps.get_model('grievance_social_protection', 'GrievanceType'),
        apps.get_model('grievance_social_protection', 'GrievanceChannel'),
        user,
        TicketConfig.grievance_channels,
    )
    print(f"  grievance setup: {added['categories']} categories, {added['types']} types, "
          f"{added['channels']} channels added")


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0012_users_officers_admins'),
        ('grievance_social_protection', '0028_grievance_officer_program_search'),
    ]

    # nothing to undo: seeded rows may already be in use by tickets
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
