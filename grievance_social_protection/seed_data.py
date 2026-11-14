"""
The grievance categories (each with its types and days to resolve) and channels TASAF starts with. Migration 0028
adds whatever is missing on every database, and `manage.py seed_grievances` can add or reset them by hand.
"""

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


def _create(model, user, **fields):
    row = model(user_created=user, user_updated=user, **fields)
    try:
        # the app's models record who saved them
        row.save(username=user.username)
    except TypeError:
        # a migration's frozen model has the plain save
        row.save()
    return row


def seed_missing(category_model, type_model, channel_model, user, channels, log=lambda message: None):
    """
    Add categories, types and channels that do not exist yet; never change, restore or remove existing ones.
    Names match whatever their case ("Call center" is "Call Center"), and deleted entries count as existing.
    """
    added = {'categories': 0, 'types': 0, 'channels': 0}
    for item in GRIEVANCE_CATEGORY_SEEDS:
        category = category_model.objects.filter(name__iexact=item['category']).first()
        if category is None:
            category = _create(category_model, user, name=item['category'], timeline=item['timeline'])
            added['categories'] += 1
            log(f"category added: {item['category']}")
        for type_name in item['types']:
            if not type_model.objects.filter(category=category, name__iexact=type_name).exists():
                _create(type_model, user, category=category, name=type_name)
                added['types'] += 1
                log(f"  type added: {type_name}")
    for channel_name in filter(None, channels):
        if not channel_model.objects.filter(name__iexact=channel_name).exists():
            _create(channel_model, user, name=channel_name)
            added['channels'] += 1
            log(f"channel added: {channel_name}")
    return added
