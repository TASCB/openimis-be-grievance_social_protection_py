from django.db import migrations

RIGHT = 160001  # social_protection benefit plan search: the ticket form's programme list
ROLE_SUFFIX = 'Grievance Officer'


def grant(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO "tblRoleRight" ("RoleID", "RightID", "ValidityFrom", "AuditUserId")
            SELECT DISTINCT r."RoleID", %s, NOW(), 1
            FROM "tblRole" r
            WHERE r."ValidityTo" IS NULL AND r."RoleName" ILIKE %s
              AND NOT EXISTS (
                  SELECT 1 FROM "tblRoleRight" x
                  WHERE x."RoleID" = r."RoleID" AND x."RightID" = %s AND x."ValidityTo" IS NULL
              )
            """,
            [RIGHT, f'%{ROLE_SUFFIX}', RIGHT],
        )


class Migration(migrations.Migration):

    dependencies = [
        ('grievance_social_protection', '0027_ticket_consent_given'),
    ]

    operations = [migrations.RunPython(grant, migrations.RunPython.noop)]
