from django.core.management.base import BaseCommand
from core.models import User
from grievance_social_protection.apps import TicketConfig
from grievance_social_protection.models import (
    GrievanceType,
    GrievanceCategory,
    GrievanceChannel,
)

items = [
    {
        "category": "Malipo kwa walengwa wa mpango",
        "types": [
            "Kukosa Malipo ya Ruzuku ya msingi (PCT)",
            "Kukosa Malipo ya ajira za muda (PWP)",
            "Kukosa Malipo ya Ruzuku ya Uzalishaji mali  (LE PG )",
            "Malipo Pungufu ya Ruzuku ya msingi  ( PCT)",
            "Malipo pungufu ya ajira za muda (PWP)",
            "Malipo Pungufu ya Ruzuku ya uzalishaji mali ( LE PG)",
            "Kuchelewa Malipo ya ruzuku ya msingi (PCT) (PCT, PWP, EI)",
            "Kuchelewa Malipo ya ajira za muda (PWP)",
            "Kuchelewa Malipo ya ruzuku ya uzalishaji mali  (LE PG)",
            "Changamoto ya kupata malipo",
        ],
    },
    {
        "category": "Malipo kwa wasio walengwa wa mpango",
        "types": [
            "Malipo Pungufu kwa watoa huduma",
            "Kuchelewa kwa Malipo ya watoa huduma",
        ],
    },
    {
        "category": "Utambuzi na Uhakiki wa kaya",
        "types": [
            "Kaya kutotambuliwa kabisa",
            "Jina la kaya kuondolewa kwenye orodha ya awali (TF3) yaliyopendekezwa",
            "Jina la kaya kuondolewa kwenye orodha ya mwisho (TF4) iliyopitishwa",
            "Kaya kutoingiziwa taarifa kwenye kishkwambi/kutododoswa kwa sababu yoyote ile",
            "Kuingizwa kwenye mpango kwa kaya isiyo na vigezo",
            "Kaya kutokuhakikiwa / kufanyiwa tathmini",
            "Kaya imehakikiwa haipo kwenye orodha ya malipo",
            "Kaya kusimamishiwa malipo (suspended from payment)",
        ],
    },
    {
        "category": "Kuhuisha taarifa za  walengwa",
        "types": [
            "Mtoto aliyezaliwa  kukosekana kwenye orodha ya kaya",
            "Wanafunzi kutokuwepo kwenye orodha ya kaya",
            "Mtoto kutokubadilishiwa kituo kituo cha huduma",
            "Kutofanya mabadiliko ya hadhi ya wana kaya ( kuhama kaya au kifo)",
            "Kutoingiza wanakaya wapya waliohamia",
            "Kutobadilisha mwakilishi wa kaya",
            "Kutorekebisha taarifa za wanakaya",
        ],
    },
    {
        "category": "Huduma zisizoridhisha",
        "types": [
            "Malalamiko yasiyotatuliwa kwa wakati",
            "Kukosa ushauri wa kitaalamu kuhusu kilimo, ufugaji na ujasiriamali",
            "Utovu wa nidhamu wa watumishi",
            "Kuchelewa kulipwa malipo/madai",
            "Watumishi kutumia lugha chafu",
            "Kunyimwa haki au  huduma kutokana na ubaguzi",
        ],
    },
    {
        "category": "Unyanyasaji wa kijinisia usiohusu Unyanyasaji/uonevu/udhalilishaji wa kingono",
        "types": [
            "Matukio ya kushambuliwa kimwili",
            "Matusi au unyanyasaji wa maneno",
            "Ubaguzi wa kijinsia",
            "Unyanyasaji wa kiuchumi",
            "Changamoto za urithi",
        ],
    },
    {
        "category": "Unyanyasaji wa kijinisia unaohusu Unyanyasaji/uonevu/udhalilishaji wa kingono",
        "types": [
            "Unyanyasaji wa kingono",
            "Uonevu au udhalilishaji wa kingono",
        ],
    },
    {
        "category": "Mazingira",
        "types": [
            "Udhibiti duni wa uchafuzi wa vumbi",
            "Usimamizi duni wa taka",
            "Ukosefu wa vifaakinga vya kutosha (PPE)",
        ],
    },
    {
        "category": "Maswala ya Ardhi",
        "types": [
            "Migogoro ya umiliki wa ardhi iliyotwaliwa",
            "Migogoro kuhusu ukubwa wa ardhi",
            "Migogoro ya mipaka ya ardhi",
        ],
    },
    {
        "category": "Maswali na maoni",
        "types": [
            "Maswali, mapendekezo, au mashaka kuhusu programu",
            "Kukosa kitambulisho au namba za NIDA",
            "Kukosa mikopo elimu ya juu",
            "Maulizo kuhusu taratibu za mpango",
            "Kusahau neno la siri la akaunti",
            "Kutopata kadi ya bima ya afya baada ya kukamilisha malipo",
            "Utapeli",
        ],
    },
]


class Command(BaseCommand):
    help = "Seed grievance types and categories"

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

        categories_created = 0
        categories_skipped = 0
        types_created = 0
        types_skipped = 0
        channels_created = 0
        channels_skipped = 0

        for item in items:
            cat_qs = GrievanceCategory.objects.filter(name=item["category"])
            if cat_qs.exists():
                g_category = cat_qs.first()
                categories_skipped += 1
                self.stdout.write(
                    f"  [SKIP] Category already exists: {item['category']}"
                )
            else:
                g_category = GrievanceCategory(
                    name=item["category"], user_created=user
                )
                g_category.save(username=username)
                categories_created += 1
                self.stdout.write(
                    self.style.SUCCESS(f"  [OK] Created category: {item['category']}")
                )

            for type_name in item["types"]:
                type_qs = GrievanceType.objects.filter(
                    name=type_name, category=g_category
                )
                if type_qs.exists():
                    types_skipped += 1
                    self.stdout.write(f"    [SKIP] Type already exists: {type_name}")
                else:
                    g_type = GrievanceType(
                        category=g_category, name=type_name, user_created=user
                    )
                    g_type.save(username=username)
                    types_created += 1
                    self.stdout.write(
                        self.style.SUCCESS(f"    [OK] Created type: {type_name}")
                    )

        for channel_name in filter(None, TicketConfig.grievance_channels):
            channel_qs = GrievanceChannel.objects.filter(name=channel_name)
            if channel_qs.exists():
                channels_skipped += 1
                self.stdout.write(
                    f"  [SKIP] Channel already exists: {channel_name}"
                )
            else:
                grievance_channel = GrievanceChannel(
                    name=channel_name, user_created=user
                )
                grievance_channel.save(username=username)
                channels_created += 1
                self.stdout.write(
                    self.style.SUCCESS(f"  [OK] Created channel: {channel_name}")
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"\nDone! Categories: {categories_created} created, {categories_skipped} skipped. "
                f"Types: {types_created} created, {types_skipped} skipped. "
                f"Channels: {channels_created} created, {channels_skipped} skipped."
            )
        )
