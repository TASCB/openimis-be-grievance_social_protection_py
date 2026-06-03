from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import User
from grievance_social_protection.apps import TicketConfig
from grievance_social_protection.models import (
    GrievanceCategory,
    GrievanceChannel,
    GrievanceType,
)


GRIEVANCE_CATEGORY_SEEDS = [
    {
        "category": "Malipo kwa walengwa wa mpango",
        "timeline": 60,
        "types": [
            "Kukosa Malipo ya Ruzuku ya msingi (PCT)",
            "Kukosa Malipo ya ajira za muda (CS-PW)",
            "Kukosa Malipo ya Ruzuku ya Uzalishaji mali (EEI)",
            "Malipo Pungufu ya Ruzuku ya msingi (PCT)",
            "Malipo pungufu ya ajira za muda (CS-PW)",
            "Malipo Pungufu ya Ruzuku ya uzalishaji mali (EEI)",
            "Kuchelewa Malipo ya ruzuku ya msingi (PCT)",
            "Kuchelewa Malipo ya ajira za muda (CS-PW)",
            "Kuchelewa Malipo ya ruzuku ya uzalishaji mali (EEI)",
            "Changamoto ya kupokea malipo",
            "Kaya kusimamishiwa malipo (suspended from payment)",
        ],
    },
    {
        "category": "Malipo kwa wasio walengwa wa mpango",
        "timeline": 45,
        "types": [
            "Kukosa malipo/kutolipwa",
            "Kupokea malipo pungufu",
            "Kuchelewa kwa Malipo",
        ],
    },
    {
        "category": "Utambuzi na Uhakiki wa kaya",
        "timeline": 21,
        "types": [
            "Kaya kutotambuliwa kabisa",
            "Jina la kaya kutoingizwa kwenye orodha ya awali (TF3) yaliyopendekezwa",
            "Jina la kaya kuondolewa kwenye orodha ya mwisho (TF4) iliyopitishwa",
            "Kaya kutoingiziwa taarifa kwenye kishkwambi/kutododoswa kwa sababu yoyote ile",
            "Kuingizwa kwenye mpango kwa kaya isiyo na vigezo",
            "Kaya kutokuhakikiwa / kufanyiwa tathmini",
            "Kaya imehakikiwa haipo kwenye orodha ya malipo",
        ],
    },
    {
        "category": "Kuhuisha taarifa za walengwa",
        "timeline": 21,
        "types": [
            "Mtoto aliyezaliwa kukosekana kwenye orodha ya kaya",
            "Wanafunzi kutokuwepo kwenye orodha ya kaya",
            "Mtoto kutokubadilishiwa kituo cha huduma",
            "Kutofanya mabadiliko ya hadhi ya wana kaya (mfano: kuhama kaya au kifo)",
            "Kutoingiza wanakaya wapya waliohamia",
            "Kutobadilisha mwakilishi wa kaya",
            "Kutorekebisha taarifa za wanakaya",
        ],
    },
    {
        "category": "Huduma zisizoridhisha",
        "timeline": 45,
        "types": [
            "Malalamiko yasiyotatuliwa kwa wakati",
            "Kukosa ushauri wa kitaalamu kuhusu kilimo, ufugaji na ujasiriamali",
            "Utovu wa nidhamu wa watumishi",
            "Watumishi kutumia lugha chafu",
            "Kunyimwa haki au huduma kutokana na ubaguzi",
        ],
    },
    {
        "category": "Unyanyasaji wa kijinsia usiohusu Unyanyasaji/uonevu/udhalilishaji wa kingono",
        "timeline": 60,
        "types": [
            "Matukio ya kushambuliwa kimwili",
            "Matusi au unyanyasaji wa maneno",
            "Ubaguzi wa kijinsia",
            "Unyanyasaji wa kiuchumi",
            "Changamoto za urithi",
        ],
    },
    {
        "category": "Unyanyasaji wa kijinsia unaohusu Unyanyasaji/uonevu/udhalilishaji wa kingono",
        "timeline": 0,
        "types": [
            "Unyanyasaji wa kingono",
            "Uonevu au udhalilishaji wa kingono",
        ],
    },
    {
        "category": "Mazingira",
        "timeline": 21,
        "types": [
            "Udhibiti duni wa uchafuzi wa vumbi",
            "Usimamizi duni wa taka",
            "Ukosefu wa vifaakinga vya kutosha (PPE)",
            "Kuumia wakati wa kazi na kutopata huduma stahiki za kitabibu",
        ],
    },
    {
        "category": "Maswala ya Ardhi",
        "timeline": 60,
        "types": [
            "Migogoro ya umiliki wa ardhi iliyotwaliwa",
            "Migogoro kuhusu ukubwa wa ardhi",
            "Migogoro ya mipaka ya ardhi",
        ],
    },
    {
        "category": "Maswali, mahitaji na maoni",
        "timeline": 14,
        "types": [
            "Maswali, mapendekezo, au mashaka kuhusu programu",
            "Kukosa kitambulisho au namba za NIDA",
            "Kukosa mikopo elimu ya juu",
            "Maulizo kuhusu taratibu za mpango",
            "Kusahau neno la siri la akaunti",
            "Kutopata kadi ya bima ya afya baada ya kukamilisha malipo",
            "Utapeli",
            "Kupoteza simu kadi au kadi ya benki",
        ],
    },
]


class Command(BaseCommand):
    help = "Reset and seed grievance types and categories"

    def add_arguments(self, parser):
        parser.add_argument(
            "--username",
            type=str,
            default="Admin",
            help="Username to use for audit trail (default: Admin)",
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
