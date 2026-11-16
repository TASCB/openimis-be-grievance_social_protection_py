from django.db import migrations

from grievance_social_protection.codes import PREFIXES, missing_code, next_code


def give_codes(apps, schema_editor):
    """Entries saved before the backend gave codes get one, in the order they were created."""
    for name, prefix in PREFIXES.items():
        model = apps.get_model('grievance_social_protection', name)
        given = 0
        for entry in model.objects.order_by('date_created', 'id'):
            if missing_code(entry.code):
                # a plain update: the historical model has neither the custom save nor the history fields
                model.objects.filter(pk=entry.pk).update(code=next_code(model, prefix))
                given += 1
        if given:
            print(f'  grievance setup: {given} {name} codes given')


class Migration(migrations.Migration):

    dependencies = [
        ('grievance_social_protection', '0029_seed_grievance_setup'),
    ]

    operations = [
        migrations.RunPython(give_codes, migrations.RunPython.noop),
    ]
