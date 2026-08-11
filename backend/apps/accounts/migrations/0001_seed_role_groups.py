from django.db import migrations

from apps.accounts.permissions import ALL_ROLES


def seed_role_groups(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    for name in ALL_ROLES:
        Group.objects.get_or_create(name=name)


def noop_reverse(apps, schema_editor):
    # Deliberately not deleting the groups on reverse: by the time anyone
    # would roll this migration back, real users may already be assigned
    # to these groups, and silently stripping their role assignments on
    # an unrelated rollback would be a surprising, hard-to-notice side
    # effect. Removing the groups (if ever desired) should be a conscious
    # follow-up migration, not an automatic reverse of this one.
    pass


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.RunPython(seed_role_groups, noop_reverse),
    ]
