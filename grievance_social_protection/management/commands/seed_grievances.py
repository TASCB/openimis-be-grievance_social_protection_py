from django.core.management.base import BaseCommand
from core.models import User
from grievance_social_protection.models import GrievanceType, GrievanceCategory

items = [
    {
        "type": "Malipo kwa walengwa wa mpango",
        "categories": [
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
        "type": "Malipo kwa wasio walengwa wa mpango",
        "categories": [
            "Malipo Pungufu kwa watoa huduma",
            "Kuchelewa kwa Malipo ya watoa huduma",
        ],
    },
    {
        "type": "Utambuzi na Uhakiki wa kaya",
        "categories": [
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
        "type": "Kuhuisha taarifa za  walengwa",
        "categories": [
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
        "type": "Huduma zisizoridhisha",
        "categories": [
            "Malalamiko yasiyotatuliwa kwa wakati",
            "Kukosa ushauri wa kitaalamu kuhusu kilimo, ufugaji na ujasiriamali",
            "Utovu wa nidhamu wa watumishi",
            "Kuchelewa kulipwa malipo/madai",
            "Watumishi kutumia lugha chafu",
            "Kunyimwa haki au  huduma kutokana na ubaguzi",
        ],
    },
    {
        "type": "Unyanyasaji wa kijinisia usiohusu Unyanyasaji/uonevu/udhalilishaji wa kingono",
        "categories": [
            "Matukio ya kushambuliwa kimwili",
            "Matusi au unyanyasaji wa maneno",
            "Ubaguzi wa kijinsia",
            "Unyanyasaji wa kiuchumi",
            "Changamoto za urithi",
        ],
    },
    {
        "type": "Unyanyasaji wa kijinisia unaohusu Unyanyasaji/uonevu/udhalilishaji wa kingono",
        "categories": [
            "Unyanyasaji wa kingono",
            "Uonevu au udhalilishaji wa kingono",
        ],
    },
    {
        "type": "Mazingira",
        "categories": [
            "Udhibiti duni wa uchafuzi wa vumbi",
            "Usimamizi duni wa taka",
            "Ukosefu wa vifaakinga vya kutosha (PPE)",
        ],
    },
    {
        "type": "Maswala ya Ardhi",
        "categories": [
            "Migogoro ya umiliki wa ardhi iliyotwaliwa",
            "Migogoro kuhusu ukubwa wa ardhi",
            "Migogoro ya mipaka ya ardhi",
        ],
    },
    {
        "type": "Maswali na maoni",
        "categories": [
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

        types_created = 0
        types_skipped = 0
        categories_created = 0
        categories_skipped = 0

        for item in items:
            g_type_qs = GrievanceType.objects.filter(name=item["type"])
            if g_type_qs.exists():
                g_type = g_type_qs.first()
                types_skipped += 1
                self.stdout.write(f"  [SKIP] Type already exists: {item['type']}")
            else:
                g_type = GrievanceType(name=item["type"], user_created=user)
                g_type.save(username=username)
                types_created += 1
                self.stdout.write(
                    self.style.SUCCESS(f"  [OK] Created type: {item['type']}")
                )

            for category_name in item["categories"]:
                cat_qs = GrievanceCategory.objects.filter(
                    name=category_name, type=g_type
                )
                if cat_qs.exists():
                    categories_skipped += 1
                    self.stdout.write(
                        f"    [SKIP] Category already exists: {category_name}"
                    )
                else:
                    category = GrievanceCategory(
                        type=g_type, name=category_name, user_created=user
                    )
                    category.save(username=username)
                    categories_created += 1
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"    [OK] Created category: {category_name}"
                        )
                    )

        self.stdout.write(
            self.style.SUCCESS(
                f"\nDone! Types: {types_created} created, {types_skipped} skipped. "
                f"Categories: {categories_created} created, {categories_skipped} skipped."
            )
        )
