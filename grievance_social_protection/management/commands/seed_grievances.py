from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import User
from grievance_social_protection.apps import TicketConfig
from grievance_social_protection.seed_data import GRIEVANCE_CATEGORY_SEEDS, seed_missing
from grievance_social_protection.models import (
    GrievanceCategory,
    GrievanceChannel,
    GrievanceType,
)




class Command(BaseCommand):
    help = (
        "Add the grievance categories, types and channels TASAF starts with that are missing. "
        "With --reset, delete all categories and types first and create them again."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--username",
            type=str,
            default="Admin",
            help="Username to use for audit trail (default: Admin)",
        )
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete every category and type first (tickets keep their own copy of the category name)",
        )

    def handle(self, *args, **kwargs):
        username = kwargs["username"]

        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(f"User '{username}' does not exist. Aborting.")
            )
            return

        self.stdout.write(f"Seeding with user: {username}")

        if not kwargs["reset"]:
            with transaction.atomic():
                added = seed_missing(
                    GrievanceCategory, GrievanceType, GrievanceChannel, user,
                    TicketConfig.grievance_channels, log=self.stdout.write,
                )
            self.stdout.write(self.style.SUCCESS(
                f"Done: {added['categories']} categories, {added['types']} types and "
                f"{added['channels']} channels added; existing ones left as they are."
            ))
            return

        with transaction.atomic():
            deleted_types = GrievanceType.objects.count()
            deleted_categories = GrievanceCategory.objects.count()
            GrievanceType.objects.all().delete()
            GrievanceCategory.objects.all().delete()

            categories_created = 0
            types_created = 0
            channels_created = 0
            channels_skipped = 0

            self.stdout.write(
                f"Cleared {deleted_categories} categories and {deleted_types} types."
            )

            for item in GRIEVANCE_CATEGORY_SEEDS:
                category = GrievanceCategory(
                    name=item["category"],
                    timeline=item["timeline"],
                    user_created=user,
                    user_updated=user,
                )
                category.save(username=username)
                categories_created += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  [OK] Created category: {item['category']} "
                        f"({item['timeline']} days)"
                    )
                )

                for type_name in item["types"]:
                    grievance_type = GrievanceType(
                        category=category,
                        name=type_name,
                        user_created=user,
                        user_updated=user,
                    )
                    grievance_type.save(username=username)
                    types_created += 1
                    self.stdout.write(
                        self.style.SUCCESS(f"    [OK] Created type: {type_name}")
                    )

            for channel_name in filter(None, TicketConfig.grievance_channels):
                channel_qs = GrievanceChannel.objects.filter(name=channel_name)
                if channel_qs.exists():
                    channels_skipped += 1
                    self.stdout.write(f"  [SKIP] Channel already exists: {channel_name}")
                else:
                    grievance_channel = GrievanceChannel(
                        name=channel_name,
                        user_created=user,
                        user_updated=user,
                    )
                    grievance_channel.save(username=username)
                    channels_created += 1
                    self.stdout.write(
                        self.style.SUCCESS(f"  [OK] Created channel: {channel_name}")
                    )

        self.stdout.write(
            self.style.SUCCESS(
                f"\nDone! Categories reset: {deleted_categories} deleted, "
                f"{categories_created} created. Types reset: {deleted_types} deleted, "
                f"{types_created} created. Channels: {channels_created} created, "
                f"{channels_skipped} skipped."
            )
        )
