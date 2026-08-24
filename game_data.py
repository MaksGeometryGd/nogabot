"""
game_data.py — статичные игровые данные: предметы (ITEMS), кейсы (CASES),
рецепты крафта (RECIPES), апгрейды/престиж (UPGRADES/PRESTIGE_UPGRADES),
уровни (пороги, тиры) и связанные структуры.
"""
import bisect

from premium_emoji import *  # noqa: F401,F403
from config import CRAFT_MAX_LEVEL, LEG_LIMIT, MEK_LIMIT

ITEMS = {
    "amulet": ("🪬", "Амулет галактики", 17, 10),
    "orb":    ("🔮", "Шар парадокса", 14, 20),
    "pill":   ("💊", "Таблетка силы", 12, 30),
    "candle": ("🪔", "Свеча солнцестояния", 14, 35),
    "gift":   ("💮", "Подарок кошко-девочки", 45, 5),
    "star":   ("⭐️", "Звезда перерождения", 30, 0),
    "daily_charm": (PREMIUM_DAILY_CHARM, "Дневной амулет", 15, 0),
    "mk_mgg":       (PREMIUM_MK_MGG, "Амулет MGG", 125, 0.57),
    "mk_sandsmoon": (PREMIUM_MK_SANDSMOON, "Амулет SandsMoon", 40, 3.45),
    "mk_fixsahal1": (PREMIUM_MK_FIXSAHAL1, "Амулет Fixsahal1", 30, 5.75),
    "mk_mk":        (PREMIUM_MK_MK, "Амулет Mk", 90, 1.72),
    "mk_panther":   (PREMIUM_MK_PANTHER, "Амулет Haos", 60, 8.04),
    "mk_vector":    (PREMIUM_MK_VECTOR, "Амулет Vector", 40, 4.02),
    "mk_broken":    (PREMIUM_MK_BROKEN, "Сломанный амулет", 1, 60),
    "mk_mary":      (PREMIUM_MK_MARY, "Амулет Mary", 45, 5.75),
    "mk_veron03":   (PREMIUM_MK_VERON03, "Амулет Veron03", 60, 10),
    "vip_charm":    (PREMIUM_VIP_ITEM, "VIP-амулет", 250, 0),
    "strange_coin": (PREMIUM_STRANGE_COIN, "Странная монета", 0, 0.7),

    "power_amulet":        (PREMIUM_POWER_AMULET, "Амулет силы", 40, 0),
    "galaxy_power_amulet": (PREMIUM_GALAXY_POWER_AMULET, "Амулет силы галактики", 80, 0),
    "galaxy_might_amulet": (PREMIUM_GALAXY_MIGHT_AMULET, "Амулет Мощи галактики", 100, 0),
    "hybrid_amulet":       (PREMIUM_HYBRID_AMULET, "Неактивированный гибридный амулет", 0, 0),
    "friendship_essence":  (PREMIUM_FRIENDSHIP_ESSENCE, "Эссенция дружбы", 0, 0),
    "time_particle":       (PREMIUM_TIME_PARTICLE, "Частица времени", 0, 0),
    "god_essence":         (PREMIUM_GOD_ESSENCE, "Эссенция Бога", 700, 0),
    "koshko_amulet":       (PREMIUM_KOSHKO_AMULET, "Амулет кошко-девочки", 800, 0),
    "devotion_coin":       (PREMIUM_DEVOTION_COIN, "Монета боготворства", 0, 0),
    "old_vase":            (PREMIUM_OLD_VASE, "Старая ваза", 0, 0.4),
    "golden_vase":         (PREMIUM_GOLDEN_VASE, "Золотая ваза", 0, 0),
    "godly_vase":          (PREMIUM_GODLY_VASE, "Боготворная ваза", 0, 0),

    "lucky_charm":  (PREMIUM_LUCKY_CHARM, "Малый амулет удачи", 15, 0),
    "swift_pill":   (PREMIUM_SWIFT_PILL, "Ускоренная таблетка", 12, 0),
    "party_set":    (PREMIUM_PARTY_SET, "Праздничный набор", 18, 0),
    "warm_candle":  (PREMIUM_WARM_CANDLE, "Тёплая свеча", 0, 0),

    "ice_shard":     (PREMIUM_ICE_SHARD, "Ледяной осколок", 80, 12),
    "ember":         (PREMIUM_EMBER, "Уголёк", 45, 12),
    "dragon_claw":   (PREMIUM_DRAGON_CLAW, "Коготь дракона", 55, 8),
    "paradox_charm": (PREMIUM_PARADOX_CHARM, "Оберег парадокса", 65, 5),
    "shadow_mask":   (PREMIUM_SHADOW_MASK, "Маска тени", 95, 1.5),
    "tide_wave":     (PREMIUM_TIDE_WAVE, "Волна прилива", 50, 10),
    "warrior_skull": (PREMIUM_WARRIOR_SKULL, "Череп воина", 1, 7),
    "broken_clock":  (PREMIUM_BROKEN_CLOCK, "Сломанные часы", 0, 15),
    "essence_drop":  (PREMIUM_ESSENCE_DROP, "Капля эссенции", 0, 10),
    "comet_shard":   (PREMIUM_COMET_SHARD, "Осколок кометы", 0, 3),
    "koshko_gift":  (PREMIUM_KOSHKO_GIFT, "Дар кошко-девочки", 0, 2),
    "ancient_stone": (PREMIUM_ANCIENT_STONE, "Древний камень", 0, 18),
    "fate_thread":   (PREMIUM_FATE_THREAD, "Нить судьбы", 0, 4),

    "kotyara_amulet":  (PREMIUM_KOTYARA_AMULET, "Амулет Котяры", 95, 0),
    "miku_amulet":     (PREMIUM_MIKU_AMULET, "Амулет Мику", 75, 0),
    "golda":           (PREMIUM_GOLDA_ITEM, "Голда", 52, 0),
    "karambit_gold":   (PREMIUM_KARAMBIT_GOLD, "Керамбит голд", 228, 0),
    "butterfly_legacy": (PREMIUM_BUTTERFLY_LEGACY, "Бабочка легаси", 69, 0),
    "krest_amulet":    (PREMIUM_KREST_AMULET, "Амулет Креста", 100, 0),
    "fati_amulet":     (PREMIUM_FATI_AMULET, "Амулет Фати", 80, 0),

    "chaos_orb":     (PREMIUM_CHAOS_ORB, "Шар хаоса", 0, 100),
    "chronos_clock": (PREMIUM_CHRONOS_CLOCK, "Часы Хроноса", 0, 120),
    "chronos_orb":   (PREMIUM_CHRONOS_ORB, "Хвост Джевила", 0, 120),

    "miku_fan_amulet": (PREMIUM_MIKU_FAN_AMULET, "Амулет Фаната Мику", 300, 0),

    "nogost_coin":       (PREMIUM_NOGOST_COIN, "Монета Ногости", 200, 0),
    "godly_nogost_coin": (PREMIUM_GODLY_NOGOST_COIN, "Монета Бога Ногости", 500, 0),
    "craft_coin":        (PREMIUM_CRAFT_COIN, "Монета Крафта", 0, 0),
    "bitcoin":           (PREMIUM_BITCOIN, "Биткоин", 0, 0),
    "rebirth_coin":      (PREMIUM_REBIRTH_COIN, "Монета Перерождения", 0, 0),
    "evolution_coin":    (PREMIUM_EVOLUTION_COIN, "Монета Эволюции", 0, 0),
    "awakening_coin":    (PREMIUM_AWAKENING_COIN, "Монета Пробуждения", 0, 0),
}

# Разделение ITEMS на «бустеры» (экипируемые, дают процентный буст к добыче) и «предметы»
# (сырьё для крафта / пассивные / коллекционные) для команды «помощь бустер|предмет».
# Правило: boost_percent > 0 -> бустер. Единственное исключение — chronos_orb: он тоже
# экипируется (см. _format_equipped_item_line), но эффект случайный (10-400%), поэтому
# в ITEMS у него boost_percent = 0 — добавляем его в бустеры вручную.
HELP_BOOSTER_KEYS = {k for k, v in ITEMS.items() if v[2] > 0} | {"chronos_orb"}
HELP_ITEM_KEYS = set(ITEMS.keys()) - HELP_BOOSTER_KEYS

def find_item_key_by_name(query: str, allowed_keys: set):
    """Ищет ключ в ITEMS по русскому названию, ограничиваясь набором allowed_keys
    (бустеры либо предметы). Как find_item_by_name (см. команды «!дать б/п»): сначала точное
    совпадение, иначе — по вхождению подстроки в название.
    Возвращает (key, None) при однозначном совпадении, (None, [варианты]) если совпадений
    несколько, (None, []) если не найдено вообще."""
    q = (query or "").strip().lower()
    if not q:
        return None, []
    for key in allowed_keys:
        if ITEMS[key][1].strip().lower() == q:
            return key, None
    matches = [key for key in allowed_keys if q in ITEMS[key][1].lower()]
    if len(matches) == 1:
        return matches[0], None
    if len(matches) > 1:
        matches.sort(key=lambda k: ITEMS[k][1])
        return None, matches
    return None, []

NON_TRADABLE_ITEMS = {
    "vip_charm",
    "kotyara_amulet", "miku_amulet", "golda", "karambit_gold", "butterfly_legacy",
    "krest_amulet", "fati_amulet",
    "chaos_orb", "chronos_clock", "chronos_orb",
    "miku_fan_amulet",
    "nogost_coin", "godly_nogost_coin", "craft_coin", "bitcoin",
    "rebirth_coin", "evolution_coin", "awakening_coin",
}

PASSIVE_ITEMS = {
    "strange_coin",
    "hybrid_amulet", "friendship_essence", "time_particle", "devotion_coin",
    "old_vase", "golden_vase", "godly_vase", "warm_candle",
    "broken_clock", "essence_drop", "comet_shard", "koshko_gift", "ancient_stone", "fate_thread",
    "craft_coin", "bitcoin", "rebirth_coin", "evolution_coin", "awakening_coin",
}

SELL_PRICE = {
    "amulet": 8, "orb": 6, "pill": 5, "candle": 4, "gift": 20, "star": 15, "daily_charm": 10,
    "mk_mgg": 60, "mk_sandsmoon": 18, "mk_fixsahal1": 14, "mk_mk": 22, "mk_panther": 10,
    "mk_vector": 18, "mk_broken": 8, "mk_mary": 20, "mk_veron03": 30, "vip_charm": 50,
    "strange_coin": 12,
    "power_amulet": 40, "galaxy_power_amulet": 90, "galaxy_might_amulet": 150,
    "hybrid_amulet": 200, "friendship_essence": 260, "time_particle": 220,
    "god_essence": 1000, "koshko_amulet": 1400, "devotion_coin": 60, "old_vase": 15, "golden_vase": 120, "godly_vase": 500,
    "lucky_charm": 20, "swift_pill": 18, "party_set": 25, "warm_candle": 14,
    "ice_shard": 15, "ember": 15, "dragon_claw": 22, "paradox_charm": 28, "shadow_mask": 45,
    "tide_wave": 16, "warrior_skull": 24,
    "broken_clock": 8, "essence_drop": 14, "comet_shard": 30, "koshko_gift": 35,
    "ancient_stone": 6, "fate_thread": 32,
    "nogost_coin": 300, "godly_nogost_coin": 900, "craft_coin": 150, "bitcoin": 250,
    "rebirth_coin": 400, "evolution_coin": 350, "awakening_coin": 1200,
}

ITEM_FLAT_BONUS = {
    "amulet": 1, "orb": 1, "pill": 1, "candle": 1,
    "star": 2, "gift": 3,
}

CASES = {
    1: {"name": "Базовый кейс", "price": 20, "pool": ["amulet", "orb", "pill", "candle", "gift", "old_vase"]},
    2: {"name": "Кейс Сапортов", "price": 50,
        "pool": ["mk_mgg", "mk_sandsmoon", "mk_fixsahal1", "mk_mk", "mk_panther", "mk_vector",
                 "mk_broken", "mk_mary", "mk_veron03", "strange_coin"]},
    3: {"name": "Кейс Стихий и Крафта", "price": 500,
        "pool": ["ice_shard", "ember", "dragon_claw", "paradox_charm", "shadow_mask", "tide_wave", "warrior_skull",
                 "broken_clock", "essence_drop", "comet_shard", "koshko_gift", "ancient_stone", "fate_thread"]},
}

CASE_SELLABLE_ITEMS = list(dict.fromkeys(
    CASES[1]["pool"] + CASES[2]["pool"] + CASES[3]["pool"]
))
AUTOSELL_PAGE_SIZE = 8

def parse_auto_sell_items(raw: str) -> set:
    return set(x for x in (raw or "").split(",") if x)

def format_auto_sell_items(items: set) -> str:
    return ",".join(sorted(items))

async def apply_case_reward(user_id: int, item_key: str, upgrades: dict,
                             auto_sell_enabled: bool, auto_sell_items: set) -> tuple[int, str]:
    """Выдаёт выпавший из кейса предмет — либо в инвентарь как обычно, либо, если включена
    авто-продажа и этот предмет отмечен в конфиге, сразу продаёт его за монеты.
    Возвращает (получено_монет, текст-пометка для ответа, например ' (авто-продано за 8🪙)')."""
    if auto_sell_enabled and item_key in auto_sell_items and item_key not in NON_TRADABLE_ITEMS:
        sell_lvl = upgrade_level(upgrades, "sell_boost")
        price = SELL_PRICE.get(item_key, 1) + sell_bonus_coins(upgrades)
        await db_exec("UPDATE users SET coins = coins + ? WHERE user_id = ?", (price, user_id))
        return price, f" (авто-продано за {price}🪙)"
    await add_item(user_id, item_key)
    return 0, ""

ALL_PLAYER_AMULETS = [
    "amulet", "mk_mgg", "mk_sandsmoon", "mk_fixsahal1", "mk_mk",
    "mk_panther", "mk_vector", "mk_mary", "mk_veron03",
]

RECIPES = {
    "lucky_charm": {
        "level": 0,
        "ingredients": {"amulet": 1, "orb": 1},
    },
    "swift_pill": {
        "level": 0,
        "ingredients": {"pill": 2, "candle": 1},
    },
    "party_set": {
        "level": 0,
        "ingredients": {"gift": 1, "candle": 1, "pill": 1},
    },
    "warm_candle": {
        "level": 0,
        "ingredients": {"candle": 3},
    },

    "power_amulet": {
        "level": 0,
        "ingredients": {"pill": 1, "mk_broken": 1},
    },
    "galaxy_power_amulet": {
        "level": 1,
        "ingredients": {"power_amulet": 1, "candle": 1, "amulet": 1},
    },
    "galaxy_might_amulet": {
        "level": 1,
        "ingredients": {"galaxy_power_amulet": 1, "power_amulet": 1},
    },
    "hybrid_amulet": {
        "level": 2,
        "ingredients": {"orb": 1, "galaxy_might_amulet": 1},
        "needs_all_amulets": True,
    },
    "friendship_essence": {
        "level": 2,
        "ingredients": {"hybrid_amulet": 1, "star": 1, "gift": 1},
    },
    "time_particle": {
        "level": 1,
        "ingredients": {"pill": 1, "orb": 1, "amulet": 1, "candle": 1, "gift": 1},
    },
    "god_essence": {
        "level": 2,
        "ingredients": {"time_particle": 1, "friendship_essence": 1, "mk_broken": 1},
        "craft_points_cost": 1,
    },
    "koshko_amulet": {
        "level": 2,
        "ingredients": {"party_set": 1, "mk_mgg": 1, "god_essence": 1, "time_particle": 1},
    },
    "devotion_coin": {
        "level": 1,
        "ingredients": {"strange_coin": 1},
        "coin_cost": 1000,
    },
    "golden_vase": {
        "level": 1,
        "ingredients": {"old_vase": 1},
        "score_cost": 50000,
    },
    "godly_vase": {
        "level": 2,
        "ingredients": {"golden_vase": 1, "devotion_coin": 1},
        "craft_points_cost": 1,
    },

    "chaos_orb": {
        "level": 1,
        "ingredients": {"orb": 10, "paradox_charm": 2},
    },
    "chronos_clock": {
        "level": 1,
        "ingredients": {"broken_clock": 10, "essence_drop": 1},
        "rebirth_cost": 5,
    },
    "chronos_orb": {
        "level": 3,
        "ingredients": {"chaos_orb": 69, "chronos_clock": 1, "essence_drop": 5},
        "craft_points_cost": 20,
    },

    "miku_fan_amulet": {
        "level": 1,
        "ingredients": {"mk_sandsmoon": 1, "miku_amulet": 1},
    },

    "nogost_coin": {
        "level": 2,
        "ingredients": {"strange_coin": 1},
        "score_cost": 10_000_000,
    },
    "godly_nogost_coin": {
        "level": 3,
        "ingredients": {"nogost_coin": 3, "godly_vase": 3},
    },
    "craft_coin": {
        "level": 3,
        "ingredients": {"strange_coin": 1},
        "craft_points_cost": 50,
    },
    "bitcoin": {
        "level": 2,
        "ingredients": {"strange_coin": 5},
        "coin_cost": 1_000_000,
    },
    "rebirth_coin": {
        "level": 3,
        "ingredients": {"strange_coin": 1},
        "rebirth_cost": 5000,
    },
    "evolution_coin": {
        "level": 2,
        "ingredients": {"strange_coin": 1, "galaxy_might_amulet": 5},
    },
    "awakening_coin": {
        "level": 3,
        "ingredients": {"evolution_coin": 1, "rebirth_coin": 1},
    },
}

UNIQUE_BOOSTER_TIERS = ["power_amulet", "galaxy_power_amulet", "galaxy_might_amulet", "god_essence", "koshko_amulet"]

UNIQUE_LIMIT_OVERRIDES = {
    "power_amulet": {"mek_limit": 15},
    "galaxy_power_amulet": {"galaxy_limit": 1},
    "galaxy_might_amulet": {"galaxy_limit": 1},
    "god_essence": {"mek_limit": 30, "leg_limit": 15, "galaxy_limit": 5, "star_limit": 1},
    "koshko_amulet": {"mek_limit": 30, "leg_limit": 15, "galaxy_limit": 5, "star_limit": 1, "paw_limit": 3},
}
GOD_ESSENCE_TIMER_CUT = 5
GOD_ESSENCE_FARM_SPEED = 5
TIME_PARTICLE_FARM_SPEED = 4
PAW_POINT_MULTIPLIER = 3
ICE_SHARD_SAVE_CHANCE = 0.20

EVOLUTION_COIN_SAVE_PCT = 0.30
REBIRTH_COIN_SAVE_PCT = 0.50
AWAKENING_COIN_SAVE_PCT = 0.70
AWAKENING_COIN_PRESTIGE_CHANCE = 0.01
AWAKENING_COIN_PRESTIGE_AMOUNT = 3
AWAKENING_COIN_BADGE_CHANCE = 0.0001
DRAGON_CLAW_POTION_MULT = 4
TIDE_WAVE_PROC_CHANCE = 0.05

CHAOS_ORB_FARM_CHANCE = 0.02
CHAOS_ORB_FARM_MIN = 1
CHAOS_ORB_FARM_MAX = 10_000_000

CHRONOS_ORB_REBIRTH_CHANCE = 0.009
CHRONOS_ORB_REBIRTH_MIN, CHRONOS_ORB_REBIRTH_MAX = 1, 500
CHRONOS_ORB_FARM_MULT_MIN, CHRONOS_ORB_FARM_MULT_MAX = 0.1, 5.0
CHRONOS_ORB_COIN_CHANCE = 0.05
CHRONOS_ORB_COIN_MIN, CHRONOS_ORB_COIN_MAX = 1, 10_000
CHRONOS_ORB_LEGS_CHANCE = 0.02
CHRONOS_ORB_LEGS_MIN, CHRONOS_ORB_LEGS_MAX = 1, 10_000_000
CHRONOS_ORB_NO_CD_CHANCE = 0.07
CHRONOS_ORB_PRESTIGE_CHANCE = 0.01
CHRONOS_ORB_PRESTIGE_MIN, CHRONOS_ORB_PRESTIGE_MAX = 0, 20
CHRONOS_ORB_POTION_CHANCE = 0.01
CHRONOS_ORB_BOOSTER_CHANCE = 0.01
CHRONOS_ORB_BADGE_CHANCE = 0.001
CHRONOS_ORB_STRANGE_COIN_CHANCE = 0.0069
CHRONOS_ORB_OLD_VASE_CHANCE = 0.0069

CHRONOS_BOOST_INTERVAL = 300
CHRONOS_BOOST_MIN, CHRONOS_BOOST_MAX = 10, 400

GOD_ESSENCE_FLAVOR = f"{PREMIUM_GOD_ESSENCE} Сила бога активирована."
KOSHKO_AMULET_FLAVOR = f"{PREMIUM_KOSHKO_AMULET} Сила кошко-девочки активна."
CHRONOS_ORB_FLAVOR = f"{PREMIUM_CHRONOS_ORB} ХАОС! ХАОС! ХАОС!"
GOD_TIER_LIKE = {"god_essence", "koshko_amulet"}

# ---- Справочные тексты для «помощь бустер <название>» ----
# Источник получения (крафт/номер кейса) определяем автоматически по RECIPES/CASES —
# так описание не разъедется с реальными данными при правке рецептов или пулов кейсов.
# HELP_BOOSTER_SOURCE_OVERRIDE — для бустеров, чей реальный источник не крафт/кейс
# (например, начисляется напрямую кодом за игровое действие) — переопределяет автоопределение.
HELP_BOOSTER_SOURCE_OVERRIDE = {
    "star": "даётся автоматически за каждое перерождение",
    "daily_charm": "выпадает за ежедневный бонус (команда «бонус») на 5-й день серии",
    "vip_charm": "выдаётся при покупке VIP-статуса",
}

def _help_booster_source(key: str) -> str:
    if key in HELP_BOOSTER_SOURCE_OVERRIDE:
        return HELP_BOOSTER_SOURCE_OVERRIDE[key]
    sources = []
    if key in RECIPES:
        sources.append("получается в крафтах")
    for case_num, case_data in CASES.items():
        if key in case_data["pool"]:
            sources.append(f"выпадает из «{case_data['name']}»")
    if not sources:
        return "выдаётся вручную админом или по промокоду"
    return ", ".join(sources)

# Дополнительные «изюминки» для особых бустеров — то, что не считать по одной формуле
# (уникальные слоты, секретные механики, случайный эффект и т.д.).
HELP_BOOSTER_EXTRA = {
    "god_essence": (
        "Это топовый крафтовый бустер уникального яруса — при равном экипе перебивает "
        "все остальные уникальные бустеры (амулеты силы, амулет кошко-девочки — кроме него самого). "
        "Также увеличивает лимиты по ногам/мек-ногам/галактикам и ускоряет кулдаун фермы."
    ),
    "koshko_amulet": (
        "Самый сильный уникальный бустер в игре — перебивает даже Эссенцию Бога. "
        "Даёт максимальные лимиты по ногам/мек-ногам/галактикам/звёздам и открывает лимит «лап»."
    ),
    "power_amulet": "Первая ступень уникальных бустеров — открывает увеличенный лимит по мек-ногам.",
    "galaxy_power_amulet": "Вторая ступень уникальных бустеров — открывает лимит по галактикам.",
    "galaxy_might_amulet": "Третья ступень уникальных бустеров, требуется для дальнейшего крафта Гибридного амулета.",
    "chronos_orb": (
        "Особый бустер: вместо фиксированного процента даёт СЛУЧАЙНЫЙ буст добычи от 10% до 400% "
        "при каждом фарме — иногда почти ничего, иногда джекпот. Дополнительно может случайно "
        "подарить очки перерождения, монеты, ноги, снять кулдаун фермы, дать очки престижа, "
        "зелье, другой бустер, бейдж, странную монету или старую вазу — всё это ХАОС!"
    ),
    "vip_charm": "Мощный бустер, доступный только тем, у кого куплен VIP-статус (см. «помощь бейдж vip»).",
}

def format_help_booster_text(key: str) -> str:
    emoji, name, boost, _ = ITEMS[key]
    lines = [f"+{boost}% к добыче, пока экипирован." if key != "chronos_orb" else "Даёт случайный буст добычи (см. ниже)."]
    lines.append(f"Как получить: {_help_booster_source(key)}.")
    extra = HELP_BOOSTER_EXTRA.get(key)
    if extra:
        lines.append(extra)
    return "\n".join(lines)

# ---- Справочные тексты для «помощь предмет <название>» ----
# Кто использует этот предмет как ингредиент в крафте — считаем по RECIPES, чтобы карта
# «зачем он нужен» не расходилась с реальными рецептами.
_HELP_ITEM_USED_IN = {}
for _target, _recipe in RECIPES.items():
    for _ing in _recipe["ingredients"]:
        _HELP_ITEM_USED_IN.setdefault(_ing, []).append(_target)

# Пассивные эффекты — срабатывают, просто пока предмет лежит в инвентаре (экипировать не нужно).
# Для «сейв-монет» (evolution/rebirth/awakening) используем реальные проценты из констант,
# для остального — текст по факту того, что делает соответствующий apply_*_proc.
HELP_ITEM_EXTRA = {
    "strange_coin": "Пассивный эффект: пока лежит в инвентаре — +5 🪙 к каждому базовому фарму ног.",
    "warm_candle": "Пассивный эффект: пока лежит в инвентаре — +3 🪙 к каждому базовому фарму ног.",
    "devotion_coin": "Пассивный эффект: пока лежит в инвентаре — +15 🪙 к фарму (иногда +35 🪙 с шансом 10%).",
    "old_vase": "Пассивный эффект: при фарме ног — небольшой шанс (~1%) на +1 🉑 очко перерождения.",
    "golden_vase": "Пассивный эффект: при фарме ног — шанс (~6%) на +1 🉑 очко перерождения (сильнее Старой вазы).",
    "godly_vase": (
        "Пассивный эффект: при фарме ног — шанс на очки перерождения по нарастающей, "
        "вплоть до редкого джекпота +200 🉑 (сильнее всех остальных ваз)."
    ),
    "bitcoin": "Пассивный эффект: при базовом фарме ног — очень редкий шанс (0.05%) на джекпот +15 000 000 🪙.",
    "rebirth_coin": "Пассивный эффект: пока лежит в инвентаре — гарантированно +2 🉑 к каждому базовому фарму ног.",
    "craft_coin": "Пассивный эффект: при фарме ног — шанс дать +1 💠 очко крафта.",
    "evolution_coin": f"При эволюции сохраняет {round(EVOLUTION_COIN_SAVE_PCT * 100)}% очков ноги вместо полного обнуления.",
    "rebirth_coin": (
        "Пассивный эффект: пока лежит в инвентаре — гарантированно +2 🉑 к каждому базовому фарму ног. "
        f"Также при перерождении сохраняет {round(REBIRTH_COIN_SAVE_PCT * 100)}% очков ноги."
    ),
    "awakening_coin": (
        f"Самая мощная сейв-монета: сохраняет {round(AWAKENING_COIN_SAVE_PCT * 100)}% очков ноги и "
        "уровня эволюции при ЛЮБОМ сбросе (и эволюция, и перерождение). Есть небольшой шанс "
        "дополнительно дать очки престижа или редкий бейдж."
    ),
    "chaos_orb": "Крафт-сырьё для Шара Хроноса — сам по себе лежит пассивно без эффекта, нужен только для крафта.",
}

def _help_item_source(key: str) -> str:
    if key in RECIPES:
        return "получается в крафтах"
    for case_num, case_data in CASES.items():
        if key in case_data["pool"]:
            return f"выпадает из «{case_data['name']}»"
    return "выдаётся вручную админом или по промокоду"

def format_help_item_text(key: str) -> str:
    lines = [f"Как получить: {_help_item_source(key)}."]

    used_in = _HELP_ITEM_USED_IN.get(key)
    if used_in:
        used_names = ", ".join(esc(ITEMS[u][1]) for u in used_in if u in ITEMS)
        lines.append(f"Используется как ингредиент в крафте: {used_names}.")

    extra = HELP_ITEM_EXTRA.get(key)
    if extra:
        lines.append(extra)

    if not used_in and not extra:
        lines.append("Коллекционный предмет — можно продать или уничтожить, прямого эффекта не даёт.")

    return "\n".join(lines)

def get_active_unique_tier(active_items):
    """Самый сильный уникальный крафт-бустер среди экипированных, либо None."""
    equipped = set(_normalize_active_items(active_items))
    best = None
    for key in UNIQUE_BOOSTER_TIERS:
        if key in equipped:
            best = key
    return best

def active_farm_limits(active_items, prestige_upgrades: dict = None) -> dict:
    """Лимиты за сообщение (🦵/🦿/🌌/⭐️) с учётом сильнейшего уникального бустера
    + постоянных бонусов дерева престижа (p_legs/p_mek, см. PRESTIGE_UPGRADES)
    + плоского бонуса от 🔥 Уголька (+1 к лимиту 🦵, складывается с чем угодно)
    + плоского бонуса от 🔶 Монеты Бога Ногости (+15 к лимиту 🦵, только пока экипирована)."""
    tier = get_active_unique_tier(active_items)
    overrides = UNIQUE_LIMIT_OVERRIDES.get(tier, {})
    prestige_upgrades = prestige_upgrades or {}
    leg_bonus = prestige_bonus(prestige_upgrades, "p_legs")
    mek_bonus = prestige_bonus(prestige_upgrades, "p_mek")
    equipped = set(_normalize_active_items(active_items))
    if "ember" in equipped:
        leg_bonus += 1
    if "godly_nogost_coin" in equipped:
        leg_bonus += 15
    return {
        "mek_limit": overrides.get("mek_limit", MEK_LIMIT) + mek_bonus,
        "leg_limit": overrides.get("leg_limit", LEG_LIMIT) + leg_bonus,
        "galaxy_limit": overrides.get("galaxy_limit", 0),
        "star_limit": overrides.get("star_limit", 0),
        "paw_limit": overrides.get("paw_limit", 0),
    }

def recipe_missing_ingredients(inventory_map: dict, coins: int, score: int, recipe: dict,
                                prestige_upgrades: dict = None, craft_points: int = 0, rebirth_points: int = 0) -> list:
    """Список недостающих требований рецепта в виде читаемых строк. Пустой список = всё есть."""
    missing = []
    for ing_key, qty in recipe.get("ingredients", {}).items():
        have = inventory_map.get(ing_key, 0)
        if have < qty:
            name = ITEMS[ing_key][1]
            missing.append(f"{name}: {have}/{qty}")
    if recipe.get("needs_all_amulets"):
        for ing_key in ALL_PLAYER_AMULETS:
            if inventory_map.get(ing_key, 0) < 1:
                missing.append(f"{ITEMS[ing_key][1]}: 0/1")
    coin_cost = craft_coin_cost_with_discount(recipe.get("coin_cost", 0), prestige_upgrades)
    if coin_cost and coins < coin_cost:
        missing.append(f"Монеты: {coins}/{coin_cost} 🪙")
    score_cost = recipe.get("score_cost", 0)
    if score_cost and score < score_cost:
        missing.append(f"Очки ног: {score}/{score_cost}")
    craft_points_cost = recipe.get("craft_points_cost", 0)
    if craft_points_cost and craft_points < craft_points_cost:
        missing.append(f"Очки крафта: {craft_points}/{craft_points_cost} 💠")
    rebirth_cost = recipe.get("rebirth_cost", 0)
    if rebirth_cost and rebirth_points < rebirth_cost:
        missing.append(f"Очки перерождения: {rebirth_points}/{rebirth_cost} 🉑")
    return missing

def format_recipe_requirements(recipe: dict) -> str:
    parts = [f"{qty}x {ITEMS[k][1]}" for k, qty in recipe.get("ingredients", {}).items()]
    if recipe.get("needs_all_amulets"):
        parts.append("по 1x каждого амулета игрока (кроме VIP и Сломанного)")
    if recipe.get("coin_cost"):
        parts.append(f"{recipe['coin_cost']} 🪙")
    if recipe.get("score_cost"):
        parts.append(f"{recipe['score_cost']} очков ног")
    if recipe.get("craft_points_cost"):
        parts.append(f"{recipe['craft_points_cost']} 💠")
    if recipe.get("rebirth_cost"):
        parts.append(f"{recipe['rebirth_cost']} 🉑")
    return " + ".join(parts)

REBIRTH_MIN_EVO = 5
REBIRTH_EVO_STEP = 3
REBIRTH_POINTS_PER_STEP = 2
REBIRTH_HARDNESS_STEP = 0.125
PRESTIGE_PER_REBIRTH = 1
PRESTIGE_PER_ULTRA_REBIRTH = 50

def _linear_cost(base: int, step: int):
    return lambda level: base + step * (level - 1)

def _per_n_levels_cost(base: int, step: int, n: int):
    return lambda level: base + step * ((level - 1) // n)

UPGRADES = {
    "farm_yield": {
        "name": "Ферма ДОБЫЧА",
        "desc": "+10% к добыче фермы за лвл",
        "max_level": 10,
        "cost": _linear_cost(1, 1),
        "category": 1,
    },
    "farm_cd": {
        "name": "Ферма КД",
        "desc": "-2 мин к КД фермы за лвл",
        "max_level": 5,
        "cost": _linear_cost(1, 2),
        "category": 1,
    },
    "auto_farm_legs": {
        "name": "Авто-Ферма НОГИ",
        "desc": "1:10 ног/мин · 2:100 ног/30с · 3:1000 ног/10с",
        "max_level": 3,
        "cost": _linear_cost(1, 4),
        "category": 1,
    },
    "auto_farm_coins": {
        "name": "Авто-Ферма КОИНЫ",
        "desc": "1:1 коин/5мин · 2:5 коин/5мин · 3:10 коин/3мин",
        "max_level": 3,
        "cost": _linear_cost(1, 2),
        "category": 1,
    },
    "booster": {
        "name": "Бустер",
        "desc": "+5% буст ко всему за лвл",
        "max_level": 50,
        "cost": _per_n_levels_cost(1, 1, 3),
        "category": 2,
    },
    "equip_slots": {
        "name": "Слоты экипировки",
        "desc": "+1 слот экипировки за лвл (база 1, макс 3 слота на 2 лвл)",
        "max_level": 2,
        "cost": _linear_cost(5, 5),
        "category": 2,
    },
    "discount": {
        "name": "Скидка",
        "desc": "-10% к цене кейсов за лвл",
        "max_level": 3,
        "cost": _linear_cost(1, 1),
        "category": 2,
    },
    "sell_boost": {
        "name": "Продажа",
        "desc": "+2 коина к продаже за лвл (3 лвл: 1% шанс +1 🉑 при продаже)",
        "max_level": 3,
        "cost": _linear_cost(2, 2),
        "category": 2,
    },
    "crafts": {
        "name": "Крафты", "desc": "Открывает уровни рецептов крафта (0/1/2/3) за 🉑",
        "max_level": CRAFT_MAX_LEVEL,
        "cost": lambda level: 5000 if level == CRAFT_MAX_LEVEL else _linear_cost(15, 20)(level),
        "category": 3,
        "extra_cost": lambda level: (
            ("craft_points", 10) if level == CRAFT_MAX_LEVEL else None
        ),
    },
    "brew_speed": {
        "name": "Скорость готовки зелья",
        "desc": "-10% времени варки зелья за лвл",
        "max_level": 5,
        "cost": _linear_cost(3, 3),
        "category": 3,
    },
    "brew_duration": {
        "name": "Длительность зелья",
        "desc": "+20% к длительности эффекта зелий за лвл",
        "max_level": 3,
        "cost": _linear_cost(5, 5),
        "category": 3,
    },
    "exchanger": {"name": "Обменник", "desc": "В разработке", "max_level": 2, "cost": None, "category": 3, "wip": True},
}
UPGRADE_ORDER = list(UPGRADES.keys())
UPGRADE_CATEGORIES = {1: "🌾 Ферма", 2: "🎒 Экономика", 3: "🔨 Крафты и прочее"}

def _prestige_cost(base: int, growth: float):
    return lambda level: round(base * (growth ** (level - 1)))

def _echelon_bonus(level: int) -> int:
    """Общий паттерн разреженности: чем выше уровень, тем реже даётся следующая "ступенька" эффекта.
    Уровни 1-5: +1 ступень за уровень. С 5 ур эшелоны удваиваются бесконечно — границы [5,10) шаг 2,
    [10,20) шаг 4, [20,40) шаг 8, [40,80) шаг 16 и т.д. Проверено: с 5 ур нужно пройти 2 уровня ради
    следующей ступени (5→7), с 10 ур — 4 уровня (10→14). Замкнутая формула — быстрая даже для
    гигантских уровней (после Ультра перерождения), не цикл по каждому уровню."""
    if level <= 0:
        return 0
    if level <= 5:
        return level
    bonus = 5
    start = 5
    gap = 2
    while start < level:
        end = start * 2
        span = min(level, end) - start
        bonus += span // gap
        if level >= end:
            start = end
            gap *= 2
        else:
            break
    return bonus

def _milestone_bonus(milestones: list):
    """Особая кривая для 'штучных' веток (напр. Слоты: +1 на 1 ур, следующий +1 только на 100 ур).
    milestones — отсортированный список уровней, на которых бонус увеличивается на 1.
    Использует bisect — быстро даже для больших списков милстоунов."""
    def _fn(level: int) -> int:
        return bisect.bisect_right(milestones, level)
    return _fn

def _per_level_bonus(level: int) -> int:
    """Прямая (не разреженная) кривая: каждый купленный уровень сразу даёт +1 к эффекту.
    Используется только для 'Слоты' — это очень мощный бонус, поэтому взамен разреженности
    его цена растёт в 10 раз за уровень (см. _prestige_cost(2, 10) в p_slots)."""
    return max(0, level)

PRESTIGE_UPGRADES = {
    "p_legs": {
        "name": "Обычные ноги", "emoji": "🦵",
        "desc": "+1 к лимиту 🦵",
        "cost": _prestige_cost(1, 1.08),
        "bonus": _echelon_bonus,
    },
    "p_mek": {
        "name": "Робо ноги", "emoji": "🦿",
        "desc": "+1 к лимиту 🦿",
        "cost": _prestige_cost(1, 1.09),
        "bonus": _echelon_bonus,
    },
    "p_slots": {
        "name": "Слоты", "emoji": "🎒",
        "desc": "+1 слот экипировки за КАЖДЫЙ уровень (цена растёт x10 за уровень — самая дорогая ветка)",
        "cost": _prestige_cost(2, 10.0),
        "bonus": _per_level_bonus,
    },
    "p_farm_speed": {
        "name": "Скорость фарма", "emoji": "⏱️",
        "desc": "-1% к КД фермы",
        "cost": _prestige_cost(1, 1.08),
        "bonus": _echelon_bonus,
    },
    "p_farm_yield": {
        "name": "Добыча", "emoji": "📈",
        "desc": "+0.5% к множителю фермы",
        "cost": _prestige_cost(1, 1.08),
        "bonus": _echelon_bonus,
    },
    "p_brew_speed": {
        "name": "Скорость варки", "emoji": "🔥",
        "desc": "-2% времени варки зелий",
        "cost": _prestige_cost(1, 1.08),
        "bonus": _echelon_bonus,
    },
    "p_craft_discount": {
        "name": "Скидка крафта", "emoji": "🔨",
        "desc": "-1% к стоимости крафта",
        "cost": _prestige_cost(1, 1.08),
        "bonus": _echelon_bonus,
    },
    "p_echo": {
        "name": "Эхо", "emoji": "🔮",
        "desc": "+1% шанс бонус-очка перерождения",
        "cost": _prestige_cost(1, 1.10),
        "bonus": _echelon_bonus,
    },
}
PRESTIGE_ORDER = list(PRESTIGE_UPGRADES.keys())
PRESTIGE_PAGE_SIZE = 4

POTIONS = {
    "potion_speed": {
        "emoji": "🧪⚡", "name": "Зелье ускорения",
        "desc": "x2 к добыче фермы",
        "effect": "farm_x2",
        "brew_cost": 40, "brew_seconds": 600,
        "duration_seconds": 1800,
    },
    "potion_luck": {
        "emoji": "🧪🍀", "name": "Зелье удачи",
        "desc": "x2 к шансу проков ваз и Эссенции Бога",
        "effect": "luck_x2",
        "brew_cost": 50, "brew_seconds": 900,
        "duration_seconds": 1800,
    },
    "potion_haste": {
        "emoji": "🧪🌀", "name": "Зелье без КД",
        "desc": "Следующие 3 фарма без ожидания кулдауна",
        "effect": "no_cd",
        "brew_cost": 60, "brew_seconds": 1200,
        "charges": 3,
    },
}
POTION_ORDER = list(POTIONS.keys())
NO_CD_CHARGES_KEY = "potion_haste"

AUTO_FARM_LEGS_RATES = {1: (10, 60), 2: (100, 30), 3: (1000, 10)}
AUTO_FARM_COINS_RATES = {1: (1, 300), 2: (5, 300), 3: (10, 180)}

