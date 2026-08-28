import asyncio
import bisect
import functools
import os
import random
import re
import time
from datetime import datetime
from urllib.parse import quote, unquote

import libsql
import aiohttp
from aiogram import Bot, Dispatcher, F, BaseMiddleware
from aiogram.exceptions import TelegramRetryAfter, TelegramBadRequest
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.types import (
    Message, CallbackQuery, ErrorEvent, InlineKeyboardMarkup, InlineKeyboardButton,
    LabeledPrice, PreCheckoutQuery,
)
from aiohttp import web

def _load_dotenv_if_present():
    for path in ("/home/container/.env", os.path.join(os.path.dirname(__file__), ".env")):
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    os.environ.setdefault(key, value)
        except Exception as e:
            print(f".env не удалось прочитать ({path}): {e}")
        break

_load_dotenv_if_present()

TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_USERNAME = "MaksGeometryGd"
ADMIN_USER_ID = 7148430462
TURSO_URL = os.environ.get("TURSO_DATABASE_URL")
TURSO_TOKEN = os.environ.get("TURSO_AUTH_TOKEN")

# --- Обязательная подписка на канал (проверяется на !ферма, эволюция, перерождение) ---
REQUIRED_CHANNEL_USERNAME = "mggnoganews"          # без @ и без ссылки
REQUIRED_CHANNEL_URL = "https://t.me/mggnoganews"
REQUIRED_CHANNEL_CHAT_ID = f"@{REQUIRED_CHANNEL_USERNAME}"
SUBSCRIPTION_CHECK_CACHE_TTL = 300  # сек, чтобы не долбить Telegram API на каждый фарм
_subscription_cache: dict[int, tuple[bool, float]] = {}

PREMIUM_MIKU = '<tg-emoji emoji-id="5199793038410391513">🤩</tg-emoji>'
PREMIUM_MGG = '<tg-emoji emoji-id="6327920744789444368">🥰</tg-emoji>'

PREMIUM_BADGE_EVO = '<tg-emoji emoji-id="5370704514561093615">🏅</tg-emoji>'
PREMIUM_BADGE_CASE = '<tg-emoji emoji-id="5328257610472775810">🎖️</tg-emoji>'
PREMIUM_BADGE_FARM = '<tg-emoji emoji-id="5415966542078683753">🥇</tg-emoji>'
PREMIUM_BADGE_EVO5 = '<tg-emoji emoji-id="5372812377135789260">👑</tg-emoji>'

# ==== Бейджи за уровень эволюции (10/25/50/100/250/500/1000/5000/10000) ====
# emoji-id пустые — вставь свои готовые id, fallback-эмодзи уже расставлены по смыслу названия.
PREMIUM_BADGE_EVO10 = '<tg-emoji emoji-id="6019118557621653717">🔰</tg-emoji>'
PREMIUM_BADGE_EVO25 = '<tg-emoji emoji-id="6021737443995160656">🥈</tg-emoji>'
PREMIUM_BADGE_EVO50 = '<tg-emoji emoji-id="6021831143001689820">🥋</tg-emoji>'
PREMIUM_BADGE_EVO100 = '<tg-emoji emoji-id="5462948145652594708">🏆</tg-emoji>'
PREMIUM_BADGE_EVO250 = '<tg-emoji emoji-id="6008035368744521190">👑</tg-emoji>'
PREMIUM_BADGE_EVO500 = '<tg-emoji emoji-id="5802946896494334636">☄️</tg-emoji>'
PREMIUM_BADGE_EVO1000 = '<tg-emoji emoji-id="5206263763124117710">🌌</tg-emoji>'
PREMIUM_BADGE_EVO5000 = '<tg-emoji emoji-id="5787496116719195306">🔱</tg-emoji>'
PREMIUM_BADGE_EVO10000 = '<tg-emoji emoji-id="5267389029011182710">🛡️</tg-emoji>'
PREMIUM_BADGE_EVO50000 = '<tg-emoji emoji-id="5888974760720732797">💥</tg-emoji>'
PREMIUM_BADGE_EVO100000 = '<tg-emoji emoji-id="6325484162597784431">📜</tg-emoji>'
PREMIUM_BADGE_EVO1000000 = '<tg-emoji emoji-id="5431805131630852717">🌟</tg-emoji>'

# ==== Бейджи за открытые кейсы (50/500/5000) ====
PREMIUM_BADGE_CASE50 = '<tg-emoji emoji-id="5235695112419303615">🎁</tg-emoji>'
PREMIUM_BADGE_CASE500 = '<tg-emoji emoji-id="5188400169506334671">🎰</tg-emoji>'
PREMIUM_BADGE_CASE5000 = '<tg-emoji emoji-id="5460938959951513194">💣</tg-emoji>'

# ==== Бейджи за суммарно нафармленные очки ноги ====
PREMIUM_BADGE_FARM1M = '<tg-emoji emoji-id="5463270938214678914">🌱</tg-emoji>'
PREMIUM_BADGE_FARM500M = '<tg-emoji emoji-id="5174879174371837069">🚀</tg-emoji>'
PREMIUM_BADGE_FARM5B = '<tg-emoji emoji-id="5431610634036845778">⚙️</tg-emoji>'
PREMIUM_BADGE_FARM1T = '<tg-emoji emoji-id="5388722374814214652">⚡️</tg-emoji>'
PREMIUM_BADGE_FARM1Q = '<tg-emoji emoji-id="5298816567436400568">🌌</tg-emoji>'
PREMIUM_BADGE_FARM1QI = '<tg-emoji emoji-id="5418296093685342477">🦵</tg-emoji>'

# ==== Бейджи за баланс монет ====
PREMIUM_BADGE_COIN1K = '<tg-emoji emoji-id="5449418135381759397">🪙</tg-emoji>'
PREMIUM_BADGE_COIN10K = '<tg-emoji emoji-id="5190526908462292507">💰</tg-emoji>'
PREMIUM_BADGE_COIN100K = '<tg-emoji emoji-id="5431389597839937743">💵</tg-emoji>'
PREMIUM_BADGE_COIN10M = '<tg-emoji emoji-id="5415594207068822547">🏦</tg-emoji>'
PREMIUM_BADGE_COIN1B = '<tg-emoji emoji-id="5285087180488726417">👑</tg-emoji>'
PREMIUM_BADGE_COIN10B = '<tg-emoji emoji-id="5323396295904209738">🏛️</tg-emoji>'

# ==== Бейджи за баланс очков перерождения ====
PREMIUM_BADGE_REBIRTH100 = '<tg-emoji emoji-id="6032728694802354547">🕯️</tg-emoji>'
PREMIUM_BADGE_REBIRTH10K = '<tg-emoji emoji-id="6265068953588994740">✨</tg-emoji>'
PREMIUM_BADGE_REBIRTH1M = '<tg-emoji emoji-id="5337128947027036693">🌠</tg-emoji>'
PREMIUM_BADGE_REBIRTH1B = '<tg-emoji emoji-id="5228699714500710949">👁️</tg-emoji>'
PREMIUM_BADGE_REBIRTH10B = '<tg-emoji emoji-id="5242433645523775166">♾️</tg-emoji>'

# ==== Бейдж за ультра-перерождение ====
PREMIUM_BADGE_ULTRA_REBIRTH = '<tg-emoji emoji-id="5447546448763699600">🔥</tg-emoji>'

# ==== Бейджи за стрик ежедневного бонуса ====
PREMIUM_BADGE_STREAK7 = '<tg-emoji emoji-id="5314665117017718786">📅</tg-emoji>'
PREMIUM_BADGE_STREAK30 = '<tg-emoji emoji-id="5274013522144016987">🗓️</tg-emoji>'

# ==== Бейджи за количество крафтов ====
PREMIUM_BADGE_CRAFT10 = '<tg-emoji emoji-id="5231151548121244459">🔨</tg-emoji>'
PREMIUM_BADGE_CRAFT100 = '<tg-emoji emoji-id="5354931010943347669">⚒️</tg-emoji>'

# ==== Бейджи за очки престижа ====
PREMIUM_BADGE_PRESTIGE10 = '<tg-emoji emoji-id="5049027699067062001">🎭</tg-emoji>'
PREMIUM_BADGE_PRESTIGE100 = '<tg-emoji emoji-id="5406980362393902143">🧘</tg-emoji>'
PREMIUM_BADGE_PRESTIGE25000 = '<tg-emoji emoji-id="5386617411342449059">📿</tg-emoji>'
PREMIUM_BADGE_PRESTIGE50000 = '<tg-emoji emoji-id="5388706032463671610">🕊️</tg-emoji>'
PREMIUM_BADGE_PRESTIGE100000 = '<tg-emoji emoji-id="6251413878165472946">👁️</tg-emoji>'
PREMIUM_BADGE_PRESTIGE250000 = '<tg-emoji emoji-id="5460788837959623745">🌀</tg-emoji>'
PREMIUM_BADGE_PRESTIGE500000 = '<tg-emoji emoji-id="5330274071848438189">🧠</tg-emoji>'
PREMIUM_BADGE_PRESTIGE1000000 = '<tg-emoji emoji-id="5192703340189871377">♾️</tg-emoji>'

PREMIUM_DAILY_CHARM = '<tg-emoji emoji-id="5233570349148311519">🧿</tg-emoji>'

PREMIUM_MK_MGG = '<tg-emoji emoji-id="5420141555233071341">🧿</tg-emoji>'
PREMIUM_MK_SANDSMOON = '<tg-emoji emoji-id="5197260300490907908">🌙</tg-emoji>'
PREMIUM_MK_FIXSAHAL1 = '<tg-emoji emoji-id="6325473957755488220">🔧</tg-emoji>'
PREMIUM_MK_MK = '<tg-emoji emoji-id="5776399733702528178">🪝</tg-emoji>'
PREMIUM_MK_PANTHER = '<tg-emoji emoji-id="5393538390362705684">⚡️</tg-emoji>'
PREMIUM_MK_VECTOR = '<tg-emoji emoji-id="6206233738494347353">↗️</tg-emoji>'
PREMIUM_MK_BROKEN = '<tg-emoji emoji-id="5208923808169222461">💔</tg-emoji>'

PREMIUM_OWNER_BADGE = '<tg-emoji emoji-id="5204056085509477484">💠</tg-emoji>'
PREMIUM_VIP_BADGE = '<tg-emoji emoji-id="5233333941263437275">💎</tg-emoji>'
PREMIUM_VIP_ITEM = '<tg-emoji emoji-id="5344025423258864934">🎗️</tg-emoji>'
PREMIUM_MK_MARY = '<tg-emoji emoji-id="6328022870521808963">🌹</tg-emoji>'
PREMIUM_MK_VERON03 = '<tg-emoji emoji-id="5429446558930182229">🔷</tg-emoji>'
PREMIUM_STRANGE_COIN = '<tg-emoji emoji-id="5035428694441592026">🪙</tg-emoji>'

PREMIUM_POWER_AMULET = '<tg-emoji emoji-id="5364047860713143546">💪</tg-emoji>'
PREMIUM_GALAXY_POWER_AMULET = '<tg-emoji emoji-id="5451648825431175858">🌠</tg-emoji>'
PREMIUM_GALAXY_MIGHT_AMULET = '<tg-emoji emoji-id="5335070858828344908">🌋</tg-emoji>'
PREMIUM_HYBRID_AMULET = '<tg-emoji emoji-id="5204242195032336769">🧬</tg-emoji>'
PREMIUM_FRIENDSHIP_ESSENCE = '<tg-emoji emoji-id="5843554051341422500">🤝</tg-emoji>'
PREMIUM_TIME_PARTICLE = '<tg-emoji emoji-id="5363857580777029543">⏳</tg-emoji>'
PREMIUM_GOD_ESSENCE = '<tg-emoji emoji-id="5242602154270667208">👁️</tg-emoji>'
PREMIUM_DEVOTION_COIN = '<tg-emoji emoji-id="5416007206829047767">🟡</tg-emoji>'
PREMIUM_OLD_VASE = '<tg-emoji emoji-id="6334461494649948210">🏺</tg-emoji>'
PREMIUM_GOLDEN_VASE = '<tg-emoji emoji-id="5954115825324527429">⚱️</tg-emoji>'
PREMIUM_GODLY_VASE = '<tg-emoji emoji-id="5242521945756413456">🏆</tg-emoji>'
PREMIUM_LUCKY_CHARM = '<tg-emoji emoji-id="5435935451355555165">🍀</tg-emoji>'
PREMIUM_SWIFT_PILL = '<tg-emoji emoji-id="5886217713839246898">⚡</tg-emoji>'
PREMIUM_PARTY_SET = '<tg-emoji emoji-id="5852607601883221665">🎉</tg-emoji>'
PREMIUM_WARM_CANDLE = '<tg-emoji emoji-id="5253717838870363235">🕯</tg-emoji>'
PREMIUM_KOSHKO_AMULET = '<tg-emoji emoji-id="5371041424680710006">🐈</tg-emoji>'

PREMIUM_CRAFT_POINT = '<tg-emoji emoji-id="5254028100979787948">💠</tg-emoji>'

PREMIUM_KOTYARA_AMULET = '<tg-emoji emoji-id="5415692772273312091">🐱</tg-emoji>'
PREMIUM_MIKU_AMULET = '<tg-emoji emoji-id="5397821533613735774">🎤</tg-emoji>'
PREMIUM_GOLDA_ITEM = '<tg-emoji emoji-id="5330230039843709983">🥇</tg-emoji>'
PREMIUM_KARAMBIT_GOLD = '<tg-emoji emoji-id="5060114895148680390">🔪</tg-emoji>'
PREMIUM_BUTTERFLY_LEGACY = '<tg-emoji emoji-id="4943160586331490355">🦋</tg-emoji>'

PREMIUM_KREST_AMULET = '<tg-emoji emoji-id="5282820155015971423">✝️</tg-emoji>'
PREMIUM_FATI_AMULET = '<tg-emoji emoji-id="5404393696865041225">🤲</tg-emoji>'
PREMIUM_GUITARIST_CROWN = '<tg-emoji emoji-id="5445191681404057893">👑</tg-emoji>'
PREMIUM_VILON_AMULET = '<tg-emoji emoji-id="5386386711469117619">🔱</tg-emoji>'
PREMIUM_MIKU_RING = '<tg-emoji emoji-id="5292079619174852549">💍</tg-emoji>'
PREMIUM_MIKU_FAN_AMULET = '<tg-emoji emoji-id="5199714801286132798">🎧</tg-emoji>'

PREMIUM_BADGE_TESTER = '<tg-emoji emoji-id="5217791863368470760">🥰</tg-emoji>'
PREMIUM_BADGE_SUPPORT = '<tg-emoji emoji-id="5947343263194157527">🛠️</tg-emoji>'
PREMIUM_BADGE_POWER = '<tg-emoji emoji-id="5780703608760700844">💪</tg-emoji>'
PREMIUM_BADGE_TOP1_PAST = '<tg-emoji emoji-id="5363999757079429238">👑</tg-emoji>'

PREMIUM_CHAOS_ORB = '<tg-emoji emoji-id="5201679280672616755">🌀</tg-emoji>'
PREMIUM_CHRONOS_CLOCK = '<tg-emoji emoji-id="5237697056805510735">⏰</tg-emoji>'
PREMIUM_CHRONOS_ORB = '<tg-emoji emoji-id="5305669252181672918">🔮</tg-emoji>'
PREMIUM_BADGE_CHAOS_MASTER = '<tg-emoji emoji-id="5237888066886064441">⚡️</tg-emoji>'

PREMIUM_NOGOST_COIN = '<tg-emoji emoji-id="5413879072008724252">🪙</tg-emoji>'
PREMIUM_GODLY_NOGOST_COIN = '<tg-emoji emoji-id="5361563655924110883">🪙</tg-emoji>'
PREMIUM_CRAFT_COIN = '<tg-emoji emoji-id="5334956805971792834">🪙</tg-emoji>'
PREMIUM_BITCOIN = '<tg-emoji emoji-id="5474537505015486009">🪙</tg-emoji>'
PREMIUM_REBIRTH_COIN = '<tg-emoji emoji-id="6032751750186799376">🪙</tg-emoji>'
PREMIUM_EVOLUTION_COIN = '<tg-emoji emoji-id="5366230850855777158">🪙</tg-emoji>'
PREMIUM_AWAKENING_COIN = '<tg-emoji emoji-id="5767231090922101971">🪙</tg-emoji>'
PREMIUM_BADGE_INVESTOR = '<tg-emoji emoji-id="5298614648138919107">💹</tg-emoji>'

# ==== Эво-апгрейд: премиум-эмодзи для ожерелий/карманной звезды/искры (вставь свои emoji-id) ====
PREMIUM_REBIRTH_SPARK = '<tg-emoji emoji-id="5467837274429335080">✨</tg-emoji>'
PREMIUM_STAR_NECKLACE = '<tg-emoji emoji-id="5415853988165734070">📿</tg-emoji>'
PREMIUM_BLAZING_STAR_NECKLACE = '<tg-emoji emoji-id="5938541999031325561">📿</tg-emoji>'
PREMIUM_POCKET_STAR = '<tg-emoji emoji-id="5435957248314579621">🌠</tg-emoji>'

# ==== Крафт 3 ур.: Любитель Мастерства + его дроп-предмет nano-IT (вставь свои emoji-id) ====
PREMIUM_MASTERY_LOVER_AMULET = '<tg-emoji emoji-id="5936158605714661655">🤖</tg-emoji>'
PREMIUM_NANO_IT = '<tg-emoji emoji-id="5452097366045783407">🔩</tg-emoji>'

PREMIUM_ICE_SHARD = '<tg-emoji emoji-id="5363812028353898315">🧊</tg-emoji>'
PREMIUM_EMBER = '<tg-emoji emoji-id="5773638078321135255">🔥</tg-emoji>'
PREMIUM_DRAGON_CLAW = '<tg-emoji emoji-id="5307771389564954063">🐉</tg-emoji>'
PREMIUM_PARADOX_CHARM = '<tg-emoji emoji-id="5467522315887594988">🧿</tg-emoji>'
PREMIUM_SHADOW_MASK = '<tg-emoji emoji-id="5463247917189977301">🕶️</tg-emoji>'
PREMIUM_TIDE_WAVE = '<tg-emoji emoji-id="5994370062708904465">🌊</tg-emoji>'
PREMIUM_WARRIOR_SKULL = '<tg-emoji emoji-id="5231105033625423869">💀</tg-emoji>'
PREMIUM_BROKEN_CLOCK = '<tg-emoji emoji-id="5431903044000306112">🕰️</tg-emoji>'
PREMIUM_ESSENCE_DROP = '<tg-emoji emoji-id="5260717261173304462">🩸</tg-emoji>'
PREMIUM_COMET_SHARD = '<tg-emoji emoji-id="5294390831271129091">🌠</tg-emoji>'
PREMIUM_ANCIENT_STONE = '<tg-emoji emoji-id="5224412151728328775">🪨</tg-emoji>'
PREMIUM_FATE_THREAD = '<tg-emoji emoji-id="5366343945934624965">🧵</tg-emoji>'
PREMIUM_KOSHKO_GIFT = '<tg-emoji emoji-id="6217230280701251264">🎀</tg-emoji>'

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

REGULAR_THRESHOLDS = [10, 50, 150, 300, 500, 800, 1200, 1600, 2000, 2400,
                       3000, 3600, 4200, 4800, 5400, 6000, 6600, 7200, 7800, 8400]

CUSTOM_LEVELS = [
    (9000,  "🦵🍀", "нога удачи"),
    (9600,  "🦵🌬️", "нога воздухана"),
    (10200, "🦵🌔", "нога SandsMoon"),
    (10800, "🦵🍗", "гигантская нога"),
    (11400, "🦵✨", "блестящая нога"),
    (12000, "🦵🥉", "бронзовая нога"),
    (12600, "🦵🥈", "серебряная нога"),
    (13200, "🦵🏆", "золотая нога"),
    (13800, "🦵💎", "алмазная нога"),
    (14400, "🦵💀", "нога смерти"),
    (15000, "🦵😎", "нога Fixsahal1"),
    (15600, "🦵👼", "нога ангела"),
    (16200, "🦵🐺", "нога Волка"),
    (16800, PREMIUM_MIKU, "нога Мику"),
    (17400, "🦵🏇", "нога героя"),
    (18000, "🦵👁", "нога полу-бога"),
    (18600, "🦵🌌", "космическая нога"),
    (19200, "🦵🧿", "нога бога"),
    (19800, PREMIUM_MGG, "нога MGG"),
]

ALL_THRESHOLDS = REGULAR_THRESHOLDS + [t for t, _, _ in CUSTOM_LEVELS]
MAX_LEVEL_SCORE = ALL_THRESHOLDS[-1]

EXTRA_TIERS = [
    (40, 42, "🦵☄️", "нога Метеорита"),
    (43, 45, "🦵🌠✨", "нога Кометы"),
    (46, 48, "🦵🪐", "нога Планеты"),
    (49, 50, "🦵🪐💍", "нога Сатурна"),
    (51, 53, "🦵⚡🔥", "нога Плазмы"),
    (54, 55, "🦵🔥🌊", "нога Солнечной вспышки"),
    (56, 58, "🦵📡✨", "нога Пульсара"),
    (59, 60, "🦵📡💫", "нога Магнетара"),
    (61, 65, "🦵🌠", "нога Квазара"),
    (66, 70, "🦵🌠🌠", "нога Блазара"),
    (71, 75, "🦵🌑🕳️", "нога Тёмной Материи"),
    (76, 80, "🦵🌑⚡", "нога Тёмной Энергии"),
    (81, 90, "🦵⚫🕳️", "нога Чёрной дыры"),
    (91, 100, "🦵⚫🌀", "нога Сверхмассивной чёрной дыры"),
    (101, 112, "🦵🌌", "нога галактики"),
    (113, 125, "🦵🌌✨", "нога Млечного Пути"),
    (126, 138, "🦵🌠🌌", "нога вселенной"),
    (139, 150, "🦵🌠🌌🔭", "нога Наблюдаемой вселенной"),
    (151, 175, "🦵🌀🌌", "нога Мультивселенной"),
    (176, 200, "🦵⚛️🌀", "нога Сингулярности"),
    (201, 250, "🦵⚛️💥", "нога Большого Взрыва"),
    (251, 300, "🦵🌀🌌♾️", "нога Метавселенной"),
    (301, 400, "🦵☢️⚛️", "нога Антиматерии"),
    (401, 500, "🦵☢️🌀", "нога Аннигиляции"),
    (501, 750, "🦵⬛🌌", "нога пустоты"),
    (751, 1000, "🦵⬛♾️", "нога Абсолютной пустоты"),
    (1001, 1250, "🦵♾️🌀", "нога Парадокса"),
    (1251, 1500, "🦵♾️🔁", "нога Временной петли"),
    (1501, 1750, "🦵🟩💻", "нога Матрицы"),
    (1751, 2000, "🦵🟩🧠", "нога Симуляции"),
    (2001, 2500, "🦵🔷🔁", "нога Фрактала"),
    (2501, 3000, "🦵🔷♾️", "нога Бесконечного Фрактала"),
    (3001, 4000, "🦵🌀⏳🕳️", "нога Разрыва пространственно-временного континуума"),
    (4001, 5000, "🦵🌀⏳💥", "нога Коллапса реальности"),
    (5001, 5500, "🦵🚀", "нога Сверхсветового прыжка"),
    (5501, 6000, "🦵🚀💫", "нога Прыжка через червоточину"),
    (6001, 6750, "🦵🚀🌌", "нога Гиперпространственного прыжка"),
    (6751, 7500, "🦵🌀🕳️", "нога Кротовой норы"),
    (7501, 8500, "🦵⏳🌀", "нога Искривления времени"),
    (8501, 9750, "🦵⏳🔀", "нога Временного парадокса"),
    (9751, 11250, "🦵⏳❌", "нога Стирателя моментов"),
    (11251, 13000, "🦵⏳❌🌀", "нога Стирателя тайм-лайнов"),
    (13001, 15000, "🦵⏳❌🕳️", "нога Стирателя эпох"),
    (15001, 17500, "🦵⏳❌🌌", "нога Стирателя вселенных"),
    (17501, 20000, "🦵⏳❌♾️", "нога Стирателя реальностей"),
]
MGG_MEGA_LEVEL = 20001
MGG_MEGA_EMOJI = PREMIUM_MGG
MGG_MEGA_NAME = "нога кошко-девочки MGG"

ULTRA_REQUIRED_EVO = 50
ULTRA_REQUIRED_LEG_LEVEL = MGG_MEGA_LEVEL
ULTRA_REQUIRED_REBIRTHS = 5

ULTRA_LEG_LEVEL = 20002
ULTRA_LEG_EMOJI = "🦵🧪"
ULTRA_LEG_NAME = "тест нога"

# Визуальные тиры для ULTRA-диапазона (level >= 20002). Первые тиры узкие (шаг 15),
# дальше ширина каждого тира растёт геометрически (x~2.15), чтобы за разумное число
# ступеней дойти до астрономических уровней. Всё, что выше последнего тира (до
# ULTRA_LEVEL_CAP = 2×10^100), попадает в ULTRA_LEG_NAME как «потолочное» название —
# такие уровни физически недостижимы обычным фармом, только через ручную admin-выдачу.
ULTRA_TIERS = [
    (20002, 20016, "🦵⚠️🌀", "нога Аномалии"),
    (20017, 20048, "🦵🧬", "нога Мутации"),
    (20049, 20117, "🦵🌡️", "нога Абсолютного нуля"),
    (20118, 20265, "🦵🔬", "нога Планковской длины"),
    (20266, 20583, "🦵🌫️", "нога Квантовой пены"),
    (20584, 21267, "🦵🎲🌀", "нога Квантовой неопределённости"),
    (21268, 22738, "🦵🐈‍⬛📦", "нога кота Шрёдингера"),
    (22739, 25901, "🦵🕸️", "нога Струнной теории"),
    (25902, 32701, "🦵📐🌌", "нога 11-го измерения"),
    (32702, 47321, "🦵🌈🌀", "нога Браны"),
    (47322, 78754, "🦵🪞🌌", "нога Зеркальной вселенной"),
    (78755, 146335, "🦵🔁♾️", "нога Вечного возвращения"),
    (146336, 291634, "🦵🌌❌", "нога Схлопывания вселенной"),
    (291635, 604027, "🦵🧊💫", "нога Большого Замерзания"),
    (604028, 1275672, "🦵🔥🌌", "нога Большого Сжатия"),
    (1275673, 2719709, "🦵📖🌌", "нога Книги Судеб вселенной"),
    (2719710, 5824389, "🦵🎭🌌", "нога Иллюзии реальности"),
    (5824390, 12499451, "🦵🧩♾️", "нога Головоломки бытия"),
    (12499452, 26850834, "🦵👁️‍🗨️", "нога Всевидящего наблюдателя"),
    (26850835, 57706307, "🦵🌌🧠", "нога Космического разума"),
    (57706308, 124045574, "🦵⚙️🌌", "нога Симулятора вселенных"),
    (124045575, 266674998, "🦵🗺️♾️", "нога Карты всех вселенных"),
    (266674999, 573328260, "🦵🧿🌌", "нога Ока Мультиверса"),
    (573328261, 1232632773, "🦵🔗🌌", "нога Сцепленных вселенных"),
    (1232632774, 2650137476, "🦵🌌🌌", "нога Вселенной вселенных"),
    (2650137477, 5697772587, "🦵♾️🧠", "нога Бесконечного разума"),
    (5697772588, 12025085910546, "🦵📜♾️", "нога Летописи бытия"),
    (12025085910547, 25853934684689, "🦵🗿♾️", "нога Изначального творца"),
    (25853934684690, 55585959549096, "🦵🌌👑", "нога Владыки мультивселенной"),
    (55585959549097, 119509813007571, "🦵♾️👑", "нога Императора бесконечности"),
    (119509813007572, 256946097943292, "🦵❔♾️", "нога За пределами понимания"),
]

ULTRA_LEVEL_CAP = 2 * 10 ** 100

ULTRA_REBIRTH_BOOST = 5.0

LEG_POINT = 1
LEG_LIMIT = 5
MEK_POINT = 18
MEK_LIMIT = 10

# ==== Эво-апгрейд: новые «ноги»-эмодзи, открывающиеся по уровню эволюции ====
# Каждая запись: emoji -> (evolution_level_required, точки за штуку, лимит символов в сообщении).
# Точки считаются как MEK_POINT * (1 + bonus_pct/100), т.е. «на X% выше, чем робоноги».
EVO_LEG_TIERS = {
    "🦶": {"level": 10, "bonus_pct": 20, "limit": 10},
    "👣": {"level": 20, "bonus_pct": 30, "limit": 5},
    "🧦": {"level": 50, "bonus_pct": 50, "limit": 5},
    "👟": {"level": 100, "bonus_pct": 100, "limit": 5},
    "🥾": {"level": 250, "bonus_pct": 200, "limit": 5},
    "🩴": {"level": 500, "bonus_pct": 500, "limit": 3},
    "👢": {"level": 1000, "bonus_pct": 1200, "limit": 2},
}
EVO_LEG_EMOJI_ORDER = ["🦶", "👣", "🧦", "👟", "🥾", "🩴", "👢"]
# level -> emoji, для быстрой проверки «на этом уровне эволюции разблокировалась новая нога».
EVO_LEG_UNLOCK_BY_LEVEL = {cfg["level"]: emoji for emoji, cfg in EVO_LEG_TIERS.items()}

# Уровни эволюции для остальных разблокировок «Эво-апгрейда».
EVO_UNLOCK_REBIRTH_SPARK_LEVEL = 5    # ✨ Искра перерождения
EVO_UNLOCK_MEK2_LEVEL = 10            # доп. бонус к добыче «фермы» (см. EVO_FARM_BONUS_LVL10); сама 🦶 через EVO_LEG_TIERS
EVO_UNLOCK_NECKLACE_CRAFTS_LEVEL = 15  # крафты: Ожерелье из звёзд / пылающей звезды / Карманная звезда

# Доп. добыча фермы (команда «ферма») при достижении 10 уровня эволюции.
EVO_FARM_BONUS_LVL10 = 4000

# 🔥📿 Ожерелье пылающей звезды (крафт-бустер 15 ур. эволюции, +210% к добыче при экипировке):
# при фарме ног независимые шансы дать очки перерождения / очки престижа.
BLAZING_NECKLACE_REBIRTH_CHANCE = 0.017
BLAZING_NECKLACE_REBIRTH_RANGE = (1, 15)
BLAZING_NECKLACE_PRESTIGE_CHANCE = 0.012
BLAZING_NECKLACE_PRESTIGE_RANGE = (1, 3)

# 📿 Ожерелье из звёзд (крафт-бустер 15 ур. эволюции, +120% к добыче при экипировке):
# шанс дать предмет из кейса 1 при фарме ног.
STAR_NECKLACE_CASE1_DROP_CHANCE = 0.025

# 🌠 Карманная звезда (не бустер, пассивный предмет из крафта 15 ур. эволюции):
# буст команды «ферма» x1.6 + гарантированные очки перерождения за каждый её вызов,
# и отдельно буст x1.2 обычной фармы ног (🦵/🦿/... в чате).
POCKET_STAR_FARM_CMD_MULT = 1.6
POCKET_STAR_FARM_CMD_REBIRTH_RANGE = (1, 10)
POCKET_STAR_LEG_FARM_MULT = 1.2

# 30 уровень: пассивный буст «Поток эволюции» — шанс на доп. эволюцию сверху при каждой эволюции.
EVO_FLOW_UNLOCK_LEVEL = 30
EVO_FLOW_EXTRA_CHANCE = 0.10

# Шанс кражи предмета у случайного игрока того же чата при фарме ног (🦵/🦿) — не привязан
# к какому-либо бустеру, срабатывает у всех. Ворует только из CASE_SELLABLE_ITEMS (кейсы
# 1-2-3), никогда крафтовые/уникальные/эво-предметы. Если у выбранной жертвы нечего украсть —
# тихий промах, без сообщения.
LEG_STEAL_CHANCE = 0.01

# Сколько бейджей игрок может ОДНОВРЕМЕННО показывать (в топах/профиле/инфо) — как слоты
# экипировки в инвентаре: заработать можно сколько угодно, но включить показ — не больше этого.
BADGES_DISPLAY_LIMIT = 5

# 🔱 Амулет Вилона: пока экипирован, каждый фарм ног (🦵/🦿) идёт в счётчик; на VILON_TRIGGER_EVERY-й
# раз счётчик сбрасывается и активируется x3 к добыче фермы/ног на VILON_BOOST_SECONDS секунд.
VILON_TRIGGER_EVERY = 20
VILON_BOOST_SECONDS = 20
VILON_BOOST_MULT = 3

# 🐱 Амулет Котяры: пока экипирован, при каждом фарме ног — шанс KOTYARA_BOOST_CHANCE дать
# x2 к добыче на KOTYARA_BOOST_SECONDS секунд (поверх обычного пассивного буста амулета).
KOTYARA_BOOST_CHANCE = 0.25
KOTYARA_BOOST_SECONDS = 10
KOTYARA_BOOST_MULT = 2

# 💍 Кольцо Мику: пока экипировано, символ 🎶 в тексте фарма ног (лимит 1 за сообщение)
# удваивает итог фарма — применяется как множитель поверх total, аналогично 🌌/⭐️.
MIKU_RING_SYMBOL_LIMIT = 1
MIKU_RING_FARM_MULT = 2

# Бейджи за уровень эволюции — (ключ, название) по возрастанию порога. Сами emoji-константы
# (PREMIUM_BADGE_EVO<N>) берутся из premium_emoji.py по этому же ключу с префиксом evo_milestone_.
EVO_MILESTONE_BADGE_LEVELS = [
    ("evo_milestone_10", 10, "Новичок в эво"),
    ("evo_milestone_25", 25, "Средний в эво"),
    ("evo_milestone_50", 50, "Мастер эво"),
    ("evo_milestone_100", 100, "Эво-чемпион"),
    ("evo_milestone_250", 250, "Король эво"),
    ("evo_milestone_500", 500, "Уничтожитель Эво"),
    ("evo_milestone_1000", 1000, "Всемогущий в эво"),
    ("evo_milestone_5000", 5000, "Эво-бог"),
    ("evo_milestone_10000", 10000, "Эво-Титан"),
    ("evo_milestone_50000", 50000, "Эво-Крушитель"),
    ("evo_milestone_100000", 100000, "Эво-Легенда"),
    ("evo_milestone_1000000", 1000000, "Эво-Абсолют"),
]

# Бейджи за количество открытых кейсов (любых).
CASE_MILESTONE_BADGE_LEVELS = [
    ("case_milestone_50", 50, "Любитель кейсов"),
    ("case_milestone_500", 500, "Кейсовый безумец"),
    ("case_milestone_5000", 5000, "Разоритель Кейсов"),
]

# Бейджи за суммарно нафармленные очки ноги (total_farmed).
FARM_MILESTONE_BADGE_LEVELS = [
    ("farm_milestone_1m", 1_000_000, "Начальный фармер"),
    ("farm_milestone_500m", 500_000_000, "Продвинутый фармер"),
    ("farm_milestone_5b", 5_000_000_000, "Мастер фарма"),
    ("farm_milestone_1t", 1_000_000_000_000, "Бог фарма"),
    ("farm_milestone_1q", 1_000_000_000_000_000, "Всемогущий фармер"),
    ("farm_milestone_1qi", 1_000_000_000_000_000_000, "Фармер-ногость"),
]

# Бейджи за баланс монет (🪙, coins).
COIN_MILESTONE_BADGE_LEVELS = [
    ("coin_milestone_1k", 1_000, "Мелкий вкладчик"),
    ("coin_milestone_10k", 10_000, "Коллекционер монет"),
    ("coin_milestone_100k", 100_000, "Денежный мешок"),
    ("coin_milestone_10m", 10_000_000, "Магнат"),
    ("coin_milestone_1b", 1_000_000_000, "Коин-Олигарх"),
    ("coin_milestone_10b", 10_000_000_000, "Хозяин Экономики"),
]

# Бейджи за баланс очков перерождения (🉑, rebirth_points).
REBIRTH_MILESTONE_BADGE_LEVELS = [
    ("rebirth_milestone_100", 100, "Первое дыхание"),
    ("rebirth_milestone_10k", 10_000, "Искра цикла"),
    ("rebirth_milestone_1m", 1_000_000, "Странник перерождений"),
    ("rebirth_milestone_1b", 1_000_000_000, "Владыка Циклов"),
    ("rebirth_milestone_10b", 10_000_000_000, "Бессмертный"),
]

# Бейджи за стрик ежедневного бонуса (bonus_streak — дней подряд, см. daily_bonus()).
STREAK_MILESTONE_BADGE_LEVELS = [
    ("streak_milestone_7", 7, "Неутомимый"),
    ("streak_milestone_30", 30, "Железная воля"),
]

# Бейджи за количество успешных крафтов (crafts_done).
CRAFT_MILESTONE_BADGE_LEVELS = [
    ("craft_milestone_10", 10, "Ремесленник"),
    ("craft_milestone_100", 100, "Мастер-Кузнец"),
]

# Бейджи за баланс очков престижа (💠🔮 prestige_points).
PRESTIGE_MILESTONE_BADGE_LEVELS = [
    ("prestige_milestone_10", 10, "Искушённый"),
    ("prestige_milestone_100", 100, "Просветлённый"),
    ("prestige_milestone_25000", 25000, "Хранитель Мудрости"),
    ("prestige_milestone_50000", 50000, "Вознёсшийся"),
    ("prestige_milestone_100000", 100000, "Владыка Престижа"),
    ("prestige_milestone_250000", 250000, "Трансцендентный"),
    ("prestige_milestone_500000", 500000, "Абсолютный Разум"),
    ("prestige_milestone_1000000", 1000000, "За Гранью Престижа"),
]

FARM_COOLDOWN = 1200
FARM_BASE = (70, 170)
FARM_EVOLVED = (500, 900)

EXCHANGE_RATE = 200
REVERSE_EXCHANGE_RATE = 150
CRAFT_POINTS_EXCHANGE_RATE = 100
CRAFT_MAX_LEVEL = 3

DAILY_TABLE = [100, 250, 500, 750, 1000]
DAILY_MIN_GAP = 20 * 3600
DAILY_STREAK_LIMIT = 48 * 3600

BADGE_EVO_TOTAL = 30000

EVO_HARDNESS_RATE = 0.20
EVO_BOOST_STEP = 0.10

# Базовый уровень ноги (порог очков), нужный, чтобы сделать «эволюция» с 0 эво.
# С каждой пройденной эволюцией сам требуемый уровень растёт на 1 (39 -> 40 -> 41 -> ...),
# независимо от EVO_HARDNESS_RATE (которое усложняет стоимость ЭТОГО же уровня в процентах).
EVO_REQUIRED_BASE_LEVEL = 39

VIP_BOOST = 2.0

LEG_REPLY_COOLDOWN = 1
LEG_FARM_COOLDOWN = 0.8
VIP_STARS_PRICE = 15
VIP_FOREVER_SECONDS = 100 * 365 * 86400
PING_INTERVAL = 600

TEXTS = {
    "promo_create_1": 'Формат: !промокод создать "тип" "количество" "активаций" "название"\n'
                       'Тип: ноги/эво/коин/очкп/крафт или предмет:<ключ>.',
    "promo_create_2": '❌ Неизвестный тип награды: «{v0}». Смотри формат: ноги/эво/коин/очкп/крафт или предмет:<ключ>.',
    "promo_create_3": '❌ Количество должно быть положительным числом.',
    "promo_create_4": '❌ Число активаций должно быть положительным числом.',
    "promo_create_5": '❌ Промокод «{v0}» уже существует. Сначала удали его: !промокод удалить "{v0}".',
    "promo_create_6": '✅ Промокод «{v0}» создан!\nНаграда: {v1} × {v2}\nАктиваций: {v3}',
    "promo_delete_1": 'Формат: !промокод удалить "название"',
    "promo_delete_2": '❌ Промокод «{v0}» не найден.',
    "promo_delete_3": '🗑 Промокод «{v0}» удалён.',
    "promo_list_1": 'Активных промокодов пока нет.',
    "promo_list_2": '🎟 <b>Промокоды ({v0}):</b>\n{v1}',
    "promo_redeem_1": 'Формат: промокод <название> (или промо <название>)',
    "promo_redeem_2": '❌ Такого промокода не существует.',
    "promo_redeem_3": '⚠️ Активации промокода «{v0}» закончились.',
    "promo_redeem_4": '⚠️ Ты уже активировал этот промокод раньше.',
    "promo_redeem_5": '🎉 Промокод «{v0}» активирован! Получено: {v1}',

    "promo_create_badge_1": 'Формат: !промокод создать бейдж "название_бейджа" "название_промокода"\n'
                             'Доступные бейджи: фанат мику, сапорт, потужность, топ1 в прошлом.',
    "promo_create_badge_2": '❌ Неизвестный бейдж: «{v0}». Смотри список доступных бейджей: фанат мику, сапорт, потужность, топ1 в прошлом.',
    "promo_create_badge_3": '❌ Промокод «{v0}» уже существует. Сначала удали его: !промокод удалить "{v0}".',
    "promo_create_badge_4": '✅ Промокод «{v0}» создан!\nНаграда: {v1} бейдж «{v2}»\nАктиваций: 1',

    "maybe_announce_levelup_1": '🎉 {v0} поднялся до нового уровня! {v1}{v2}{v3}',
    "notify_off_1": 'Уведомления о новом уровне выключены.',
    "notify_on_1": 'Уведомления о новом уровне включены.',
    "vip_info_command_1": 'У тебя уже есть VIP-статус! 💎',
    "vip_info_command_2": '💎 VIP даёт постоянный буст +{v0}% к добыче.\nЦена: {v1} звёзд Telegram — выдаётся навсегда. Для оформления напиши админу.',
    "auto_evolve_not_vip_1": '⚠️ Авто-эволюция доступна только с VIP-статусом. Команда «вип» — как получить.',
    "auto_evolve_on_1": '⚙️💎 Авто-эволюция включена. Как только хватит очков — эволюция сработает сама.',
    "auto_evolve_off_1": '⚙️ Авто-эволюция выключена.',
    "auto_rebirth_not_vip_1": '⚠️ Авто-перерождение доступно только с VIP-статусом. Команда «вип» — как получить.',
    "auto_rebirth_on_1": '♻️💎 Авто-перерождение включено. Как только эволюция достигнет {v0} — перерождение сработает само.',
    "auto_rebirth_off_1": '♻️ Авто-перерождение выключено.',
    "ping_not_vip_1": '⚠️ Команда «пинг» доступна только с VIP-статусом. Команда «вип» — как получить.',
    "vip_stats_not_vip_1": '⚠️ Команда «стата» доступна только с VIP-статусом. Команда «вип» — как получить.',
    "compact_off_1": '📋 Краткий режим выключен — бонусы (вазы, монеты, шары и т.д.) снова показываются полностью.',
    "compact_on_1": '📋 Краткий режим включён — доп. тексты бонусов при фарме скрыты, видна только основная строка.',
    "auto_sell_on_1": '💰 Авто-продажа включена. Настрой список предметов: «авто продажа настройка».',
    "auto_sell_off_1": '💰 Авто-продажа выключена.',
    "vip_case_open_1": 'Формат: вип открыть кейс <номер> <кол-во> (максимум 20 за раз).',
    "vip_case_open_2": '⚠️ Авто-эволюция VIP-only. Команда «вип» — как получить.',
    "vip_case_open_3": 'Такого кейса нет. Посмотри «кейсы» — список номеров.',
    "vip_case_open_4": 'Максимум 20 кейсов за одну команду.',
    "vip_case_open_5": 'Не хватает монет: нужно {v0} 🪙, у тебя {v1} 🪙.',
    "vip_case_open_6": '💎📦 Открыто {v0}× «{v1}» за {v2} 🪙 (осталось {v3} 🪙):\n{v4}',
    "buy_vip_invoice_1": 'Это не твоя покупка!',
    "process_successful_payment_1": '💎 Оплата прошла! VIP-статус выдан навсегда. Спасибо за поддержку!',
    "badges_menu_1": 'У тебя пока нет значков. Качай ногу, эволюционируй, открывай кейсы!',
    "badges_menu_2": f'🏷 Твои значки (жми, чтобы включить/выключить показ — максимум {BADGES_DISPLAY_LIMIT} одновременно):',
    "toggle_badge_1": 'Это не твои значки!',
    "toggle_badge_2": 'Готово!',
    "toggle_badge_3": f'Уже показано максимум значков ({BADGES_DISPLAY_LIMIT}) — сначала выключи один, чтобы включить другой.',
    "count_legs_1": '{v0} {v1} → +{v2} очков{v3} {v4}(Всего: {v5}){v6}',
    "count_legs_2": 'Лютый рофл засчитан! {v0} → +{v1} очков{v2} (Всего: {v3}){v4}',
    "info_player_1": 'Игрок не найден (он ещё не писал ноги в этом боте).',
    "send_legs_top_1": 'В топе пока пусто, никто еще не кинул ногу... 🧍',
    "send_evo_top_1": 'В топе пока пусто.',
    "send_coin_top_1": 'В топе пока пусто.',
    "send_rebirth_top_1": 'В топе пока пусто.',
    "require_subscription_1": '📝 Для работы на ферме нужно быть подписанным на канал.\nПодписывайтесь на канал и бегом обратно фармить',
    "farm_1": 'Ферма на кулдауне ⏳ Осталось {v0} мин {v1} сек',
    "farm_2": '{v0} 🦵 +{v1} очков (Всего: {v2}){v3}{v4}{v5}{v6}',
    "farm_3": 'Наферметил ногу! 🦵 +{v0} очков (Всего: {v1}){v2}{v3}{v4}',
    "daily_bonus_1": 'Бонус уже забирал сегодня ⏳ Приходи через {v0} ч {v1} мин',
    "daily_bonus_2": '🎁 День {v0}: +{v1} очков ноги (Всего: {v2}){v3}',
    "reverse_exchange_1": 'Количество монет должно быть больше нуля.',
    "reverse_exchange_2": 'Недостаточно монет. У тебя {v0} 🪙.',
    "reverse_exchange_3": 'Обменял {v0} 🪙 → +{v1} очков ноги (Всего очков: {v2})',
    "exchange_1": 'Формат: обменять <количество монет>. Курс: {v0} очков ноги = 1 монета.',
    "exchange_2": 'Количество монет должно быть больше нуля.',
    "exchange_3": 'Недостаточно очков. У тебя {v0}, максимум можешь обменять на {v1} 🪙.',
    "exchange_4": 'Обменял {v0} очков → +{v1} 🪙 монет (Всего монет: {v2}){v3}',
    "transfer_currency_1": 'Ответь этой командой на сообщение того, кому передаёшь.',
    "transfer_currency_2": 'Нельзя передать самому себе.',
    "transfer_currency_3": 'Передавать можно только с 1 уровня эволюции.',
    "transfer_currency_4": 'Недостаточно очков. У тебя {v0}.',
    "transfer_currency_5": '{v0} передал {v1} очков игроку {v2}.',
    "transfer_currency_6": 'Недостаточно монет. У тебя {v0}.',
    "transfer_currency_7": '{v0} передал {v1} 🪙 игроку {v2}.',
    "transfer_item_direct_1": 'Ответь этой командой на сообщение того, кому передаёшь предмет.',
    "transfer_item_direct_2": '❌ Такого предмета не существует: «{v0}». Проверь название в «инвентарь».',
    "transfer_item_direct_3": '🚫 {v0} {v1} нельзя передать — это личный значок, не предмет.',
    "transfer_item_direct_4": 'Нельзя передать предмет самому себе.',
    "transfer_item_direct_5": 'У тебя нет предмета «{v0}».',
    "transfer_item_direct_6": '{v0} {v1} передан игроку {v2}!',
    "give_or_transfer_1": 'Укажи, что передать: число+валюту («дать 100 коин») или название предмета («передать свеча»).',
    "give_or_transfer_2": 'Некорректное количество.',
    "give_or_transfer_3": '❌ Такой валюты не существует: «{v0}». Доступно: ног, коин.',
    "give_or_transfer_4": 'Некорректное количество.',
    "sell_item_1": 'Не нашёл такой предмет среди {v0}. Если это не то — попробуй «{v1} <название>».',
    "sell_item_2": '🚫 {v0} {v1} нельзя продать — это личный значок, не предмет.',
    "sell_item_3": 'У тебя нет предмета «{v0}».',
    "sell_item_4": 'Продал {v0} {v1} за {v2} 🪙.{v3}',
    "sell_item_4_all": 'Продал всё: {v0} {v1} x{v2} за {v3} 🪙.{v4}',
    "sell_wrong_format_1": 'Не понял формат. Укажи тип: «продать б <название>» — для бустеров, «продать п <название>» — для предметов.',
    "destroy_item_1": 'Не нашёл такой предмет среди {v0}. Если это не то — попробуй «{v1} <название>».',
    "destroy_item_2": '🚫 {v0} {v1} нельзя уничтожить — это личный значок, не предмет.',
    "destroy_item_3": 'У тебя нет предмета «{v0}».',
    "destroy_item_4": '🗑 Уничтожил {v0} {v1}. Без награды — назад не вернуть.',
    "destroy_wrong_format_1": 'Не понял формат. Укажи тип: «уничтожение б <название>» — для бустеров, «уничтожение п <название>» — для предметов.',
    "inventory_1": '🎒 Инвентарь пуст.',
    "inventory_back_to_menu_1": 'Это не твой инвентарь!',
    "inventory_open_category_1": 'Это не твой инвентарь!',
    "toggle_equip_1": 'Это не твой инвентарь!',
    "potion_brew_busy_1": '🔥 Котёл уже занят — дождись, пока текущее зелье сварится.',
    "potion_brew_no_coins_1": 'Не хватает монет: нужно {v0} 🪙, у тебя {v1} 🪙.',
    "potion_brew_started_1": '⚗️ Варка начата: {v0} {v1} будет готово через {v2}.',
    "potion_collect_none_1": 'Котёл пуст — нечего забирать.',
    "potion_collect_not_ready_1": 'Зелье ещё варится — подожди {v0}.',
    "potion_collect_ok_1": '✅ Забрал: {v0} {v1}!',
    "potion_use_none_1": 'У тебя нет такого зелья в запасе.',
    "potion_use_ok_1": '{v0} {v1} выпито! Действует {v2}.',
    "potion_use_ok_charges_1": '{v0} {v1} выпито! Действует следующие {v2} использования фермы.',
    "toggle_equip_2": 'Этот предмет нельзя экипировать — он действует пассивно, пока лежит в инвентаре.',
    "toggle_equip_4": 'Готово!',
    "toggle_equip_5": 'Занято максимум слотов ({v0}) — сначала сними один бустер, чтобы надеть другой.',
    "craft_do_1": 'Это не твой крафт!',
    "craft_do_2": 'Рецепт не найден.',
    "craft_do_3": 'Нужен уровень крафта {v0}, у тебя {v1}.',
    "craft_do_4": 'Готово!',
    "send_case_inspect_1": 'Такого кейса нет.',
    "open_case_instant_1": 'Такого кейса нет.',
    "open_case_instant_2": 'Не хватает монет. Нужно {v0} 🪙, у тебя {v1} 🪙.',
    "open_case_instant_3": '🎉 Выпало: {v0} {v1} (+{v2}%)!\nОстаток монет: {v3} 🪙',
    "case_list_1": 'Доступные кейсы:',
    "inspect_case_callback_1": 'Это не твоё меню!',
    "buy_case_1": 'Это не твой кейс!',
    "buy_case_2": 'Не хватает монет. Нужно {v0} 🪙',
    "buy_case_3": 'Кейс открыт!',
    "evolve_1": 'Нужно достичь «ногу мгг» (39 ур, {v0} очков), чтобы эволюционировать.',
    "evolve_2": '🎆 ЭВОЛЮЦИЯ! Прогресс сброшен, теперь у тебя {v0} уровень эволюции навсегда.\n⚠️ Прокачка уровней теперь на {v1}% сложнее.{v2}',
    "toggle_event_1": '🌟 Ивент «Золотая ногость» запущен! Х2 к фарме ног во всех чатах.',
    "toggle_event_2": 'Ивент «Золотая ногость» окончен.',
    "upgrade_change_page_1": 'Это не твоё меню прокачки!',
    "upgrade_buy_1": 'Это не твоё меню прокачки!',
    "upgrade_buy_2": 'Этот раздел ещё в разработке.',
    "upgrade_buy_3": 'Максимальный уровень уже достигнут.',
    "upgrade_buy_4": 'Не хватает 🉑. Нужно {v0}, у тебя {v1}.',
    "upgrade_buy_5": 'Улучшено! {v0} → {v1} лвл',
    "prestige_buy_4": 'Не хватает 🔮. Нужно {v0}, у тебя {v1}.',
    "rebirth_1": 'Перерождение доступно с {v0} уровня эволюции (сейчас у тебя {v1}). Каждые {v2} уровней эво = 1 🉑.',
    "rebirth_2": '🉑 <b>ПЕРЕРОЖДЕНИЕ!</b>\nОчки ноги и эволюция сброшены. Получено: +{v0} 🉑 (Всего: {v1}) и +{v3} 🔮 престижа.\n⚠️ Эволюции теперь на {v2}% сложнее, чем с нуля.\nПрокачки из меню «апгрейд» остались с тобой навсегда.',
    "ultra_rebirth_locked_1": (
        '🌌 <b>Ультра перерождение</b> заблокировано:\n'
        '● Эволюция: {v0}/{v1}\n'
        '● Уровень ноги: {v2}/{v3}\n'
        '● Перерождений: {v4}/{v5}\n'
        '● Монета Пробуждения в инвентаре: {v6}\n'
        '● Хвост Джевила в инвентаре: {v7}\n'
        '⚠️ Нужны все пять условий сразу.'
    ),
    "ultra_rebirth_already_1": '🌌 Ты уже прошёл Ультра перерождение — второй раз нельзя.',
    "ultra_rebirth_confirm_1": (
        '🌌 <b>Тайны ждут вас.</b>\n'
        'За порогом — обнуление очков, эволюции и перерождений. Пути назад не будет.\n'
        'Открой то, что видели не все: {v0} {v1} ({v2} лвл) и постоянный буст +{v3}% к добыче.\n'
        'Прокачки и предметы шагнут в неизвестность вместе с тобой.'
    ),
    "ultra_rebirth_success_1": (
        '🌌✨ <b>Порог пройден. Тайны раскрыты.</b>\n'
        'Открыт {v0} {v1} ({v2} лвл) и постоянный буст добычи +{v3}%.\n'
        'Получено +{v4} 🔮 очков престижа.\n'
        'Прокачки и предметы остались с тобой навсегда.'
    ),
    "ultra_rebirth_cancelled_1": 'Ультра перерождение отменено — прогресс не тронут.',
    "ultra_rebirth_not_owner_1": 'Это не твоё подтверждение!',
    "show_balance_1": '💰 <b>Твой баланс</b>\n━━━━━━━━━━━━━━━━━━\n👣 Очки ноги: <code>{v0}</code>\n🪙 Монеты: <code>{v1}</code>\n🉑 Очки перерождения: <code>{v2}</code> (перерождений: {v3})\n💠 Очки крафта: <code>{v5}</code>\n{v4}',
    "admin_give_rebirth_1": 'Формат: !дать очкп <количество> [себе] (в ответ на сообщение игрока)',
    "admin_give_rebirth_2": 'Ответь этой командой на сообщение игрока, либо допиши «себе».',
    "admin_give_rebirth_3": 'Некорректное количество.',
    "admin_give_rebirth_4": 'Выдано {v0} 🉑 игроку {v1} (Всего: {v2})',
    "admin_take_rebirth_1": 'Формат: !снять очкп <количество> [себе] (в ответ на сообщение игрока)',
    "admin_take_rebirth_2": 'Ответь этой командой на сообщение игрока, либо допиши «себе».',
    "admin_take_rebirth_3": 'Некорректное количество.',
    "admin_take_rebirth_4": 'Снято {v0} 🉑 у игрока {v1} (Осталось: {v2})',
    "broadcast_news_1": 'Напиши текст новости после команды: !новость <текст>',
    "broadcast_news_2": 'Разослано в {v0} чатов. Не удалось: {v1}.',
    "admin_give_legs_1": 'Формат: !дать ног <количество> [себе] (в ответ на сообщение игрока)',
    "admin_give_legs_2": 'Ответь этой командой на сообщение игрока, либо допиши «себе».',
    "admin_give_legs_3": 'Некорректное количество.',
    "admin_give_legs_4": 'Выдано {v0} очков ноги игроку {v1}. Теперь у него: {v2}',
    "admin_take_legs_1": 'Формат: !снять ноги <количество> [себе] (в ответ на сообщение игрока)',
    "admin_take_legs_2": 'Ответь этой командой на сообщение игрока, либо допиши «себе».',
    "admin_take_legs_3": 'Некорректное количество.',
    "admin_take_legs_4": 'Снято очков у {v0}. Теперь у него: {v1}',
    "admin_give_evo_1": 'Формат: !дать эво <количество> [себе] (в ответ на сообщение игрока)',
    "admin_give_evo_2": 'Ответь этой командой на сообщение игрока, либо допиши «себе».',
    "admin_give_evo_3": 'Некорректное количество.',
    "admin_give_evo_4": 'Выдано {v0} уровней эволюции игроку {v1}. Теперь: {v2}',
    "admin_take_evo_1": 'Формат: !снять эво <количество> [себе] (в ответ на сообщение игрока)',
    "admin_take_evo_2": 'Ответь этой командой на сообщение игрока, либо допиши «себе».',
    "admin_take_evo_3": 'Некорректное количество.',
    "admin_take_evo_4": 'Снято {v0} уровней эволюции у {v1}. Теперь: {v2}',
    "admin_give_coin_1": 'Формат: !дать коин <количество> [себе] (в ответ на сообщение игрока)',
    "admin_give_coin_2": 'Ответь этой командой на сообщение игрока, либо допиши «себе».',
    "admin_give_coin_3": 'Некорректное количество.',
    "admin_give_coin_4": 'Выдано {v0} 🪙 игроку {v1}. Теперь: {v2}',
    "admin_take_coin_1": 'Формат: !снять коин <количество> [себе] (в ответ на сообщение игрока)',
    "admin_take_coin_2": 'Ответь этой командой на сообщение игрока, либо допиши «себе».',
    "admin_take_coin_3": 'Некорректное количество.',
    "admin_take_coin_4": 'Снято {v0} 🪙 у {v1}. Теперь: {v2}',
    "admin_give_boost_1": 'Формат: !дать б <название бустера> [себе] (в ответ на сообщение игрока)',
    "admin_give_boost_2": 'Не нашёл такой бустер. Для пассивных предметов используй «!дать п».',
    "admin_give_boost_3": 'Ответь этой командой на сообщение игрока, либо допиши «себе».',
    "admin_give_boost_4": 'Выдан бустер {v0} {v1} игроку {v2}.',
    "admin_take_boost_1": 'Формат: !снять б <название бустера> [себе] (в ответ на сообщение игрока)',
    "admin_take_boost_2": 'Не нашёл такой бустер. Для пассивных предметов используй «!снять п».',
    "admin_take_boost_3": 'Ответь этой командой на сообщение игрока, либо допиши «себе».',
    "admin_take_boost_4": 'Снят бустер {v0} {v1} у игрока {v2}.',
    "admin_take_boost_5": 'У игрока {v0} нет предмета «{v1}».',
    "admin_give_passive_1": 'Формат: !дать п <название предмета> [себе] (в ответ на сообщение игрока)',
    "admin_give_passive_2": 'Не нашёл такой пассивный предмет. Для бустеров используй «!дать б».',
    "admin_give_passive_3": 'Ответь этой командой на сообщение игрока, либо допиши «себе».',
    "admin_give_passive_4": 'Выдан предмет {v0} {v1} игроку {v2}.',
    "admin_take_passive_1": 'Формат: !снять п <название предмета> [себе] (в ответ на сообщение игрока)',
    "admin_take_passive_2": 'Не нашёл такой пассивный предмет. Для бустеров используй «!снять б».',
    "admin_take_passive_3": 'Ответь этой командой на сообщение игрока, либо допиши «себе».',
    "admin_take_passive_4": 'Снят предмет {v0} {v1} у игрока {v2}.',
    "admin_take_passive_5": 'У игрока {v0} нет предмета «{v1}».',
    "admin_give_vip_1": 'Формат: !дать вип <дней> [себе] (в ответ на сообщение игрока)',
    "admin_give_vip_2": 'Ответь этой командой на сообщение игрока, либо допиши «себе».',
    "admin_give_vip_3": 'Некорректное количество дней.',
    "admin_give_vip_4": 'Выдан VIP на {v0} дн. игроку {v1}.',
    "admin_take_vip_1": 'Формат: !снять вип [себе] (в ответ на сообщение игрока)',
    "admin_take_vip_2": 'Ответь этой командой на сообщение игрока, либо допиши «себе».',
    "admin_take_vip_3": 'VIP снят у игрока {v0}.',
    "admin_reset_1": 'Формат: !сбросить [себе] (в ответ на сообщение игрока)',
    "admin_reset_2": 'Ответь этой командой на сообщение игрока, либо допиши «себе».',
    "admin_reset_3": 'Полный сброс прогресса игрока {v0} выполнен.',

    "nick_set_too_long": 'Слишком длинный ник — максимум 50 символов (у тебя {v0}).',
    "nick_set_empty": 'Укажи сам ник: +ник <текст>',
    "nick_set_taken": 'Этот ник уже занят другим игроком.',
    "nick_set_ok": 'Ник установлен: {v0}',
    "nick_clear_ok": 'Ник сброшен, теперь отображается твой обычный юзернейм.',

    "admin_set_legs_1": 'Формат: !установить ног <число> [себе] (в ответ на сообщение игрока)',
    "admin_set_legs_2": 'Ответь этой командой на сообщение игрока, либо допиши «себе».',
    "admin_set_legs_3": 'Некорректное число.',
    "admin_set_legs_4": 'Игроку {v0} установлено очков: {v1} (было {v2}).',
    "admin_give_legs_lvl_1": 'Формат: !дать ноги лвл<число> [себе] (в ответ на сообщение игрока), например: !дать ноги лвл20001',
    "admin_give_legs_lvl_2": 'Ответь этой командой на сообщение игрока, либо допиши «себе».',
    "admin_give_legs_lvl_3": 'Максимальный доступный уровень для этого игрока: {v0}.',
    "admin_give_legs_lvl_4": 'Игроку {v1} установлен {v0} лвл ноги (очков: {v2}).',

    "admin_set_evo_1": 'Формат: !установить эво <число> [себе] (в ответ на сообщение игрока)',
    "admin_set_evo_2": 'Ответь этой командой на сообщение игрока, либо допиши «себе».',
    "admin_set_evo_3": 'Некорректное число.',
    "admin_set_evo_4": 'Игроку {v0} установлен уровень эволюции: {v1} (было {v2}).',

    "admin_reset_cd_1": 'Формат: !сброс кд [себе] (в ответ на сообщение игрока)',
    "admin_reset_cd_2": 'Ответь этой командой на сообщение игрока, либо допиши «себе».',
    "admin_reset_cd_3": 'Кулдаун фермы сброшен у игрока {v0}.',

    "admin_reset_bonus_1": 'Формат: !сброс бонус [себе] (в ответ на сообщение игрока)',
    "admin_reset_bonus_2": 'Ответь этой командой на сообщение игрока, либо допиши «себе».',
    "admin_reset_bonus_3": 'Ежедневный бонус сброшен у игрока {v0} — можно забрать снова.',

    "admin_give_case_1": 'Формат: !дать кейс <номер> <кол-во> [себе] (в ответ на сообщение игрока)',
    "admin_give_case_2": 'Ответь этой командой на сообщение игрока, либо допиши «себе».',
    "admin_give_case_3": 'Нет кейса с таким номером.',
    "admin_give_case_4": 'Количество должно быть от 1 до 100.',
    "admin_give_case_5": '🎁 Игроку {v0} бесплатно открыт кейс «{v1}» {v2} раз(а):\n{v3}',

    "admin_debug_1": 'Формат: !дебаг @username',
    "admin_debug_2": 'Игрок не найден (он ещё не писал ноги в этом боте).',
    "admin_debug_3": '🛠 <b>Дебаг {v0}:</b>\n<code>{v1}</code>',

    "admin_show_text_1": 'Формат: !текст <ключ>',
    "admin_show_text_2": 'Нет такого ключа в TEXTS.',
    "admin_show_text_3": '🔑 <code>{v0}</code>:\n{v1}',

    "admin_simulate_evo_1": 'Формат: !симулировать эволюция @username',
    "admin_simulate_evo_2": 'Игрок не найден (он ещё не писал ноги в этом боте).',
    "admin_simulate_evo_3": '🔬 Симуляция эволюции для {v0}:\nОчков: {v1} / нужно {v2}\nТекущая эво: {v3}\n{v4}',
    "admin_simulate_evo_ok": '✅ Условие выполнено — может эволюционировать.',
    "admin_simulate_evo_fail": '❌ Не хватает {v0} очков.',

    "admin_stats_1": (
        '📊 <b>Статистика бота:</b>\n'
        '● Игроков всего: <code>{v0}</code>\n'
        '● Суммарно очков в экономике: <code>{v1}</code>\n'
        '● Суммарно монет в обороте: <code>{v2}</code>\n'
        '● Суммарно 🉑 очков перерождения: <code>{v3}</code>\n'
        '● Открыто кейсов всего: <code>{v4}</code>\n'
        '● Активных VIP: <code>{v5}</code>\n'
        '● Забанено из топов: <code>{v6}</code>'
    ),

    "admin_restart_1": '♻️ Перезапускаю бота...',
    "admin_unshow_all_badges_1": '🏷 Показ бейджей отключён у всех игроков. Каждый может заново включить нужные через «бейджи».',

    "admin_event_custom_1": 'Формат: !ивент х<множитель> <минуты>, например: !ивент х3 30',
    "admin_event_custom_2": 'Множитель и время должны быть положительными числами.',
    "admin_event_custom_3": '🌟 Ивент запущен! Множитель х{v0} на {v1} мин. (для всех чатов).',

    "admin_set_rebirth_1": 'Формат: !установить очкп <число> [себе] (в ответ на сообщение игрока)',
    "admin_set_rebirth_2": 'Ответь этой командой на сообщение игрока, либо допиши «себе».',
    "admin_set_rebirth_3": 'Некорректное число.',
    "admin_set_rebirth_4": 'Игроку {v0} установлено очков перерождения: {v1} (было {v2}).',

    "admin_wipe_economy_1": 'Формат: !обнулить экономику @username',
    "admin_wipe_economy_2": 'Игрок не найден (он ещё не писал ноги в этом боте).',
    "admin_wipe_economy_3": 'Экономика игрока {v0} обнулена: очки, монеты и 🉑 сброшены в 0. Инвентарь и апгрейды не тронуты.',

    "admin_personal_boost_1": 'Формат: !мультипликатор ферма <число> <минуты> [себе] (в ответ на сообщение игрока)',
    "admin_personal_boost_2": 'Ответь этой командой на сообщение игрока, либо допиши «себе».',
    "admin_personal_boost_3": 'Множитель и время должны быть положительными числами.',
    "admin_personal_boost_4": '🚀 Игроку {v0} выдан личный буст фермы х{v1} на {v2} мин.',

    "admin_give_item_1": 'Формат: !дать предмет <ключ> <кол-во> [себе] (в ответ на сообщение игрока)',
    "admin_give_item_2": 'Ответь этой командой на сообщение игрока, либо допиши «себе».',
    "admin_give_item_3": 'Нет предмета с таким ключом.',
    "admin_give_item_4": 'Количество должно быть от 1 до 1000.',
    "admin_give_item_5": 'Игроку {v0} выдано: {v1} {v2} × {v3}.',
    "admin_give_key_1": 'Формат: !дать ключ <ключ> <кол-во> [себе] (в ответ на сообщение игрока)',
    "admin_give_key_2": 'Ответь этой командой на сообщение игрока, либо допиши «себе».',
    "admin_give_key_3": 'Нет предмета с таким ключом.',
    "admin_give_key_4": 'Количество должно быть от 1 до 1000.',
    "admin_give_key_5": 'Игроку {v0} выдано: {v1} {v2} × {v3}.',

    "admin_clear_inventory_1": 'Формат: !очистить инвентарь @username',
    "admin_clear_inventory_2": 'Игрок не найден (он ещё не писал ноги в этом боте).',
    "admin_clear_inventory_3": 'Инвентарь игрока {v0} полностью очищен.',

    "admin_set_upgrade_1": 'Формат: !дать апгрейд <ключ> <уровень> [себе] (в ответ на сообщение игрока)',
    "admin_set_upgrade_2": 'Ответь этой командой на сообщение игрока, либо допиши «себе».',
    "admin_set_upgrade_3": 'Нет апгрейда с таким ключом.',
    "admin_set_upgrade_4": 'Уровень должен быть от 0 до {v0}.',
    "admin_set_upgrade_5": 'Игроку {v0} установлен апгрейд «{v1}»: уровень {v2}.',

    "admin_ultra_rebirth_1": 'Формат: !ультра навсегда себе (или ответом на сообщение игрока)',
    "admin_ultra_rebirth_2": 'Игроку {v0} выдан статус Ультра перерождения (принудительно, без сброса прогресса).',
    "admin_vip_forever_1": 'Ответь этой командой на сообщение игрока, либо допиши «себе».',
    "admin_vip_forever_2": '👑 Игроку {v0} выдан VIP навсегда.',

    "admin_reset_nick_1": 'Формат: !сброс ник @username',
    "admin_reset_nick_2": 'Игрок не найден (он ещё не писал ноги в этом боте).',
    "admin_reset_nick_3": 'У игрока не было установлено ника.',
    "admin_reset_nick_4": 'Ник игрока {v0} сброшен (был: {v1}).',

    "admin_list_vip_1": 'Сейчас нет игроков с активным VIP.',
    "admin_list_vip_2": '👑 <b>Активный VIP ({v0}):</b>\n{v1}',

    "admin_list_nicknames_1": 'Сейчас ни у кого не установлен ник.',
    "admin_list_nicknames_2": '📛 <b>Установленные ники ({v0}):</b>\n{v1}',

    "admin_find_1": 'Формат: !найти @username',
    "admin_find_2": 'Игрок не найден (он ещё не писал ноги в этом боте).',
    "admin_find_3": '🔎 {v0} — бот видел его в {v1} чате(ах):\n{v2}',
    "admin_find_4": 'Бот не встречал этого игрока ни в одном чате.',
    "admin_players_1": 'Игроков пока нет.',
    "admin_players_2": '👥 <b>Игроки ({v0}):</b>\n{v1}',
    "admin_logs_all_1": 'Логов пока нет.',
    "admin_logs_all_2": '📜 <b>Все логи ({v0}):</b>\n{v1}',
    "admin_top_spam_1": 'За выбранный период команд от игроков не было.',
    "admin_top_spam_2": '🚨 <b>Топ спама за {v0} мин. ({v1} игроков):</b>\n{v2}',
    "admin_list_chats_1": 'Бот пока нигде не активен (ещё никто не писал команды в группах).',
    "admin_list_chats_2": '💬 Чаты бота ({v0}):\n{v1}',

    "admin_logs_1": 'Лог пуст.',
    "admin_logs_2": '📜 <b>Последние действия ({v0}):</b>\n{v1}',
    "admin_logs_clear_1": '🧹 Очищено записей лога: {v0}. Осталось: {v1} (за последние 7 дней).',

    "admin_ping_1": '🏓 Понг! Ответ БД за {v0} мс.',
    "admin_ping_2": '🏓 Понг! 5 замеров SELECT 1 (мс): {v0}\nmin={v1} avg={v2} max={v3}',

    "admin_event_stop_1": 'Ивент остановлен.',
    "admin_event_stop_2": 'Ивент и так не активен.',

    "admin_event_status_1": '🌟 Ивент активен. Множитель х{v0}. Осталось: {v1}',
    "admin_event_status_2": 'Ивент сейчас не активен.',
    "admin_event_status_forever": 'без ограничения по времени',

    "help_root_1": (
        '❓ <b>Помощь</b>\n'
        'Введите значение: <b>бустер / предмет / зелье / бейдж / команда</b>\n\n'
        'Например: «помощь бейдж vip», «помощь бустер эссенция бога», «помощь команда апг».'
    ),
    "help_unknown_section_1": (
        '❓ Не понял раздел «{v0}».\n'
        'Введите значение: <b>бустер / предмет / зелье / бейдж / команда</b>'
    ),

    "help_badge_general_1": (
        '🏷 <b>Бейджи</b> — значки за достижения и события, отображаются рядом с ником в топах.\n'
        'Их можно скрывать/показывать через команду «значки».\n'
        'Спроси про конкретный: «помощь бейдж <название>» (например vip, владелец, фанат мику).'
    ),
    "help_badge_not_found_1": (
        '❓ Бейдж «{v0}» не найден.\n'
        'Доступные: {v1}\n'
        'Формат: «помощь бейдж <название>»'
    ),
    "help_badge_ambiguous_1": (
        '❓ Уточни, какой бейдж имеешь в виду «{v0}»:\n{v1}'
    ),

    "help_booster_general_1": (
        '🧪 <b>Бустеры</b> — экипируемые предметы, дающие постоянный процентный буст к добыче, пока надеты.\n'
        'Экипировать/снять можно через «инвентарь» → «Бустеры».\n'
        'Спроси про конкретный: «помощь бустер <название>» (например эссенция бога).'
    ),
    "help_booster_not_found_1": (
        '❓ Бустер «{v0}» не найден.\n'
        'Проверь название или посмотри список: «мои бустеры».\n'
        'Формат: «помощь бустер <название>»'
    ),
    "help_booster_ambiguous_1": (
        '❓ Уточни, какой бустер имеешь в виду «{v0}»:\n{v1}'
    ),
    "help_booster_info_1": '🧪 <b>{v0} {v1}</b>\n{v2}',

    "help_item_general_1": (
        '📦 <b>Предметы</b> — вещи без прямого процентного буста: сырьё для крафта, коллекционные или пассивные предметы.\n'
        'Посмотреть свои: «инвентарь» → «Предметы».\n'
        'Спроси про конкретный: «помощь предмет <название>» (например странная монета).'
    ),
    "help_item_not_found_1": (
        '❓ Предмет «{v0}» не найден.\n'
        'Проверь название или посмотри список: «мои предметы».\n'
        'Формат: «помощь предмет <название>»'
    ),
    "help_item_ambiguous_1": (
        '❓ Уточни, какой предмет имеешь в виду «{v0}»:\n{v1}'
    ),
    "help_item_info_1": '📦 <b>{v0} {v1}</b>\n{v2}',

    "help_potion_general_1": (
        '⚗️ <b>Зелья</b> — варятся в котле за монеты и время, при использовании дают временный эффект.\n'
        'Открой «мои зелья» — там кнопками: варить, забрать готовое, выпить.\n'
        'Спроси про конкретное: «помощь зелье <название>».'
    ),
    "help_potion_not_found_1": (
        '❓ Зелье «{v0}» не найдено.\n'
        'Проверь название или посмотри список: «мои зелья».\n'
        'Формат: «помощь зелье <название>»'
    ),
    "help_potion_ambiguous_1": (
        '❓ Уточни, какое зелье имеешь в виду «{v0}»:\n{v1}'
    ),
    "help_potion_info_1": '⚗️ <b>{v0} {v1}</b>\n{v2}',

    "help_command_general_1": (
        '🛠 <b>Команды</b> — основные действия в боте: ферма, бонус, апгрейд, крафт, кейсы и т.д.\n'
        'Спроси про конкретную: «помощь команда <название>» (например апг).'
    ),
    "help_command_not_found_1": (
        '❓ Команда «{v0}» не найдена.\n'
        'Доступные: {v1}\n'
        'Формат: «помощь команда <название>»'
    ),
    "help_command_ambiguous_1": (
        '❓ Уточни, какую команду имеешь в виду «{v0}»:\n{v1}'
    ),
    "help_command_info_1": '🛠 <b>{v0} {v1}</b>\n{v2}',

    "admin_give_all_1": '❓ Не понял, кому выдавать. Ответь на сообщение игрока командой «!дать всё» или напиши «!дать всё себе».',
    "admin_give_all_2": '✅ {v0} получил(а) все предметы, бустеры и зелья (по 1 шт. каждого): {v1} 📦🧪 + {v2} ⚗️.',

    "admin_levelup_notify_off_all_1": '✅ Показ нового уровня отключён у всех игроков ({v0}).',
}

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

    "kotyara_amulet":  (PREMIUM_KOTYARA_AMULET, "Амулет Котяры", 280, 0),
    "miku_amulet":     (PREMIUM_MIKU_AMULET, "Амулет Мику", 75, 0),
    "golda":           (PREMIUM_GOLDA_ITEM, "Голда", 52, 0),
    "karambit_gold":   (PREMIUM_KARAMBIT_GOLD, "Керамбит голд", 228, 0),
    "butterfly_legacy": (PREMIUM_BUTTERFLY_LEGACY, "Бабочка легаси", 69, 0),
    "krest_amulet":    (PREMIUM_KREST_AMULET, "Амулет Креста", 100, 0),
    "fati_amulet":     (PREMIUM_FATI_AMULET, "Амулет Фати", 80, 0),
    "guitarist_crown": (PREMIUM_GUITARIST_CROWN, "Корона Гитариста", 69, 0),
    "vilon_amulet":    (PREMIUM_VILON_AMULET, "Амулет Вилона", 120, 0),
    "miku_ring":       (PREMIUM_MIKU_RING, "Кольцо Мику", 250, 0),

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

    # ==== Эво-апгрейд (10/15 ур. эволюции) ====
    "rebirth_spark":  (PREMIUM_REBIRTH_SPARK, "Искра перерождения", 0, 20),
    "star_necklace":  (PREMIUM_STAR_NECKLACE, "Ожерелье из звёзд", 120, 0),
    "blazing_star_necklace": (PREMIUM_BLAZING_STAR_NECKLACE, "Ожерелье пылающей звезды", 210, 0),
    "pocket_star":    (PREMIUM_POCKET_STAR, "Карманная звезда", 0, 0),

    # ==== Крафт 3 ур.: Любитель Мастерства + его дроп-предмет nano-IT ====
    "mastery_lover_amulet": (PREMIUM_MASTERY_LOVER_AMULET, "Любитель Мастерства", 600, 0),
    "nano_it":              (PREMIUM_NANO_IT, "nano-IT", 0, 0),
}

# Разделение ITEMS на «бустеры» (экипируемые, дают процентный буст к добыче) и «предметы»
# (сырьё для крафта / пассивные / коллекционные) для команды «помощь бустер|предмет».
# Правило: boost_percent > 0 -> бустер. Единственное исключение — chronos_orb: он тоже
# экипируется (см. _format_equipped_item_line), но эффект случайный (10-400%), поэтому
# в ITEMS у него boost_percent = 0 — добавляем его в бустеры вручную.
HELP_BOOSTER_KEYS = {k for k, v in ITEMS.items() if v[2] > 0} | {"chronos_orb"}
HELP_ITEM_KEYS = set(ITEMS.keys()) - HELP_BOOSTER_KEYS

# Бейджи за уровень эволюции (см. EVO_MILESTONE_BADGE_LEVELS в config.py). Эмодзи-константы
# PREMIUM_BADGE_EVO<N> лежат в premium_emoji.py — здесь просто собираем их в один список
# (key, emoji, label, threshold), который перебирает badge_list() в economy.py.
EVO_MILESTONE_BADGES = [
    (key, globals()[f"PREMIUM_BADGE_EVO{threshold}"], label, threshold)
    for key, threshold, label in EVO_MILESTONE_BADGE_LEVELS
]

# Бейджи за открытые кейсы — тот же паттерн (key, emoji, label, threshold), перебирается в badge_list().
CASE_MILESTONE_BADGES = [
    ("case_milestone_50", PREMIUM_BADGE_CASE50, "Любитель кейсов", 50),
    ("case_milestone_500", PREMIUM_BADGE_CASE500, "Кейсовый безумец", 500),
    ("case_milestone_5000", PREMIUM_BADGE_CASE5000, "Разоритель Кейсов", 5000),
]

# Бейджи за суммарно нафармленные очки ноги (total_farmed).
FARM_MILESTONE_BADGES = [
    ("farm_milestone_1m", PREMIUM_BADGE_FARM1M, "Начальный фармер", 1_000_000),
    ("farm_milestone_500m", PREMIUM_BADGE_FARM500M, "Продвинутый фармер", 500_000_000),
    ("farm_milestone_5b", PREMIUM_BADGE_FARM5B, "Мастер фарма", 5_000_000_000),
    ("farm_milestone_1t", PREMIUM_BADGE_FARM1T, "Бог фарма", 1_000_000_000_000),
    ("farm_milestone_1q", PREMIUM_BADGE_FARM1Q, "Всемогущий фармер", 1_000_000_000_000_000),
    ("farm_milestone_1qi", PREMIUM_BADGE_FARM1QI, "Фармер-ногость", 1_000_000_000_000_000_000),
]

# Бейджи за баланс монет (🪙).
COIN_MILESTONE_BADGES = [
    ("coin_milestone_1k", PREMIUM_BADGE_COIN1K, "Мелкий вкладчик", 1_000),
    ("coin_milestone_10k", PREMIUM_BADGE_COIN10K, "Коллекционер монет", 10_000),
    ("coin_milestone_100k", PREMIUM_BADGE_COIN100K, "Денежный мешок", 100_000),
    ("coin_milestone_10m", PREMIUM_BADGE_COIN10M, "Магнат", 10_000_000),
    ("coin_milestone_1b", PREMIUM_BADGE_COIN1B, "Коин-Олигарх", 1_000_000_000),
    ("coin_milestone_10b", PREMIUM_BADGE_COIN10B, "Хозяин Экономики", 10_000_000_000),
]

# Бейджи за баланс очков перерождения (🉑).
REBIRTH_MILESTONE_BADGES = [
    ("rebirth_milestone_100", PREMIUM_BADGE_REBIRTH100, "Первое дыхание", 100),
    ("rebirth_milestone_10k", PREMIUM_BADGE_REBIRTH10K, "Искра цикла", 10_000),
    ("rebirth_milestone_1m", PREMIUM_BADGE_REBIRTH1M, "Странник перерождений", 1_000_000),
    ("rebirth_milestone_1b", PREMIUM_BADGE_REBIRTH1B, "Владыка Циклов", 1_000_000_000),
    ("rebirth_milestone_10b", PREMIUM_BADGE_REBIRTH10B, "Бессмертный", 10_000_000_000),
]

# Бейджи за стрик ежедневного бонуса (bonus_streak).
STREAK_MILESTONE_BADGES = [
    ("streak_milestone_7", PREMIUM_BADGE_STREAK7, "Неутомимый", 7),
    ("streak_milestone_30", PREMIUM_BADGE_STREAK30, "Железная воля", 30),
]

# Бейджи за количество успешных крафтов (crafts_done).
CRAFT_MILESTONE_BADGES = [
    ("craft_milestone_10", PREMIUM_BADGE_CRAFT10, "Ремесленник", 10),
    ("craft_milestone_100", PREMIUM_BADGE_CRAFT100, "Мастер-Кузнец", 100),
]

# Бейджи за баланс очков престижа (prestige_points).
PRESTIGE_MILESTONE_BADGES = [
    ("prestige_milestone_10", PREMIUM_BADGE_PRESTIGE10, "Искушённый", 10),
    ("prestige_milestone_100", PREMIUM_BADGE_PRESTIGE100, "Просветлённый", 100),
    ("prestige_milestone_25000", PREMIUM_BADGE_PRESTIGE25000, "Хранитель Мудрости", 25000),
    ("prestige_milestone_50000", PREMIUM_BADGE_PRESTIGE50000, "Вознёсшийся", 50000),
    ("prestige_milestone_100000", PREMIUM_BADGE_PRESTIGE100000, "Владыка Престижа", 100000),
    ("prestige_milestone_250000", PREMIUM_BADGE_PRESTIGE250000, "Трансцендентный", 250000),
    ("prestige_milestone_500000", PREMIUM_BADGE_PRESTIGE500000, "Абсолютный Разум", 500000),
    ("prestige_milestone_1000000", PREMIUM_BADGE_PRESTIGE1000000, "За Гранью Престижа", 1000000),
]

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
    "krest_amulet", "fati_amulet", "guitarist_crown", "vilon_amulet", "miku_ring",
    "chaos_orb", "chronos_clock", "chronos_orb",
    "miku_fan_amulet",
    "nogost_coin", "godly_nogost_coin", "craft_coin", "bitcoin",
    "rebirth_coin", "evolution_coin", "awakening_coin",
    "pocket_star", "rebirth_spark", "star_necklace", "blazing_star_necklace",
    "mastery_lover_amulet",
}

PASSIVE_ITEMS = {
    "strange_coin",
    "hybrid_amulet", "friendship_essence", "time_particle", "devotion_coin",
    "old_vase", "golden_vase", "godly_vase", "warm_candle",
    "broken_clock", "essence_drop", "comet_shard", "koshko_gift", "ancient_stone", "fate_thread",
    "craft_coin", "bitcoin", "rebirth_coin", "evolution_coin", "awakening_coin",
    "pocket_star", "nano_it",
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
    "rebirth_spark": 25, "star_necklace": 180, "blazing_star_necklace": 420,
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

    "mastery_lover_amulet": {
        "level": 3,
        "ingredients": {"chronos_orb": 2},
        "rebirth_cost": 1488,
        "refund_ingredients": {"chronos_orb": 1},
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

    # ==== Эво-апгрейд: рецепты 15 уровня эволюции ====
    "star_necklace": {
        "level": 1,
        "ingredients": {"star": 2, "mk_broken": 20},
    },
    "blazing_star_necklace": {
        "level": 1,
        "ingredients": {"star_necklace": 1, "rebirth_spark": 5},
        "rebirth_cost": 5,
    },
    "pocket_star": {
        "level": 1,
        "ingredients": {"star": 5},
        "rebirth_cost": 5,
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

# ==== 🤖 Любитель Мастерства: пока экипирован, при каждом фарме ног независимо
# проверяются 5 эффектов (несколько могут сработать одновременно за один фарм) ====
MASTERY_LOVER_BITCOIN_CHANCE_CHANCE = 0.005   # шанс временно поднять шанс дропа биткоина
MASTERY_LOVER_BITCOIN_CHANCE_BONUS = 0.001    # +0.1% к шансу дропа биткоина при этом проке
MASTERY_LOVER_CRAFT_CHANCE = 0.01
MASTERY_LOVER_CRAFT_AMOUNT = 15
MASTERY_LOVER_REBIRTH_CHANCE = 0.02
MASTERY_LOVER_REBIRTH_AMOUNT = 200
MASTERY_LOVER_PRESTIGE_CHANCE = 0.015
MASTERY_LOVER_PRESTIGE_AMOUNT = 50
MASTERY_LOVER_NANO_IT_CHANCE = 0.03
NANO_IT_BOOST_PCT_PER_UNIT = 5

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
    "guitarist_crown": (
        f"Пассивный эффект пока экипирована: шанс {round(LEG_STEAL_CHANCE * 100)}% при фарме ног "
        "украсть 1 предмет из Кейса 1/2/3 у случайного игрока этого же чата."
    ),
    "vilon_amulet": (
        f"Пассивный эффект пока экипирован: каждые {VILON_TRIGGER_EVERY} фармов ног подряд "
        f"даёт x{VILON_BOOST_MULT} к добыче фермы и ног на {VILON_BOOST_SECONDS} секунд."
    ),
    "galaxy_power_amulet": "Вторая ступень уникальных бустеров — открывает лимит по галактикам.",
    "galaxy_might_amulet": "Третья ступень уникальных бустеров, требуется для дальнейшего крафта Гибридного амулета.",
    "chronos_orb": (
        "Особый бустер: вместо фиксированного процента даёт СЛУЧАЙНЫЙ буст добычи от 10% до 400% "
        "при каждом фарме — иногда почти ничего, иногда джекпот. Дополнительно может случайно "
        "подарить очки перерождения, монеты, ноги, снять кулдаун фермы, дать очки престижа, "
        "зелье, другой бустер, бейдж, странную монету или старую вазу — всё это ХАОС!"
    ),
    "vip_charm": "Мощный бустер, доступный только тем, у кого куплен VIP-статус (см. «помощь бейдж vip»).",
    "star_necklace": "Пассивный эффект пока экипировано: шанс 2.5% при фарме ног выдать случайный предмет из Базового кейса.",
    "blazing_star_necklace": (
        "Пассивный эффект пока экипировано: при фарме ног — шанс 1.7% на 1-15 🉑 очков перерождения "
        "и независимый шанс 1.2% на 1-3 очка престижа."
    ),
    "kotyara_amulet": (
        f"Пассивный эффект пока экипирован: при фарме ног — шанс {round(KOTYARA_BOOST_CHANCE * 100)}% "
        f"включить x{KOTYARA_BOOST_MULT} к добыче на {KOTYARA_BOOST_SECONDS} секунд (поверх обычного буста)."
    ),
    "mastery_lover_amulet": (
        "Топовый крафтовый бустер (3 ур. крафта). Пока экипирован, при каждом фарме ног независимо "
        "проверяются 5 эффектов: 0.5% — временно повышает шанс дропа 🟠 Биткоина на этот фарм; "
        "1% — +15💠 очков крафта; 2% — +200🉑 очков перерождения; 1.5% — +50🔮 очков престижа; "
        "3% — +1 предмет nano-IT (пассивно даёт +5% к добыче за каждую единицу в инвентаре)."
    ),
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
    "rebirth_spark": "Даётся автоматически при достижении 5 уровня эволюции. Крафт-сырьё для Ожерелья пылающей звезды.",
    "pocket_star": (
        "Пассивный эффект: пока лежит в инвентаре (экипировать не нужно) — команда «ферма» "
        f"даёт в {POCKET_STAR_FARM_CMD_MULT}x больше и гарантированно "
        f"+{POCKET_STAR_FARM_CMD_REBIRTH_RANGE[0]}-{POCKET_STAR_FARM_CMD_REBIRTH_RANGE[1]} 🉑 очков перерождения. "
        f"Обычная фарма ног (🦵/🦿... в чате) — x{POCKET_STAR_LEG_FARM_MULT}."
    ),
    "nano_it": (
        f"Пассивный эффект: пока лежит в инвентаре (экипировать не нужно) — даёт +{NANO_IT_BOOST_PCT_PER_UNIT}% "
        "к добыче за КАЖДУЮ единицу в инвентаре (например, 3 шт. = +15%, суммируется с остальными бустерами). "
        "Выпадает случайно от 🤖 Любителя Мастерства."
    ),
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
    result = " + ".join(parts)
    if recipe.get("refund_ingredients"):
        refund_parts = [f"{qty}x {ITEMS[k][1]}" for k, qty in recipe["refund_ingredients"].items()]
        result += f" (вернётся: {', '.join(refund_parts)})"
    return result

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

BADGES_PAGE_SIZE = 6

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

AMOUNT = r"(\d+(?:\.\d+)?к{0,4})"
_AMOUNT_TOKEN_RE = re.compile(r"^\d+(?:\.\d+)?к{0,4}$", re.IGNORECASE)

ADMIN_GIVE_LEGS_RE = re.compile(rf"^!дать ног {AMOUNT}(\s+себе)?$", re.IGNORECASE)
ADMIN_TAKE_LEGS_RE = re.compile(rf"^!снять ноги (?:{AMOUNT}|все)(\s+себе)?$", re.IGNORECASE)
ADMIN_GIVE_EVO_RE = re.compile(rf"^!дать эво {AMOUNT}(\s+себе)?$", re.IGNORECASE)
ADMIN_TAKE_EVO_RE = re.compile(rf"^!снять эво (?:{AMOUNT}|все)(\s+себе)?$", re.IGNORECASE)
ADMIN_GIVE_COIN_RE = re.compile(rf"^!дать коин {AMOUNT}(\s+себе)?$", re.IGNORECASE)
ADMIN_TAKE_COIN_RE = re.compile(rf"^!снять коин (?:{AMOUNT}|все)(\s+себе)?$", re.IGNORECASE)
ADMIN_GIVE_BOOST_RE = re.compile(r"^!дать б (.+?)(\s+себе)?$", re.IGNORECASE)
ADMIN_TAKE_BOOST_RE = re.compile(r"^!снять б (.+?)(\s+себе)?$", re.IGNORECASE)
ADMIN_GIVE_ITEM_RE = re.compile(r"^!дать п (.+?)(\s+себе)?$", re.IGNORECASE)
ADMIN_TAKE_ITEM_RE = re.compile(r"^!снять п (.+?)(\s+себе)?$", re.IGNORECASE)
ADMIN_GIVE_VIP_RE = re.compile(rf"^!дать вип {AMOUNT}(\s+себе)?$", re.IGNORECASE)
ADMIN_TAKE_VIP_RE = re.compile(r"^!снять вип(\s+себе)?$", re.IGNORECASE)
ADMIN_RESET_RE = re.compile(r"^!сбросить(\s+себе)?$", re.IGNORECASE)
ADMIN_GIVE_REBIRTH_RE = re.compile(rf"^!дать очкп {AMOUNT}(\s+себе)?$", re.IGNORECASE)
ADMIN_TAKE_REBIRTH_RE = re.compile(rf"^!снять очкп (?:{AMOUNT}|все)(\s+себе)?$", re.IGNORECASE)
ADMIN_GIVE_CRAFT_RE = re.compile(rf"^!дать (?:крафт|очкк) {AMOUNT}(\s+себе)?$", re.IGNORECASE)
ADMIN_TAKE_CRAFT_RE = re.compile(rf"^!снять (?:крафт|очкк) (?:{AMOUNT}|все)(\s+себе)?$", re.IGNORECASE)
ADMIN_GIVE_LEGS_LVL_RE = re.compile(r"^!дать ноги лвл(\d+)(\s+себе)?$", re.IGNORECASE)

PEER_GIVE_LEGS_RE = re.compile(rf"^дать ног {AMOUNT}$", re.IGNORECASE)
PEER_GIVE_COIN_RE = re.compile(rf"^дать коин {AMOUNT}$", re.IGNORECASE)

EXCHANGE_RE = re.compile(rf"^обменять {AMOUNT}$", re.IGNORECASE)
REVERSE_EXCHANGE_RE = re.compile(rf"^обменять {AMOUNT} коин$", re.IGNORECASE)
CRAFT_EXCHANGE_RE = re.compile(rf"^обменять {AMOUNT} (?:крафт|очкк)$", re.IGNORECASE)
CRAFT_EXCHANGE_TO_RE = re.compile(rf"^обменять (?:крафт|очкк) {AMOUNT}$", re.IGNORECASE)
CASE_NUM_RE = re.compile(r"^кейс (\d+)$", re.IGNORECASE)
INFO_RE = re.compile(r"^инфо\s+@?(\w+)$", re.IGNORECASE)
NICK_SET_RE = re.compile(r"^\+ник\s+(.+)$", re.IGNORECASE)
NICK_CLEAR_RE = re.compile(r"^-ник$", re.IGNORECASE)
ADMIN_SET_LEGS_RE = re.compile(rf"^!установить ног {AMOUNT}(\s+себе)?$", re.IGNORECASE)
ADMIN_SET_EVO_RE = re.compile(rf"^!установить эво {AMOUNT}(\s+себе)?$", re.IGNORECASE)
ADMIN_RESET_CD_RE = re.compile(r"^!сброс кд(\s+себе)?$", re.IGNORECASE)
ADMIN_RESET_BONUS_RE = re.compile(r"^!сброс бонус(\s+себе)?$", re.IGNORECASE)
ADMIN_GIVE_CASE_RE = re.compile(r"^!дать кейс\s+(\d+)\s+(\d+)(\s+себе)?$", re.IGNORECASE)
ADMIN_DEBUG_RE = re.compile(r"^!дебаг\s+@?(\w+)$", re.IGNORECASE)
ADMIN_SHOW_TEXT_RE = re.compile(r"^!текст\s+(\S+)$", re.IGNORECASE)
ADMIN_SIMULATE_EVO_RE = re.compile(r"^!симулировать эволюция\s+@?(\w+)$", re.IGNORECASE)
ADMIN_EVENT_CUSTOM_RE = re.compile(r"^!ивент\s+х(\d+(?:\.\d+)?)\s+(\d+)$", re.IGNORECASE)

ADMIN_SET_REBIRTH_RE = re.compile(rf"^!установить очкп {AMOUNT}(\s+себе)?$", re.IGNORECASE)
ADMIN_WIPE_ECONOMY_RE = re.compile(r"^!обнулить экономику\s+@?(\w+)$", re.IGNORECASE)
ADMIN_PERSONAL_BOOST_RE = re.compile(r"^!мультипликатор ферма\s+(\d+(?:\.\d+)?)\s+(\d+)(\s+себе)?$", re.IGNORECASE)
ADMIN_GIVE_ITEM_RE = re.compile(r"^!дать предмет\s+(\S+)\s+(\d+)(\s+себе)?$", re.IGNORECASE)
ADMIN_GIVE_KEY_RE = re.compile(r"^!дать ключ\s+(\S+)\s+(\d+)(\s+себе)?$", re.IGNORECASE)
ADMIN_CLEAR_INVENTORY_RE = re.compile(r"^!очистить инвентарь\s+@?(\w+)$", re.IGNORECASE)
ADMIN_SET_UPGRADE_RE = re.compile(r"^!дать апгрейд\s+(\S+)\s+(\d+)(\s+себе)?$", re.IGNORECASE)
ADMIN_VIP_FOREVER_RE = re.compile(r"^!вип навсегда(\s+себе)?$", re.IGNORECASE)
ADMIN_ULTRA_REBIRTH_RE = re.compile(r"^!ультра навсегда(\s+себе)?$", re.IGNORECASE)
ADMIN_RESET_NICK_RE = re.compile(r"^!сброс ник\s+@?(\w+)$", re.IGNORECASE)
ADMIN_FIND_RE = re.compile(r"^!найти\s+@?(\w+)$", re.IGNORECASE)
ADMIN_GIVE_ALL_RE = re.compile(r"^!дать всё(\s+себе)?$", re.IGNORECASE)
ADMIN_LEVELUP_NOTIFY_OFF_ALL_RE = re.compile(r"^!смс выкл всем$", re.IGNORECASE)

PROMO_CREATE_RE = re.compile(
    r'^!промокод создать\s+"([^"]+)"\s+"([^"]+)"\s+"([^"]+)"\s+"([^"]+)"$', re.IGNORECASE
)
PROMO_CREATE_BADGE_RE = re.compile(
    r'^!промокод создать бейдж\s+"([^"]+)"\s+"([^"]+)"$', re.IGNORECASE
)
PROMO_DELETE_RE = re.compile(r'^!промокод удалить\s+"([^"]+)"$', re.IGNORECASE)
PROMO_LIST_RE = re.compile(r'^!промокод список$', re.IGNORECASE)
PROMO_REDEEM_RE = re.compile(r'^(?:промокод|промо)\s+(\S+)$', re.IGNORECASE)

NEWS_PREFIX = "!новость "

FIXED_COMMANDS = {
    "моя нога", "топ ног", "гл топ ног", "топ эво", "гл топ эво", "топ коин", "гл топ коин",
    "ферма", "фарма", "инвентарь", "эволюция", "кейс", "кейсы", "бонус",
    "смс выкл", "смс вкл", "вип", "!ивент ноги", "бейджи",
    "перерождение", "апгрейд", "прокачка", "апг", "престиж", "баланс", "топ очкп", "гл топ очкп",
    "топ ноги вся", "топ коин вся", "топ эво вся", "топ очкп вся", "топ вся", "гл топ", "крафты", "крафт",
    "мои предметы", "предметы", "мои бустеры", "бустеры", "мой инвентарь", "-ник",
    "мои зелья", "зелья",
    "!список вип", "!список ников", "!список чат", "!логи", "!логи вся", "!пинг", "!ивент стоп", "!ивент статус",
    "!игроки",
    "ультра перерождение", "ультра перерождение подтверждаю",
    "авто эво вкл", "авто эво выкл", "авто эволюция вкл", "авто эволюция выкл",
    "авто перерождение вкл", "авто перерождение выкл", "авто рб вкл", "авто рб выкл",
    "авто ребёрт вкл", "авто ребёрт выкл", "авто реберт вкл", "авто реберт выкл",
    "авто продажа вкл", "авто продажа выкл", "авто продажа настройка", "авто продажа конфиг", "авто продажа настройки",
    "!смс выкл всем",
}
PREFIX_COMMANDS = (
    "обменять ", "!дать ног", "!снять ноги", "!дать эво", "!снять эво",
    "!дать коин", "!снять коин", "!дать б", "!снять б", "!дать п", "!снять п", "!дать вип", "!снять вип", "!сбросить",
    "передать ", "дать ", "кейс ", NEWS_PREFIX, "инфо ", "продать",
    "!дать очкп", "!снять очкп", "!дать крафт", "открыть кейс", "осмотреть кейс", "осмотр кейс", "крафты ", "крафт ", "уничтожение",
    "+ник ", "!установить ног", "!установить эво",
    "!сброс кд", "!сброс бонус", "!дать кейс", "!дебаг ", "!текст ", "!симулировать эволюция", "!ивент х",
    "!установить очкп", "!обнулить экономику", "!мультипликатор ферма", "!дать предмет",
    "!очистить инвентарь", "!дать апгрейд", "!вип навсегда", "!сброс ник", "!найти ", "!ультра навсегда",
    "вип открыть кейс", "бустеры поиск ", "!дать ключ", "!дать всё",
)

def is_command_text(text: str) -> bool:
    t = text.lower()
    if t in FIXED_COMMANDS:
        return True
    return any(t.startswith(p) for p in PREFIX_COMMANDS)

_TOP_WORDS = ["топ", "топчик", "ладдер", "лидеры", "лиддеры", "рейтинг", "top", "ladder", "lider", "liders", "leaders", "rating"]
_LEG_WORDS = ["ног", "ноги", "ногой", "leg", "legs", "foot", "feet"]
_COIN_WORDS = ["коин", "коины", "коинов", "монета", "монеты", "монет", "coin", "coins", "money", "валюта"]
_EVO_WORDS = ["эво", "эволюция", "эволюции", "эволюционировать", "evolution", "evolutions", "evo"]
_BALANCE_WORDS = ["баланс", "бал", "кошелек", "кошелёк", "деньги", "bal", "balance", "cash", "счет", "счёт"]
_REBIRTH_WORDS = ["перерождение", "перерождения", "ребёрт", "реберт", "ребёрты", "ребирты", "рб", "rebirth", "rb", "rebith"]
_CASE_WORDS = ["кейс", "сундук", "коробка", "case", "box"]
_CASES_WORDS = ["кейсы", "сундуки", "коробки", "cases", "boxes"]
_VIP_WORDS = ["вип", "vip", "випка", "premium", "премиум"]
_EXCHANGE_WORDS = ["обменять", "обмен", "обменник", "свап", "swap", "exchange"]

ALIAS_PHRASES = {}

def _register_phrases(canon: str, words):
    for w in words:
        ALIAS_PHRASES[w.lower()] = canon

_register_phrases("вип", _VIP_WORDS)
_register_phrases("баланс", _BALANCE_WORDS)
_register_phrases("перерождение", _REBIRTH_WORDS)
_register_phrases("эволюция", _EVO_WORDS)
_register_phrases("кейс", _CASE_WORDS)
_register_phrases("кейсы", _CASES_WORDS)
ALIAS_PHRASES["моя ношка"] = "моя нога"
ALIAS_PHRASES["моя ножка"] = "моя нога"
ALIAS_PHRASES["моя ноги"] = "моя нога"

for _top in _TOP_WORDS:
    for _leg in _LEG_WORDS:
        ALIAS_PHRASES[f"{_top} {_leg}"] = "топ ног"
        ALIAS_PHRASES[f"гл {_top} {_leg}"] = "гл топ ног"
        ALIAS_PHRASES[f"{_top} {_leg} вся"] = "топ ноги вся"
    for _coin in _COIN_WORDS:
        ALIAS_PHRASES[f"{_top} {_coin}"] = "топ коин"
        ALIAS_PHRASES[f"гл {_top} {_coin}"] = "гл топ коин"
        ALIAS_PHRASES[f"{_top} {_coin} вся"] = "топ коин вся"
    for _evo in _EVO_WORDS:
        ALIAS_PHRASES[f"{_top} {_evo}"] = "топ эво"
        ALIAS_PHRASES[f"гл {_top} {_evo}"] = "гл топ эво"
        ALIAS_PHRASES[f"{_top} {_evo} вся"] = "топ эво вся"
    for _rb in _REBIRTH_WORDS:
        ALIAS_PHRASES[f"{_top} {_rb}"] = "топ очкп"
        ALIAS_PHRASES[f"гл {_top} {_rb}"] = "гл топ очкп"
        ALIAS_PHRASES[f"{_top} {_rb} вся"] = "топ очкп вся"
    ALIAS_PHRASES[f"{_top} вся"] = "топ вся"
ALIAS_PHRASES.pop("топ топ", None)

def normalize_alias_text(text: str) -> str:
    """Заменяет известную фразу-алиас на канонический текст команды. Не трогает команды
    с параметрами (числа, названия предметов, юзернеймы) — под них есть отдельная токенная
    замена ниже (normalize_alias_prefix), не полнофразовая."""
    if not text:
        return text
    stripped = text.strip()
    if not stripped:
        return text
    lowered = stripped.lower()
    return ALIAS_PHRASES.get(lowered, text)

_PARAM_TERM_TO_CANON = {}
for _w in _LEG_WORDS:
    _PARAM_TERM_TO_CANON[_w.lower()] = "ног"
for _w in _COIN_WORDS:
    _PARAM_TERM_TO_CANON[_w.lower()] = "коин"
for _w in _EVO_WORDS:
    _PARAM_TERM_TO_CANON[_w.lower()] = "эво"
for _w in _REBIRTH_WORDS:
    _PARAM_TERM_TO_CANON[_w.lower()] = "очкп"
for _w in _EXCHANGE_WORDS:
    _PARAM_TERM_TO_CANON[_w.lower()] = "обменять"
for _w in _CASE_WORDS:
    _PARAM_TERM_TO_CANON[_w.lower()] = "кейс"

_PARAM_PROTECTED = {"б", "п"}

_CASE_WORDS_SET = {w.lower() for w in _CASE_WORDS}

def normalize_case_number(text: str) -> str:
    """'сундук 2' / 'box 2' -> 'кейс 2'. Первое слово само является термином кейса,
    число (аргумент) не трогаем."""
    if not text:
        return text
    stripped = text.strip()
    if not stripped:
        return text
    parts = stripped.split(" ", 1)
    if len(parts) != 2:
        return text
    first, rest = parts[0].lower(), parts[1]
    if first in _CASE_WORDS_SET and first != "кейс" and rest.strip().isdigit():
        return "кейс " + rest
    return text

def normalize_alias_prefix(text: str) -> str:
    """Для команд вида '<преф> <термин> <аргументы...>' заменяет только термин сразу после
    известного префикса (!дать/!снять/дать/продать/обменять/кейс), не трогая аргументы."""
    if not text:
        return text
    stripped = text.strip()
    if not stripped:
        return text

    lowered = stripped.lower()
    known_prefixes = ("!дать ", "!снять ", "дать ")
    matched_prefix = None
    for p in known_prefixes:
        if lowered.startswith(p):
            matched_prefix = p
            break
    if matched_prefix is None:
        return text

    original_prefix = stripped[:len(matched_prefix)]
    rest = stripped[len(matched_prefix):]
    if not rest:
        return text

    rest_words = rest.split(" ", 1)
    term = rest_words[0]
    tail = rest_words[1] if len(rest_words) > 1 else ""
    lterm = term.lower()

    if lterm in _PARAM_PROTECTED:
        return text
    if lterm not in _PARAM_TERM_TO_CANON:
        return text

    canon_term = _PARAM_TERM_TO_CANON[lterm]
    if matched_prefix == "!снять " and canon_term == "ног":
        canon_term = "ноги"

    if canon_term == lterm:
        return text

    new_text = original_prefix + canon_term + (" " + tail if tail else "")
    return new_text

def normalize_exchange_suffix(text: str) -> str:
    """'обменять 10 монет' / 'обменять 10 coin' -> 'обменять 10 коин'. Не трогает 'обменять 10'
    (старая команда очки->монеты, без термина в хвосте)."""
    if not text:
        return text
    stripped = text.strip()
    lowered = stripped.lower()
    if not lowered.startswith("обменять "):
        return text
    rest = stripped[len("обменять "):].strip()
    if not rest:
        return text
    parts = rest.split(" ", 1)
    if len(parts) != 2:
        return text
    amount_word, term = parts[0], parts[1].strip()
    if not _AMOUNT_TOKEN_RE.match(amount_word):
        return text
    lterm = term.lower()
    if lterm not in _PARAM_TERM_TO_CANON:
        return text
    canon_term = _PARAM_TERM_TO_CANON[lterm]
    if canon_term != "коин" or canon_term == lterm:
        return text
    return f"обменять {amount_word} {canon_term}"

_FUZZY_CANDIDATES = None
_FUZZY_MAX_DIST = 1
_FUZZY_MIN_LEN = 4

def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        curr = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            curr[j] = min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost)
        prev = curr
    return prev[-1]

def _get_fuzzy_candidates():
    global _FUZZY_CANDIDATES
    if _FUZZY_CANDIDATES is None:
        _FUZZY_CANDIDATES = sorted(set(FIXED_COMMANDS) | set(ALIAS_PHRASES.keys()))
    return _FUZZY_CANDIDATES

def normalize_alias_fuzzy(text: str) -> str:
    if not text:
        return text
    stripped = text.strip()
    if not stripped or " " in stripped:
        return text
    lowered = stripped.lower()
    if lowered in FIXED_COMMANDS or lowered in ALIAS_PHRASES:
        return text
    if len(lowered) < _FUZZY_MIN_LEN:
        return text
    best_word = None
    best_dist = _FUZZY_MAX_DIST + 1
    for cand in _get_fuzzy_candidates():
        if " " in cand:
            continue
        if abs(len(cand) - len(lowered)) > _FUZZY_MAX_DIST:
            continue
        d = _levenshtein(lowered, cand)
        if d < best_dist:
            best_dist = d
            best_word = cand
            if d == 0:
                break
    if best_word is None or best_dist > _FUZZY_MAX_DIST:
        return text
    canon = ALIAS_PHRASES.get(best_word, best_word)
    return canon

def apply_command_aliases(text: str) -> str:
    """Единая точка входа: применяет все виды алиасинга по порядку. Возвращает исходный текст,
    если ни один нормализатор не нашёл, что менять (в т.ч. для обычных сообщений с ногами 🦵/🦿 —
    там нет алиасов, и текст останется как есть)."""
    if not text:
        return text
    if text != text.strip():
        stripped_lower = text.strip().lower()
        if stripped_lower in FIXED_COMMANDS or stripped_lower in ALIAS_PHRASES:
            text = text.strip()
    result = normalize_alias_text(text)
    if result != text:
        return result
    result = normalize_case_number(text)
    if result != text:
        return result
    result = normalize_exchange_suffix(text)
    if result != text:
        return result
    result = normalize_alias_prefix(text)
    if result != text:
        return result
    result = normalize_alias_fuzzy(text)
    return result

def esc(text: str) -> str:
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def parse_amount(text: str):
    m = re.match(r"^(\d+(?:\.\d+)?)(к{0,4})$", text.strip().lower())
    if not m:
        return None
    number = float(m.group(1))
    k_count = len(m.group(2))
    return round(number * (1000 ** k_count))

TG_EMOJI_RE = re.compile(r"<tg-emoji[^>]*>(.*?)</tg-emoji>")

def plain_emoji(emoji_html: str) -> str:
    m = TG_EMOJI_RE.match(emoji_html or "")
    return m.group(1) if m else (emoji_html or "")

def strip_premium_emoji(text: str) -> str:
    """Убирает все <tg-emoji> обёртки из готового текста, оставляя фолбэк-символы."""
    return TG_EMOJI_RE.sub(lambda m: m.group(1), text or "")

async def safe_reply(message: Message, text: str, reply_markup=None):
    """Как message.reply(), но если Telegram отклонил сообщение из-за невалидного
    emoji-id в premium-эмодзи (битый/непризнанный custom_emoji_id) — повторяет
    отправку с обычными эмодзи вместо того, чтобы command тихо "не открывался"."""
    try:
        return await message.reply(text, reply_markup=reply_markup)
    except TelegramBadRequest:
        return await message.reply(strip_premium_emoji(text), reply_markup=reply_markup)

async def safe_edit_text(callback: CallbackQuery, text: str, reply_markup=None):
    """Как callback.message.edit_text(), но не роняет хендлер, если Telegram отклонил
    правку. Это критично для инлайн-кнопок: если edit_text бросает исключение ДО того,
    как хендлер успел вызвать callback.answer(), Telegram держит кнопку в состоянии
    "часики" до собственного таймаута — именно это ощущается как "не нажимается"/
    "нажимается криво". Ловим и гасим самые частые причины:
    - "message is not modified" — юзер дважды подряд нажал одну и ту же кнопку
      (текст/клавиатура не изменились); это не ошибка, просто нечего обновлять.
    - "message to edit not found" / "query is too old" — сообщение удалено или
      кнопка нажата на старом сообщении после рестарта бота.
    - невалидный premium emoji-id — как и раньше, повторяем без премиум-обёртки.
    """
    try:
        return await callback.message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as e:
        err = str(e).lower()
        if "message is not modified" in err:
            return None
        if "message to edit not found" in err or "query is too old" in err or "message can't be edited" in err:
            return None
        try:
            return await callback.message.edit_text(strip_premium_emoji(text), reply_markup=reply_markup)
        except TelegramBadRequest:
            return None

def build_regular_visual(level: int) -> str:
    if level <= 5:
        return "🦵" * level
    idx = level - 6
    tier = idx // 5
    pos = idx % 5 + 1
    tier_emoji = ["🦵🏻", "🦵🏽", "🦿"][tier]
    prev_emoji = ["🦵", "🦵🏻", "🦵🏽"][tier]
    return tier_emoji * pos + prev_emoji * (5 - pos)

# Начиная с level 20002 (старт ULTRA-диапазона) стоимость КАЖДОГО отдельного уровня растёт
# по своей отдельной шкале: level 20002 стоит ровно 100 000 000 очков, дальше — «почучуть»
# (полиномиально, степень n^1.15) относительно позиции n = level - 20001 в этом диапазоне.
# Формула суммируется точно (прямой цикл) до ULTRA_EXACT_SUM_CUTOFF, а выше — через
# приближение Эйлера-Маклорена (расхождение < 0.002% уже на границе, дальше меньше) —
# без этого точный цикл был бы слишком медленным на экстремальных уровнях (level ~ 10^100).
ULTRA_STEP_BASE_COST = 100_000_000
ULTRA_STEP_POWER = 1.15
ULTRA_EXACT_SUM_CUTOFF = 1000

@functools.lru_cache(maxsize=4096)
def _ultra_step_cost(n: int) -> int:
    """Стоимость перехода на n-й уровень ULTRA-диапазона (n=1 -> level 20002 -> 100 000 000)."""
    return round(ULTRA_STEP_BASE_COST * n ** ULTRA_STEP_POWER)

@functools.lru_cache(maxsize=4096)
def _ultra_extra_score(n: int) -> int:
    """Сумма стоимостей уровней 1..n сверх базового threshold(level=20001), n = level - 20001."""
    if n <= 0:
        return 0
    if n <= ULTRA_EXACT_SUM_CUTOFF:
        return sum(_ultra_step_cost(i) for i in range(1, n + 1))
    p = ULTRA_STEP_POWER
    approx = n ** (p + 1) / (p + 1) + n ** p / 2 + p * n ** (p - 1) / 12 - p * (p - 1) * (p - 2) * n ** (p - 3) / 720
    return round(ULTRA_STEP_BASE_COST * approx)

def base_level_threshold(level: int) -> int:
    if level <= 39:
        return ALL_THRESHOLDS[level - 1]
    if level <= ULTRA_REQUIRED_LEG_LEVEL:  # <= 20001, старая формула без изменений
        return MAX_LEVEL_SCORE + round(200 * (level - 39) ** 1.5)
    t20001 = MAX_LEVEL_SCORE + round(200 * (ULTRA_REQUIRED_LEG_LEVEL - 39) ** 1.5)
    return t20001 + _ultra_extra_score(level - ULTRA_REQUIRED_LEG_LEVEL)

def level_threshold(level: int, evolution_level: int, rebirth_count: int = 0, active_items=None) -> int:
    evo_extra = EVO_HARDNESS_RATE * evolution_level
    rebirth_extra = REBIRTH_HARDNESS_STEP * rebirth_count
    if active_items and "paradox_charm" in set(_normalize_active_items(active_items)):
        evo_extra *= 0.5
        rebirth_extra *= 0.5
    hardness = (1 + evo_extra) * (1 + rebirth_extra)
    return round(base_level_threshold(level) * hardness)

def get_level_index(score: int, evolution_level: int = 0, rebirth_count: int = 0,
                     ultra_rebirth: bool = False) -> int:
    cap = ULTRA_LEVEL_CAP if ultra_rebirth else ULTRA_REQUIRED_LEG_LEVEL
    lo, hi = 0, cap
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if level_threshold(mid, evolution_level, rebirth_count) <= score:
            lo = mid
        else:
            hi = mid - 1
    return lo

def get_level_visual(level: int):
    if level == 0:
        return "🧍", "обычный безногий челик", True
    if level <= 20:
        return build_regular_visual(level), "", True
    if level <= 39:
        _, emoji, name = CUSTOM_LEVELS[level - 21]
        return emoji, name, True
    if level >= ULTRA_LEG_LEVEL:
        for start, end, emoji, name in ULTRA_TIERS:
            if start <= level <= end:
                return emoji, name, True
        return ULTRA_LEG_EMOJI, ULTRA_LEG_NAME, True
    if level >= MGG_MEGA_LEVEL:
        return MGG_MEGA_EMOJI, MGG_MEGA_NAME, True
    for start, end, emoji, name in EXTRA_TIERS:
        if start <= level <= end:
            return emoji, name, True
    return "❓", "неизвестный уровень", True

def next_level_text(score: int, evolution_level: int, rebirth_count: int = 0,
                     ultra_rebirth: bool = False) -> str:
    level = get_level_index(score, evolution_level, rebirth_count, ultra_rebirth)
    cap = ULTRA_LEVEL_CAP if ultra_rebirth else ULTRA_REQUIRED_LEG_LEVEL
    if level >= cap:
        return "Ты достиг абсолютного предела ноги — дальше только легенды 🌌"
    nxt = level_threshold(level + 1, evolution_level, rebirth_count)
    return f"До {level + 1} уровня осталось {nxt - score} очков"

def coin_tree_slot_bonus(inventory_map: dict) -> int:
    """+1 слот экипировки за 🟣 Монету Перерождения, +1 слот за ⚪️ Монету Пробуждения
    (суммируются, если есть обе — по 1 шт. каждой достаточно, лёжа в инвентаре, экипировать
    не нужно)."""
    bonus = 0
    if inventory_map.get("rebirth_coin", 0) > 0:
        bonus += 1
    if inventory_map.get("awakening_coin", 0) > 0:
        bonus += 1
    return bonus

def equipped_slots_max(upgrades: dict, prestige_upgrades: dict = None, bonus_slots: int = 0) -> int:
    prestige_upgrades = prestige_upgrades or {}
    return 1 + upgrade_level(upgrades, "equip_slots") + prestige_bonus(prestige_upgrades, "p_slots") + bonus_slots

def parse_equipped(equipped_str: str) -> list:
    """Очередь экипированных предметов: индекс 0 = надет раньше всех (первым вылетит при переполнении)."""
    return [k for k in (equipped_str or "").split(",") if k]

def format_equipped(items: list) -> str:
    return ",".join(items)

def equip_item(equipped_str: str, item_key: str, max_slots: int) -> list:
    """Добавляет item_key в конец очереди. Если он уже был в очереди — переставляет в конец
    (эквивалент «снял и заново надел»). При переполнении вылетает элемент с индекса 0."""
    items = [k for k in parse_equipped(equipped_str) if k != item_key]
    items.append(item_key)
    while len(items) > max_slots:
        items.pop(0)
    return items

def unequip_item(equipped_str: str, item_key: str) -> list:
    """Убирает item_key из очереди, если он там есть."""
    return [k for k in parse_equipped(equipped_str) if k != item_key]

def parse_potions(potions_str: str) -> dict:
    """'key:value,key:value' -> {key: value}. Для time-based зелий value = unix until_ts,
    для charge-based (no_cd) value = оставшиеся заряды."""
    result = {}
    for part in (potions_str or "").split(","):
        if not part or ":" not in part:
            continue
        key, _, val = part.partition(":")
        if key in POTIONS:
            try:
                result[key] = int(val)
            except ValueError:
                pass
    return result

def format_potions(potions: dict) -> str:
    return ",".join(f"{k}:{v}" for k, v in potions.items() if v > 0)

def active_potions_now(potions_str: str, now: int = None, active_items=None) -> dict:
    """Отфильтровывает истёкшие time-based зелья (charge-based остаются, пока заряды > 0).
    ⏰ Часы Хроноса: пока экипированы, время action-зелий не тикает (не удаляем по истечению) —
    сама запись until_ts в БД не трогается, поэтому после снятия предмета зелье честно
    доедает оставшееся время."""
    now = now or int(time.time())
    frozen = bool(active_items and "chronos_clock" in set(_normalize_active_items(active_items)))
    parsed = parse_potions(potions_str)
    result = {}
    for key, val in parsed.items():
        cfg = POTIONS[key]
        if cfg["effect"] == "no_cd":
            if val > 0:
                result[key] = val
        else:
            if val > now or frozen:
                result[key] = val
    return result

def potion_duration_seconds(key: str, upgrades: dict) -> int:
    base = POTIONS[key]["duration_seconds"]
    bonus = 1 + 0.20 * upgrade_level(upgrades, "brew_duration")
    return round(base * bonus)

CHAOS_ORB_BREW_CUT = 0.90

def brew_seconds_for(key: str, upgrades: dict, prestige_upgrades: dict = None, active_items=None) -> int:
    base = POTIONS[key]["brew_seconds"]
    cut = 1 - 0.10 * upgrade_level(upgrades, "brew_speed")
    if prestige_upgrades:
        p_speed = prestige_bonus(prestige_upgrades, "p_brew_speed")
        if p_speed:
            cut -= 0.02 * p_speed
    if active_items and "chaos_orb" in set(_normalize_active_items(active_items)):
        cut -= CHAOS_ORB_BREW_CUT
    cut = max(0.1, cut)
    return max(30, round(base * cut))

def has_potion_effect(potions: dict, effect: str) -> bool:
    return any(POTIONS[k]["effect"] == effect for k in potions)

async def consume_no_cd_charge(user_id: int, potions: dict) -> dict:
    """Списывает 1 заряд зелья 'без КД', если оно активно. Возвращает обновлённый potions dict."""
    if NO_CD_CHARGES_KEY not in potions:
        return potions
    left = potions[NO_CD_CHARGES_KEY] - 1
    new_potions = dict(potions)
    if left > 0:
        new_potions[NO_CD_CHARGES_KEY] = left
    else:
        new_potions.pop(NO_CD_CHARGES_KEY, None)
    await db_exec("UPDATE users SET active_potions = ? WHERE user_id = ?", (format_potions(new_potions), user_id))
    return new_potions

def parse_potion_stock(stock_str: str) -> dict:
    """Сваренные, но не выпитые зелья: 'key:qty,key:qty' -> {key: qty}."""
    result = {}
    for part in (stock_str or "").split(","):
        if not part or ":" not in part:
            continue
        key, _, qty = part.partition(":")
        if key in POTIONS:
            try:
                q = int(qty)
                if q > 0:
                    result[key] = q
            except ValueError:
                pass
    return result

def format_potion_stock(stock: dict) -> str:
    return ",".join(f"{k}:{v}" for k, v in stock.items() if v > 0)

def get_multiplier(evolution_level: int, active_items, vip_active: bool, upgrades: dict = None,
                    ultra_rebirth: bool = False, chronos_boost_pct: int = 100, nano_it_count: int = 0) -> float:
    mult = 1.0
    if evolution_level >= 2:
        mult += EVO_BOOST_STEP
    if evolution_level >= 3:
        mult += EVO_BOOST_STEP * (evolution_level - 2)
    equipped_set = set(_normalize_active_items(active_items))
    total_boost_percent = 0
    for item_key in equipped_set:
        if item_key in ITEMS and item_key != "chronos_orb":
            total_boost_percent += ITEMS[item_key][2]
    mult += total_boost_percent / 100
    if "chronos_orb" in equipped_set:
        mult += chronos_boost_pct / 100
    if vip_active:
        mult += VIP_BOOST
    if upgrades:
        mult += 0.05 * upgrade_level(upgrades, "booster")
    if ultra_rebirth:
        mult += ULTRA_REBIRTH_BOOST
    if nano_it_count:
        mult += (NANO_IT_BOOST_PCT_PER_UNIT * nano_it_count) / 100
    return mult

def _normalize_active_items(active_items):
    """Принимает список/кортеж ключей предметов, либо None. Строки сюда не передаём —
    для строки очереди сначала вызывай parse_equipped()."""
    if active_items is None:
        return []
    if isinstance(active_items, str):
        return [active_items] if active_items in ITEMS else parse_equipped(active_items)
    return [k for k in active_items if k]

def total_flat_bonus(active_items) -> int:
    return sum(ITEM_FLAT_BONUS.get(k, 0) for k in _normalize_active_items(active_items))

def parse_hidden(hidden_str: str) -> set:
    return set(h for h in (hidden_str or "").split(",") if h)

def parse_shown(shown_str: str) -> set:
    """Явно включённые (не скрытые) ключи бейджей — whitelist модель, аналог инвентаря:
    сколько бы бейджей игрок ни заработал, показываются только эти, максимум BADGES_DISPLAY_LIMIT."""
    return set(s for s in (shown_str or "").split(",") if s)

def parse_upgrades(upgrades_str: str) -> dict:
    result = {}
    for part in (upgrades_str or "").split(","):
        if not part or ":" not in part:
            continue
        key, _, lvl = part.partition(":")
        if key in UPGRADES:
            try:
                result[key] = int(lvl)
            except ValueError:
                pass
    return result

def format_upgrades(upgrades: dict) -> str:
    return ",".join(f"{k}:{v}" for k, v in upgrades.items() if v > 0)

def upgrade_level(upgrades: dict, key: str) -> int:
    return upgrades.get(key, 0)

def upgrade_next_cost(key: str, upgrades: dict):
    cfg = UPGRADES[key]
    if cfg.get("wip") or cfg["cost"] is None:
        return None
    level = upgrade_level(upgrades, key)
    if level >= cfg["max_level"]:
        return None
    return cfg["cost"](level + 1)

def upgrade_next_extra_cost(key: str, upgrades: dict):
    """Доп. стоимость в другой валюте для следующего уровня апгрейда (напр. крафты ур.3 = 🉑+💠).
    Возвращает (currency_field, amount) либо None, если для этого уровня доп. валюты нет."""
    cfg = UPGRADES[key]
    if cfg.get("wip") or cfg["cost"] is None or not cfg.get("extra_cost"):
        return None
    level = upgrade_level(upgrades, key)
    if level >= cfg["max_level"]:
        return None
    return cfg["extra_cost"](level + 1)

def parse_prestige_upgrades(upgrades_str: str) -> dict:
    result = {}
    for part in (upgrades_str or "").split(","):
        if not part or ":" not in part:
            continue
        key, _, lvl = part.partition(":")
        if key in PRESTIGE_UPGRADES:
            try:
                result[key] = int(lvl)
            except ValueError:
                pass
    return result

def format_prestige_upgrades(upgrades: dict) -> str:
    return ",".join(f"{k}:{v}" for k, v in upgrades.items() if v > 0)

def prestige_level(upgrades: dict, key: str) -> int:
    return upgrades.get(key, 0)

def prestige_next_cost(key: str, upgrades: dict) -> int:
    """Бесконечная ветка — цена следующего уровня всегда определена, потолка нет."""
    level = prestige_level(upgrades, key)
    return PRESTIGE_UPGRADES[key]["cost"](level + 1)

def prestige_bonus(upgrades: dict, key: str) -> int:
    """Текущий эффект ветки на её нынешнем уровне (0, если ветка ещё не куплена)."""
    level = prestige_level(upgrades, key)
    return PRESTIGE_UPGRADES[key]["bonus"](level)

async def claim_offline_auto_farm(user_id: int, row) -> tuple:
    """Начисляет оффлайн-доход от Авто-Фермы НОГИ/КОИНЫ по разнице времени.
    Возвращает (legs_gained, coins_gained, new_score, new_coins)."""
    upgrades = parse_upgrades(row[16])
    legs_lvl = upgrade_level(upgrades, "auto_farm_legs")
    coins_lvl = upgrade_level(upgrades, "auto_farm_coins")
    score, coins = row[2], row[5]
    last_claim = row[17] or 0
    now = int(time.time())

    if not legs_lvl and not coins_lvl:
        if not last_claim:
            await db_exec("UPDATE users SET last_auto_claim = ? WHERE user_id = ?", (now, user_id))
        return 0, 0, score, coins

    if not last_claim:
        await db_exec("UPDATE users SET last_auto_claim = ? WHERE user_id = ?", (now, user_id))
        return 0, 0, score, coins

    elapsed = max(0, now - last_claim)
    legs_gained = 0
    coins_gained = 0

    if legs_lvl:
        amount, per_seconds = AUTO_FARM_LEGS_RATES[legs_lvl]
        legs_gained = int(elapsed // per_seconds) * amount
    if coins_lvl:
        amount, per_seconds = AUTO_FARM_COINS_RATES[coins_lvl]
        coins_gained = int(elapsed // per_seconds) * amount

    if legs_gained == 0 and coins_gained == 0:
        return 0, 0, score, coins

    new_score = score + legs_gained
    new_coins = coins + coins_gained
    await db_exec(
        "UPDATE users SET score = ?, coins = ?, total_farmed = total_farmed + ?, last_auto_claim = ? WHERE user_id = ?",
        (new_score, new_coins, legs_gained, now, user_id),
    )
    return legs_gained, coins_gained, new_score, new_coins

def rebirth_hardness_multiplier(rebirth_count: int) -> float:
    return 1 + REBIRTH_HARDNESS_STEP * rebirth_count

def farm_yield_multiplier(upgrades: dict) -> float:
    return 1 + 0.10 * upgrade_level(upgrades, "farm_yield")

def farm_cd_seconds(upgrades: dict, active_items=None, has_time_particle: bool = False,
                     prestige_upgrades: dict = None) -> int:
    reduction = 120 * upgrade_level(upgrades, "farm_cd")
    cooldown = max(60, FARM_COOLDOWN - reduction)

    tier = get_active_unique_tier(active_items) if active_items is not None else None
    if tier in GOD_TIER_LIKE:
        cooldown = cooldown / GOD_ESSENCE_FARM_SPEED - GOD_ESSENCE_TIMER_CUT
    elif has_time_particle:
        cooldown = cooldown / TIME_PARTICLE_FARM_SPEED

    if prestige_upgrades:
        p_speed = prestige_bonus(prestige_upgrades, "p_farm_speed")
        if p_speed:
            cooldown *= max(0.1, 1 - 0.01 * p_speed)

    return max(30, round(cooldown))

def booster_upgrade_multiplier(upgrades: dict) -> float:
    return 1 + 0.05 * upgrade_level(upgrades, "booster")

def case_discount(upgrades: dict) -> float:
    return 0.10 * upgrade_level(upgrades, "discount")

def case_price_with_discount(base_price: int, upgrades: dict) -> int:
    discount = case_discount(upgrades)
    return max(1, round(base_price * (1 - discount)))

def craft_coin_cost_with_discount(base_cost: int, prestige_upgrades: dict = None) -> int:
    """Скидка крафта — целиком за счёт ветки престижа p_craft_discount (обычной скидки крафта
    в игре не было ранее, эта механика впервые вводится через дерево престижа)."""
    if not base_cost:
        return 0
    if not prestige_upgrades:
        return base_cost
    discount = 0.01 * prestige_bonus(prestige_upgrades, "p_craft_discount")
    discount = min(0.9, discount)
    return max(1, round(base_cost * (1 - discount)))

def sell_bonus_coins(upgrades: dict) -> int:
    return 2 * upgrade_level(upgrades, "sell_boost")

def badge_list(username: str, evolution_level: int, cases_opened: int, total_farmed: int, vip_active: bool,
                promo_badges: set = frozenset(), coins: int = 0, rebirth_points: int = 0,
                ultra_rebirth: bool = False, bonus_streak: int = 0, crafts_done: int = 0,
                prestige_points: int = 0):
    result = []
    if username and username.lower() == ADMIN_USERNAME.lower():
        result.append(("owner", PREMIUM_OWNER_BADGE, "Владелец"))
    if vip_active:
        result.append(("vip", PREMIUM_VIP_BADGE, "VIP"))
    if evolution_level >= 1:
        result.append(("evo", PREMIUM_BADGE_EVO, "1+ эволюция"))
    if cases_opened >= 5:
        result.append(("case", PREMIUM_BADGE_CASE, "5+ кейсов"))
    if total_farmed >= BADGE_EVO_TOTAL:
        result.append(("farm", PREMIUM_BADGE_FARM, "30k нафармлено"))
    if evolution_level >= 5:
        result.append(("evo5", PREMIUM_BADGE_EVO5, "5 эволюция"))
    for key, emoji, label, threshold in EVO_MILESTONE_BADGES:
        if evolution_level >= threshold:
            result.append((key, emoji, label))
    for key, emoji, label, threshold in CASE_MILESTONE_BADGES:
        if cases_opened >= threshold:
            result.append((key, emoji, label))
    for key, emoji, label, threshold in FARM_MILESTONE_BADGES:
        if total_farmed >= threshold:
            result.append((key, emoji, label))
    for key, emoji, label, threshold in COIN_MILESTONE_BADGES:
        if coins >= threshold:
            result.append((key, emoji, label))
    for key, emoji, label, threshold in REBIRTH_MILESTONE_BADGES:
        if rebirth_points >= threshold:
            result.append((key, emoji, label))
    if ultra_rebirth:
        result.append(("ultra_rebirth", PREMIUM_BADGE_ULTRA_REBIRTH, "Ультра-Феникс"))
    for key, emoji, label, threshold in STREAK_MILESTONE_BADGES:
        if bonus_streak >= threshold:
            result.append((key, emoji, label))
    for key, emoji, label, threshold in CRAFT_MILESTONE_BADGES:
        if crafts_done >= threshold:
            result.append((key, emoji, label))
    for key, emoji, label, threshold in PRESTIGE_MILESTONE_BADGES:
        if prestige_points >= threshold:
            result.append((key, emoji, label))
    for key in promo_badges:
        if key in PROMO_BADGES:
            emoji, name = PROMO_BADGES[key]
            result.append((key, emoji, name))
    return result

def get_badges(username: str, evolution_level: int, cases_opened: int, total_farmed: int, vip_active: bool,
                shown: set = frozenset(), promo_badges: set = frozenset(), coins: int = 0,
                rebirth_points: int = 0, ultra_rebirth: bool = False, bonus_streak: int = 0,
                crafts_done: int = 0, prestige_points: int = 0) -> str:
    """shown — whitelist явно включённых ключей бейджей (см. parse_shown). Показываются
    только они, максимум BADGES_DISPLAY_LIMIT штук — как со слотами экипировки в инвентаре,
    а не «все заработанные минус скрытые»."""
    earned = badge_list(username, evolution_level, cases_opened, total_farmed, vip_active, promo_badges,
                         coins, rebirth_points, ultra_rebirth, bonus_streak, crafts_done, prestige_points)
    visible = [emoji for key, emoji, _ in earned if key in shown]
    return "".join(visible[:BADGES_DISPLAY_LIMIT])

def badges_keyboard(earned, shown: set, user_id: int, page: int = 0) -> InlineKeyboardMarkup:
    total_pages = max(1, (len(earned) - 1) // BADGES_PAGE_SIZE + 1)
    page = max(0, min(page, total_pages - 1))
    start = page * BADGES_PAGE_SIZE
    rows = []
    for key, emoji, label in earned[start:start + BADGES_PAGE_SIZE]:
        state = "✅ показан" if key in shown else "🙈 скрыт"
        rows.append([InlineKeyboardButton(
            text=f"{plain_emoji(emoji)} {label} — {state}",
            callback_data=f"badge:{user_id}:{page}:{key}",
        )])

    if total_pages > 1:
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton(text="◀️", callback_data=f"badge_page:{user_id}:{page - 1}", style="primary"))
        nav.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="badge_noop"))
        if page < total_pages - 1:
            nav.append(InlineKeyboardButton(text="▶️", callback_data=f"badge_page:{user_id}:{page + 1}", style="primary"))
        rows.append(nav)
    return InlineKeyboardMarkup(inline_keyboard=rows)

def farm_range(evolution_level: int):
    return FARM_EVOLVED if evolution_level >= 1 else FARM_BASE

def is_admin(message: Message) -> bool:
    return message.from_user.id == ADMIN_USER_ID or (message.from_user.username or "").lower() == ADMIN_USERNAME.lower()

def subscription_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Подписаться на канал", url=REQUIRED_CHANNEL_URL)],
        [InlineKeyboardButton(text="✅ Я подписался", callback_data="check_sub")],
    ])

async def is_subscribed(user_id: int) -> bool:
    """Проверяет подписку на REQUIRED_CHANNEL_CHAT_ID с коротким кэшем,
    чтобы не спамить getChatMember на каждый фарм/эво/перерождение."""
    cached = _subscription_cache.get(user_id)
    now = time.monotonic()
    if cached and now - cached[1] < SUBSCRIPTION_CHECK_CACHE_TTL:
        return cached[0]

    try:
        member = await bot.get_chat_member(REQUIRED_CHANNEL_CHAT_ID, user_id)
        subscribed = member.status not in ("left", "kicked")
        print(f"[sub-check] user={user_id} status={member.status} -> subscribed={subscribed}")
    except Exception as e:
        # ВРЕМЕННО (диагностика): раньше любая ошибка тут пропускала пользователя (subscribed=True).
        # Сейчас логируем во весь голос, чтобы увидеть причину. Пока не разберёмся — считаем НЕ подписанным.
        print(f"[sub-check] ОШИБКА при проверке ({REQUIRED_CHANNEL_CHAT_ID}, user={user_id}): {type(e).__name__}: {e}")
        subscribed = False

    _subscription_cache[user_id] = (subscribed, now)
    return subscribed

async def require_subscription(message: Message) -> bool:
    """Возвращает True если можно продолжать выполнение команды.
    Если пользователь не подписан — отправляет требование подписаться и возвращает False."""
    user_id = message.from_user.id
    if is_admin(message):
        return True
    if await is_subscribed(user_id):
        return True
    await message.reply(TEXTS["require_subscription_1"], reply_markup=subscription_keyboard())
    return False

@dp.callback_query(F.data == "check_sub")
async def check_sub_callback(callback: CallbackQuery):
    user_id = callback.from_user.id
    _subscription_cache.pop(user_id, None)  # форс-рекheck, не ждём TTL кэша
    if await is_subscribed(user_id):
        await callback.answer("✅ Подписка подтверждена! Можешь фармить дальше.", show_alert=True)
        try:
            await callback.message.delete()
        except TelegramBadRequest:
            pass
    else:
        await callback.answer("❌ Подписки пока не вижу. Подпишись на канал и попробуй ещё раз.", show_alert=True)

def roll_case_item(case_num: int) -> str:
    pool = CASES[case_num]["pool"]
    weights = [ITEMS[k][3] for k in pool]
    return random.choices(pool, weights=weights, k=1)[0]

def case_drop_table(case_num: int) -> list:
    """Список (item_key, эмодзи, имя, буст%, шанс_в_процентах) для конкретного кейса,
    отсортированный по убыванию шанса."""
    pool = CASES[case_num]["pool"]
    weights = [ITEMS[k][3] for k in pool]
    total = sum(weights)
    rows = []
    for k, w in zip(pool, weights):
        emoji, name, percent, _ = ITEMS[k]
        chance = round(w / total * 100, 2) if total else 0
        rows.append((k, emoji, name, percent, chance))
    rows.sort(key=lambda r: r[4], reverse=True)
    return rows

def find_item_by_name(query: str, only_passive=None):
    q = query.strip().lower()
    candidates = ITEMS.items()
    if only_passive is True:
        candidates = [(k, v) for k, v in candidates if k in PASSIVE_ITEMS]
    elif only_passive is False:
        candidates = [(k, v) for k, v in candidates if k not in PASSIVE_ITEMS]
    for key, (_, name, _, _) in candidates:
        if name.lower() == q:
            return key
    matches = [key for key, (_, name, _, _) in candidates if q in name.lower()]
    if len(matches) == 1:
        return matches[0]
    return None

async def resolve_target(message: Message, to_self: bool):
    if to_self:
        return message.from_user
    if message.reply_to_message:
        return message.reply_to_message.from_user
    return None

from concurrent.futures import ThreadPoolExecutor

DB_WORKER_COUNT = int(os.environ.get("DB_WORKER_COUNT", "1"))

_db_queues: list = []
_db_worker_tasks: list = []
_db_conns: list = []
_db_executor = ThreadPoolExecutor(max_workers=DB_WORKER_COUNT, thread_name_prefix="db-worker")

_user_cache: dict = {}
_USERS_WRITE_RE = re.compile(r"\b(?:UPDATE|DELETE\s+FROM)\s+users\b", re.IGNORECASE)

def _invalidate_user_cache(user_id):
    _user_cache.pop(user_id, None)

def _connect(worker_idx):
    if _db_conns[worker_idx] is None:
        _db_conns[worker_idx] = libsql.connect(database=TURSO_URL, auth_token=TURSO_TOKEN)
    return _db_conns[worker_idx]

def _exec_sync(worker_idx, sql, params):
    conn = _connect(worker_idx)
    conn.execute(sql, params)
    conn.commit()

def _exec_many_sync(worker_idx, sql, params_list):
    conn = _connect(worker_idx)
    conn.executemany(sql, params_list)
    conn.commit()

def _query_sync(worker_idx, sql, params):
    conn = _connect(worker_idx)
    cur = conn.execute(sql, params)
    return cur.fetchall()

async def _db_worker(worker_idx):
    """Один из DB_WORKER_COUNT потоков. Каждый воркер берёт задачи строго из
    СВОЕЙ очереди по одной — его соединение всегда используется из одного и
    того же потока (никаких гонок внутри соединения), но разные воркеры со
    своими соединениями могут работать параллельно, а не ждать друг друга."""
    loop = asyncio.get_event_loop()
    queue = _db_queues[worker_idx]
    while True:
        fn, sql, params, future = await queue.get()
        try:
            result = await loop.run_in_executor(_db_executor, fn, worker_idx, sql, params)
            if not future.done():
                future.set_result(result)
        except Exception as e:
            if not future.done():
                future.set_exception(e)
        finally:
            queue.task_done()

def _ensure_db_workers():
    global _db_queues, _db_worker_tasks, _db_conns
    if not _db_queues:
        _db_queues = [asyncio.Queue() for _ in range(DB_WORKER_COUNT)]
        _db_conns = [None] * DB_WORKER_COUNT
        _db_worker_tasks = [None] * DB_WORKER_COUNT
    for i in range(DB_WORKER_COUNT):
        if _db_worker_tasks[i] is None or _db_worker_tasks[i].done():
            _db_worker_tasks[i] = asyncio.create_task(_db_worker(i))

def _pick_worker(params):
    for p in params:
        if isinstance(p, int) and not isinstance(p, bool):
            return p % DB_WORKER_COUNT
    return 0

async def _db_submit(fn, sql, params):
    _ensure_db_workers()
    worker_idx = _pick_worker(params)
    future = asyncio.get_event_loop().create_future()
    await _db_queues[worker_idx].put((fn, sql, params, future))
    return await future

async def db_exec(sql, params=()):
    await _db_submit(_exec_sync, sql, params)
    if _USERS_WRITE_RE.search(sql):
        if "WHERE user_id = ?" in sql and params:
            _invalidate_user_cache(params[-1])
        else:
            _user_cache.clear()

async def db_exec_many(sql, params_list):
    """Как db_exec, но один запрос в очередь воркера выполняет executemany
    сразу для списка наборов параметров — используется для батчинга (см.
    _flush_player_log_buffer), чтобы N записей стоили очереди воркера как одна."""
    if not params_list:
        return
    await _db_submit(_exec_many_sync, sql, params_list)

async def db_query(sql, params=()):
    return await _db_submit(_query_sync, sql, params)

async def db_query_one(sql, params=()):
    rows = await db_query(sql, params)
    return rows[0] if rows else None

USER_COLUMNS = (
    "user_id, username, score, evolution_level, last_farm, coins, active_item, "
    "cases_opened, total_farmed, last_bonus, bonus_streak, levelup_notify, vip_until, hidden_badges, "
    "rebirth_points, rebirth_count, upgrades, last_auto_claim, equipped_items, nickname, top_banned, "
    "ultra_rebirth, auto_evolve, active_potions, brewing_potion, brewing_until, potion_stock, "
    "prestige_points, prestige_upgrades, auto_rebirth, auto_sell, auto_sell_items, craft_points, "
    "promo_badges, chronos_boost_pct, compact_mode, crafts_done, vilon_streak, vilon_boost_until, shown_badges, "
    "kotyara_boost_until"
)

def display_name(username: str, nickname: str = None) -> str:
    """Имя для отображения: ник, если задан, иначе обычный telegram-username."""
    return nickname if nickname else username

async def init_db():
    await db_exec("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            score INTEGER DEFAULT 0,
            evolution_level INTEGER DEFAULT 0,
            last_farm INTEGER DEFAULT 0,
            coins INTEGER DEFAULT 0,
            active_item TEXT,
            cases_opened INTEGER DEFAULT 0,
            total_farmed INTEGER DEFAULT 0,
            last_bonus INTEGER DEFAULT 0,
            bonus_streak INTEGER DEFAULT 0,
            levelup_notify INTEGER DEFAULT 1,
            vip_until INTEGER DEFAULT 0
        )
    """)
    await db_exec("""
        CREATE TABLE IF NOT EXISTS inventory (
            user_id INTEGER,
            item_key TEXT,
            qty INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, item_key)
        )
    """)
    await db_exec("""
        CREATE TABLE IF NOT EXISTS chat_members (
            user_id INTEGER,
            chat_id INTEGER,
            PRIMARY KEY (user_id, chat_id)
        )
    """)
    await db_exec("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    await db_exec("""
        CREATE TABLE IF NOT EXISTS personal_boosts (
            user_id INTEGER PRIMARY KEY,
            multiplier REAL DEFAULT 1,
            until INTEGER DEFAULT 0
        )
    """)
    await db_exec("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts INTEGER,
            admin_username TEXT,
            command TEXT
        )
    """)
    await db_exec("""
        CREATE TABLE IF NOT EXISTS player_action_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts INTEGER,
            user_id INTEGER,
            username TEXT,
            command TEXT
        )
    """)
    await db_exec("""
        CREATE INDEX IF NOT EXISTS idx_player_action_log_user_ts
        ON player_action_log (user_id, ts)
    """)
    await db_exec("""
        CREATE TABLE IF NOT EXISTS banned_chats (
            chat_id INTEGER PRIMARY KEY,
            title TEXT,
            banned_by TEXT,
            banned_at INTEGER
        )
    """)
    await db_exec("""
        CREATE TABLE IF NOT EXISTS banned_users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            banned_by TEXT,
            banned_at INTEGER,
            reason TEXT DEFAULT 'manual'
        )
    """)
    try:
        await db_exec("ALTER TABLE banned_users ADD COLUMN reason TEXT DEFAULT 'manual'")
    except Exception:
        pass
    await db_exec("""
        CREATE TABLE IF NOT EXISTS promocodes (
            code TEXT PRIMARY KEY,
            reward_type TEXT NOT NULL,
            reward_key TEXT DEFAULT '',
            amount INTEGER NOT NULL,
            activations_left INTEGER NOT NULL,
            created_by TEXT,
            created_at INTEGER
        )
    """)
    await db_exec("""
        CREATE TABLE IF NOT EXISTS promocode_uses (
            user_id INTEGER,
            code TEXT,
            used_at INTEGER,
            PRIMARY KEY (user_id, code)
        )
    """)
    for stmt in (
        "ALTER TABLE users ADD COLUMN levelup_notify INTEGER DEFAULT 1",
        "ALTER TABLE users ADD COLUMN vip_until INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN hidden_badges TEXT DEFAULT ''",
        "ALTER TABLE users ADD COLUMN rebirth_points INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN rebirth_count INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN upgrades TEXT DEFAULT ''",
        "ALTER TABLE users ADD COLUMN last_auto_claim INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN active_item2 TEXT DEFAULT NULL",
        "ALTER TABLE users ADD COLUMN equipped_items TEXT DEFAULT ''",
        "ALTER TABLE users ADD COLUMN nickname TEXT DEFAULT NULL",
        "ALTER TABLE users ADD COLUMN top_banned INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN ultra_rebirth INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN auto_evolve INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN active_potions TEXT DEFAULT ''",
        "ALTER TABLE users ADD COLUMN brewing_potion TEXT DEFAULT NULL",
        "ALTER TABLE users ADD COLUMN brewing_until INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN potion_stock TEXT DEFAULT ''",
        "ALTER TABLE users ADD COLUMN prestige_points INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN prestige_upgrades TEXT DEFAULT ''",
        "ALTER TABLE users ADD COLUMN auto_rebirth INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN auto_sell INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN auto_sell_items TEXT DEFAULT ''",
        "ALTER TABLE users ADD COLUMN craft_points INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN promo_badges TEXT DEFAULT ''",
        "ALTER TABLE users ADD COLUMN chronos_boost_pct INTEGER DEFAULT 100",
        "ALTER TABLE users ADD COLUMN compact_mode INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN crafts_done INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN vilon_streak INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN vilon_boost_until INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN shown_badges TEXT DEFAULT ''",
        "ALTER TABLE users ADD COLUMN kotyara_boost_until INTEGER DEFAULT 0",
    ):
        try:
            await db_exec(stmt)
        except Exception:
            pass

async def get_user(user_id: int):
    if user_id in _user_cache:
        return _user_cache[user_id]
    row = await db_query_one(f"SELECT {USER_COLUMNS} FROM users WHERE user_id = ?", (user_id,))
    if row is not None:
        _user_cache[user_id] = row
    return row

async def get_user_by_username(username: str):
    return await db_query_one(f"SELECT {USER_COLUMNS} FROM users WHERE lower(username) = lower(?)", (username,))

async def ensure_user(user_id: int, username: str):
    row = await get_user(user_id)
    if row is None:
        await db_exec("INSERT INTO users (user_id, username, score) VALUES (?, ?, 0)", (user_id, username))
        now = int(time.time())
        new_row = (user_id, username, 0, 0, 0, 0, None, 0, 0, 0, 0, 1, 0, "", 0, 0, "", now, "", None, 0, 0, 0, "", None, 0, "", 0, "", 0, "", "", 0, "", 100)
        _user_cache[user_id] = new_row
        return new_row
    if row[1] != username:
        await db_exec("UPDATE users SET username = ? WHERE user_id = ?", (username, user_id))
    return row

async def get_inventory(user_id: int):
    return await db_query("SELECT item_key, qty FROM inventory WHERE user_id = ? AND qty > 0", (user_id,))

async def add_item(user_id: int, item_key: str, qty: int = 1):
    await db_exec(
        "INSERT INTO inventory (user_id, item_key, qty) VALUES (?, ?, ?) "
        "ON CONFLICT(user_id, item_key) DO UPDATE SET qty = qty + excluded.qty",
        (user_id, item_key, qty),
    )

PROMO_TYPE_ALIASES = {
    "ноги": "legs", "нога": "legs", "ног": "legs",
    "эво": "evo", "эволюция": "evo",
    "коин": "coin", "коины": "coin", "монеты": "coin",
    "очкп": "rebirth", "перерождение": "rebirth",
    "крафт": "craft", "очкк": "craft",
}
PROMO_TYPE_COLUMN = {
    "legs": "score",
    "evo": "evolution_level",
    "coin": "coins",
    "rebirth": "rebirth_points",
    "craft": "craft_points",
}
PROMO_TYPE_LABEL = {
    "legs": "🦵 очков ноги",
    "evo": "🧬 очков эволюции",
    "coin": "🪙 монет",
    "rebirth": "🉑 очков перерождения",
    "craft": "💠 очков крафта",
}

PROMO_BADGES = {
    "tester":       (PREMIUM_BADGE_TESTER, "Фанат Мику"),
    "support":      (PREMIUM_BADGE_SUPPORT, "Сапорт"),
    "power":        (PREMIUM_BADGE_POWER, "Потужность"),
    "top1_past":    (PREMIUM_BADGE_TOP1_PAST, "Топ 1 в прошлом"),
    "chaos_master": (PREMIUM_BADGE_CHAOS_MASTER, "Мастер Хаоса⚡️"),
    "investor":     (PREMIUM_BADGE_INVESTOR, "Инвестировал в #####"),
}
PROMO_BADGE_ALIASES = {
    "фанат мику": "tester",
    "сапорт": "support",
    "потужность": "power",
    "топ1 в прошлом": "top1_past",
    "топ 1 в прошлом": "top1_past",
    "мастер хаоса": "chaos_master",
    "инвестировал в #####": "investor",
}

# Справочник для команды «помощь бейдж <название>»: ключ (как в badge_list/PROMO_BADGES) ->
# (эмодзи, русские алиасы для поиска, текст объяснения). Алиасы через запятую в подсказке —
# просто самый первый считается «каноничным» именем бейджа.
HELP_BADGES = {
    "owner":       (PREMIUM_OWNER_BADGE, ["владелец", "овнер", "admin", "админ"],
                    "Этот бейдж есть только у владельца бота — выдаётся автоматически по нику, вручную получить нельзя."),
    "vip":         (PREMIUM_VIP_BADGE, ["vip", "вип"],
                    "Этот бейдж даётся всем игрокам у кого есть VIP-статус. Пропадает, если VIP закончился."),
    "evo":         (PREMIUM_BADGE_EVO, ["1+ эволюция", "эволюция", "эво"],
                    "Даётся за первую эволюцию (39 уровень ноги, «ногу мгг»). Один раз пройдёшь эволюцию — бейдж останется навсегда."),
    "case":        (PREMIUM_BADGE_CASE, ["5+ кейсов", "кейсы", "кейс"],
                    "Даётся за открытие 5 или более кейсов (любых, суммарно)."),
    "farm":        (PREMIUM_BADGE_FARM, ["30k нафармлено", "ферма", "фарм"],
                    f"Даётся, когда суммарно нафармлено {BADGE_EVO_TOTAL} очков ноги (считается всё время, не сбрасывается)."),
    "evo5":        (PREMIUM_BADGE_EVO5, ["5 эволюция", "5эво", "5 эво"],
                    "Даётся по достижению 5 уровня эволюции."),
    "tester":      (PREMIUM_BADGE_TESTER, ["фанат мику"],
                    "Выдаётся вручную админом или по промокоду преданным фанатам Мику."),
    "support":     (PREMIUM_BADGE_SUPPORT, ["сапорт", "support"],
                    "Выдаётся вручную админом или по промокоду тем, кто помогает с поддержкой игроков."),
    "power":       (PREMIUM_BADGE_POWER, ["потужность"],
                    "Выдаётся вручную админом или по промокоду — почётный значок за вклад в развитие бота."),
    "top1_past":   (PREMIUM_BADGE_TOP1_PAST, ["топ1 в прошлом", "топ 1 в прошлом", "топ1"],
                    "Выдаётся тем, кто когда-то был на первом месте в топе игроков."),
    "chaos_master": (PREMIUM_BADGE_CHAOS_MASTER, ["мастер хаоса"],
                    "Редкий бейдж, связанный с Шаром Хаоса и Хроносом — выдаётся вручную или по промокоду."),
    "investor":    (PREMIUM_BADGE_INVESTOR, ["инвестировал в #####"],
                    "Выдаётся вручную админом или по промокоду за поддержку проекта."),
}

def find_help_badge_key(query: str):
    """Ищет ключ HELP_BADGES по русскому названию/алиасу. Сначала точное совпадение,
    иначе — по вхождению подстроки в любой из алиасов (как find_item_by_name).
    Возвращает (key, None) при однозначном совпадении, (None, [варианты]) при неоднозначности,
    (None, []) если не найдено."""
    q = (query or "").strip().lower()
    if not q:
        return None, []
    for key, (_, aliases, _) in HELP_BADGES.items():
        if q == key.lower() or q in (a.lower() for a in aliases):
            return key, None
    matches = [key for key, (_, aliases, _) in HELP_BADGES.items() if any(q in a.lower() for a in aliases)]
    if len(matches) == 1:
        return matches[0], None
    if len(matches) > 1:
        matches.sort(key=lambda k: HELP_BADGES[k][1][0])
        return None, matches
    return None, []

def parse_promo_badges(raw: str) -> set:
    return set(x for x in (raw or "").split(",") if x)

def format_promo_badges(badges: set) -> str:
    return ",".join(sorted(badges))

def find_promo_badge_key(name_raw: str):
    """Находит ключ PROMO_BADGES по русскому названию бейджа (из команды создания промокода)."""
    return PROMO_BADGE_ALIASES.get(name_raw.strip().lower())

async def add_promo_badge(user_id: int, badge_key: str):
    row = await db_query_one("SELECT promo_badges FROM users WHERE user_id = ?", (user_id,))
    current = parse_promo_badges(row[0] if row else "")
    current.add(badge_key)
    await db_exec("UPDATE users SET promo_badges = ? WHERE user_id = ?", (format_promo_badges(current), user_id))

def parse_promo_type(raw: str):
    """Разбирает строку типа награды из команды создания промокода.
    Возвращает (reward_type, reward_key) либо None, если тип не распознан.
    "предмет:<ключ>" -> ("item", "<ключ>"); "бейдж" обрабатывается отдельным синтаксисом
    (см. PROMO_CREATE_BADGE_RE); иначе алиас из PROMO_TYPE_ALIASES -> (type, "")."""
    raw = raw.strip().lower()
    if raw.startswith("предмет:") or raw.startswith("предмет "):
        item_key = raw.split(":", 1)[1].strip() if ":" in raw else raw.split(" ", 1)[1].strip()
        if item_key not in ITEMS:
            return None
        return ("item", item_key)
    reward_type = PROMO_TYPE_ALIASES.get(raw)
    if not reward_type:
        return None
    return (reward_type, "")

async def apply_promo_reward(user_id: int, reward_type: str, reward_key: str, amount: int):
    """Выдаёт награду промокода игроку. Возвращает текст для показа в ответе (что именно выдано)."""
    if reward_type == "item":
        await add_item(user_id, reward_key, amount)
        emoji, name, _, _ = ITEMS[reward_key]
        return f"{emoji} {esc(name)} ×{amount}"

    if reward_type == "badge":
        await add_promo_badge(user_id, reward_key)
        emoji, name = PROMO_BADGES[reward_key]
        return f"{emoji} бейдж «{esc(name)}»"

    column = PROMO_TYPE_COLUMN[reward_type]
    await db_exec(
        f"UPDATE users SET {column} = {column} + ? WHERE user_id = ?",
        (amount, user_id),
    )
    return f"{amount} {PROMO_TYPE_LABEL[reward_type]}"

async def remove_item(user_id: int, item_key: str, qty: int = 1) -> bool:
    row = await db_query_one("SELECT qty FROM inventory WHERE user_id = ? AND item_key = ?", (user_id, item_key))
    if not row or row[0] < qty:
        return False
    await db_exec("UPDATE inventory SET qty = ? WHERE user_id = ? AND item_key = ?", (row[0] - qty, user_id, item_key))
    return True

async def apply_farm_bonuses(user_id: int, active_items, inventory_map: dict, luck_boost: bool = False) -> dict:
    """Считает все монетные пассивки (Странная монета, Тёплая свеча, Монета боготворства) одним
    общим числом монет + бонус Эссенции Бога (монеты гарант, очки перерождения — шанс x2 при
    зелье удачи). Один UPDATE. Возвращает {'coins': N, 'rebirth': N, 'evo': 0 (не используется), 'is_god': bool}."""
    coin_bonus = 0
    if inventory_map.get("strange_coin", 0) > 0:
        coin_bonus += 5
    if inventory_map.get("warm_candle", 0) > 0:
        coin_bonus += 3
    if inventory_map.get("devotion_coin", 0) > 0:
        coin_bonus += 15
        if random.random() < 0.10:
            coin_bonus += 20

    rebirth_bonus = 0
    tier = get_active_unique_tier(active_items)
    is_god = tier in GOD_TIER_LIKE
    if is_god:
        max_coin = 70 if tier == "koshko_amulet" else 50
        coin_bonus += random.randint(1, max_coin)
        rebirth_chance = 0.60 if luck_boost else 0.30
        if random.random() < rebirth_chance:
            rebirth_bonus += random.randint(1, 3)

    if coin_bonus or rebirth_bonus:
        await db_exec(
            "UPDATE users SET coins = coins + ?, rebirth_points = rebirth_points + ? "
            "WHERE user_id = ?",
            (coin_bonus, rebirth_bonus, user_id),
        )
    return {"coins": coin_bonus, "rebirth": rebirth_bonus, "evo": 0, "is_god": is_god, "tier": tier}

async def apply_vase_proc(user_id: int, inventory_map: dict, luck_boost: bool = False) -> str:
    """Проки пассивных ваз при фарме ног. Срабатывает только самая сильная имеющаяся ваза.
    luck_boost (зелье удачи) удваивает эффективный ролл — вдвое повышает шанс на каждый порог."""
    roll_scale = 0.5 if luck_boost else 1.0
    if inventory_map.get("godly_vase", 0) > 0:
        roll = random.random() * roll_scale
        if roll < 0.002:
            await db_exec("UPDATE users SET rebirth_points = rebirth_points + 400 WHERE user_id = ?", (user_id,))
            return f"\n{PREMIUM_GODLY_VASE} Боготворная ваза: СУПЕР УДАЧА! +400🉑!"
        if roll < 0.022:
            await db_exec("UPDATE users SET rebirth_points = rebirth_points + 20 WHERE user_id = ?", (user_id,))
            return f"\n{PREMIUM_GODLY_VASE} Боготворная ваза: +20🉑!"
        if roll < 0.122:
            await db_exec("UPDATE users SET rebirth_points = rebirth_points + 10 WHERE user_id = ?", (user_id,))
            return f"\n{PREMIUM_GODLY_VASE} Боготворная ваза: +10🉑!"
        if roll < 0.322:
            await db_exec("UPDATE users SET rebirth_points = rebirth_points + 6 WHERE user_id = ?", (user_id,))
            return f"\n{PREMIUM_GODLY_VASE} Боготворная ваза: +6🉑!"
        if roll < 1.122:
            await db_exec("UPDATE users SET rebirth_points = rebirth_points + 2 WHERE user_id = ?", (user_id,))
            return f"\n{PREMIUM_GODLY_VASE} Боготворная ваза: +2🉑!"
        return ""
    if inventory_map.get("golden_vase", 0) > 0:
        if random.random() * roll_scale < 0.06:
            await db_exec("UPDATE users SET rebirth_points = rebirth_points + 1 WHERE user_id = ?", (user_id,))
            return f"\n{PREMIUM_GOLDEN_VASE} Золотая ваза: +1🉑!"
        return ""
    if inventory_map.get("old_vase", 0) > 0:
        if random.random() * roll_scale < 0.05:
            await db_exec("UPDATE users SET rebirth_points = rebirth_points + 1 WHERE user_id = ?", (user_id,))
            return f"\n{PREMIUM_OLD_VASE} Старая ваза: +1🉑!"
        return ""
    return ""

def _random_booster_pool() -> list:
    """Все выбиваемые/крафтовые бустеры (boost_percent > 0), кроме предметов 1+ уровня крафта
    (см. RECIPES) и кроме любого предмета из NON_TRADABLE_ITEMS — используется шансом на выдачу
    бустера от 🔮 Шара Хроноса.
    NON_TRADABLE_ITEMS уже помечает все эксклюзивные/уникальные амулеты, короны, кольца и
    эво-предметы (golda, karambit_gold, guitarist_crown, vilon_amulet, miku_ring, star_necklace
    и т.д.) — так что достаточно этой одной проверки, чтобы ни один из них никогда не выпал
    случайно через Хвост Джевила: получить их можно только крафтом или ручной выдачей админа."""
    pool = []
    for key, (_, _, boost_percent, _) in ITEMS.items():
        if boost_percent <= 0:
            continue
        if key in NON_TRADABLE_ITEMS:
            continue
        recipe = RECIPES.get(key)
        if recipe and recipe.get("level", 0) >= 1:
            continue
        pool.append(key)
    return pool

async def apply_chaos_orb_proc(user_id: int, active_items) -> str:
    """🌀 Шар хаоса: пока экипирован, шанс 2% при фарме ног поймать бонус-фарму
    (случайное количество очков ноги от 1 до 10 000 000)."""
    if "chaos_orb" not in set(_normalize_active_items(active_items)):
        return ""
    if random.random() >= CHAOS_ORB_FARM_CHANCE:
        return ""
    bonus = random.randint(CHAOS_ORB_FARM_MIN, CHAOS_ORB_FARM_MAX)
    await db_exec("UPDATE users SET score = score + ? WHERE user_id = ?", (bonus, user_id))
    return f"\n🌀 Шар хаоса: РЕДКИЙ ПРОК! +{bonus} очков ноги!"

async def apply_blazing_necklace_proc(user_id: int, active_items) -> str:
    """🔥📿 Ожерелье пылающей звезды: пока экипировано, при фарме ног — шанс 1.7% дать
    1-15 очков перерождения и независимый шанс 1.2% дать 1-3 очка престижа."""
    if "blazing_star_necklace" not in set(_normalize_active_items(active_items)):
        return ""
    text = ""
    if random.random() < BLAZING_NECKLACE_REBIRTH_CHANCE:
        gained = random.randint(*BLAZING_NECKLACE_REBIRTH_RANGE)
        await db_exec("UPDATE users SET rebirth_points = rebirth_points + ? WHERE user_id = ?", (gained, user_id))
        text += f"\n{ITEMS['blazing_star_necklace'][0]} Ожерелье пылающей звезды: +{gained}🉑!"
    if random.random() < BLAZING_NECKLACE_PRESTIGE_CHANCE:
        gained = random.randint(*BLAZING_NECKLACE_PRESTIGE_RANGE)
        await db_exec("UPDATE users SET prestige_points = prestige_points + ? WHERE user_id = ?", (gained, user_id))
        text += f"\n{ITEMS['blazing_star_necklace'][0]} Ожерелье пылающей звезды: +{gained} очков престижа!"
    return text

async def apply_mastery_lover_proc(user_id: int, active_items) -> tuple[str, float]:
    """🤖 Любитель Мастерства: пока экипирован, при каждом фарме ног независимо проверяются
    5 эффектов — несколько могут сработать за один фарм одновременно:
    0.5% -> временный бонус +0.1% к шансу дропа биткоина (см. apply_bitcoin_proc);
    1% -> +15 очков крафта; 2% -> +200 очков перерождения; 1.5% -> +50 очков престижа;
    3% -> +1 предмет nano-IT.
    Возвращает (текст-приписка, бонус_к_шансу_биткоина_на_этот_фарм)."""
    if "mastery_lover_amulet" not in set(_normalize_active_items(active_items)):
        return "", 0.0
    text = ""
    bitcoin_bonus = 0.0
    if random.random() < MASTERY_LOVER_BITCOIN_CHANCE_CHANCE:
        bitcoin_bonus = MASTERY_LOVER_BITCOIN_CHANCE_BONUS
        text += f"\n{PREMIUM_MASTERY_LOVER_AMULET} Любитель Мастерства: шанс дропа Биткоина повышен на этот фарм!"
    if random.random() < MASTERY_LOVER_CRAFT_CHANCE:
        await db_exec("UPDATE users SET craft_points = craft_points + ? WHERE user_id = ?",
                      (MASTERY_LOVER_CRAFT_AMOUNT, user_id))
        text += f"\n{PREMIUM_MASTERY_LOVER_AMULET} Любитель Мастерства: +{MASTERY_LOVER_CRAFT_AMOUNT}💠 очков крафта!"
    if random.random() < MASTERY_LOVER_REBIRTH_CHANCE:
        await db_exec("UPDATE users SET rebirth_points = rebirth_points + ? WHERE user_id = ?",
                      (MASTERY_LOVER_REBIRTH_AMOUNT, user_id))
        text += f"\n{PREMIUM_MASTERY_LOVER_AMULET} Любитель Мастерства: +{MASTERY_LOVER_REBIRTH_AMOUNT}🉑 очков перерождения!"
    if random.random() < MASTERY_LOVER_PRESTIGE_CHANCE:
        await db_exec("UPDATE users SET prestige_points = prestige_points + ? WHERE user_id = ?",
                      (MASTERY_LOVER_PRESTIGE_AMOUNT, user_id))
        text += f"\n{PREMIUM_MASTERY_LOVER_AMULET} Любитель Мастерства: +{MASTERY_LOVER_PRESTIGE_AMOUNT}🔮 очков престижа!"
    if random.random() < MASTERY_LOVER_NANO_IT_CHANCE:
        await add_item(user_id, "nano_it", 1)
        text += f"\n{PREMIUM_MASTERY_LOVER_AMULET} Любитель Мастерства: +1 {PREMIUM_NANO_IT} nano-IT!"
    return text, bitcoin_bonus

async def apply_star_necklace_proc(user_id: int, active_items) -> str:
    """📿 Ожерелье из звёзд: пока экипировано, при фарме ног — шанс 2.5% выдать
    случайный предмет из Базового кейса (кейс 1, крафт-уровень 1)."""
    if "star_necklace" not in set(_normalize_active_items(active_items)):
        return ""
    if random.random() >= STAR_NECKLACE_CASE1_DROP_CHANCE:
        return ""
    item_key = random.choice(CASES[1]["pool"])
    await add_item(user_id, item_key)
    emoji, name, _, _ = ITEMS[item_key]
    return f"\n{ITEMS['star_necklace'][0]} Ожерелье из звёзд: выпал {emoji} {name}!"

async def apply_leg_farm_steal(user_id: int, chat_id: int, active_items) -> str:
    """👑 Корона Гитариста: пока экипирована, шанс LEG_STEAL_CHANCE при фарме ног (🦵/🦿)
    украсть 1 случайный предмет из CASE_SELLABLE_ITEMS (только кейсы 1-2-3 — никогда
    крафтовые/уникальные/эво-предметы) у случайного другого игрока ЭТОГО ЖЕ чата.
    Если у жертвы нечего украсть — тихий промах."""
    if "guitarist_crown" not in set(_normalize_active_items(active_items)):
        return ""
    if random.random() >= LEG_STEAL_CHANCE:
        return ""

    candidates = await db_query(
        "SELECT user_id FROM chat_members WHERE chat_id = ? AND user_id != ?", (chat_id, user_id)
    )
    if not candidates:
        return ""

    victim_id = random.choice(candidates)[0]
    victim_inv = await get_inventory(victim_id)
    stealable = [k for k, q in victim_inv if k in CASE_SELLABLE_ITEMS and q > 0]
    if not stealable:
        return ""

    item_key = random.choice(stealable)
    removed = await remove_item(victim_id, item_key, 1)
    if not removed:
        return ""

    await add_item(user_id, item_key)

    victim_row = await get_user(victim_id)
    victim_name = "игрока" if victim_row is None else display_name(
        victim_row[1], victim_row[19] if len(victim_row) > 19 else None
    )
    emoji, name, _, _ = ITEMS[item_key]
    return f"\n🥷 Кража удалась! Стащено {emoji} {esc(name)} у {esc(victim_name)}!"

async def apply_vilon_amulet_trigger(user_id: int, active_items, vilon_streak: int) -> str:
    """🔱 Амулет Вилона: пока экипирован, каждый фарм ног (🦵/🦿) считается в персональный
    счётчик. На VILON_TRIGGER_EVERY-й раз счётчик сбрасывается и активируется x3 к добыче
    на VILON_BOOST_SECONDS секунд (см. apply_vilon_amulet_boost — сам множитель применяется
    отдельно, эта функция только считает и включает таймер)."""
    if "vilon_amulet" not in set(_normalize_active_items(active_items)):
        return ""

    new_streak = vilon_streak + 1
    if new_streak < VILON_TRIGGER_EVERY:
        await db_exec("UPDATE users SET vilon_streak = ? WHERE user_id = ?", (new_streak, user_id))
        return ""

    boost_until = int(time.time()) + VILON_BOOST_SECONDS
    await db_exec(
        "UPDATE users SET vilon_streak = 0, vilon_boost_until = ? WHERE user_id = ?",
        (boost_until, user_id),
    )
    return f"\n{ITEMS['vilon_amulet'][0]} Амулет Вилона: РЫВОК! x{VILON_BOOST_MULT} к добыче на {VILON_BOOST_SECONDS} сек!"

def apply_vilon_amulet_boost(total: int, vilon_boost_until: int) -> int:
    """Применяет активный x3 от Амулета Вилона к уже посчитанному total, если таймер ещё
    не истёк. Не требует экипировки в момент применения — буст, один раз запущенный,
    доигрывает своё время даже если амулет сняли (как и action-зелья)."""
    if vilon_boost_until and vilon_boost_until > int(time.time()):
        return round(total * VILON_BOOST_MULT)
    return total

async def apply_kotyara_amulet_trigger(user_id: int, active_items) -> str:
    """🐱 Амулет Котяры: пока экипирован, при каждом фарме ног — независимый шанс
    KOTYARA_BOOST_CHANCE (25%) включить x2 к добыче на KOTYARA_BOOST_SECONDS (10) секунд
    (см. apply_kotyara_amulet_boost — сам множитель применяется отдельно, эта функция
    только кидает шанс и включает таймер)."""
    if "kotyara_amulet" not in set(_normalize_active_items(active_items)):
        return ""
    if random.random() >= KOTYARA_BOOST_CHANCE:
        return ""
    boost_until = int(time.time()) + KOTYARA_BOOST_SECONDS
    await db_exec("UPDATE users SET kotyara_boost_until = ? WHERE user_id = ?", (boost_until, user_id))
    return f"\n{ITEMS['kotyara_amulet'][0]} Амулет Котяры: МУРЛЫК-РЫВОК! x{KOTYARA_BOOST_MULT} к добыче на {KOTYARA_BOOST_SECONDS} сек!"

def apply_kotyara_amulet_boost(total: int, kotyara_boost_until: int) -> int:
    """Применяет активный x2 от Амулета Котяры к уже посчитанному total, если таймер ещё
    не истёк. Не требует экипировки в момент применения — буст, один раз запущенный,
    доигрывает своё время даже если амулет сняли (как и Амулет Вилона)."""
    if kotyara_boost_until and kotyara_boost_until > int(time.time()):
        return round(total * KOTYARA_BOOST_MULT)
    return total

def apply_coin_tree_farm_roll(gained: int, active_items) -> tuple:
    """🟤 Монета Ногости / 🔶 Монета Бога Ногости: независимый ролл на КАЖДОМ базовом фарме
    ног (после всех обычных множителей, включая x3/x6 boost_percent самих этих монет —
    те уже учтены в get_multiplier()). Срабатывает только самая сильная экипированная монета
    из пары (Бог > обычная), как и остальные парные бустеры в игре.
    Возвращает (новое gained, текст для ответа)."""
    equipped = set(_normalize_active_items(active_items))
    if "godly_nogost_coin" in equipped:
        roll = random.random()
        if roll < 0.10:
            bonus_gained = gained * 5
            return bonus_gained, f"\n{PREMIUM_GODLY_NOGOST_COIN} Монета Бога Ногости: x5 к фарму! +{bonus_gained - gained} очков ноги!"
        if roll < 0.30:
            bonus_gained = gained * 3
            return bonus_gained, f"\n{PREMIUM_GODLY_NOGOST_COIN} Монета Бога Ногости: x3 к фарму! +{bonus_gained - gained} очков ноги!"
        return gained, ""
    if "nogost_coin" in equipped:
        roll = random.random()
        if roll < 0.05:
            bonus_gained = gained * 5
            return bonus_gained, f"\n{PREMIUM_NOGOST_COIN} Монета Ногости: x5 к фарму! +{bonus_gained - gained} очков ноги!"
        if roll < 0.25:
            bonus_gained = gained * 3
            return bonus_gained, f"\n{PREMIUM_NOGOST_COIN} Монета Ногости: x3 к фарму! +{bonus_gained - gained} очков ноги!"
        return gained, ""
    return gained, ""

async def apply_godly_nogost_coin_case_proc(user_id: int, inventory_map: dict) -> str:
    """🔶 Монета Бога Ногости: пассивно (даже не экипирована — работает лёжа в инвентаре, как
    и остальные пассивные монеты) шанс 0.7% при базовом фарме ног дать +100 очков престижа
    и +5 000 000 (5кк) очков ноги одним общим проком за фарм."""
    if inventory_map.get("godly_nogost_coin", 0) <= 0:
        return ""
    if random.random() >= 0.007:
        return ""
    await db_exec(
        "UPDATE users SET score = score + 5000000, prestige_points = prestige_points + 100 WHERE user_id = ?",
        (user_id,),
    )
    return f"\n{PREMIUM_GODLY_NOGOST_COIN} Монета Бога Ногости: УДАЧА! +100🔮 и +5 000 000 очков ноги!"

async def apply_craft_coin_proc(user_id: int, inventory_map: dict) -> str:
    """🔘 Монета Крафта: пассивно (лёжа в инвентаре) шанс 5% при отправке в чат сообщения
    с эмодзи ноги (🦵/🦿) дать +1 💠 очко крафта."""
    if inventory_map.get("craft_coin", 0) <= 0:
        return ""
    if random.random() >= 0.05:
        return ""
    await db_exec("UPDATE users SET craft_points = craft_points + 1 WHERE user_id = ?", (user_id,))
    return f"\n{PREMIUM_CRAFT_COIN} Монета Крафта: +1💠 очко крафта!"

async def apply_bitcoin_proc(user_id: int, inventory_map: dict, bonus_chance: float = 0.0) -> str:
    """🟠 Биткоин: пассивно (лёжа в инвентаре) шанс 0.05% при базовом фарме ног дать
    +15 000 000 (15кк) 🪙 монет. bonus_chance — временная прибавка к шансу (например,
    от проков 🤖 Любителя Мастерства) на этот конкретный фарм."""
    if inventory_map.get("bitcoin", 0) <= 0:
        return ""
    if random.random() >= 0.0005 + bonus_chance:
        return ""
    await db_exec("UPDATE users SET coins = coins + 15000000 WHERE user_id = ?", (user_id,))
    return f"\n{PREMIUM_BITCOIN} Биткоин: КРИПТО-ДЖЕКПОТ! +15 000 000{PREMIUM_BITCOIN}!"

async def apply_rebirth_coin_proc(user_id: int, inventory_map: dict) -> str:
    """🟣 Монета Перерождения: пассивно (лёжа в инвентаре) при КАЖДОМ базовом фарме ног
    даёт +2 🉑 очка перерождения гарантированно."""
    if inventory_map.get("rebirth_coin", 0) <= 0:
        return ""
    await db_exec("UPDATE users SET rebirth_points = rebirth_points + 2 WHERE user_id = ?", (user_id,))
    return f"\n{PREMIUM_REBIRTH_COIN} Монета Перерождения: +2🉑!"

async def apply_chronos_orb_procs(user_id: int, active_items) -> tuple:
    """🔮 Хвост Джевила: пока экипирован, при каждом фарме ног независимо проверяются все
    эффекты — несколько могут сработать за один фарм одновременно.
    Возвращает (текст_для_ответа, сбросить_кулдаун: bool, доп_множитель_фарма: float)."""
    if "chronos_orb" not in set(_normalize_active_items(active_items)):
        return "", False, 1.0

    lines = []
    reset_cd = False
    farm_extra_mult = random.uniform(CHRONOS_ORB_FARM_MULT_MIN, CHRONOS_ORB_FARM_MULT_MAX)
    lines.append(f"\n🔮 Хвост Джевила: рандом-множитель фарма x{farm_extra_mult:.2f}")

    if random.random() < CHRONOS_ORB_REBIRTH_CHANCE:
        amount = random.randint(CHRONOS_ORB_REBIRTH_MIN, CHRONOS_ORB_REBIRTH_MAX)
        await db_exec("UPDATE users SET rebirth_points = rebirth_points + ? WHERE user_id = ?", (amount, user_id))
        lines.append(f"🔮 Хвост Джевила: +{amount} 🉑!")

    if random.random() < CHRONOS_ORB_COIN_CHANCE:
        amount = random.randint(CHRONOS_ORB_COIN_MIN, CHRONOS_ORB_COIN_MAX)
        await db_exec("UPDATE users SET coins = coins + ? WHERE user_id = ?", (amount, user_id))
        lines.append(f"🔮 Хвост Джевила: +{amount} 🪙!")

    if random.random() < CHRONOS_ORB_LEGS_CHANCE:
        amount = random.randint(CHRONOS_ORB_LEGS_MIN, CHRONOS_ORB_LEGS_MAX)
        await db_exec("UPDATE users SET score = score + ? WHERE user_id = ?", (amount, user_id))
        lines.append(f"🔮 Хвост Джевила: +{amount} очков ноги!")

    if random.random() < CHRONOS_ORB_NO_CD_CHANCE:
        reset_cd = True
        lines.append("🔮 Хвост Джевила: кулдаун фермы обнулён!")

    if random.random() < CHRONOS_ORB_PRESTIGE_CHANCE:
        amount = random.randint(CHRONOS_ORB_PRESTIGE_MIN, CHRONOS_ORB_PRESTIGE_MAX)
        if amount > 0:
            await db_exec("UPDATE users SET prestige_points = prestige_points + ? WHERE user_id = ?", (amount, user_id))
            lines.append(f"🔮 Хвост Джевила: +{amount} 🔮 очков престижа!")

    if random.random() < CHRONOS_ORB_POTION_CHANCE:
        potion_key = random.choice(POTION_ORDER)
        stock_row = await db_query_one("SELECT potion_stock FROM users WHERE user_id = ?", (user_id,))
        stock = parse_potion_stock(stock_row[0] if stock_row else "")
        stock[potion_key] = stock.get(potion_key, 0) + 1
        await db_exec("UPDATE users SET potion_stock = ? WHERE user_id = ?", (format_potion_stock(stock), user_id))
        cfg = POTIONS[potion_key]
        lines.append(f"🔮 Хвост Джевила: +1 {cfg['emoji']} {esc(cfg['name'])}!")

    if random.random() < CHRONOS_ORB_BOOSTER_CHANCE:
        pool = _random_booster_pool()
        if pool:
            booster_key = random.choice(pool)
            await add_item(user_id, booster_key, 1)
            emoji, name, _, _ = ITEMS[booster_key]
            lines.append(f"🔮 Хвост Джевила: +1 {emoji} {esc(name)}!")

    if random.random() < CHRONOS_ORB_BADGE_CHANCE:
        await add_promo_badge(user_id, "chaos_master")
        emoji, name = PROMO_BADGES["chaos_master"]
        lines.append(f"🔮 Хвост Джевила: ПОЛУЧЕН БЕЙДЖ {emoji} «{esc(name)}»!!!")

    if random.random() < CHRONOS_ORB_STRANGE_COIN_CHANCE:
        await add_item(user_id, "strange_coin", 1)
        lines.append(f"🔮 Хвост Джевила: +1 {ITEMS['strange_coin'][0]} Странная монета!")

    if random.random() < CHRONOS_ORB_OLD_VASE_CHANCE:
        await add_item(user_id, "old_vase", 1)
        lines.append(f"🔮 Хвост Джевила: +1 {ITEMS['old_vase'][0]} Старая ваза!")

    return "\n".join(lines), reset_cd, farm_extra_mult

async def chronos_orb_boost_loop():
    """Фоновый таск: раз в CHRONOS_BOOST_INTERVAL (5 мин) пересчитывает рандомный % буста
    (10-400%) для ВСЕХ игроков сразу — не только для тех, у кого экипирован Хвост Джевила
    (дёшево одним UPDATE, а не по каждому фарму), см. get_multiplier(). Первый пересчёт —
    сразу при старте бота, чтобы буст не простаивал на 0%/100% до первого 5-минутного тика."""
    while True:
        try:
            new_pct = random.randint(CHRONOS_BOOST_MIN, CHRONOS_BOOST_MAX)
            await db_exec("UPDATE users SET chronos_boost_pct = ?", (new_pct,))
        except Exception as e:
            print(f"chronos_orb_boost_loop ошибка: {e}")
        await asyncio.sleep(CHRONOS_BOOST_INTERVAL)

AUTO_LOG_CLEANUP_INTERVAL = 24 * 60 * 60
AUTO_AUDIT_LOG_DAYS = 7
AUTO_PLAYER_LOG_DAYS = 2

async def auto_log_cleanup_loop():
    """Фоновый таск: раз в сутки сам чистит старые записи логов — те же сроки,
    что и дефолты ручных команд !чистлоги / !чистлоги игроки. player_action_log
    пишется на КАЖДУЮ команду каждого игрока (см. ThrottleMiddleware) и без
    регулярной чистки растёт быстрее всего, раздувая БД и, как следствие, время
    отклика на запросы к ней. Первый прогон — не сразу при старте (сон в начале
    цикла), чтобы не толкаться с init_db на старте бота."""
    while True:
        await asyncio.sleep(AUTO_LOG_CLEANUP_INTERVAL)
        try:
            audit_cutoff = int(time.time()) - AUTO_AUDIT_LOG_DAYS * 86400
            await db_exec("DELETE FROM audit_log WHERE ts < ?", (audit_cutoff,))
            player_cutoff = int(time.time()) - AUTO_PLAYER_LOG_DAYS * 86400
            await db_exec("DELETE FROM player_action_log WHERE ts < ?", (player_cutoff,))
        except Exception as e:
            print(f"auto_log_cleanup_loop ошибка: {e}")

async def is_event_active() -> bool:
    active, _ = await get_event_state()
    return active

_event_state_cache = {"value": None, "until": 0.0}
_EVENT_STATE_TTL = 3.0

async def get_event_state():
    """Возвращает (активен: bool, множитель: float) с учётом автоистечения по времени.
    Кэшируется на _EVENT_STATE_TTL секунд — см. _event_state_cache."""
    now_mono = time.monotonic()
    if _event_state_cache["value"] is not None and now_mono < _event_state_cache["until"]:
        return _event_state_cache["value"]

    rows = await db_query(
        "SELECT key, value FROM settings WHERE key IN ('event_active', 'event_multiplier', 'event_until')"
    )
    d = {k: v for k, v in rows}
    if d.get("event_active") != "1":
        result = (False, 1.0)
    else:
        until = int(d.get("event_until") or 0)
        if until and int(time.time()) > until:
            await db_exec("UPDATE settings SET value = '0' WHERE key = 'event_active'")
            result = (False, 1.0)
        else:
            mult = float(d.get("event_multiplier") or 2)
            result = (True, mult)

    _event_state_cache["value"] = result
    _event_state_cache["until"] = now_mono + _EVENT_STATE_TTL
    return result

def _invalidate_event_state_cache():
    _event_state_cache["value"] = None

async def get_event_multiplier() -> float:
    active, mult = await get_event_state()
    return mult if active else 1.0

async def get_personal_multiplier(user_id: int) -> float:
    """Личный временный буст фермы игроку (!мультипликатор ферма), с автоистечением."""
    row = await db_query_one("SELECT multiplier, until FROM personal_boosts WHERE user_id = ?", (user_id,))
    if not row:
        return 1.0
    multiplier, until = row
    if until and int(time.time()) > until:
        await db_exec("DELETE FROM personal_boosts WHERE user_id = ?", (user_id,))
        return 1.0
    return float(multiplier)

async def log_admin_action(message: Message):
    admin_username = message.from_user.username or str(message.from_user.id)
    await db_exec(
        "INSERT INTO audit_log (ts, admin_username, command) VALUES (?, ?, ?)",
        (int(time.time()), admin_username, message.text.strip()[:200]),
    )

PLAYER_LOG_MIN_INTERVAL = 1.0
_player_log_last = {}
_player_log_skipped = {}
_player_log_calls_since_cleanup = 0
_PLAYER_LOG_CLEANUP_EVERY = 500

PLAYER_LOG_FLUSH_INTERVAL = 5.0
_player_log_buffer: list = []

def _cleanup_player_log_throttle(now: float):
    ttl = PLAYER_LOG_MIN_INTERVAL * 20
    stale = [uid for uid, t in _player_log_last.items() if now - t > ttl]
    for uid in stale:
        del _player_log_last[uid]
        _player_log_skipped.pop(uid, None)

async def _log_player_action(user_id: int, username: str, text: str):
    global _player_log_calls_since_cleanup
    now = time.monotonic()
    last = _player_log_last.get(user_id, 0)
    if now - last < PLAYER_LOG_MIN_INTERVAL:
        _player_log_skipped[user_id] = _player_log_skipped.get(user_id, 0) + 1
        return
    skipped = _player_log_skipped.pop(user_id, 0)
    _player_log_last[user_id] = now

    _player_log_calls_since_cleanup += 1
    if _player_log_calls_since_cleanup >= _PLAYER_LOG_CLEANUP_EVERY:
        _player_log_calls_since_cleanup = 0
        _cleanup_player_log_throttle(now)

    command = text.strip()[:200]
    if skipped:
        command = f"{command} [+{skipped} пропущено за <{PLAYER_LOG_MIN_INTERVAL:.0f}с]"
    _player_log_buffer.append((int(time.time()), user_id, username, command))

async def _flush_player_log_buffer():
    """Фоновый цикл: раз в PLAYER_LOG_FLUSH_INTERVAL сек сбрасывает накопленные
    записи player_action_log ОДНИМ запросом (executemany на стороне воркера),
    вместо отдельного INSERT на каждое действие игрока."""
    while True:
        await asyncio.sleep(PLAYER_LOG_FLUSH_INTERVAL)
        if not _player_log_buffer:
            continue
        batch, _player_log_buffer[:] = _player_log_buffer[:], []
        try:
            await db_exec_many(
                "INSERT INTO player_action_log (ts, user_id, username, command) VALUES (?, ?, ?, ?)",
                batch,
            )
        except Exception as e:
            print(f"_flush_player_log_buffer ошибка: {e}")

async def track_membership(user_id: int, chat_id: int):
    await db_exec("INSERT OR IGNORE INTO chat_members (user_id, chat_id) VALUES (?, ?)", (user_id, chat_id))

async def get_all_chat_ids():
    rows = await db_query("SELECT DISTINCT chat_id FROM chat_members")
    return [r[0] for r in rows]

async def build_top(chat_id, order_column: str, limit: int = 10):
    if chat_id is None:
        rows = await db_query(
            f"SELECT username, score, evolution_level, coins, cases_opened, total_farmed, vip_until, shown_badges, rebirth_points, rebirth_count, nickname, ultra_rebirth, promo_badges, bonus_streak, prestige_points, crafts_done "
            f"FROM users WHERE (top_banned IS NULL OR top_banned = 0) ORDER BY {order_column} DESC LIMIT ?",
            (limit,),
        )
    else:
        rows = await db_query(
            f"""SELECT u.username, u.score, u.evolution_level, u.coins, u.cases_opened, u.total_farmed, u.vip_until, u.shown_badges, u.rebirth_points, u.rebirth_count, u.nickname, u.ultra_rebirth, u.promo_badges, u.bonus_streak, u.prestige_points, u.crafts_done
                FROM users u JOIN chat_members cm ON u.user_id = cm.user_id
                WHERE cm.chat_id = ? AND (u.top_banned IS NULL OR u.top_banned = 0) ORDER BY u.{order_column} DESC LIMIT ?""",
            (chat_id, limit),
        )
    return rows

def is_vip_active(vip_until: int) -> bool:
    return bool(vip_until) and vip_until > int(time.time())

def _percent_label(item_key: str, percent: int) -> str:
    """Подпись буста для кнопок/списков. chronos_orb — спец-случай: у него рандомный
    буст 10-400% (пересчитывается раз в 5 мин), фикс. число тут вводило бы в заблуждение."""
    if item_key == "chronos_orb":
        return "+10-400%, рандом"
    return f"+{percent}%"

def inventory_keyboard(inventory_rows, active_item: str, user_id: int) -> InlineKeyboardMarkup:
    rows = []
    for item_key, qty in inventory_rows:
        if item_key in PASSIVE_ITEMS:
            continue
        emoji, name, percent, _ = ITEMS[item_key]
        is_equipped = active_item == item_key
        mark = " ✅" if is_equipped else ""
        rows.append([InlineKeyboardButton(
            text=f"{name} {plain_emoji(emoji)} ({_percent_label(item_key, percent)}) x{qty}{mark}",
            callback_data=f"equip:{user_id}:{item_key}",
            style="success" if is_equipped else None,
        )])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def get_chat(event):
    if isinstance(event, Message):
        return event.chat
    if isinstance(event, CallbackQuery) and event.message:
        return event.message.chat
    return None

_leg_farm_last: dict = {}

class AliasNormalizeMiddleware(BaseMiddleware):
    """Переписывает message.text на канонический вид команды ДО того, как текст попадёт
    в остальные middleware/хендлеры (is_command_text, ThrottleMiddleware, сами @dp.message)."""
    async def __call__(self, handler, event, data):
        if isinstance(event, Message) and event.text:
            new_text = apply_command_aliases(event.text)
            if new_text != event.text:
                event = event.model_copy(update={"text": new_text})
        return await handler(event, data)

class PrivateBlockMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        chat = get_chat(event)
        if chat is not None and chat.type == "private":
            user = event.from_user
            if not (user and (user.username or "").lower() == ADMIN_USERNAME.lower()):
                if isinstance(event, CallbackQuery):
                    try:
                        await event.answer()
                    except Exception:
                        pass
                return
        return await handler(event, data)

class TrackMembershipMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        if isinstance(event, Message) and event.chat.type in ("group", "supergroup") and event.from_user:
            await track_membership(event.from_user.id, event.chat.id)
        return await handler(event, data)

class ThrottleMiddleware(BaseMiddleware):
    """Троттлинг для текстовых команд."""
    def __init__(self, rate: float = 1.5):
        self.rate = rate
        self.last_call = {}

    async def __call__(self, handler, event, data):
        user_id = event.from_user.id if event.from_user else None
        if user_id is None:
            return await handler(event, data)

        text = getattr(event, "text", None)
        if not text or not is_command_text(text):
            return await handler(event, data)

        username = event.from_user.username or str(user_id)
        asyncio.create_task(_log_player_action(user_id, username, text))

        now = time.monotonic()
        key = (user_id, "cmd")
        if now - self.last_call.get(key, 0) < self.rate:
            return
        self.last_call[key] = now
        return await handler(event, data)

class CallbackThrottleMiddleware(BaseMiddleware):
    """Троттлинг для инлайн-кнопок. Короткий кулдаун (350-500мс) и, что критично,
    ВСЕГДА отвечает на callback_query — иначе Telegram держит кнопку в состоянии
    "загрузка" до собственного таймаута, что выглядит как зависшая/незажимаемая кнопка.

    ВАЖНО: ключ (user_id, callback_data) почти всегда уникален (страница/предмет/id
    внутри callback_data), поэтому last_call растёт без ограничений и никогда не
    чистится сам — за часы работы с активной аудиторией это утечка памяти и
    постепенное замедление (в т.ч. ощущается как "кнопки тормозят"). Раз в
    CLEANUP_EVERY вызовов выбрасываем протухшие записи (старше rate * 20)."""
    CLEANUP_EVERY = 500

    def __init__(self, rate: float = 0.4):
        self.rate = rate
        self.last_call = {}
        self._calls_since_cleanup = 0

    def _cleanup(self, now: float):
        ttl = self.rate * 20
        stale = [k for k, t in self.last_call.items() if now - t > ttl]
        for k in stale:
            del self.last_call[k]

    async def __call__(self, handler, event: CallbackQuery, data):
        user_id = event.from_user.id if event.from_user else None
        if user_id is None:
            return await handler(event, data)

        now = time.monotonic()
        key = (user_id, event.data)
        if now - self.last_call.get(key, 0) < self.rate:
            try:
                await event.answer()
            except Exception:
                pass
            return
        self.last_call[key] = now

        self._calls_since_cleanup += 1
        if self._calls_since_cleanup >= self.CLEANUP_EVERY:
            self._calls_since_cleanup = 0
            self._cleanup(now)

        return await handler(event, data)

class StaleCallbackGuardMiddleware(BaseMiddleware):
    """Многие callback-хендлеры делают callback.data.split(":") и int(parts[N]) без
    защиты, полагаясь на то, что бот сам генерирует callback_data. Это верно почти
    всегда — но если формат callback_data когда-нибудь поменяется (новая версия
    бота), кнопки под СТАРЫМИ сообщениями (отправленными до обновления) начнут
    падать с ValueError/IndexError прямо на парсинге, ДО вызова callback.answer().
    Без этой страховки такая кнопка виснет с "часиками" до таймаута Telegram —
    тот же симптом, что чинили в safe_edit_text, только с другим триггером.
    Ловим узко (только ValueError/IndexError) — остальные ошибки идут в общий
    @dp.errors() как и раньше, тут ничего не маскируем сверх этого."""
    async def __call__(self, handler, event: CallbackQuery, data):
        try:
            return await handler(event, data)
        except (ValueError, IndexError):
            try:
                await event.answer("Кнопка устарела, обнови меню заново.", show_alert=True)
            except Exception:
                pass
            return

dp.callback_query.middleware(StaleCallbackGuardMiddleware())

dp.message.outer_middleware(AliasNormalizeMiddleware())
dp.message.middleware(TrackMembershipMiddleware())
dp.message.middleware(ThrottleMiddleware(0.6))
dp.callback_query.middleware(CallbackThrottleMiddleware(0.15))

_last_leg_reply = {}

@dp.errors()
async def error_handler(event: ErrorEvent):
    """ВАЖНО (баг, который ломал ВСЕ текстовые команды молча): в aiogram 3.x хендлер
    @dp.errors() получает ОДИН аргумент — объект ErrorEvent (с .update и .exception
    внутри), а не два отдельных позиционных (event, exception), как было раньше в
    aiogram 2.x. Со старой сигнатурой def error_handler(event, exception) aiogram на
    каждый вызов бросал TypeError ("missing 1 required positional argument") ВНУТРИ
    самого обработчика ошибок — а это значит, что при любом исключении в любом
    хендляре (farm/эволюция/перерождение/...) юзер не получал вообще ничего: ни
    результата команды, ни даже фолбэк-сообщения "попробуй ещё раз", потому что
    сам механизм отправки этого фолбэка падал ещё до отправки. Симптом ровно такой,
    какой был на скрине: команда молчит всегда, при любом отдельном вызове, без
    исключений в логах (потому что traceback.print_exc() тоже не успевал выполниться
    в старой версии — TypeError происходил на уровне вызова хендлера aiogram'ом).
    Теперь сигнатура правильная: exception достаём из event.exception."""
    exception = event.exception

    if isinstance(exception, TelegramRetryAfter):
        await asyncio.sleep(exception.retry_after)
        return True

    import traceback
    traceback.print_exc()
    print(f"Необработанная ошибка: {exception!r}")

    try:
        message = getattr(event.update, "message", None)
        if message is not None:
            await message.reply("⚠️ Что-то пошло не так при обработке команды, попробуй ещё раз.")
    except Exception:
        pass

    return True

async def maybe_announce_levelup(message: Message, username: str, old_score: int, new_score: int,
                                  evolution_level: int, notify: bool, rebirth_count: int = 0,
                                  ultra_rebirth: bool = False):
    if not notify:
        return
    old_level = get_level_index(old_score, evolution_level, rebirth_count, ultra_rebirth)
    new_level = get_level_index(new_score, evolution_level, rebirth_count, ultra_rebirth)
    if new_level <= old_level:
        return
    emoji, name, show_level = get_level_visual(new_level)
    lvl_part = f" ({new_level} лвл)" if show_level else ""
    name_part = f" {esc(name)}" if name else ""
    await message.reply(TEXTS["maybe_announce_levelup_1"].format(v0=esc(username), v1=emoji, v2=name_part, v3=lvl_part))

@dp.message(F.text.lower() == "смс выкл")
async def notify_off(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"
    await ensure_user(user_id, username)
    await db_exec("UPDATE users SET levelup_notify = 0 WHERE user_id = ?", (user_id,))
    await message.reply(TEXTS["notify_off_1"])

@dp.message(F.text.lower() == "смс вкл")
async def notify_on(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"
    await ensure_user(user_id, username)
    await db_exec("UPDATE users SET levelup_notify = 1 WHERE user_id = ?", (user_id,))
    await message.reply(TEXTS["notify_on_1"])

@dp.message(F.text.lower() == "кратко выкл")
async def compact_mode_off(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"
    await ensure_user(user_id, username)
    await db_exec("UPDATE users SET compact_mode = 0 WHERE user_id = ?", (user_id,))
    await message.reply(TEXTS["compact_off_1"])

@dp.message(F.text.lower() == "кратко вкл")
async def compact_mode_on(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"
    await ensure_user(user_id, username)
    await db_exec("UPDATE users SET compact_mode = 1 WHERE user_id = ?", (user_id,))
    await message.reply(TEXTS["compact_on_1"])

@dp.message(F.text.regexp(r"(?i)^\+ник\s+.+$"))
async def set_nickname(message: Message):
    match = NICK_SET_RE.match(message.text.strip())
    if not match:
        await message.reply(TEXTS["nick_set_empty"])
        return

    nickname = match.group(1).strip().strip('"').strip("'").strip()
    if not nickname:
        await message.reply(TEXTS["nick_set_empty"])
        return
    if len(nickname) > 50:
        await message.reply(TEXTS["nick_set_too_long"].format(v0=len(nickname)))
        return

    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"
    await ensure_user(user_id, username)

    taken = await db_query_one(
        "SELECT user_id FROM users WHERE lower(nickname) = lower(?) AND user_id != ?",
        (nickname, user_id),
    )
    if taken:
        await message.reply(TEXTS["nick_set_taken"])
        return

    await db_exec("UPDATE users SET nickname = ? WHERE user_id = ?", (nickname, user_id))
    await safe_reply(message, TEXTS["nick_set_ok"].format(v0=esc(nickname)))

@dp.message(F.text.lower() == "-ник")
async def clear_nickname(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"
    await ensure_user(user_id, username)
    await db_exec("UPDATE users SET nickname = NULL WHERE user_id = ?", (user_id,))
    await message.reply(TEXTS["nick_clear_ok"])

def buy_vip_keyboard(user_id: int) -> InlineKeyboardMarkup:
    contact_text = quote("Привет! Хочу оформить VIP-статус")
    contact_url = f"https://t.me/{ADMIN_USERNAME}?text={contact_text}"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✉️ Написать админу", url=contact_url)],
    ])

@dp.message(F.text.lower() == "вип")
async def vip_info_command(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"
    row = await ensure_user(user_id, username)
    vip_until = row[12]

    if is_vip_active(vip_until):
        await message.reply(TEXTS["vip_info_command_1"])
        return

    await message.reply(
        TEXTS["vip_info_command_2"].format(v0=round(VIP_BOOST * 100), v1=VIP_STARS_PRICE),
        reply_markup=buy_vip_keyboard(user_id),
    )

@dp.message(F.text.lower().in_({"авто эво вкл", "авто эволюция вкл"}))
async def auto_evolve_on(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"
    row = await ensure_user(user_id, username)
    vip_until = row[12]

    if not is_vip_active(vip_until):
        await message.reply(TEXTS["auto_evolve_not_vip_1"])
        return

    await db_exec("UPDATE users SET auto_evolve = 1 WHERE user_id = ?", (user_id,))
    await message.reply(TEXTS["auto_evolve_on_1"])

@dp.message(F.text.lower().in_({"авто эво выкл", "авто эволюция выкл"}))
async def auto_evolve_off(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"
    await ensure_user(user_id, username)

    await db_exec("UPDATE users SET auto_evolve = 0 WHERE user_id = ?", (user_id,))
    await message.reply(TEXTS["auto_evolve_off_1"])

@dp.message(F.text.lower().in_({"авто перерождение вкл", "авто рб вкл", "авто ребёрт вкл", "авто реберт вкл"}))
async def auto_rebirth_on(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"
    row = await ensure_user(user_id, username)
    vip_until = row[12]

    if not is_vip_active(vip_until):
        await message.reply(TEXTS["auto_rebirth_not_vip_1"])
        return

    await db_exec("UPDATE users SET auto_rebirth = 1 WHERE user_id = ?", (user_id,))
    await message.reply(TEXTS["auto_rebirth_on_1"].format(v0=REBIRTH_MIN_EVO))

@dp.message(F.text.lower().in_({"авто перерождение выкл", "авто рб выкл", "авто ребёрт выкл", "авто реберт выкл"}))
async def auto_rebirth_off(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"
    await ensure_user(user_id, username)

    await db_exec("UPDATE users SET auto_rebirth = 0 WHERE user_id = ?", (user_id,))
    await message.reply(TEXTS["auto_rebirth_off_1"])

@dp.message(F.text.lower() == "пинг")
async def vip_ping(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"
    row = await ensure_user(user_id, username)
    vip_until = row[12]

    if not is_vip_active(vip_until):
        await message.reply(TEXTS["ping_not_vip_1"])
        return

    start = time.monotonic()
    sent = await message.reply("🏓 Понг...")
    delay_ms = round((time.monotonic() - start) * 1000)
    await sent.edit_text(f"🏓 Понг! Задержка: {delay_ms} мс")

@dp.message(F.text.lower() == "авто продажа вкл")
async def auto_sell_on(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"
    await ensure_user(user_id, username)

    await db_exec("UPDATE users SET auto_sell = 1 WHERE user_id = ?", (user_id,))
    await message.reply(TEXTS["auto_sell_on_1"])

@dp.message(F.text.lower() == "авто продажа выкл")
async def auto_sell_off(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"
    await ensure_user(user_id, username)

    await db_exec("UPDATE users SET auto_sell = 0 WHERE user_id = ?", (user_id,))
    await message.reply(TEXTS["auto_sell_off_1"])

@dp.message(F.text.lower().in_({"авто продажа настройка", "авто продажа конфиг", "авто продажа настройки"}))
async def auto_sell_config(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"
    row = await ensure_user(user_id, username)
    auto_sell_enabled = bool(row[30])
    auto_sell_items = parse_auto_sell_items(row[31])
    await message.reply(
        format_autosell_text(auto_sell_enabled, auto_sell_items),
        reply_markup=autosell_keyboard(auto_sell_enabled, auto_sell_items, user_id),
    )

@dp.callback_query(F.data.startswith("autosell_toggle:"))
async def autosell_toggle(callback: CallbackQuery):
    parts = callback.data.split(":")
    owner_id = int(parts[1])
    item_key = parts[2]
    page = int(parts[3]) if len(parts) > 3 else 0
    if callback.from_user.id != owner_id:
        await callback.answer(TEXTS["inventory_open_category_1"], show_alert=True)
        return
    if item_key not in CASE_SELLABLE_ITEMS:
        await callback.answer()
        return
    await callback.answer()

    row = await get_user(owner_id)
    auto_sell_enabled = bool(row[30])
    auto_sell_items = parse_auto_sell_items(row[31])

    if item_key in auto_sell_items:
        auto_sell_items.discard(item_key)
    else:
        auto_sell_items.add(item_key)

    await db_exec("UPDATE users SET auto_sell_items = ? WHERE user_id = ?", (format_auto_sell_items(auto_sell_items), owner_id))
    await safe_edit_text(callback, 
        format_autosell_text(auto_sell_enabled, auto_sell_items, page),
        reply_markup=autosell_keyboard(auto_sell_enabled, auto_sell_items, owner_id, page),
    )

@dp.callback_query(F.data.startswith("autosell_switch:"))
async def autosell_switch(callback: CallbackQuery):
    parts = callback.data.split(":")
    owner_id = int(parts[1])
    page = int(parts[2]) if len(parts) > 2 else 0
    if callback.from_user.id != owner_id:
        await callback.answer(TEXTS["inventory_open_category_1"], show_alert=True)
        return

    row = await get_user(owner_id)
    auto_sell_enabled = not bool(row[30])
    auto_sell_items = parse_auto_sell_items(row[31])
    await callback.answer(TEXTS["auto_sell_on_1"] if auto_sell_enabled else TEXTS["auto_sell_off_1"])

    await db_exec("UPDATE users SET auto_sell = ? WHERE user_id = ?", (1 if auto_sell_enabled else 0, owner_id))
    await safe_edit_text(callback, 
        format_autosell_text(auto_sell_enabled, auto_sell_items, page),
        reply_markup=autosell_keyboard(auto_sell_enabled, auto_sell_items, owner_id, page),
    )

@dp.callback_query(F.data.startswith("autosell_page:"))
async def autosell_page_nav(callback: CallbackQuery):
    _, owner_str, page_str = callback.data.split(":")
    owner_id = int(owner_str)
    page = int(page_str)
    if callback.from_user.id != owner_id:
        await callback.answer(TEXTS["inventory_open_category_1"], show_alert=True)
        return
    await callback.answer()

    row = await get_user(owner_id)
    auto_sell_enabled = bool(row[30])
    auto_sell_items = parse_auto_sell_items(row[31])
    await safe_edit_text(callback, 
        format_autosell_text(auto_sell_enabled, auto_sell_items, page),
        reply_markup=autosell_keyboard(auto_sell_enabled, auto_sell_items, owner_id, page),
    )

VIP_CASE_OPEN_RE = re.compile(r"^вип открыть кейс\s+(\d+)\s+(\d+)$", re.IGNORECASE)
VIP_CASE_OPEN_LIMIT = 20

@dp.message(F.text.regexp(r"(?i)^вип открыть кейс\s+"))
async def vip_open_case_bulk(message: Message):
    """VIP-версия owner-команды '!дать кейс' — открывает несколько кейсов разом,
    но платно (списывает монеты за каждый кейс) и только себе, лимит 20 за раз."""
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"

    match = VIP_CASE_OPEN_RE.match(message.text.strip())
    if not match:
        await message.reply(TEXTS["vip_case_open_1"])
        return

    row = await ensure_user(user_id, username)
    vip_until = row[12]
    if not is_vip_active(vip_until):
        await message.reply(TEXTS["vip_case_open_2"])
        return

    case_num = int(match.group(1))
    count = int(match.group(2))
    case = CASES.get(case_num)
    if not case:
        await message.reply(TEXTS["vip_case_open_3"])
        return
    if count < 1 or count > VIP_CASE_OPEN_LIMIT:
        await message.reply(TEXTS["vip_case_open_4"])
        return

    coins = row[5]
    upgrades = parse_upgrades(row[16])
    auto_sell_enabled = bool(row[30])
    auto_sell_items = parse_auto_sell_items(row[31])
    unit_price = case_price_with_discount(case["price"], upgrades)
    total_price = unit_price * count

    if coins < total_price:
        await message.reply(TEXTS["vip_case_open_5"].format(v0=total_price, v1=coins))
        return

    won = {}
    sold = {}
    sold_coins_total = 0
    for _ in range(count):
        item_key = roll_case_item(case_num)
        coins_got, _ = await apply_case_reward(user_id, item_key, upgrades, auto_sell_enabled, auto_sell_items)
        if coins_got:
            sold[item_key] = sold.get(item_key, 0) + 1
            sold_coins_total += coins_got
        else:
            won[item_key] = won.get(item_key, 0) + 1

    new_coins = coins - total_price + sold_coins_total
    await db_exec(
        "UPDATE users SET coins = coins - ?, cases_opened = cases_opened + ? WHERE user_id = ?",
        (total_price, count, user_id),
    )

    loot_lines = "\n".join(f"● {ITEMS[k][0]} {esc(ITEMS[k][1])} × {qty}" for k, qty in won.items())
    if sold:
        sold_lines = ", ".join(f"{ITEMS[k][0]} {esc(ITEMS[k][1])} × {qty}" for k, qty in sold.items())
        loot_lines += f"\n💰 Авто-продано: {sold_lines} (+{sold_coins_total} 🪙)"
    await safe_reply(
        message,
        TEXTS["vip_case_open_6"].format(v0=count, v1=esc(case["name"]), v2=total_price, v3=new_coins, v4=loot_lines),
    )

@dp.callback_query(F.data.startswith("buy_vip:"))
async def buy_vip_invoice(callback: CallbackQuery):
    owner_id = int(callback.data.split(":")[1])
    if callback.from_user.id != owner_id:
        await callback.answer(TEXTS["buy_vip_invoice_1"], show_alert=True)
        return

    await bot.send_invoice(
        chat_id=callback.message.chat.id,
        title="VIP статус навсегда",
        description=f"Постоянный буст +{round(VIP_BOOST * 100)}% к добыче ноги.",
        payload=f"vip:{owner_id}",
        currency="XTR",
        prices=[LabeledPrice(label="VIP навсегда", amount=VIP_STARS_PRICE)],
        provider_token="",
    )
    await callback.answer()

@dp.pre_checkout_query()
async def process_pre_checkout(pre_checkout_query: PreCheckoutQuery):
    payload = pre_checkout_query.invoice_payload or ""
    if payload.startswith("vip:"):
        await pre_checkout_query.answer(ok=True)
    else:
        await pre_checkout_query.answer(ok=False, error_message="Неизвестный товар.")

@dp.message(F.successful_payment)
async def process_successful_payment(message: Message):
    payload = message.successful_payment.invoice_payload or ""
    if not payload.startswith("vip:"):
        return
    target_id = int(payload.split(":")[1])
    username = message.from_user.username or message.from_user.first_name or "Без имени"
    row = await ensure_user(target_id, username)

    was_vip_before = is_vip_active(row[12])
    new_vip_until = int(time.time()) + VIP_FOREVER_SECONDS
    await db_exec("UPDATE users SET vip_until = ? WHERE user_id = ?", (new_vip_until, target_id))
    if not was_vip_before:
        await add_item(target_id, "vip_charm")

    await message.reply(TEXTS["process_successful_payment_1"])

@dp.message(F.text.lower() == "бейджи")
async def badges_menu(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"
    row = await ensure_user(user_id, username)
    evolution_level, cases_opened, total_farmed, vip_until = row[3], row[7], row[8], row[12]
    coins = row[5]
    shown = parse_shown(row[39] if len(row) > 39 else "")
    promo_badges = parse_promo_badges(row[33] if len(row) > 33 else "")
    rebirth_points = row[14] if len(row) > 14 else 0
    ultra_rebirth = bool(row[21]) if len(row) > 21 else False
    bonus_streak = row[10] if len(row) > 10 else 0
    prestige_points = row[27] if len(row) > 27 else 0
    crafts_done = row[36] if len(row) > 36 else 0
    vip_active = is_vip_active(vip_until)

    earned = badge_list(username, evolution_level, cases_opened, total_farmed, vip_active, promo_badges,
                         coins, rebirth_points, ultra_rebirth, bonus_streak, crafts_done, prestige_points)
    if not earned:
        await message.reply(TEXTS["badges_menu_1"])
        return

    kb = badges_keyboard(earned, shown, user_id, page=0)
    await message.reply(TEXTS["badges_menu_2"], reply_markup=kb)

@dp.callback_query(F.data == "badge_noop")
async def badge_noop(callback: CallbackQuery):
    await callback.answer()

@dp.callback_query(F.data.startswith("badge_page:"))
async def badge_change_page(callback: CallbackQuery):
    _, owner_str, page_str = callback.data.split(":")
    owner_id = int(owner_str)
    page = int(page_str)
    if callback.from_user.id != owner_id:
        await callback.answer(TEXTS["toggle_badge_1"], show_alert=True)
        return
    await callback.answer()

    row = await get_user(owner_id)
    username, evolution_level, cases_opened, total_farmed, vip_until = row[1], row[3], row[7], row[8], row[12]
    coins = row[5]
    shown = parse_shown(row[39] if len(row) > 39 else "")
    promo_badges = parse_promo_badges(row[33] if len(row) > 33 else "")
    rebirth_points = row[14] if len(row) > 14 else 0
    ultra_rebirth = bool(row[21]) if len(row) > 21 else False
    bonus_streak = row[10] if len(row) > 10 else 0
    prestige_points = row[27] if len(row) > 27 else 0
    crafts_done = row[36] if len(row) > 36 else 0
    vip_active = is_vip_active(vip_until)

    earned = badge_list(username, evolution_level, cases_opened, total_farmed, vip_active, promo_badges,
                         coins, rebirth_points, ultra_rebirth, bonus_streak, crafts_done, prestige_points)
    kb = badges_keyboard(earned, shown, owner_id, page=page)
    await safe_edit_text(callback, TEXTS["badges_menu_2"], reply_markup=kb)

@dp.callback_query(F.data.startswith("badge:"))
async def toggle_badge(callback: CallbackQuery):
    _, owner_str, page_str, key = callback.data.split(":")
    owner_id = int(owner_str)
    page = int(page_str)
    if callback.from_user.id != owner_id:
        await callback.answer(TEXTS["toggle_badge_1"], show_alert=True)
        return

    row = await get_user(owner_id)
    username, evolution_level, cases_opened, total_farmed, vip_until = row[1], row[3], row[7], row[8], row[12]
    coins = row[5]
    shown = parse_shown(row[39] if len(row) > 39 else "")
    promo_badges = parse_promo_badges(row[33] if len(row) > 33 else "")
    rebirth_points = row[14] if len(row) > 14 else 0
    ultra_rebirth = bool(row[21]) if len(row) > 21 else False
    bonus_streak = row[10] if len(row) > 10 else 0
    prestige_points = row[27] if len(row) > 27 else 0
    crafts_done = row[36] if len(row) > 36 else 0

    if key in shown:
        shown.discard(key)
        await callback.answer(TEXTS["toggle_badge_2"])
    elif len(shown) >= BADGES_DISPLAY_LIMIT:
        await callback.answer(TEXTS["toggle_badge_3"], show_alert=True)
        return
    else:
        shown.add(key)
        await callback.answer(TEXTS["toggle_badge_2"])

    new_shown_str = ",".join(sorted(shown))
    await db_exec("UPDATE users SET shown_badges = ? WHERE user_id = ?", (new_shown_str, owner_id))

    vip_active = is_vip_active(vip_until)
    earned = badge_list(username, evolution_level, cases_opened, total_farmed, vip_active, promo_badges,
                         coins, rebirth_points, ultra_rebirth, bonus_streak, crafts_done, prestige_points)
    kb = badges_keyboard(earned, shown, owner_id, page=page)
    await safe_edit_text(callback, TEXTS["badges_menu_2"], reply_markup=kb)

@dp.message(F.text.regexp(r"[🦵🦿]"))
async def count_legs(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"
    text = message.text

    if user_id != ADMIN_USER_ID:
        now_mono = time.monotonic()
        last = _leg_farm_last.get(user_id, 0)
        if now_mono - last < LEG_FARM_COOLDOWN:
            return
        _leg_farm_last[user_id] = now_mono

    row = await ensure_user(user_id, username)
    score, evolution_level, active_item = row[2], row[3], row[6]
    levelup_notify, vip_until = row[11], row[12]
    rebirth_points, rebirth_count = row[14], row[15]
    upgrades = parse_upgrades(row[16])
    active_items = parse_equipped(row[18])
    ultra_rebirth = bool(row[21])
    auto_evolve_enabled = bool(row[22])
    auto_rebirth_enabled = bool(row[29])
    prestige_points = row[27]
    vip_active = is_vip_active(vip_until)
    potions = active_potions_now(row[23], active_items=active_items)
    prestige_upgrades = parse_prestige_upgrades(row[28])
    chronos_boost_pct = row[34] if len(row) > 34 else 100
    compact_mode = bool(row[35]) if len(row) > 35 else False
    vilon_streak = row[37] if len(row) > 37 else 0
    vilon_boost_until = row[38] if len(row) > 38 else 0
    kotyara_boost_until = row[40] if len(row) > 40 else 0
    flat_bonus = total_flat_bonus(active_items)
    limits = active_farm_limits(active_items, prestige_upgrades)

    legs = min(text.count("🦵"), limits["leg_limit"])
    gained = legs * LEG_POINT

    mek = 0
    if evolution_level >= 1:
        mek = min(text.count("🦿"), limits["mek_limit"])
        gained += mek * MEK_POINT

    evo_leg_counts = []
    for emoji, tier in EVO_LEG_TIERS.items():
        if evolution_level < tier["level"]:
            continue
        count = min(text.count(emoji), tier["limit"])
        if count:
            gained += count * round(MEK_POINT * (1 + tier["bonus_pct"] / 100))
            evo_leg_counts.append((emoji, count))

    paw = min(text.count("🐾"), limits["paw_limit"])
    gained += paw * MEK_POINT * PAW_POINT_MULTIPLIER

    galaxy = min(text.count("🌌"), limits["galaxy_limit"])
    star = min(text.count("⭐️"), limits["star_limit"])
    miku_note = 0
    if "miku_ring" in set(_normalize_active_items(active_items)):
        miku_note = min(text.count("🎶"), MIKU_RING_SYMBOL_LIMIT)

    if gained == 0:
        return

    gained += flat_bonus
    gained = round(gained * farm_yield_multiplier(upgrades))

    event_mult, personal_mult, inv = await asyncio.gather(
        get_event_multiplier(), get_personal_multiplier(user_id), get_inventory(user_id)
    )
    inventory_map = {k: q for k, q in inv}
    nano_it_count = inventory_map.get("nano_it", 0)
    mult = get_multiplier(evolution_level, active_items, vip_active, upgrades, ultra_rebirth, chronos_boost_pct, nano_it_count)
    p_yield_mult = 1 + 0.005 * prestige_bonus(prestige_upgrades, "p_farm_yield")
    total = round(gained * mult * event_mult * personal_mult * p_yield_mult)
    if galaxy:
        total = round(total * (1 + 0.20 * galaxy))
    if star:
        total = round(total * (2 ** star))
    if miku_note:
        total = round(total * MIKU_RING_FARM_MULT)
    if inventory_map.get("pocket_star", 0) > 0:
        total = round(total * POCKET_STAR_LEG_FARM_MULT)
    total = apply_vilon_amulet_boost(total, vilon_boost_until)
    total = apply_kotyara_amulet_boost(total, kotyara_boost_until)
    potion_text = ""
    if "potion_speed" in potions:
        speed_mult = DRAGON_CLAW_POTION_MULT if "dragon_claw" in set(_normalize_active_items(active_items)) else 2
        total *= speed_mult
        potion_text += f"\n🧪⚡ Зелье ускорения: x{speed_mult} к добыче!"

    chronos_text, _chronos_reset_cd, chronos_farm_mult = await apply_chronos_orb_procs(user_id, active_items)
    if chronos_farm_mult != 1.0:
        total = round(total * chronos_farm_mult)
    new_score = score + total

    await db_exec(
        "UPDATE users SET score = ?, total_farmed = total_farmed + ? WHERE user_id = ?",
        (new_score, total, user_id),
    )

    await maybe_announce_levelup(message, username, score, new_score, evolution_level, bool(levelup_notify), rebirth_count, ultra_rebirth)

    auto_evo_text = ""
    if vip_active and auto_evolve_enabled:
        evolution_level, new_score, auto_evo_text = await try_auto_evolve(user_id, new_score, evolution_level, rebirth_count, active_items)

    auto_rebirth_text = ""
    if vip_active and auto_rebirth_enabled:
        new_score, evolution_level, rebirth_count, rebirth_points, prestige_points, auto_rebirth_text = await try_auto_rebirth(
            user_id, new_score, evolution_level, rebirth_count, rebirth_points, prestige_points, prestige_upgrades, active_items
        )

    inventory_map = {k: q for k, q in inv}
    luck_boost = "luck_x2" in potions
    vase_text = await apply_vase_proc(user_id, inventory_map, luck_boost)
    bonus = await apply_farm_bonuses(user_id, active_items, inventory_map, luck_boost)
    chaos_text = await apply_chaos_orb_proc(user_id, active_items)
    necklace_text = (
        await apply_blazing_necklace_proc(user_id, active_items)
        + await apply_star_necklace_proc(user_id, active_items)
    )
    mastery_text, mastery_bitcoin_bonus = await apply_mastery_lover_proc(user_id, active_items)
    coin_tree_text = (
        await apply_godly_nogost_coin_case_proc(user_id, inventory_map)
        + await apply_bitcoin_proc(user_id, inventory_map, mastery_bitcoin_bonus)
        + await apply_rebirth_coin_proc(user_id, inventory_map)
        + await apply_craft_coin_proc(user_id, inventory_map)
    )
    steal_text = await apply_leg_farm_steal(user_id, message.chat.id, active_items)
    vilon_text = await apply_vilon_amulet_trigger(user_id, active_items, vilon_streak)
    kotyara_text = await apply_kotyara_amulet_trigger(user_id, active_items)

    now = time.monotonic()
    chat_id = message.chat.id
    if now - _last_leg_reply.get(chat_id, 0) < LEG_REPLY_COOLDOWN:
        return
    _last_leg_reply[chat_id] = now

    equipped_set = set(_normalize_active_items(active_items))

    tide_text = ""
    if "tide_wave" in equipped_set and random.random() < TIDE_WAVE_PROC_CHANCE:
        tide_item = roll_case_item(random.choice([1, 2]))
        await add_item(user_id, tide_item)
        tide_emoji, tide_name, _, _ = ITEMS[tide_item]
        tide_text = f"\n🌊 Прилив принёс: {tide_emoji} {esc(tide_name)}!"

    skull_prefix = "💀 Смерть близко.\n" if "warrior_skull" in equipped_set else ""

    parts = f"+{legs}🦵"
    if mek:
        parts += f" +{mek}🦿"
    for emoji, count in evo_leg_counts:
        parts += f" +{count}{emoji}"
    if paw:
        parts += f" +{paw}🐾"
    if galaxy:
        parts += f" +{galaxy}🌌"
    if star:
        parts += f" +{star}⭐️"

    miku_text = f"\n{ITEMS['miku_ring'][0]} Кольцо Мику: 🎶 x{MIKU_RING_FARM_MULT} к итогу!" if miku_note else ""

    coin_text = f" +{bonus['coins']}🪙" if bonus["coins"] else ""
    bonus_text = "" if compact_mode else (vase_text + potion_text + tide_text + chaos_text + chronos_text + coin_tree_text + necklace_text + mastery_text)
    extra_text = bonus_text + auto_evo_text + auto_rebirth_text + steal_text + vilon_text + kotyara_text + miku_text
    chronos_equipped = "chronos_orb" in set(_normalize_active_items(active_items))

    if bonus["is_god"]:
        flavor = CHRONOS_ORB_FLAVOR if chronos_equipped else (KOSHKO_AMULET_FLAVOR if bonus.get("tier") == "koshko_amulet" else GOD_ESSENCE_FLAVOR)
        god_extra = f" +{bonus['rebirth']}🉑" if bonus["rebirth"] else ""
        await safe_reply(
            message,
            skull_prefix + TEXTS["count_legs_1"].format(v0=flavor, v1=parts, v2=total, v3=coin_text, v4=god_extra, v5=new_score, v6=extra_text)
        )
        return

    if chronos_equipped:
        await safe_reply(
            message,
            skull_prefix + TEXTS["count_legs_1"].format(v0=CHRONOS_ORB_FLAVOR, v1=parts, v2=total, v3=coin_text, v4="", v5=new_score, v6=extra_text)
        )
        return

    await message.reply(
        skull_prefix + TEXTS["count_legs_2"].format(v0=parts, v1=total, v2=coin_text, v3=new_score, v4=extra_text)
    )

@dp.message(F.text.lower() == "моя нога")
async def my_profile(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"

    row = await ensure_user(user_id, username)
    score, evolution_level, coins, active_item = row[2], row[3], row[5], row[6]
    vip_until = row[12]
    rebirth_points, rebirth_count = row[14], row[15]
    upgrades = parse_upgrades(row[16])
    active_items = parse_equipped(row[18])
    nickname = row[19] if len(row) > 19 else None
    ultra_rebirth = bool(row[21])
    vip_active = is_vip_active(vip_until)
    shown_name = display_name(username, nickname)

    level = get_level_index(score, evolution_level, rebirth_count, ultra_rebirth)
    emoji, name, show_level = get_level_visual(level)
    display_level = level
    nxt = next_level_text(score, evolution_level, rebirth_count, ultra_rebirth)
    chronos_boost_pct = row[34] if len(row) > 34 else 100
    inv_rows_profile = await get_inventory(user_id)
    nano_it_count = {k: q for k, q in inv_rows_profile}.get("nano_it", 0)
    mult = get_multiplier(evolution_level, active_items, vip_active, upgrades, ultra_rebirth, chronos_boost_pct, nano_it_count)
    flat_bonus = total_flat_bonus(active_items)

    if vip_active:
        left = vip_until - int(time.time())
        d, rem = divmod(left, 86400)
        h = rem // 3600
        vip_line = f"● VIP статус: активен ({d} дн {h} ч) {PREMIUM_VIP_BADGE}\n"
    else:
        vip_line = "● VIP статус: не активен\n"

    lvl_line = f"● Уровень ноги: {display_level} лвл\n" if (show_level or ultra_rebirth) else ""
    name_part = f" {esc(name)}" if name else ""
    guarant_line = f"● Гарант-буст с предмета: +{flat_bonus} к итогу\n" if flat_bonus else ""
    rebirth_line = f"● Перерождений: {rebirth_count} (🉑 {rebirth_points})\n" if rebirth_count else ""
    ultra_line = "🌌 <b>Статус: После Ультра перерождения</b>\n" if ultra_rebirth else ""
    equipped_names = [ITEMS[k][1] for k in (active_items) if k and k in ITEMS]
    equip_line = ("● Экипировано:\n" + "\n".join(f"  {n}" for n in equipped_names) + "\n") if equipped_names else ""

    text = (
        f"👣 <b>ТВОЯ ЛЮТАЯ НОГОСТЬ, {esc(shown_name)}:</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"{ultra_line}"
        f"● Очки: <code>{score}</code>\n"
        f"● Монеты: <code>{coins}</code> 🪙\n"
        f"● Вид ног: {emoji}{name_part}\n"
        f"{lvl_line}"
        f"● Уровень эволюции: {evolution_level}\n"
        f"{rebirth_line}"
        f"{equip_line}"
        f"● Процентовый буст: +{round((mult - 1) * 100)}%\n"
        f"{guarant_line}"
        f"{vip_line}"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"● {nxt}"
    )
    await message.reply(text)

@dp.message(F.text.regexp(r"(?i)^инфо\s+@?\w+$"))
async def info_player(message: Message):
    match = INFO_RE.match(message.text.strip())
    if not match:
        return
    target_username = match.group(1)

    row = await get_user_by_username(target_username)
    if not row:
        await message.reply(TEXTS["info_player_1"])
        return

    username = row[1]
    score, evolution_level, coins, active_item = row[2], row[3], row[5], row[6]
    cases_opened, total_farmed = row[7], row[8]
    vip_until = row[12]
    rebirth_count = row[15] if len(row) > 15 else 0
    rebirth_points = row[14] if len(row) > 14 else 0
    shown = parse_shown(row[39] if len(row) > 39 else "")
    promo_badges = parse_promo_badges(row[33] if len(row) > 33 else "")
    nickname = row[19] if len(row) > 19 else None
    ultra_rebirth = bool(row[21]) if len(row) > 21 else False
    bonus_streak = row[10] if len(row) > 10 else 0
    prestige_points = row[27] if len(row) > 27 else 0
    crafts_done = row[36] if len(row) > 36 else 0
    shown_name = display_name(username, nickname)
    vip_active = is_vip_active(vip_until)
    level = get_level_index(score, evolution_level, rebirth_count, ultra_rebirth)
    emoji, name, show_level = get_level_visual(level)
    lvl_part = f" ({level} лвл)" if show_level else ""
    name_part = f" {esc(name)}" if name else ""
    item_text = ITEMS[active_item][1] if active_item and active_item in ITEMS else "нет"
    vip_text = "активен" if vip_active else "не активен"
    badges = get_badges(username, evolution_level, cases_opened, total_farmed, vip_active, shown, promo_badges,
                         coins, rebirth_points, ultra_rebirth, bonus_streak, crafts_done, prestige_points)

    text = (
        f"👣 <b>Инфо об игроке {esc(shown_name)}{badges}:</b>\n"
        f"● Нога: {emoji}{name_part}{lvl_part}\n"
        f"● Очки: <code>{score}</code>\n"
        f"● Монеты: <code>{coins}</code> 🪙\n"
        f"● Уровень эволюции: {evolution_level}\n"
        f"● VIP: {vip_text}"
    )
    await message.reply(text)

async def send_legs_top(message: Message, chat_id, title: str):
    rows = await build_top(chat_id, "score")

    if not rows:
        await message.reply(TEXTS["send_legs_top_1"])
        return

    text = f"🏆 <b>{title}</b>\n\n"
    for i, (username, score, evolution_level, coins, cases_opened, total_farmed, vip_until, shown_badges, rebirth_points, rebirth_count, nickname, ultra_rebirth, promo_badges_raw, bonus_streak, prestige_points, crafts_done) in enumerate(rows, 1):
        level = get_level_index(score, evolution_level, rebirth_count, bool(ultra_rebirth))
        emoji, name, show_level = get_level_visual(level)
        badges = get_badges(username, evolution_level, cases_opened, total_farmed, is_vip_active(vip_until), parse_shown(shown_badges), parse_promo_badges(promo_badges_raw), coins, rebirth_points, bool(ultra_rebirth), bonus_streak, crafts_done, prestige_points)
        lvl_part = f" ({level} лвл)" if show_level else ""
        name_part = f" {esc(name)}" if name else ""
        text += f"{i}. {esc(display_name(username, nickname))}{badges} — <code>{score}</code>\n   └ {emoji}{name_part}{lvl_part} · эво {evolution_level}\n\n"

    await message.reply(text)

async def send_evo_top(message: Message, chat_id, title: str):
    rows = await build_top(chat_id, "evolution_level")

    if not rows:
        await message.reply(TEXTS["send_evo_top_1"])
        return

    text = f"🎆 <b>{title}</b>\n\n"
    for i, (username, score, evolution_level, coins, cases_opened, total_farmed, vip_until, shown_badges, rebirth_points, rebirth_count, nickname, ultra_rebirth, promo_badges_raw, bonus_streak, prestige_points, crafts_done) in enumerate(rows, 1):
        badges = get_badges(username, evolution_level, cases_opened, total_farmed, is_vip_active(vip_until), parse_shown(shown_badges), parse_promo_badges(promo_badges_raw), coins, rebirth_points, bool(ultra_rebirth), bonus_streak, crafts_done, prestige_points)
        text += f"{i}. {esc(display_name(username, nickname))}{badges} — эво {evolution_level} ({score} очков)\n"

    await message.reply(text)

async def send_coin_top(message: Message, chat_id, title: str):
    rows = await build_top(chat_id, "coins")

    if not rows:
        await message.reply(TEXTS["send_coin_top_1"])
        return

    text = f"🪙 <b>{title}</b>\n\n"
    for i, (username, score, evolution_level, coins, cases_opened, total_farmed, vip_until, shown_badges, rebirth_points, rebirth_count, nickname, ultra_rebirth, promo_badges_raw, bonus_streak, prestige_points, crafts_done) in enumerate(rows, 1):
        badges = get_badges(username, evolution_level, cases_opened, total_farmed, is_vip_active(vip_until), parse_shown(shown_badges), parse_promo_badges(promo_badges_raw), coins, rebirth_points, bool(ultra_rebirth), bonus_streak, crafts_done, prestige_points)
        text += f"{i}. {esc(display_name(username, nickname))}{badges} — {coins} 🪙\n"

    await message.reply(text)

async def send_rebirth_top(message: Message, chat_id, title: str):
    rows = await build_top(chat_id, "rebirth_points")

    if not rows:
        await message.reply(TEXTS["send_rebirth_top_1"])
        return

    text = f"🉑 <b>{title}</b>\n\n"
    for i, (username, score, evolution_level, coins, cases_opened, total_farmed, vip_until, shown_badges, rebirth_points, rebirth_count, nickname, ultra_rebirth, promo_badges_raw, bonus_streak, prestige_points, crafts_done) in enumerate(rows, 1):
        badges = get_badges(username, evolution_level, cases_opened, total_farmed, is_vip_active(vip_until), parse_shown(shown_badges), parse_promo_badges(promo_badges_raw), coins, rebirth_points, bool(ultra_rebirth), bonus_streak, crafts_done, prestige_points)
        text += f"{i}. {esc(display_name(username, nickname))}{badges} — {rebirth_points} 🉑 (перерождений: {rebirth_count})\n"

    await message.reply(text)

@dp.message(F.text.lower() == "топ ног")
async def top_legs_local(message: Message):
    await send_legs_top(message, message.chat.id, "ТОП-10 НОГ ЭТОГО ЧАТА")

@dp.message(F.text.lower() == "гл топ ног")
async def top_legs_global(message: Message):
    await send_legs_top(message, None, "ТОП-10 НОГ ВЕЗДЕ")

@dp.message(F.text.lower() == "топ эво")
async def top_evo_local(message: Message):
    await send_evo_top(message, message.chat.id, "ТОП ЭВОЛЮЦИЙ ЭТОГО ЧАТА")

@dp.message(F.text.lower() == "гл топ эво")
async def top_evo_global(message: Message):
    await send_evo_top(message, None, "ТОП ЭВОЛЮЦИЙ ВЕЗДЕ")

@dp.message(F.text.lower() == "топ коин")
async def top_coin_local(message: Message):
    await send_coin_top(message, message.chat.id, "ТОП МОНЕТ ЭТОГО ЧАТА")

@dp.message(F.text.lower() == "гл топ коин")
async def top_coin_global(message: Message):
    await send_coin_top(message, None, "ТОП МОНЕТ ВЕЗДЕ")

@dp.message(F.text.lower() == "топ очкп")
async def top_rebirth_local(message: Message):
    await send_rebirth_top(message, message.chat.id, "ТОП ОЧКОВ ПЕРЕРОЖДЕНИЯ ЭТОГО ЧАТА")

@dp.message(F.text.lower() == "гл топ очкп")
async def top_rebirth_global(message: Message):
    await send_rebirth_top(message, None, "ТОП ОЧКОВ ПЕРЕРОЖДЕНИЯ ВЕЗДЕ")

@dp.message(F.text.lower() == "топ ноги вся")
async def top_legs_global_suffix(message: Message):
    await send_legs_top(message, None, "ТОП-10 НОГ ВЕЗДЕ")

@dp.message(F.text.lower() == "топ коин вся")
async def top_coin_global_suffix(message: Message):
    await send_coin_top(message, None, "ТОП МОНЕТ ВЕЗДЕ")

@dp.message(F.text.lower() == "топ эво вся")
async def top_evo_global_suffix(message: Message):
    await send_evo_top(message, None, "ТОП ЭВОЛЮЦИЙ ВЕЗДЕ")

@dp.message(F.text.lower() == "топ очкп вся")
async def top_rebirth_global_suffix(message: Message):
    await send_rebirth_top(message, None, "ТОП ОЧКОВ ПЕРЕРОЖДЕНИЯ ВЕЗДЕ")

@dp.message(F.text.lower().in_({"топ вся", "гл топ"}))
async def top_overall_global(message: Message):
    await send_legs_top(message, None, "ОБЩИЙ ТОП ВЕЗДЕ (по очкам ноги)")

@dp.message(F.text.lower().in_({"ферма", "фарма"}))
async def farm(message: Message):
    if not await require_subscription(message):
        return
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"
    now = int(time.time())

    row = await ensure_user(user_id, username)
    score, evolution_level, active_item = row[2], row[3], row[6]
    last_farm, levelup_notify, vip_until = row[4], row[11], row[12]
    rebirth_points, rebirth_count = row[14], row[15]
    upgrades = parse_upgrades(row[16])
    active_items = parse_equipped(row[18])
    ultra_rebirth = bool(row[21])
    auto_evolve_enabled = bool(row[22])
    auto_rebirth_enabled = bool(row[29])
    prestige_points = row[27]
    vip_active = is_vip_active(vip_until)
    potions = active_potions_now(row[23], now, active_items)
    prestige_upgrades = parse_prestige_upgrades(row[28])
    chronos_boost_pct = row[34] if len(row) > 34 else 100
    compact_mode = bool(row[35]) if len(row) > 35 else False
    vilon_boost_until = row[38] if len(row) > 38 else 0
    kotyara_boost_until = row[40] if len(row) > 40 else 0

    inv_rows = await get_inventory(user_id)
    inventory_map = {k: q for k, q in inv_rows}
    has_time_particle = inventory_map.get("time_particle", 0) > 0

    cooldown = farm_cd_seconds(upgrades, active_items, has_time_particle, prestige_upgrades)
    has_no_cd = NO_CD_CHARGES_KEY in potions
    if not has_no_cd and now - last_farm < cooldown:
        left = cooldown - (now - last_farm)
        m, s = divmod(left, 60)
        await message.reply(TEXTS["farm_1"].format(v0=m, v1=s))
        return

    auto_legs, auto_coins, score, _coins_after = await claim_offline_auto_farm(user_id, row)

    low, high = farm_range(evolution_level)
    nano_it_count = inventory_map.get("nano_it", 0)
    mult = get_multiplier(evolution_level, active_items, vip_active, upgrades, ultra_rebirth, chronos_boost_pct, nano_it_count)
    event_mult = await get_event_multiplier()
    personal_mult = await get_personal_multiplier(user_id)
    p_yield_mult = 1 + 0.005 * prestige_bonus(prestige_upgrades, "p_farm_yield")
    gained = round(random.randint(low, high) * farm_yield_multiplier(upgrades) * mult * event_mult * personal_mult * p_yield_mult)
    if evolution_level >= EVO_UNLOCK_MEK2_LEVEL:
        gained += EVO_FARM_BONUS_LVL10
    pocket_star_text = ""
    if inventory_map.get("pocket_star", 0) > 0:
        gained = round(gained * POCKET_STAR_FARM_CMD_MULT)
        rebirth_gain = random.randint(*POCKET_STAR_FARM_CMD_REBIRTH_RANGE)
        await db_exec(
            "UPDATE users SET rebirth_points = rebirth_points + ? WHERE user_id = ?",
            (rebirth_gain, user_id),
        )
        pocket_star_text = f"\n{ITEMS['pocket_star'][0]} Карманная звезда: +{rebirth_gain}🉑!"
    gained = apply_vilon_amulet_boost(gained, vilon_boost_until)
    gained = apply_kotyara_amulet_boost(gained, kotyara_boost_until)
    potion_text = ""
    if "potion_speed" in potions:
        speed_mult = DRAGON_CLAW_POTION_MULT if "dragon_claw" in set(_normalize_active_items(active_items)) else 2
        gained *= speed_mult
        potion_text += f"\n🧪⚡ Зелье ускорения: x{speed_mult} к добыче!"

    chronos_text, chronos_reset_cd, chronos_farm_mult = await apply_chronos_orb_procs(user_id, active_items)
    if chronos_farm_mult != 1.0:
        gained = round(gained * chronos_farm_mult)

    gained, nogost_coin_text = apply_coin_tree_farm_roll(gained, active_items)
    new_score = score + gained

    new_last_farm = 0 if chronos_reset_cd else now
    await db_exec(
        "UPDATE users SET score = ?, last_farm = ?, total_farmed = total_farmed + ? WHERE user_id = ?",
        (new_score, new_last_farm, gained, user_id),
    )

    if has_no_cd:
        potions = await consume_no_cd_charge(user_id, potions)
        charges_left = potions.get(NO_CD_CHARGES_KEY, 0)
        potion_text += f"\n🧪🌀 Зелье без КД: заряд использован ({charges_left} ост.)"

    luck_boost = "luck_x2" in potions
    vase_text = await apply_vase_proc(user_id, inventory_map, luck_boost)
    bonus = await apply_farm_bonuses(user_id, active_items, inventory_map, luck_boost)
    chaos_text = await apply_chaos_orb_proc(user_id, active_items)
    necklace_text = (
        await apply_blazing_necklace_proc(user_id, active_items)
        + await apply_star_necklace_proc(user_id, active_items)
    )
    mastery_text, mastery_bitcoin_bonus = await apply_mastery_lover_proc(user_id, active_items)
    coin_tree_text = (
        nogost_coin_text
        + await apply_godly_nogost_coin_case_proc(user_id, inventory_map)
        + await apply_bitcoin_proc(user_id, inventory_map, mastery_bitcoin_bonus)
        + await apply_rebirth_coin_proc(user_id, inventory_map)
    )
    kotyara_text = await apply_kotyara_amulet_trigger(user_id, active_items)

    await maybe_announce_levelup(message, username, score, new_score, evolution_level, bool(levelup_notify), rebirth_count, ultra_rebirth)

    auto_evo_text = ""
    if vip_active and auto_evolve_enabled:
        evolution_level, new_score, auto_evo_text = await try_auto_evolve(user_id, new_score, evolution_level, rebirth_count, active_items)

    auto_rebirth_text = ""
    if vip_active and auto_rebirth_enabled:
        new_score, evolution_level, rebirth_count, rebirth_points, prestige_points, auto_rebirth_text = await try_auto_rebirth(
            user_id, new_score, evolution_level, rebirth_count, rebirth_points, prestige_points, prestige_upgrades, active_items
        )

    auto_text = ""
    if auto_legs or auto_coins:
        bits = []
        if auto_legs:
            bits.append(f"+{auto_legs} очков")
        if auto_coins:
            bits.append(f"+{auto_coins} 🪙")
        auto_text = f"\n⚙️ Авто-Ферма накопила: {', '.join(bits)}"

    coin_text = f" +{bonus['coins']}🪙" if bonus["coins"] else ""
    bonus_text = "" if compact_mode else (vase_text + potion_text + chaos_text + chronos_text + coin_tree_text + pocket_star_text + necklace_text + mastery_text)
    extra_text = bonus_text + auto_evo_text + auto_rebirth_text + kotyara_text
    chronos_equipped = "chronos_orb" in set(_normalize_active_items(active_items))

    if bonus["is_god"]:
        flavor = CHRONOS_ORB_FLAVOR if chronos_equipped else GOD_ESSENCE_FLAVOR
        god_extra = f" +{bonus['rebirth']}🉑" if bonus["rebirth"] else ""
        await safe_reply(
            message,
            TEXTS["farm_2"].format(v0=flavor, v1=gained, v2=new_score, v3=coin_text, v4=god_extra, v5=auto_text, v6=extra_text)
        )
        return

    if chronos_equipped:
        await safe_reply(
            message,
            TEXTS["farm_2"].format(v0=CHRONOS_ORB_FLAVOR, v1=gained, v2=new_score, v3=coin_text, v4="", v5=auto_text, v6=extra_text)
        )
        return

    await message.reply(
        TEXTS["farm_3"].format(v0=gained, v1=new_score, v2=coin_text, v3=auto_text, v4=extra_text)
    )

@dp.message(F.text.lower() == "бонус")
async def daily_bonus(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"
    now = int(time.time())

    row = await ensure_user(user_id, username)
    score, evolution_level = row[2], row[3]
    last_bonus, bonus_streak, levelup_notify = row[9], row[10], row[11]

    elapsed = now - last_bonus
    if last_bonus and elapsed < DAILY_MIN_GAP:
        left = DAILY_MIN_GAP - elapsed
        h, rem = divmod(left, 3600)
        m = rem // 60
        await message.reply(TEXTS["daily_bonus_1"].format(v0=h, v1=m))
        return

    if last_bonus and elapsed <= DAILY_STREAK_LIMIT:
        streak = bonus_streak + 1
    else:
        streak = 1

    day_index = (streak - 1) % len(DAILY_TABLE)
    reward = DAILY_TABLE[day_index]
    new_score = score + reward

    await db_exec(
        "UPDATE users SET score = ?, total_farmed = total_farmed + ?, last_bonus = ?, bonus_streak = ? WHERE user_id = ?",
        (new_score, reward, now, streak, user_id),
    )

    item_text = ""
    if day_index == len(DAILY_TABLE) - 1:
        await add_item(user_id, "daily_charm")
        item_text = f"\n{PREMIUM_DAILY_CHARM} Плюс Дневной амулет (+15% буст) в инвентарь!"

    await maybe_announce_levelup(message, username, score, new_score, evolution_level, bool(levelup_notify))
    await message.reply(TEXTS["daily_bonus_2"].format(v0=streak, v1=reward, v2=new_score, v3=item_text))

@dp.message(F.text.regexp(REVERSE_EXCHANGE_RE))
async def reverse_exchange(message: Message):
    """обменять <кол-во> коин -> списывает коины, начисляет очки ног (1 коин = 150 очков)."""
    match = REVERSE_EXCHANGE_RE.match(message.text.strip())
    coins_wanted = parse_amount(match.group(1))
    if not coins_wanted or coins_wanted <= 0:
        await message.reply(TEXTS["reverse_exchange_1"])
        return

    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"

    row = await ensure_user(user_id, username)
    score, coins, evolution_level = row[2], row[5], row[3]
    rebirth_count = row[15]
    levelup_notify = row[11]

    if coins_wanted > coins:
        await message.reply(TEXTS["reverse_exchange_2"].format(v0=coins))
        return

    gained = coins_wanted * REVERSE_EXCHANGE_RATE
    new_coins = coins - coins_wanted
    new_score = score + gained

    await db_exec("UPDATE users SET score = ?, coins = ? WHERE user_id = ?", (new_score, new_coins, user_id))

    await maybe_announce_levelup(message, username, score, new_score, evolution_level, bool(levelup_notify), rebirth_count)
    await message.reply(TEXTS["reverse_exchange_3"].format(v0=coins_wanted, v1=gained, v2=new_score))

@dp.message(F.text.regexp(CRAFT_EXCHANGE_RE))
async def craft_exchange(message: Message):
    """обменять <кол-во> крафт/очкк -> списывает очки перерождения, начисляет очки крафта
    (курс: CRAFT_POINTS_EXCHANGE_RATE 🉑 = 1 💠). <кол-во> здесь — это 🉑, которые отдаёшь."""
    match = CRAFT_EXCHANGE_RE.match(message.text.strip())
    rebirth_wanted = parse_amount(match.group(1))
    if not rebirth_wanted or rebirth_wanted <= 0:
        await message.reply("Количество очков перерождения должно быть больше нуля.")
        return
    if rebirth_wanted % CRAFT_POINTS_EXCHANGE_RATE != 0:
        await message.reply(
            f"Обменивать можно только кратно {CRAFT_POINTS_EXCHANGE_RATE} 🉑 "
            f"(например: обменять {CRAFT_POINTS_EXCHANGE_RATE} крафт).\n"
            f"Хочешь сразу задать нужное число очков крафта — пиши «обменять очкк <число>» "
            f"(например: обменять очкк 3 → спишет {3 * CRAFT_POINTS_EXCHANGE_RATE} 🉑)."
        )
        return

    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"

    row = await ensure_user(user_id, username)
    rebirth_points = row[14]
    craft_points = row[32]

    if rebirth_wanted > rebirth_points:
        await message.reply(
            f"Недостаточно очков перерождения. У тебя {rebirth_points} 🉑, "
            f"нужно {rebirth_wanted} 🉑 (= {rebirth_wanted // CRAFT_POINTS_EXCHANGE_RATE} 💠)."
        )
        return

    gained = rebirth_wanted // CRAFT_POINTS_EXCHANGE_RATE
    new_rebirth_points = rebirth_points - rebirth_wanted
    new_craft_points = craft_points + gained

    await db_exec(
        "UPDATE users SET rebirth_points = ?, craft_points = ? WHERE user_id = ?",
        (new_rebirth_points, new_craft_points, user_id),
    )

    await message.reply(
        f"Обменял {rebirth_wanted} 🉑 → +{gained} 💠 очков крафта (Всего: {new_craft_points})"
    )

@dp.message(F.text.regexp(CRAFT_EXCHANGE_TO_RE))
async def craft_exchange_to(message: Message):
    """обменять крафт/очкк <кол-во> -> удобный обратный формат: <кол-во> это то, сколько
    очков крафта 💠 хочешь ПОЛУЧИТЬ. Бот сам считает нужные 🉑 (по курсу) и списывает их."""
    match = CRAFT_EXCHANGE_TO_RE.match(message.text.strip())
    craft_wanted = parse_amount(match.group(1))
    if not craft_wanted or craft_wanted <= 0:
        await message.reply("Количество очков крафта должно быть больше нуля.")
        return

    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"

    row = await ensure_user(user_id, username)
    rebirth_points = row[14]
    craft_points = row[32]

    rebirth_cost = craft_wanted * CRAFT_POINTS_EXCHANGE_RATE

    if rebirth_cost > rebirth_points:
        max_affordable = rebirth_points // CRAFT_POINTS_EXCHANGE_RATE
        await message.reply(
            f"Недостаточно очков перерождения. У тебя {rebirth_points} 🉑, "
            f"нужно {rebirth_cost} 🉑 на {craft_wanted} 💠.\n"
            f"Сейчас можешь обменять максимум {max_affordable} 💠 "
            f"(обменять очкк {max_affordable})." if max_affordable > 0 else
            f"Недостаточно очков перерождения. У тебя {rebirth_points} 🉑, "
            f"нужно {rebirth_cost} 🉑 на {craft_wanted} 💠."
        )
        return

    new_rebirth_points = rebirth_points - rebirth_cost
    new_craft_points = craft_points + craft_wanted

    await db_exec(
        "UPDATE users SET rebirth_points = ?, craft_points = ? WHERE user_id = ?",
        (new_rebirth_points, new_craft_points, user_id),
    )

    await message.reply(
        f"Обменял {rebirth_cost} 🉑 → +{craft_wanted} 💠 очков крафта (Всего: {new_craft_points})"
    )

@dp.message(F.text.lower().startswith("обменять "))
async def exchange(message: Message):
    match = EXCHANGE_RE.match(message.text.strip().lower())
    if not match:
        await message.reply(TEXTS["exchange_1"].format(v0=EXCHANGE_RATE))
        return

    coins_wanted = parse_amount(match.group(1))
    if not coins_wanted or coins_wanted <= 0:
        await message.reply(TEXTS["exchange_2"])
        return

    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"

    row = await ensure_user(user_id, username)
    score, coins, evolution_level = row[2], row[5], row[3]
    rebirth_count = row[15]
    ultra_rebirth = bool(row[21])

    spent = coins_wanted * EXCHANGE_RATE
    if spent > score:
        max_coins = score // EXCHANGE_RATE
        await message.reply(TEXTS["exchange_3"].format(v0=score, v1=max_coins))
        return

    old_level = get_level_index(score, evolution_level, rebirth_count, ultra_rebirth)
    new_score = score - spent
    new_level = get_level_index(new_score, evolution_level, rebirth_count, ultra_rebirth)
    new_coins = coins + coins_wanted

    await db_exec("UPDATE users SET score = ?, coins = ? WHERE user_id = ?", (new_score, new_coins, user_id))

    warn = f"\n⚠️ Уровень упал с {old_level} до {new_level}!" if new_level < old_level else ""
    await message.reply(TEXTS["exchange_4"].format(v0=spent, v1=coins_wanted, v2=new_coins, v3=warn))

async def transfer_currency(message: Message, currency: str, amount: int):
    """currency: 'ног' или 'коин'. Общая логика для дать/передать <число> <валюта>."""
    if not message.reply_to_message:
        await message.reply(TEXTS["transfer_currency_1"])
        return

    receiver = message.reply_to_message.from_user
    sender = message.from_user
    if receiver.id == sender.id:
        await message.reply(TEXTS["transfer_currency_2"])
        return

    sender_username = sender.username or sender.first_name or "Без имени"
    receiver_username = receiver.username or receiver.first_name or "Без имени"

    sender_row = await ensure_user(sender.id, sender_username)
    if sender_row[3] < 1:
        await message.reply(TEXTS["transfer_currency_3"])
        return

    if currency == "ног":
        if sender_row[2] < amount:
            await message.reply(TEXTS["transfer_currency_4"].format(v0=sender_row[2]))
            return
        receiver_row = await ensure_user(receiver.id, receiver_username)
        new_sender = sender_row[2] - amount
        new_receiver = receiver_row[2] + amount
        await db_exec("UPDATE users SET score = ? WHERE user_id = ?", (new_sender, sender.id))
        await db_exec("UPDATE users SET score = ? WHERE user_id = ?", (new_receiver, receiver.id))
        await message.reply(TEXTS["transfer_currency_5"].format(v0=esc(sender_username), v1=amount, v2=esc(receiver_username)))
        await maybe_announce_levelup(message, receiver_username, receiver_row[2], new_receiver,
                                      receiver_row[3], bool(receiver_row[11]), receiver_row[15])
    else:
        if sender_row[5] < amount:
            await message.reply(TEXTS["transfer_currency_6"].format(v0=sender_row[5]))
            return
        await ensure_user(receiver.id, receiver_username)
        await db_exec("UPDATE users SET coins = coins - ? WHERE user_id = ?", (amount, sender.id))
        await db_exec("UPDATE users SET coins = coins + ? WHERE user_id = ?", (amount, receiver.id))
        await message.reply(TEXTS["transfer_currency_7"].format(v0=esc(sender_username), v1=amount, v2=esc(receiver_username)))

async def transfer_item_direct(message: Message, item_query: str):
    """Прямой поиск предмета по вхождению строки, без разделения на бустеры/пассивки (п.2 ТЗ)."""
    if not message.reply_to_message:
        await message.reply(TEXTS["transfer_item_direct_1"])
        return

    item_key = find_item_by_name(item_query)
    if not item_key:
        await message.reply(TEXTS["transfer_item_direct_2"].format(v0=esc(item_query)))
        return

    if item_key in NON_TRADABLE_ITEMS:
        emoji, name, _, _ = ITEMS[item_key]
        await message.reply(TEXTS["transfer_item_direct_3"].format(v0=emoji, v1=esc(name)))
        return

    sender_id = message.from_user.id
    sender_username = message.from_user.username or message.from_user.first_name or "Без имени"
    receiver = message.reply_to_message.from_user
    receiver_username = receiver.username or receiver.first_name or "Без имени"

    if receiver.id == sender_id:
        await message.reply(TEXTS["transfer_item_direct_4"])
        return

    emoji, name, _, _ = ITEMS[item_key]

    await ensure_user(sender_id, sender_username)
    await ensure_user(receiver.id, receiver_username)

    removed = await remove_item(sender_id, item_key, 1)
    if not removed:
        await message.reply(TEXTS["transfer_item_direct_5"].format(v0=esc(name)))
        return

    sender_row = await get_user(sender_id)
    remaining = await get_inventory(sender_id)
    has_more = any(k == item_key and q > 0 for k, q in remaining)
    if not has_more:
        new_equipped = unequip_item(sender_row[18], item_key)
        await db_exec("UPDATE users SET equipped_items = ? WHERE user_id = ?", (format_equipped(new_equipped), sender_id))

    await add_item(receiver.id, item_key)

    await safe_reply(message, TEXTS["transfer_item_direct_6"].format(v0=emoji, v1=esc(name), v2=esc(receiver_username)))

_TRANSFER_CURRENCY_TOKENS = {"ног": "ног", "коин": "коин"}

@dp.message(F.text.regexp(r"(?i)^(дать|передать)\s+(.+)$"))
async def give_or_transfer(message: Message):
    """Умный хендлер: 'дать 888 коин' -> валюта, 'дать свеча' / 'передать свеча' -> предмет.
    Синтаксис определяется автоматически по структуре аргументов."""
    text = message.text.strip()
    verb, _, args = text.partition(" ")
    args = args.strip()
    if not args:
        await message.reply(TEXTS["give_or_transfer_1"])
        return

    parts = args.split(" ", 1)
    first_word = parts[0]
    rest = parts[1].strip() if len(parts) > 1 else ""

    if _AMOUNT_TOKEN_RE.match(first_word) and rest:
        currency_word = rest.split(" ", 1)[0].lower()
        if currency_word in _TRANSFER_CURRENCY_TOKENS:
            amount = parse_amount(first_word)
            if not amount or amount <= 0:
                await message.reply(TEXTS["give_or_transfer_2"])
                return
            await transfer_currency(message, _TRANSFER_CURRENCY_TOKENS[currency_word], amount)
            return
        else:
            await message.reply(TEXTS["give_or_transfer_3"].format(v0=esc(currency_word)))
            return

    if first_word.lower() in _TRANSFER_CURRENCY_TOKENS and rest and _AMOUNT_TOKEN_RE.match(rest.split(" ", 1)[0]):
        amount_word = rest.split(" ", 1)[0]
        amount = parse_amount(amount_word)
        if not amount or amount <= 0:
            await message.reply(TEXTS["give_or_transfer_4"])
            return
        await transfer_currency(message, _TRANSFER_CURRENCY_TOKENS[first_word.lower()], amount)
        return

    await transfer_item_direct(message, args)

async def sell_item(message: Message, prefix: str, only_passive: bool):
    raw = message.text[len(prefix):].strip()
    sell_all = False
    if raw.lower().endswith(" все"):
        sell_all = True
        raw = raw[:-len(" все")].strip()
    item_query = raw
    item_key = find_item_by_name(item_query, only_passive=only_passive)
    if not item_key:
        wrong_cmd = "продать п" if only_passive is False else "продать б"
        await message.reply(TEXTS["sell_item_1"].format(v0='предметов' if only_passive else 'бустеров', v1=wrong_cmd))
        return

    if item_key in NON_TRADABLE_ITEMS:
        emoji, name, _, _ = ITEMS[item_key]
        await message.reply(TEXTS["sell_item_2"].format(v0=emoji, v1=esc(name)))
        return

    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"
    await ensure_user(user_id, username)

    emoji, name, _, _ = ITEMS[item_key]

    if sell_all:
        owned_row = await db_query_one("SELECT qty FROM inventory WHERE user_id = ? AND item_key = ?", (user_id, item_key))
        qty = owned_row[0] if owned_row else 0
        if qty <= 0:
            await message.reply(TEXTS["sell_item_3"].format(v0=esc(name)))
            return
    else:
        qty = 1

    removed = await remove_item(user_id, item_key, qty)
    if not removed:
        await message.reply(TEXTS["sell_item_3"].format(v0=esc(name)))
        return

    row = await get_user(user_id)
    remaining = await get_inventory(user_id)
    has_more = any(k == item_key and q > 0 for k, q in remaining)
    if not has_more:
        new_equipped = unequip_item(row[18], item_key)
        await db_exec("UPDATE users SET equipped_items = ? WHERE user_id = ?", (format_equipped(new_equipped), user_id))

    upgrades = parse_upgrades(row[16])
    sell_lvl = upgrade_level(upgrades, "sell_boost")
    unit_price = SELL_PRICE.get(item_key, 1) + sell_bonus_coins(upgrades)
    price = unit_price * qty

    bonus_rebirth = 0
    if sell_lvl >= 3 and random.random() < 0.01:
        bonus_rebirth = 1

    if bonus_rebirth:
        await db_exec(
            "UPDATE users SET coins = coins + ?, rebirth_points = rebirth_points + ? WHERE user_id = ?",
            (price, bonus_rebirth, user_id),
        )
    else:
        await db_exec("UPDATE users SET coins = coins + ? WHERE user_id = ?", (price, user_id))

    bonus_text = " 🎉 Повезло! +1 🉑!" if bonus_rebirth else ""
    if sell_all and qty > 1:
        await safe_reply(message, TEXTS["sell_item_4_all"].format(v0=emoji, v1=esc(name), v2=qty, v3=price, v4=bonus_text))
    else:
        await safe_reply(message, TEXTS["sell_item_4"].format(v0=emoji, v1=esc(name), v2=price, v3=bonus_text))

@dp.message(F.text.lower().startswith("продать б "))
async def sell_booster(message: Message):
    await sell_item(message, "продать б ", only_passive=False)

@dp.message(F.text.lower().startswith("продать п "))
async def sell_passive(message: Message):
    await sell_item(message, "продать п ", only_passive=True)

@dp.message(F.text.regexp(r"(?i)^продать(\s+.*)?$"))
async def sell_wrong_format(message: Message):
    """Ловит 'продать <название>' без б/п (или вообще без аргумента) — чтобы не было тишины."""
    lower = message.text.lower()
    if lower.startswith("продать б ") or lower.startswith("продать п "):
        return
    await message.reply(
        TEXTS["sell_wrong_format_1"]
    )

async def destroy_item(message: Message, prefix: str, only_passive: bool):
    item_query = message.text[len(prefix):].strip()
    item_key = find_item_by_name(item_query, only_passive=only_passive)
    if not item_key:
        wrong_cmd = "уничтожение п" if only_passive is False else "уничтожение б"
        await message.reply(TEXTS["destroy_item_1"].format(v0='предметов' if only_passive else 'бустеров', v1=wrong_cmd))
        return

    if item_key in NON_TRADABLE_ITEMS:
        emoji, name, _, _ = ITEMS[item_key]
        await message.reply(TEXTS["destroy_item_2"].format(v0=emoji, v1=esc(name)))
        return

    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"
    await ensure_user(user_id, username)

    removed = await remove_item(user_id, item_key, 1)
    emoji, name, _, _ = ITEMS[item_key]
    if not removed:
        await message.reply(TEXTS["destroy_item_3"].format(v0=esc(name)))
        return

    row = await get_user(user_id)
    remaining = await get_inventory(user_id)
    has_more = any(k == item_key and q > 0 for k, q in remaining)
    if not has_more:
        new_equipped = unequip_item(row[18], item_key)
        await db_exec("UPDATE users SET equipped_items = ? WHERE user_id = ?", (format_equipped(new_equipped), user_id))

    await safe_reply(message, TEXTS["destroy_item_4"].format(v0=emoji, v1=esc(name)))

@dp.message(F.text.lower().startswith("уничтожение б "))
async def destroy_booster(message: Message):
    await destroy_item(message, "уничтожение б ", only_passive=False)

@dp.message(F.text.lower().startswith("уничтожение п "))
async def destroy_passive(message: Message):
    await destroy_item(message, "уничтожение п ", only_passive=True)

@dp.message(F.text.regexp(r"(?i)^уничтожение(\s+.*)?$"))
async def destroy_wrong_format(message: Message):
    lower = message.text.lower()
    if lower.startswith("уничтожение б ") or lower.startswith("уничтожение п "):
        return
    await message.reply(
        TEXTS["destroy_wrong_format_1"]
    )

def _format_equipped_item_line(item_key: str) -> str:
    emoji, name, boost_percent, _ = ITEMS[item_key]
    if item_key == "chronos_orb":
        return f"{emoji} {esc(name)} (+10-400%, рандом)"
    return f"{emoji} {esc(name)} (+{boost_percent}%)"

def format_inventory_menu_text(active_items, upgrades: dict = None, prestige_upgrades: dict = None, bonus_slots: int = 0):
    items = _normalize_active_items(active_items)
    max_slots = equipped_slots_max(upgrades or {}, prestige_upgrades or {}, bonus_slots)
    equipped = [_format_equipped_item_line(k) for k in items if k in ITEMS]
    equipped_header = f"Экипировано ({len(equipped)}/{max_slots}):"
    equipped_text = equipped_header + ("\n" + "\n".join(equipped) if equipped else " ничего")
    return f"🎒 <b>Твой инвентарь</b>\n{equipped_text}\n\nВыбери раздел:"

INV_PAGE_SIZE = 5
POTION_PAGE_SIZE = 6

def inventory_menu_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🧪 Бустеры", callback_data=f"inv_cat:{user_id}:boosters:0")],
        [InlineKeyboardButton(text="📦 Предметы", callback_data=f"inv_cat:{user_id}:items:0")],
        [InlineKeyboardButton(text="⚗️ Зелья", callback_data=f"inv_cat:{user_id}:potions:0")],
    ])

def _paginate(items: list, page: int, page_size: int = INV_PAGE_SIZE):
    """Возвращает (нарезка_страницы, страница_в_границах, всего_страниц)."""
    total_pages = max(1, (len(items) + page_size - 1) // page_size)
    page = max(0, min(page, total_pages - 1))
    start = page * page_size
    return items[start:start + page_size], page, total_pages

def _pagination_row(callback_prefix: str, user_id: int, page: int, total_pages: int, extra: str = "") -> list:
    """Строка навигации ◀️ n/N ▶️. extra — доп. часть callback_data (например поисковый запрос)."""
    if total_pages <= 1:
        return []
    suffix = f":{extra}" if extra else ""
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️", callback_data=f"{callback_prefix}:{user_id}:{page - 1}{suffix}", style="primary"))
    nav.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton(text="▶️", callback_data=f"{callback_prefix}:{user_id}:{page + 1}{suffix}", style="primary"))
    return nav

def boosters_keyboard(rows, active_items, user_id: int, page: int = 0, query: str = None) -> InlineKeyboardMarkup:
    equipped = set(_normalize_active_items(active_items))
    boosters = [(k, q) for k, q in rows if k not in PASSIVE_ITEMS]
    if query:
        ql = query.lower()
        boosters = [(k, q) for k, q in boosters if ql in ITEMS[k][1].lower()]
    page_items, page, total_pages = _paginate(boosters, page)

    kb_rows = []
    for item_key, qty in page_items:
        emoji, name, percent, _ = ITEMS[item_key]
        is_equipped = item_key in equipped
        mark = " ✅" if is_equipped else ""
        cb = f"equip:{user_id}:{item_key}:{page}"
        if query:
            cb += f":{quote(query)}"
        kb_rows.append([InlineKeyboardButton(
            text=f"{name} {plain_emoji(emoji)} ({_percent_label(item_key, percent)}) x{qty}{mark}",
            callback_data=cb,
            style="success" if is_equipped else None,
        )])

    if query:
        nav_row = _pagination_row("inv_boost_search_page", user_id, page, total_pages, extra=quote(query))
    else:
        nav_row = _pagination_row("inv_boost_page", user_id, page, total_pages)
    if nav_row:
        kb_rows.append(nav_row)
    kb_rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data=f"inv_menu:{user_id}")])
    return InlineKeyboardMarkup(inline_keyboard=kb_rows)

def items_keyboard(user_id: int, rows=None, page: int = 0) -> InlineKeyboardMarkup:
    rows = rows or []
    passive = [(k, q) for k, q in rows if k in PASSIVE_ITEMS]
    _, page, total_pages = _paginate(passive, page)
    kb_rows = []
    nav_row = _pagination_row("inv_items_page", user_id, page, total_pages)
    if nav_row:
        kb_rows.append(nav_row)
    kb_rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data=f"inv_menu:{user_id}")])
    return InlineKeyboardMarkup(inline_keyboard=kb_rows)

def format_autosell_text(auto_sell_enabled: bool, auto_sell_items: set, page: int = 0) -> str:
    _, page, total_pages = _paginate(CASE_SELLABLE_ITEMS, page, AUTOSELL_PAGE_SIZE)
    page_suffix = f" (стр. {page + 1}/{total_pages})" if total_pages > 1 else ""
    status = "включена ✅" if auto_sell_enabled else "выключена ❌"
    return (
        f"💰 <b>Авто-продажа дропа из кейсов 1/2/3</b>{page_suffix}\n"
        f"Статус: {status}\n"
        f"Отмечено предметов: {len(auto_sell_items)}\n\n"
        f"Жми на предмет, чтобы включить/выключить его авто-продажу:"
    )

def autosell_keyboard(auto_sell_enabled: bool, auto_sell_items: set, user_id: int, page: int = 0) -> InlineKeyboardMarkup:
    page_items, page, total_pages = _paginate(CASE_SELLABLE_ITEMS, page, AUTOSELL_PAGE_SIZE)
    kb_rows = []
    for item_key in page_items:
        emoji, name, _, _ = ITEMS[item_key]
        is_on = item_key in auto_sell_items
        mark = "✅" if is_on else "❌"
        kb_rows.append([InlineKeyboardButton(
            text=f"{name} {plain_emoji(emoji)} {mark}",
            callback_data=f"autosell_toggle:{user_id}:{item_key}:{page}",
            style="success" if is_on else "danger",
        )])

    nav_row = _pagination_row("autosell_page", user_id, page, total_pages)
    if nav_row:
        kb_rows.append(nav_row)

    switch_text = "🔴 Выключить авто-продажу" if auto_sell_enabled else "🟢 Включить авто-продажу"
    kb_rows.append([InlineKeyboardButton(
        text=switch_text, callback_data=f"autosell_switch:{user_id}:{page}",
        style="danger" if auto_sell_enabled else "success",
    )])
    kb_rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data=f"inv_menu:{user_id}")])
    return InlineKeyboardMarkup(inline_keyboard=kb_rows)

def format_boosters_text(rows, max_slots: int = 1, page: int = 0, query: str = None):
    boosters = [(k, q) for k, q in rows if k not in PASSIVE_ITEMS]
    if query:
        ql = query.lower()
        boosters = [(k, q) for k, q in boosters if ql in ITEMS[k][1].lower()]
        if not boosters:
            return f"🔍 По запросу «{esc(query)}» бустеров не найдено."
        _, page, total_pages = _paginate(boosters, page)
        page_suffix = f" (стр. {page + 1}/{total_pages})" if total_pages > 1 else ""
        return f"🔍 Поиск «{esc(query)}»{page_suffix}:"
    if not boosters:
        return f"🧪 У тебя нет бустеров. Можно носить одновременно {max_slots}."
    _, page, total_pages = _paginate(boosters, page)
    page_suffix = f" (стр. {page + 1}/{total_pages})" if total_pages > 1 else ""
    return f"🧪 Твои бустеры (можно носить одновременно {max_slots}){page_suffix}:"

def format_items_text(rows, page: int = 0):
    passive = [(k, q) for k, q in rows if k in PASSIVE_ITEMS]
    if not passive:
        return "📦 У тебя нет предметов."
    page_items, page, total_pages = _paginate(passive, page)
    page_suffix = f" (стр. {page + 1}/{total_pages})" if total_pages > 1 else ""
    lines = [f"📦 Твои предметы (нельзя экипировать, действуют пассивно){page_suffix}:\n"]
    for item_key, qty in page_items:
        emoji, name, _, _ = ITEMS[item_key]
        lines.append(f"{emoji} {esc(name)} x{qty}")
    return "\n".join(lines)

def format_time_left(seconds: int) -> str:
    seconds = max(0, seconds)
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}ч {m}м"
    if m:
        return f"{m}м {s}с"
    return f"{s}с"

# ---- Справочные тексты для «помощь зелье <название>» ----
def find_potion_key_by_name(query: str):
    """Ищет ключ POTIONS по русскому названию. Сначала точное совпадение, иначе — по
    вхождению подстроки (как find_item_by_name). Возвращает (key, None) при однозначном
    совпадении, (None, [варианты]) при неоднозначности, (None, []) если не найдено."""
    q = (query or "").strip().lower()
    if not q:
        return None, []
    for key, cfg in POTIONS.items():
        if cfg["name"].strip().lower() == q:
            return key, None
    matches = [key for key, cfg in POTIONS.items() if q in cfg["name"].lower()]
    if len(matches) == 1:
        return matches[0], None
    if len(matches) > 1:
        matches.sort(key=lambda k: POTIONS[k]["name"])
        return None, matches
    return None, []

def format_help_potion_text(key: str) -> str:
    cfg = POTIONS[key]
    lines = [cfg["desc"] + "."]

    if cfg["effect"] == "no_cd":
        lines.append(f"Действует: {cfg['charges']} следующих использования фермы.")
    else:
        lines.append(f"Длительность эффекта: {format_time_left(cfg['duration_seconds'])} после выпития.")

    lines.append(
        f"Варка: {cfg['brew_cost']} 🪙, занимает {format_time_left(cfg['brew_seconds'])} "
        "— открой «мои зелья» и жми «⚗️ Варить»."
    )
    lines.append("Забрать готовое и выпить — тоже кнопками там же («✅ Забрать» / «▶️ Использовать»).")
    lines.append("Скорость и длительность варки можно улучшить в апгрейдах: «Скорость готовки зелья», «Длительность зелья».")
    return "\n".join(lines)

def format_potions_text(inventory_potions: dict, active_potions: dict, brewing_potion: str, brewing_until: int,
                         upgrades: dict, now: int = None, page: int = 0) -> str:
    now = now or int(time.time())
    _, page, total_pages = _paginate(POTION_ORDER, page, POTION_PAGE_SIZE)
    page_suffix = f" (стр. {page + 1}/{total_pages})" if total_pages > 1 else ""
    lines = [f"⚗️ <b>Зелья</b>{page_suffix}"]

    if brewing_potion and brewing_potion in POTIONS:
        cfg = POTIONS[brewing_potion]
        left = brewing_until - now
        if left > 0:
            lines.append(f"🔥 {cfg['emoji']} {esc(cfg['name'])} — готово через {format_time_left(left)}")
        else:
            lines.append(f"✅ {cfg['emoji']} {esc(cfg['name'])} готово — забери ниже")
    else:
        lines.append("🔥 Котёл свободен")

    for key, val in active_potions.items():
        cfg = POTIONS[key]
        if cfg["effect"] == "no_cd":
            lines.append(f"● {cfg['emoji']} {val} исп.")
        else:
            lines.append(f"● {cfg['emoji']} {format_time_left(val - now)}")

    owned = [f"{POTIONS[k]['emoji']}x{q}" for k, q in inventory_potions.items() if q > 0]
    if owned:
        lines.append("В запасе:")
        lines.extend(f"  {o}" for o in owned)
    else:
        lines.append("В запасе: пусто")

    return "\n".join(lines)

def potions_keyboard(inventory_potions: dict, brewing_potion: str, brewing_until: int, user_id: int,
                      upgrades: dict, now: int = None, prestige_upgrades: dict = None, page: int = 0,
                      active_items=None) -> InlineKeyboardMarkup:
    now = now or int(time.time())
    kb_rows = []

    brewing_active = bool(brewing_potion) and brewing_until > now
    brewing_ready = bool(brewing_potion) and brewing_until <= now

    page_order, page, total_pages = _paginate(POTION_ORDER, page, POTION_PAGE_SIZE)

    if brewing_ready:
        cfg = POTIONS[brewing_potion]
        kb_rows.append([InlineKeyboardButton(
            text=f"✅ Забрать {cfg['emoji']} {cfg['name']}",
            callback_data=f"potion_collect:{user_id}",
        )])
    elif not brewing_active:
        for key in page_order:
            cfg = POTIONS[key]
            seconds = brew_seconds_for(key, upgrades, prestige_upgrades, active_items)
            kb_rows.append([InlineKeyboardButton(
                text=f"⚗️ Варить {cfg['emoji']} {cfg['name']} ({cfg['brew_cost']}🪙, {format_time_left(seconds)})",
                callback_data=f"potion_brew:{user_id}:{key}",
            )])

    for key in page_order:
        qty = inventory_potions.get(key, 0)
        if qty > 0:
            cfg = POTIONS[key]
            kb_rows.append([InlineKeyboardButton(
                text=f"▶️ Использовать {cfg['emoji']} {cfg['name']} (x{qty})",
                callback_data=f"potion_use:{user_id}:{key}",
            )])

    nav_row = _pagination_row("inv_potion_page", user_id, page, total_pages)
    if nav_row:
        kb_rows.append(nav_row)
    kb_rows.append([InlineKeyboardButton(text="🔄 Обновить", callback_data=f"inv_cat:{user_id}:potions:{page}")])
    kb_rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data=f"inv_menu:{user_id}")])
    return InlineKeyboardMarkup(inline_keyboard=kb_rows)

@dp.message(F.text.lower().in_({"инвентарь", "мой инвентарь"}))
async def inventory(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"

    row = await ensure_user(user_id, username)
    upgrades = parse_upgrades(row[16])
    active_items = parse_equipped(row[18])
    prestige_upgrades = parse_prestige_upgrades(row[28])
    rows = await get_inventory(user_id)

    if not rows:
        await message.reply(TEXTS["inventory_1"])
        return

    await safe_reply(message, format_inventory_menu_text(active_items, upgrades, prestige_upgrades), reply_markup=inventory_menu_keyboard(user_id))

@dp.message(F.text.lower().in_({"мои предметы", "предметы"}))
async def my_items_tab(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"
    await ensure_user(user_id, username)
    rows = await get_inventory(user_id)
    await safe_reply(message, format_items_text(rows), reply_markup=items_keyboard(user_id, rows))

@dp.message(F.text.lower().in_({"мои бустеры", "бустеры"}))
async def my_boosters_tab(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"
    row = await ensure_user(user_id, username)
    upgrades = parse_upgrades(row[16])
    active_items = parse_equipped(row[18])
    prestige_upgrades = parse_prestige_upgrades(row[28])
    rows = await get_inventory(user_id)
    inventory_map = {k: q for k, q in rows}
    max_slots = equipped_slots_max(upgrades, prestige_upgrades, coin_tree_slot_bonus(inventory_map))
    await message.reply(format_boosters_text(rows, max_slots), reply_markup=boosters_keyboard(rows, active_items, user_id, 0))

@dp.message(F.text.lower().regexp(r"^бустеры поиск\s+.+$"))
async def my_boosters_search(message: Message):
    query = message.text.strip()[len("бустеры поиск"):].strip()
    if not query:
        return
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"
    row = await ensure_user(user_id, username)
    active_items = parse_equipped(row[18])
    rows = await get_inventory(user_id)
    await message.reply(
        format_boosters_text(rows, page=0, query=query),
        reply_markup=boosters_keyboard(rows, active_items, user_id, 0, query=query),
    )

@dp.message(F.text.lower().in_({"мои зелья", "зелья"}))
async def my_potions_tab(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"
    row = await ensure_user(user_id, username)
    upgrades = parse_upgrades(row[16])
    stock = parse_potion_stock(row[26])
    active_items = parse_equipped(row[18])
    active = active_potions_now(row[23], active_items=active_items)
    brewing_potion, brewing_until = row[24], row[25]
    prestige_upgrades = parse_prestige_upgrades(row[28])
    await message.reply(
        format_potions_text(stock, active, brewing_potion, brewing_until, upgrades),
        reply_markup=potions_keyboard(stock, brewing_potion, brewing_until, user_id, upgrades, prestige_upgrades=prestige_upgrades, active_items=active_items),
    )

@dp.callback_query(F.data.startswith("inv_menu:"))
async def inventory_back_to_menu(callback: CallbackQuery):
    owner_id = int(callback.data.split(":")[1])
    if callback.from_user.id != owner_id:
        await callback.answer(TEXTS["inventory_back_to_menu_1"], show_alert=True)
        return
    await callback.answer()

    row = await get_user(owner_id)
    upgrades = parse_upgrades(row[16])
    active_items = parse_equipped(row[18])
    prestige_upgrades = parse_prestige_upgrades(row[28])
    rows = await get_inventory(owner_id)
    inventory_map = {k: q for k, q in rows}
    await safe_edit_text(callback, format_inventory_menu_text(active_items, upgrades, prestige_upgrades, coin_tree_slot_bonus(inventory_map)), reply_markup=inventory_menu_keyboard(owner_id))

@dp.callback_query(F.data.startswith("inv_cat:"))
async def inventory_open_category(callback: CallbackQuery):
    parts = callback.data.split(":")
    owner_id = int(parts[1])
    category = parts[2]
    page = int(parts[3]) if len(parts) > 3 else 0
    if callback.from_user.id != owner_id:
        await callback.answer(TEXTS["inventory_open_category_1"], show_alert=True)
        return
    await callback.answer()

    if category == "boosters":
        rows = await get_inventory(owner_id)
        row = await get_user(owner_id)
        upgrades = parse_upgrades(row[16])
        active_items = parse_equipped(row[18])
        prestige_upgrades = parse_prestige_upgrades(row[28])
        inventory_map = {k: q for k, q in rows}
        max_slots = equipped_slots_max(upgrades, prestige_upgrades, coin_tree_slot_bonus(inventory_map))
        await safe_edit_text(callback, format_boosters_text(rows, max_slots, page), reply_markup=boosters_keyboard(rows, active_items, owner_id, page))
    elif category == "potions":
        row = await get_user(owner_id)
        upgrades = parse_upgrades(row[16])
        stock = parse_potion_stock(row[26])
        active_items = parse_equipped(row[18])
        active = active_potions_now(row[23], active_items=active_items)
        brewing_potion, brewing_until = row[24], row[25]
        prestige_upgrades = parse_prestige_upgrades(row[28])
        await safe_edit_text(
            callback,
            format_potions_text(stock, active, brewing_potion, brewing_until, upgrades, page=page),
            reply_markup=potions_keyboard(stock, brewing_potion, brewing_until, owner_id, upgrades, prestige_upgrades=prestige_upgrades, page=page, active_items=active_items),
        )
    else:
        rows = await get_inventory(owner_id)
        await safe_edit_text(callback, format_items_text(rows, page), reply_markup=items_keyboard(owner_id, rows, page))

@dp.callback_query(F.data.startswith("potion_brew:"))
async def potion_brew_start(callback: CallbackQuery):
    parts = callback.data.split(":")
    owner_id = int(parts[1])
    potion_key = parts[2]
    if callback.from_user.id != owner_id:
        await callback.answer(TEXTS["inventory_open_category_1"], show_alert=True)
        return
    if potion_key not in POTIONS:
        await callback.answer()
        return

    now = int(time.time())
    row = await get_user(owner_id)
    coins = row[5]
    upgrades = parse_upgrades(row[16])
    active_items = parse_equipped(row[18])
    brewing_potion, brewing_until = row[24], row[25]
    prestige_upgrades = parse_prestige_upgrades(row[28])

    if brewing_potion and brewing_until > now:
        await callback.answer(TEXTS["potion_brew_busy_1"], show_alert=True)
        return

    cfg = POTIONS[potion_key]
    if coins < cfg["brew_cost"]:
        await callback.answer(TEXTS["potion_brew_no_coins_1"].format(v0=cfg["brew_cost"], v1=coins), show_alert=True)
        return

    seconds = brew_seconds_for(potion_key, upgrades, prestige_upgrades, active_items)
    new_until = now + seconds
    await db_exec(
        "UPDATE users SET coins = coins - ?, brewing_potion = ?, brewing_until = ? WHERE user_id = ?",
        (cfg["brew_cost"], potion_key, new_until, owner_id),
    )

    stock = parse_potion_stock(row[26])
    await safe_edit_text(
        callback,
        format_potions_text(stock, active_potions_now(row[23], now, active_items), potion_key, new_until, upgrades, now),
        reply_markup=potions_keyboard(stock, potion_key, new_until, owner_id, upgrades, now, prestige_upgrades, active_items=active_items),
    )
    await callback.answer(TEXTS["potion_brew_started_1"].format(v0=cfg["emoji"], v1=cfg["name"], v2=format_time_left(seconds)))

@dp.callback_query(F.data.startswith("potion_collect:"))
async def potion_collect(callback: CallbackQuery):
    owner_id = int(callback.data.split(":")[1])
    if callback.from_user.id != owner_id:
        await callback.answer(TEXTS["inventory_open_category_1"], show_alert=True)
        return

    now = int(time.time())
    row = await get_user(owner_id)
    brewing_potion, brewing_until = row[24], row[25]
    upgrades = parse_upgrades(row[16])
    active_items = parse_equipped(row[18])
    prestige_upgrades = parse_prestige_upgrades(row[28])

    if not brewing_potion:
        await callback.answer(TEXTS["potion_collect_none_1"], show_alert=True)
        return
    if brewing_until > now:
        await callback.answer(TEXTS["potion_collect_not_ready_1"].format(v0=format_time_left(brewing_until - now)), show_alert=True)
        return

    stock = parse_potion_stock(row[26])
    stock[brewing_potion] = stock.get(brewing_potion, 0) + 1
    await db_exec(
        "UPDATE users SET brewing_potion = NULL, brewing_until = 0, potion_stock = ? WHERE user_id = ?",
        (format_potion_stock(stock), owner_id),
    )

    cfg = POTIONS[brewing_potion]
    await safe_edit_text(
        callback,
        format_potions_text(stock, active_potions_now(row[23], now, active_items), None, 0, upgrades, now),
        reply_markup=potions_keyboard(stock, None, 0, owner_id, upgrades, now, prestige_upgrades, active_items=active_items),
    )
    await callback.answer(TEXTS["potion_collect_ok_1"].format(v0=cfg["emoji"], v1=cfg["name"]))

@dp.callback_query(F.data.startswith("potion_use:"))
async def potion_use(callback: CallbackQuery):
    parts = callback.data.split(":")
    owner_id = int(parts[1])
    potion_key = parts[2]
    if callback.from_user.id != owner_id:
        await callback.answer(TEXTS["inventory_open_category_1"], show_alert=True)
        return
    if potion_key not in POTIONS:
        await callback.answer()
        return

    now = int(time.time())
    row = await get_user(owner_id)
    upgrades = parse_upgrades(row[16])
    active_items = parse_equipped(row[18])
    stock = parse_potion_stock(row[26])
    prestige_upgrades = parse_prestige_upgrades(row[28])

    if stock.get(potion_key, 0) <= 0:
        await callback.answer(TEXTS["potion_use_none_1"], show_alert=True)
        return

    stock[potion_key] -= 1
    if stock[potion_key] <= 0:
        del stock[potion_key]

    active = active_potions_now(row[23], now, active_items)
    cfg = POTIONS[potion_key]
    if cfg["effect"] == "no_cd":
        active[potion_key] = cfg["charges"]
    else:
        duration = potion_duration_seconds(potion_key, upgrades)
        active[potion_key] = now + duration

    await db_exec(
        "UPDATE users SET potion_stock = ?, active_potions = ? WHERE user_id = ?",
        (format_potion_stock(stock), format_potions(active), owner_id),
    )

    brewing_potion, brewing_until = row[24], row[25]
    await safe_edit_text(
        callback,
        format_potions_text(stock, active, brewing_potion, brewing_until, upgrades, now),
        reply_markup=potions_keyboard(stock, brewing_potion, brewing_until, owner_id, upgrades, now, prestige_upgrades, active_items=active_items),
    )
    if cfg["effect"] == "no_cd":
        await callback.answer(TEXTS["potion_use_ok_charges_1"].format(v0=cfg["emoji"], v1=cfg["name"], v2=cfg["charges"]))
    else:
        await callback.answer(TEXTS["potion_use_ok_1"].format(v0=cfg["emoji"], v1=cfg["name"], v2=format_time_left(potion_duration_seconds(potion_key, upgrades))))

@dp.callback_query(F.data.startswith("inv_boost_page:"))
async def inventory_boosters_page(callback: CallbackQuery):
    _, owner_str, page_str = callback.data.split(":")
    owner_id = int(owner_str)
    page = int(page_str)
    if callback.from_user.id != owner_id:
        await callback.answer(TEXTS["inventory_open_category_1"], show_alert=True)
        return
    await callback.answer()

    row = await get_user(owner_id)
    upgrades = parse_upgrades(row[16])
    active_items = parse_equipped(row[18])
    prestige_upgrades = parse_prestige_upgrades(row[28])
    rows = await get_inventory(owner_id)
    inventory_map = {k: q for k, q in rows}
    max_slots = equipped_slots_max(upgrades, prestige_upgrades, coin_tree_slot_bonus(inventory_map))
    await safe_edit_text(callback, format_boosters_text(rows, max_slots, page), reply_markup=boosters_keyboard(rows, active_items, owner_id, page))

@dp.callback_query(F.data.startswith("inv_boost_search_page:"))
async def inventory_boosters_search_page(callback: CallbackQuery):
    parts = callback.data.split(":")
    owner_id = int(parts[1])
    page = int(parts[2])
    query = unquote(parts[3]) if len(parts) > 3 else ""
    if callback.from_user.id != owner_id:
        await callback.answer(TEXTS["inventory_open_category_1"], show_alert=True)
        return
    await callback.answer()

    row = await get_user(owner_id)
    active_items = parse_equipped(row[18])
    rows = await get_inventory(owner_id)
    await safe_edit_text(callback, 
        format_boosters_text(rows, page=page, query=query),
        reply_markup=boosters_keyboard(rows, active_items, owner_id, page, query=query),
    )

@dp.callback_query(F.data.startswith("inv_items_page:"))
async def inventory_items_page(callback: CallbackQuery):
    _, owner_str, page_str = callback.data.split(":")
    owner_id = int(owner_str)
    page = int(page_str)
    if callback.from_user.id != owner_id:
        await callback.answer(TEXTS["inventory_open_category_1"], show_alert=True)
        return
    await callback.answer()

    rows = await get_inventory(owner_id)
    await safe_edit_text(callback, format_items_text(rows, page), reply_markup=items_keyboard(owner_id, rows, page))

@dp.callback_query(F.data.startswith("inv_potion_page:"))
async def inventory_potions_page(callback: CallbackQuery):
    _, owner_str, page_str = callback.data.split(":")
    owner_id = int(owner_str)
    page = int(page_str)
    if callback.from_user.id != owner_id:
        await callback.answer(TEXTS["inventory_open_category_1"], show_alert=True)
        return
    await callback.answer()

    row = await get_user(owner_id)
    upgrades = parse_upgrades(row[16])
    active_items = parse_equipped(row[18])
    stock = parse_potion_stock(row[26])
    active = active_potions_now(row[23], active_items=active_items)
    brewing_potion, brewing_until = row[24], row[25]
    prestige_upgrades = parse_prestige_upgrades(row[28])
    await safe_edit_text(
        callback,
        format_potions_text(stock, active, brewing_potion, brewing_until, upgrades, page=page),
        reply_markup=potions_keyboard(stock, brewing_potion, brewing_until, owner_id, upgrades, prestige_upgrades=prestige_upgrades, page=page, active_items=active_items),
    )

@dp.callback_query(F.data == "noop")
async def noop_callback(callback: CallbackQuery):
    await callback.answer()

@dp.callback_query(F.data.startswith("equip:"))
async def toggle_equip(callback: CallbackQuery):
    parts = callback.data.split(":")
    owner_id = int(parts[1])
    item_key = parts[2]
    page = int(parts[3]) if len(parts) > 3 else 0
    query = unquote(parts[4]) if len(parts) > 4 else None
    if callback.from_user.id != owner_id:
        await callback.answer(TEXTS["toggle_equip_1"], show_alert=True)
        return
    if item_key in PASSIVE_ITEMS:
        await callback.answer(TEXTS["toggle_equip_2"], show_alert=True)
        return

    row = await get_user(owner_id)
    upgrades = parse_upgrades(row[16])
    prestige_upgrades = parse_prestige_upgrades(row[28])
    rows = await get_inventory(owner_id)
    inventory_map = {k: q for k, q in rows}
    max_slots = equipped_slots_max(upgrades, prestige_upgrades, coin_tree_slot_bonus(inventory_map))

    before = parse_equipped(row[18])

    if item_key in before:
        # Уже надет -> снимаем (как выключение бейджа).
        new_equipped = unequip_item(row[18], item_key)
        await db_exec("UPDATE users SET equipped_items = ? WHERE user_id = ?", (format_equipped(new_equipped), owner_id))
        await safe_edit_text(callback,
            format_boosters_text(rows, max_slots, page, query=query),
            reply_markup=boosters_keyboard(rows, new_equipped, owner_id, page, query=query),
        )
        await callback.answer(TEXTS["toggle_equip_4"])
        return

    if len(before) >= max_slots:
        # Лимит слотов занят -> блокируем, как с бейджами ("сначала выключи один").
        await callback.answer(TEXTS["toggle_equip_5"].format(v0=max_slots), show_alert=True)
        return

    new_equipped = equip_item(row[18], item_key, max_slots)
    await db_exec("UPDATE users SET equipped_items = ? WHERE user_id = ?", (format_equipped(new_equipped), owner_id))

    await safe_edit_text(callback, 
        format_boosters_text(rows, max_slots, page, query=query),
        reply_markup=boosters_keyboard(rows, new_equipped, owner_id, page, query=query),
    )
    await callback.answer(TEXTS["toggle_equip_4"])

CRAFT_RE = re.compile(r"^крафт(?:ы)?(?:\s+(.+))?$", re.IGNORECASE)

def craft_level_of(upgrades: dict) -> int:
    return upgrade_level(upgrades, "crafts")

def recipe_is_discovered(recipe: dict, inventory_map: dict) -> bool:
    """Как в Minecraft: рецепт «открыт» (виден в списке), если у игрока есть хотя бы
    1 шт. любого предметного ингредиента. Валюта (монеты/очки/💠/🉑) на открытие не влияет —
    только на возможность реально скрафтить (см. recipe_missing_ingredients)."""
    ingredients = recipe.get("ingredients", {})
    if not ingredients and not recipe.get("needs_all_amulets"):
        return True
    for ing_key in ingredients:
        if inventory_map.get(ing_key, 0) > 0:
            return True
    if recipe.get("needs_all_amulets"):
        if any(inventory_map.get(ing_key, 0) > 0 for ing_key in ALL_PLAYER_AMULETS):
            return True
    return False

def available_recipes(craft_level: int, inventory_map: dict, query: str = None) -> list:
    """Рецепты, доступные по уровню крафта игрока И уже «открытые» (есть хотя бы 1 нужный
    предмет в инвентаре — валюта не считается), отфильтрованные по подстроке в названии результата."""
    result = []
    for key, recipe in RECIPES.items():
        if recipe["level"] > craft_level:
            continue
        if not recipe_is_discovered(recipe, inventory_map):
            continue
        if query and query.lower() not in ITEMS[key][1].lower():
            continue
        result.append(key)
    return result

def crafts_keyboard(recipe_keys: list, user_id: int, page: int = 0, query: str = "") -> InlineKeyboardMarkup:
    page_items, page, total_pages = _paginate(recipe_keys, page)

    rows = []
    for key in page_items:
        emoji, name, _, _ = ITEMS[key]
        rows.append([InlineKeyboardButton(
            text=f"{plain_emoji(emoji)} Скрафтить {name}",
            callback_data=f"craft:{user_id}:{key}",
        )])

    nav_row = _pagination_row("craft_page", user_id, page, total_pages, extra=query)
    if nav_row:
        rows.append(nav_row)
    return InlineKeyboardMarkup(inline_keyboard=rows)

def format_crafts_text(recipe_keys: list, craft_level: int, query: str, page: int = 0) -> str:
    if not recipe_keys:
        if query:
            return f"🔨 Нет доступных рецептов по запросу «{esc(query)}» (либо не хватает уровня крафта, либо нет ни одного нужного ингредиента в инвентаре)."
        return (
            f"🔨 Нет открытых рецептов ({craft_level}/{CRAFT_MAX_LEVEL} ур. крафта).\n"
            f"Рецепт появляется в списке, когда у тебя есть хотя бы 1 нужный предмет — "
            f"добывай ингредиенты в кейсах и качай апгрейд «Крафты» в прокачке!"
        )

    page_keys, page, total_pages = _paginate(recipe_keys, page)
    page_suffix = f" — стр. {page + 1}/{total_pages}" if total_pages > 1 else ""
    lines = [f"🔨 <b>Доступные рецепты</b> (уровень крафта {craft_level}/{CRAFT_MAX_LEVEL}){page_suffix}:\n"]
    for key in page_keys:
        emoji, name, _, _ = ITEMS[key]
        lines.append(f"{emoji} <b>{esc(name)}</b> = {esc(format_recipe_requirements(RECIPES[key]))}")
    return "\n".join(lines)

@dp.message(F.text.regexp(r"(?i)^крафт(ы)?(\s+.+)?$"))
async def crafts_command(message: Message):
    match = CRAFT_RE.match(message.text.strip())
    if not match:
        return
    query = (match.group(1) or "").strip() or None

    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"
    row = await ensure_user(user_id, username)
    upgrades = parse_upgrades(row[16])
    craft_level = craft_level_of(upgrades)
    inv_rows = await get_inventory(user_id)
    inventory_map = {k: q for k, q in inv_rows}

    recipe_keys = available_recipes(craft_level, inventory_map, query)
    await message.reply(
        format_crafts_text(recipe_keys, craft_level, query or "", 0),
        reply_markup=crafts_keyboard(recipe_keys, user_id, 0, query or "") if recipe_keys else None,
    )

@dp.callback_query(F.data.startswith("craft_page:"))
async def crafts_page_nav(callback: CallbackQuery):
    parts = callback.data.split(":", 3)
    owner_id = int(parts[1])
    page = int(parts[2])
    query = parts[3] if len(parts) > 3 and parts[3] else None
    if callback.from_user.id != owner_id:
        await callback.answer(TEXTS["craft_do_1"], show_alert=True)
        return
    await callback.answer()

    row = await get_user(owner_id)
    upgrades = parse_upgrades(row[16])
    craft_level = craft_level_of(upgrades)
    inv_rows = await get_inventory(owner_id)
    inventory_map = {k: q for k, q in inv_rows}
    recipe_keys = available_recipes(craft_level, inventory_map, query)

    await safe_edit_text(callback, 
        format_crafts_text(recipe_keys, craft_level, query or "", page),
        reply_markup=crafts_keyboard(recipe_keys, owner_id, page, query or "") if recipe_keys else None,
    )

@dp.callback_query(F.data.startswith("craft:"))
async def craft_do(callback: CallbackQuery):
    _, owner_str, recipe_key = callback.data.split(":")
    owner_id = int(owner_str)
    if callback.from_user.id != owner_id:
        await callback.answer(TEXTS["craft_do_1"], show_alert=True)
        return
    if recipe_key not in RECIPES:
        await callback.answer(TEXTS["craft_do_2"], show_alert=True)
        return

    row = await get_user(owner_id)
    upgrades = parse_upgrades(row[16])
    prestige_upgrades = parse_prestige_upgrades(row[28])
    craft_level = craft_level_of(upgrades)
    recipe = RECIPES[recipe_key]

    if recipe["level"] > craft_level:
        await callback.answer(TEXTS["craft_do_3"].format(v0=recipe['level'], v1=craft_level), show_alert=True)
        return

    coins, score = row[5], row[2]
    craft_points = row[32]
    rebirth_points = row[14]
    inv_rows = await get_inventory(owner_id)
    inventory_map = {k: q for k, q in inv_rows}

    missing = recipe_missing_ingredients(inventory_map, coins, score, recipe, prestige_upgrades, craft_points, rebirth_points)
    if missing:
        await callback.answer("Не хватает: " + "; ".join(missing), show_alert=True)
        return

    for ing_key, qty in recipe.get("ingredients", {}).items():
        await remove_item(owner_id, ing_key, qty)
    for ing_key, qty in recipe.get("refund_ingredients", {}).items():
        await add_item(owner_id, ing_key, qty)
    if recipe.get("needs_all_amulets"):
        for ing_key in ALL_PLAYER_AMULETS:
            await remove_item(owner_id, ing_key, 1)
    if recipe.get("coin_cost"):
        discounted_cost = craft_coin_cost_with_discount(recipe["coin_cost"], prestige_upgrades)
        await db_exec("UPDATE users SET coins = coins - ? WHERE user_id = ?", (discounted_cost, owner_id))
    if recipe.get("score_cost"):
        await db_exec("UPDATE users SET score = score - ? WHERE user_id = ?", (recipe["score_cost"], owner_id))
    if recipe.get("craft_points_cost"):
        await db_exec(
            "UPDATE users SET craft_points = craft_points - ? WHERE user_id = ?",
            (recipe["craft_points_cost"], owner_id),
        )
    if recipe.get("rebirth_cost"):
        await db_exec(
            "UPDATE users SET rebirth_points = rebirth_points - ? WHERE user_id = ?",
            (recipe["rebirth_cost"], owner_id),
        )

    await add_item(owner_id, recipe_key, 1)
    await db_exec("UPDATE users SET crafts_done = crafts_done + 1 WHERE user_id = ?", (owner_id,))

    emoji, name, _, _ = ITEMS[recipe_key]
    result_text = f"✅ Скрафтил {emoji} {name}!"

    await callback.message.reply(result_text)
    await callback.answer(TEXTS["craft_do_4"])

def case_offer_keyboard(case_num: int, user_id: int, price: int) -> InlineKeyboardMarkup:
    case = CASES[case_num]
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=f"🎁 Открыть {case['name']} ({price} 🪙)", callback_data=f"buy_case:{case_num}:{user_id}")
    ]])

def format_case_inspect_text(case_num: int, price: int, base_price: int) -> str:
    case = CASES[case_num]
    discount_line = f" (скидка, было {base_price} 🪙)" if price != base_price else ""
    lines = [f"📦 <b>{esc(case['name'])}</b>", f"Цена: {price} 🪙{discount_line}", "", "Возможный дроп:"]
    for _k, emoji, name, percent, chance in case_drop_table(case_num):
        boost_part = f" (+{percent}%)" if percent else ""
        lines.append(f"{emoji} {esc(name)}{boost_part} — {chance}%")
    return "\n".join(lines)

async def send_case_inspect(message: Message, case_num: int):
    """Меню осмотра кейса: список дропа с процентами + кнопка открытия."""
    case = CASES.get(case_num)
    if not case:
        await message.reply(TEXTS["send_case_inspect_1"])
        return
    row = await ensure_user(message.from_user.id, message.from_user.username or message.from_user.first_name or "Без имени")
    upgrades = parse_upgrades(row[16])
    price = case_price_with_discount(case["price"], upgrades)
    await message.reply(
        format_case_inspect_text(case_num, price, case["price"]),
        reply_markup=case_offer_keyboard(case_num, message.from_user.id, price),
    )

async def open_case_instant(message: Message, case_num: int):
    """'открыть кейс N' — мгновенная рулетка, минуя меню осмотра."""
    case = CASES.get(case_num)
    if not case:
        await message.reply(TEXTS["open_case_instant_1"])
        return

    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"
    row = await ensure_user(user_id, username)
    coins = row[5]
    upgrades = parse_upgrades(row[16])
    auto_sell_enabled = bool(row[30])
    auto_sell_items = parse_auto_sell_items(row[31])
    price = case_price_with_discount(case["price"], upgrades)

    if coins < price:
        await message.reply(TEXTS["open_case_instant_2"].format(v0=price, v1=coins))
        return

    item_key = roll_case_item(case_num)
    emoji, name, percent, _ = ITEMS[item_key]

    await db_exec(
        "UPDATE users SET coins = coins - ?, cases_opened = cases_opened + 1 WHERE user_id = ?",
        (price, user_id),
    )
    _sold_for, sold_text = await apply_case_reward(user_id, item_key, upgrades, auto_sell_enabled, auto_sell_items)
    new_coins = coins - price + _sold_for

    await message.reply(TEXTS["open_case_instant_3"].format(v0=emoji, v1=esc(name), v2=percent, v3=new_coins) + sold_text)

@dp.message(F.text.lower() == "кейс")
async def case_default(message: Message):
    await send_case_inspect(message, 1)

@dp.message(F.text.lower().regexp(r"^кейс \d+$"))
async def case_numbered(message: Message):
    match = CASE_NUM_RE.match(message.text.strip().lower())
    await send_case_inspect(message, int(match.group(1)))

@dp.message(F.text.lower().regexp(r"^(осмотреть кейс|осмотр кейс)\s+(\d+)$"))
async def case_inspect_command(message: Message):
    match = re.match(r"^(?:осмотреть кейс|осмотр кейс)\s+(\d+)$", message.text.strip().lower())
    await send_case_inspect(message, int(match.group(1)))

@dp.message(F.text.lower().regexp(r"^открыть кейс\s+(\d+)$"))
async def case_open_command(message: Message):
    match = re.match(r"^открыть кейс\s+(\d+)$", message.text.strip().lower())
    await open_case_instant(message, int(match.group(1)))

@dp.message(F.text.lower() == "кейсы")
async def case_list(message: Message):
    user_id = message.from_user.id
    row = await ensure_user(user_id, message.from_user.username or message.from_user.first_name or "Без имени")
    upgrades = parse_upgrades(row[16])
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"{case['name']} ({case_price_with_discount(case['price'], upgrades)} 🪙)",
            callback_data=f"inspect_case:{num}:{user_id}",
        )]
        for num, case in CASES.items()
    ])
    await message.reply(TEXTS["case_list_1"], reply_markup=kb)

@dp.callback_query(F.data.startswith("inspect_case:"))
async def inspect_case_callback(callback: CallbackQuery):
    _, case_num_str, owner_str = callback.data.split(":")
    case_num = int(case_num_str)
    owner_id = int(owner_str)
    if callback.from_user.id != owner_id:
        await callback.answer(TEXTS["inspect_case_callback_1"], show_alert=True)
        return
    await callback.answer()

    row = await get_user(owner_id)
    upgrades = parse_upgrades(row[16])
    case = CASES[case_num]
    price = case_price_with_discount(case["price"], upgrades)

    await safe_edit_text(callback, 
        format_case_inspect_text(case_num, price, case["price"]),
        reply_markup=case_offer_keyboard(case_num, owner_id, price),
    )

@dp.callback_query(F.data.startswith("buy_case:"))
async def buy_case(callback: CallbackQuery):
    _, case_num_str, owner_str = callback.data.split(":")
    case_num = int(case_num_str)
    owner_id = int(owner_str)
    if callback.from_user.id != owner_id:
        await callback.answer(TEXTS["buy_case_1"], show_alert=True)
        return

    case = CASES[case_num]

    row = await get_user(owner_id)
    coins = row[5]
    upgrades = parse_upgrades(row[16])
    auto_sell_enabled = bool(row[30])
    auto_sell_items = parse_auto_sell_items(row[31])
    price = case_price_with_discount(case["price"], upgrades)

    if coins < price:
        await callback.answer(TEXTS["buy_case_2"].format(v0=price), show_alert=True)
        return

    item_key = roll_case_item(case_num)
    emoji, name, percent, _ = ITEMS[item_key]

    await db_exec(
        "UPDATE users SET coins = coins - ?, cases_opened = cases_opened + 1 WHERE user_id = ?",
        (price, owner_id),
    )
    sold_for, sold_text = await apply_case_reward(owner_id, item_key, upgrades, auto_sell_enabled, auto_sell_items)
    new_coins = coins - price + sold_for

    await safe_edit_text(callback, 
        f"🎉 Выпало: {emoji} {esc(name)} (+{percent}%)!{sold_text}\nОстаток монет: {new_coins} 🪙",
        reply_markup=case_offer_keyboard(case_num, owner_id, price),
    )
    await callback.answer(TEXTS["buy_case_3"])

async def apply_coin_tree_save(user_id: int, inventory_map: dict, event: str, score: int, evolution_level: int) -> dict:
    """Гарантированный сейв % очков/эво при эволюции или перерождении от 🟢/🟣/⚪️ монет дерева.
    event: "evolution" или "rebirth". Работает пассивно (монеты лежат в инвентаре, экипировать
    не нужно). Если у игрока есть несколько подходящих монет — действует только САМАЯ СИЛЬНАЯ:
    ⚪️ Монета Пробуждения (работает и на эво, и на перерождение) > специфичная монета события
    (🟢 только эво, 🟣 только перерождение). При срабатывании 1% шанс +3 очка престижа и
    0.01% шанс на бейдж "Инвестировал в #####" — только у ⚪️ Монеты Пробуждения.
    Возвращает {"kept_score": int, "kept_evolution": int, "extra_text": str}."""
    kept_score = 0
    kept_evolution = 0
    extra_text = ""
    pct = 0.0
    coin_label = ""

    if inventory_map.get("awakening_coin", 0) > 0:
        pct = AWAKENING_COIN_SAVE_PCT
        coin_label = f"{PREMIUM_AWAKENING_COIN} Монета Пробуждения"
    elif event == "evolution" and inventory_map.get("evolution_coin", 0) > 0:
        pct = EVOLUTION_COIN_SAVE_PCT
        coin_label = f"{PREMIUM_EVOLUTION_COIN} Монета Эволюции"
    elif event == "rebirth" and inventory_map.get("rebirth_coin", 0) > 0:
        pct = REBIRTH_COIN_SAVE_PCT
        coin_label = f"{PREMIUM_REBIRTH_COIN} Монета Перерождения"

    if pct > 0:
        kept_score = round(score * pct)
        if event == "rebirth" or inventory_map.get("awakening_coin", 0) > 0:
            kept_evolution = round(evolution_level * pct)
        extra_text += f"\n{coin_label}: сохранено {round(pct * 100)}% ({kept_score} очков ноги{f' и {kept_evolution} ур. эво' if kept_evolution else ''})!"

        if inventory_map.get("awakening_coin", 0) > 0:
            if random.random() < AWAKENING_COIN_PRESTIGE_CHANCE:
                await db_exec(
                    "UPDATE users SET prestige_points = prestige_points + ? WHERE user_id = ?",
                    (AWAKENING_COIN_PRESTIGE_AMOUNT, user_id),
                )
                extra_text += f"\n{PREMIUM_AWAKENING_COIN} Монета Пробуждения: +{AWAKENING_COIN_PRESTIGE_AMOUNT}🔮 очка престижа!"
            if random.random() < AWAKENING_COIN_BADGE_CHANCE:
                await add_promo_badge(user_id, "investor")
                badge_emoji, badge_name = PROMO_BADGES["investor"]
                extra_text += f"\n{PREMIUM_AWAKENING_COIN} Монета Пробуждения: выпал бейдж {badge_emoji} «{badge_name}»!"

    return {"kept_score": kept_score, "kept_evolution": kept_evolution, "extra_text": extra_text}

async def evo_level_unlock_text(user_id: int, evolution_level: int) -> str:
    """Общая точка разблокировок за уровень эволюции — вызывается и из авто-эво (каскадно,
    на каждом промежуточном уровне), и из ручной «эволюция» (один уровень за раз), чтобы
    список разблокировок не расходился между ними."""
    if evolution_level == 1:
        return f"\nОткрыта фарма {FARM_EVOLVED[0]}-{FARM_EVOLVED[1]} очков и эмодзи 🦿 ({MEK_POINT} очков, до {MEK_LIMIT} раз в соо)!"
    if evolution_level == 2:
        await add_item(user_id, "star")
        return "\nПолучена ⭐️ Звезда перерождения — экипируй в инвентарь!"

    text = ""
    if evolution_level == EVO_UNLOCK_REBIRTH_SPARK_LEVEL:
        await add_item(user_id, "rebirth_spark")
        text += f"\nПолучена {ITEMS['rebirth_spark'][0]} Искра перерождения — сырьё для новых крафтов!"
    if evolution_level in EVO_LEG_UNLOCK_BY_LEVEL:
        emoji = EVO_LEG_UNLOCK_BY_LEVEL[evolution_level]
        tier = EVO_LEG_TIERS[emoji]
        text += f"\nОткрыты новые ноги {emoji} (+{tier['bonus_pct']}% к добыче робоног, лимит {tier['limit']} за сообщение)!"
    if evolution_level == EVO_UNLOCK_MEK2_LEVEL:
        text += f"\nДобыча команды «ферма» увеличена на +{EVO_FARM_BONUS_LVL10} очков!"
    if evolution_level == EVO_UNLOCK_NECKLACE_CRAFTS_LEVEL:
        text += "\nОткрыты новые крафты: Ожерелье из звёзд, Ожерелье пылающей звезды, Карманная звезда!"
    if evolution_level == EVO_FLOW_UNLOCK_LEVEL:
        text += f"\nОткрыт пассивный буст «Поток эволюции» — {round(EVO_FLOW_EXTRA_CHANCE * 100)}% шанс на доп. эволюцию сверху при каждой эволюции!"
    return text

async def try_auto_evolve(user_id: int, score: int, evolution_level: int, rebirth_count: int, active_items=None) -> tuple[int, int, str]:
    """VIP авто-эво: каскадно эволюционирует, пока очков хватает на след. эволюцию —
    например, если фарм разом принёс очков на 2 эволюции вперёд, сработают обе.
    Возвращает (итоговый evolution_level, итоговый score, текст для добавления к ответу)."""
    evolutions_done = 0
    unlock_text = ""
    score_before_last_reset = score
    while True:
        required = level_threshold(EVO_REQUIRED_BASE_LEVEL + evolution_level, evolution_level, rebirth_count, active_items)
        if score < required:
            break
        score_before_last_reset = score
        score = 0
        evolution_level += 1
        evolutions_done += 1
        unlock_text += await evo_level_unlock_text(user_id, evolution_level)
        if evolution_level >= EVO_FLOW_UNLOCK_LEVEL and random.random() < EVO_FLOW_EXTRA_CHANCE:
            evolution_level += 1
            evolutions_done += 1
            unlock_text += "\n🌊 Поток эволюции: доп. эволюция сверху!"
            unlock_text += await evo_level_unlock_text(user_id, evolution_level)

    if evolutions_done == 0:
        return evolution_level, score, ""

    inv_rows = await get_inventory(user_id)
    inventory_map = {k: q for k, q in inv_rows}
    coin_save_text = ""
    if inventory_map.get("evolution_coin", 0) > 0 or inventory_map.get("awakening_coin", 0) > 0:
        evolution_level += 1
        coin_save_text += "\n🟢 Дерево монет: доп. эволюция сверху!"
    save_result = await apply_coin_tree_save(user_id, inventory_map, "evolution", score_before_last_reset, evolution_level)
    score = save_result["kept_score"]
    coin_save_text += save_result["extra_text"]

    await db_exec("UPDATE users SET score = ?, evolution_level = ? WHERE user_id = ?", (score, evolution_level, user_id))
    times = f" ×{evolutions_done}" if evolutions_done > 1 else ""
    text = f"\n\n⚙️💎 Авто-эволюция{times}! Теперь {evolution_level} уровень эволюции.{unlock_text}{coin_save_text}"
    return evolution_level, score, text

@dp.message(F.text.lower() == "эволюция")
async def evolve(message: Message):
    if not await require_subscription(message):
        return
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"

    row = await ensure_user(user_id, username)
    score, evolution_level = row[2], row[3]
    rebirth_count = row[15]
    active_items = parse_equipped(row[18])

    required = level_threshold(EVO_REQUIRED_BASE_LEVEL + evolution_level, evolution_level, rebirth_count, active_items)
    if score < required:
        await message.reply(TEXTS["evolve_1"].format(v0=required))
        return

    new_evolution = evolution_level + 1

    ice_text = ""
    kept_score = 0
    if "ice_shard" in set(_normalize_active_items(active_items)) and random.random() < ICE_SHARD_SAVE_CHANCE:
        kept_score = score
        ice_text = "\n🧊 Ледяной осколок: очки ноги сохранены!"

    coin_save_text = ""
    if not kept_score:
        inv_rows = await get_inventory(user_id)
        inventory_map = {k: q for k, q in inv_rows}
        save_result = await apply_coin_tree_save(user_id, inventory_map, "evolution", score, evolution_level)
        kept_score = save_result["kept_score"]
        coin_save_text = save_result["extra_text"]
        if inventory_map.get("evolution_coin", 0) > 0 or inventory_map.get("awakening_coin", 0) > 0:
            new_evolution += 1
            coin_save_text += "\n🟢 Дерево монет: доп. эволюция сверху!"

    await db_exec("UPDATE users SET score = ?, evolution_level = ? WHERE user_id = ?", (kept_score, new_evolution, user_id))

    unlock_text = await evo_level_unlock_text(user_id, new_evolution)

    await message.reply(
        TEXTS["evolve_2"].format(v0=new_evolution, v1=round(EVO_HARDNESS_RATE * new_evolution * 100), v2=unlock_text + ice_text + coin_save_text)
    )

@dp.message(F.text.lower() == "!ивент ноги")
async def toggle_event(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)

    active = await is_event_active()
    new_value = "0" if active else "1"
    await db_exec(
        "INSERT INTO settings (key, value) VALUES ('event_active', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (new_value,),
    )
    if new_value == "1":
        for key, value in (("event_multiplier", "2"), ("event_until", "0")):
            await db_exec(
                "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
    _invalidate_event_state_cache()

    if new_value == "1":
        await message.reply(TEXTS["toggle_event_1"])
    else:
        await message.reply(TEXTS["toggle_event_2"])

def format_upgrade_page_text(upgrades: dict, rebirth_points: int, category: int, craft_points: int = 0) -> str:
    craft_line = f"💠 Очки крафта: <code>{craft_points}</code>\n" if category == 3 else ""
    header = (
        f"⚙️ <b>МЕНЮ ПРОКАЧКИ</b> — {UPGRADE_CATEGORIES[category]}\n"
        f"🉑 Очки перерождения: <code>{rebirth_points}</code>\n"
        f"{craft_line}"
        f"━━━━━━━━━━━━━━━━━━\n"
    )
    return header

def upgrade_page_keyboard(upgrades: dict, user_id: int, category: int) -> InlineKeyboardMarkup:
    rows = []
    for key in UPGRADE_ORDER:
        cfg = UPGRADES[key]
        if cfg["category"] != category:
            continue
        level = upgrade_level(upgrades, key)
        if cfg.get("wip"):
            label = f"🔧 {cfg['name']} — {level}/{cfg['max_level']} (в разработке)"
            rows.append([InlineKeyboardButton(text=label, callback_data="upg_noop")])
            continue
        cost = upgrade_next_cost(key, upgrades)
        if cost is None:
            label = f"✅ {cfg['name']} — {level}/{cfg['max_level']} (макс)"
            rows.append([InlineKeyboardButton(text=label, callback_data="upg_noop")])
        else:
            extra = upgrade_next_extra_cost(key, upgrades)
            extra_part = f" + {extra[1]} {plain_emoji(PREMIUM_CRAFT_POINT)}" if extra else ""
            label = f"{cfg['name']} — {level}/{cfg['max_level']} ({cost} 🉑{extra_part})"
            rows.append([InlineKeyboardButton(text=label, callback_data=f"upg_buy:{user_id}:{category}:{key}")])

    nav = []
    for cat in (1, 2, 3):
        marker = "• " if cat == category else ""
        nav.append(InlineKeyboardButton(text=f"{marker}{cat}", callback_data=f"upg_page:{user_id}:{cat}"))
    rows.append(nav)
    return InlineKeyboardMarkup(inline_keyboard=rows)

@dp.message(F.text.lower().in_({"апгрейд", "прокачка", "апг"}))
async def upgrade_menu(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"

    row = await ensure_user(user_id, username)
    upgrades = parse_upgrades(row[16])
    rebirth_points = row[14]
    craft_points = row[32]

    await message.reply(
        format_upgrade_page_text(upgrades, rebirth_points, 1, craft_points),
        reply_markup=upgrade_page_keyboard(upgrades, user_id, 1),
    )

@dp.callback_query(F.data == "upg_noop")
async def upgrade_noop(callback: CallbackQuery):
    await callback.answer()

@dp.callback_query(F.data.startswith("upg_page:"))
async def upgrade_change_page(callback: CallbackQuery):
    _, owner_str, category_str = callback.data.split(":")
    owner_id = int(owner_str)
    category = int(category_str)
    if callback.from_user.id != owner_id:
        await callback.answer(TEXTS["upgrade_change_page_1"], show_alert=True)
        return
    await callback.answer()

    row = await get_user(owner_id)
    upgrades = parse_upgrades(row[16])
    rebirth_points = row[14]
    craft_points = row[32]
    await safe_edit_text(callback, 
        format_upgrade_page_text(upgrades, rebirth_points, category, craft_points),
        reply_markup=upgrade_page_keyboard(upgrades, owner_id, category),
    )

@dp.callback_query(F.data.startswith("upg_buy:"))
async def upgrade_buy(callback: CallbackQuery):
    _, owner_str, category_str, key = callback.data.split(":")
    owner_id = int(owner_str)
    category = int(category_str)
    if callback.from_user.id != owner_id:
        await callback.answer(TEXTS["upgrade_buy_1"], show_alert=True)
        return
    if key not in UPGRADES or UPGRADES[key].get("wip"):
        await callback.answer(TEXTS["upgrade_buy_2"], show_alert=True)
        return

    row = await get_user(owner_id)
    upgrades = parse_upgrades(row[16])
    rebirth_points = row[14]
    craft_points = row[32]
    cost = upgrade_next_cost(key, upgrades)

    if cost is None:
        await callback.answer(TEXTS["upgrade_buy_3"], show_alert=True)
        return
    if rebirth_points < cost:
        await callback.answer(TEXTS["upgrade_buy_4"].format(v0=cost, v1=rebirth_points), show_alert=True)
        return

    extra = upgrade_next_extra_cost(key, upgrades)
    extra_field, extra_amount = (extra if extra else (None, 0))
    if extra_field == "craft_points" and craft_points < extra_amount:
        await callback.answer(
            f"Нужно {extra_amount} 💠 очков крафта, у тебя {craft_points}.", show_alert=True
        )
        return

    upgrades[key] = upgrade_level(upgrades, key) + 1
    new_points = rebirth_points - cost
    new_craft_points = craft_points - extra_amount if extra_field == "craft_points" else craft_points
    await db_exec(
        "UPDATE users SET rebirth_points = ?, upgrades = ?, craft_points = ? WHERE user_id = ?",
        (new_points, format_upgrades(upgrades), new_craft_points, owner_id),
    )

    await safe_edit_text(callback, 
        format_upgrade_page_text(upgrades, new_points, category, new_craft_points),
        reply_markup=upgrade_page_keyboard(upgrades, owner_id, category),
    )
    await callback.answer(TEXTS["upgrade_buy_5"].format(v0=UPGRADES[key]['name'], v1=upgrades[key]))

def format_prestige_page_text(prestige_upgrades: dict, prestige_points: int, page: int) -> str:
    total_pages = (len(PRESTIGE_ORDER) - 1) // PRESTIGE_PAGE_SIZE + 1
    header = (
        f"🔮 <b>ДЕРЕВО ПРЕСТИЖА</b> — стр. {page + 1}/{total_pages}\n"
        f"🔮 Очки престижа: <code>{prestige_points}</code>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"Ветки бесконечны — чем выше уровень, тем реже растёт эффект, а цена растёт всегда.\n"
    )
    start = page * PRESTIGE_PAGE_SIZE
    lines = [header]
    for key in PRESTIGE_ORDER[start:start + PRESTIGE_PAGE_SIZE]:
        cfg = PRESTIGE_UPGRADES[key]
        level = prestige_level(prestige_upgrades, key)
        bonus = prestige_bonus(prestige_upgrades, key)
        cost = prestige_next_cost(key, prestige_upgrades)
        lines.append(
            f"{cfg['emoji']} <b>{cfg['name']}</b> — ур. {level} (эффект: {bonus})\n"
            f"   {cfg['desc']}\n"
            f"   Следующий уровень: {cost} 🔮"
        )
    return "\n".join(lines)

def prestige_page_keyboard(prestige_upgrades: dict, user_id: int, page: int) -> InlineKeyboardMarkup:
    total_pages = (len(PRESTIGE_ORDER) - 1) // PRESTIGE_PAGE_SIZE + 1
    start = page * PRESTIGE_PAGE_SIZE
    rows = []
    for key in PRESTIGE_ORDER[start:start + PRESTIGE_PAGE_SIZE]:
        cfg = PRESTIGE_UPGRADES[key]
        level = prestige_level(prestige_upgrades, key)
        cost = prestige_next_cost(key, prestige_upgrades)
        label = f"⬆️ {cfg['emoji']} {cfg['name']} ({cost} 🔮)"
        rows.append([InlineKeyboardButton(text=label, callback_data=f"pr_buy:{user_id}:{page}:{key}")])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️", callback_data=f"pr_page:{user_id}:{page - 1}", style="primary"))
    nav.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="pr_noop"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton(text="▶️", callback_data=f"pr_page:{user_id}:{page + 1}", style="primary"))
    rows.append(nav)
    return InlineKeyboardMarkup(inline_keyboard=rows)

@dp.message(F.text.lower() == "престиж")
async def prestige_menu(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"

    row = await ensure_user(user_id, username)
    prestige_upgrades = parse_prestige_upgrades(row[28])
    prestige_points = row[27]

    await message.reply(
        format_prestige_page_text(prestige_upgrades, prestige_points, 0),
        reply_markup=prestige_page_keyboard(prestige_upgrades, user_id, 0),
    )

@dp.callback_query(F.data == "pr_noop")
async def prestige_noop(callback: CallbackQuery):
    await callback.answer()

@dp.callback_query(F.data.startswith("pr_page:"))
async def prestige_change_page(callback: CallbackQuery):
    _, owner_str, page_str = callback.data.split(":")
    owner_id = int(owner_str)
    page = int(page_str)
    if callback.from_user.id != owner_id:
        await callback.answer(TEXTS["upgrade_change_page_1"], show_alert=True)
        return
    await callback.answer()

    row = await get_user(owner_id)
    prestige_upgrades = parse_prestige_upgrades(row[28])
    prestige_points = row[27]
    await safe_edit_text(callback, 
        format_prestige_page_text(prestige_upgrades, prestige_points, page),
        reply_markup=prestige_page_keyboard(prestige_upgrades, owner_id, page),
    )

@dp.callback_query(F.data.startswith("pr_buy:"))
async def prestige_buy(callback: CallbackQuery):
    _, owner_str, page_str, key = callback.data.split(":")
    owner_id = int(owner_str)
    page = int(page_str)
    if callback.from_user.id != owner_id:
        await callback.answer(TEXTS["upgrade_buy_1"], show_alert=True)
        return
    if key not in PRESTIGE_UPGRADES:
        await callback.answer(TEXTS["upgrade_buy_2"], show_alert=True)
        return

    row = await get_user(owner_id)
    prestige_upgrades = parse_prestige_upgrades(row[28])
    prestige_points = row[27]
    cost = prestige_next_cost(key, prestige_upgrades)

    if prestige_points < cost:
        await callback.answer(TEXTS["prestige_buy_4"].format(v0=cost, v1=prestige_points), show_alert=True)
        return

    prestige_upgrades[key] = prestige_level(prestige_upgrades, key) + 1
    new_points = prestige_points - cost
    await db_exec(
        "UPDATE users SET prestige_points = ?, prestige_upgrades = ? WHERE user_id = ?",
        (new_points, format_prestige_upgrades(prestige_upgrades), owner_id),
    )

    await safe_edit_text(callback, 
        format_prestige_page_text(prestige_upgrades, new_points, page),
        reply_markup=prestige_page_keyboard(prestige_upgrades, owner_id, page),
    )
    await callback.answer(TEXTS["upgrade_buy_5"].format(v0=PRESTIGE_UPGRADES[key]['name'], v1=prestige_upgrades[key]))

async def compute_rebirth_result(user_id: int, score: int, evolution_level: int, rebirth_points: int, rebirth_count: int,
                                  prestige_points: int, prestige_upgrades: dict, active_items, inventory_map: dict) -> dict:
    """Считает результат перерождения (в т.ч. проки дерева монет, требующие БД) — общая логика
    для ручной команды «перерождение» и авто-перерождения (см. try_auto_rebirth)."""
    points_gained = (evolution_level // REBIRTH_EVO_STEP) * REBIRTH_POINTS_PER_STEP
    new_rebirth_points = rebirth_points + points_gained
    new_rebirth_count = rebirth_count + 1

    extra_text = ""
    echo_chance = 0.01 * prestige_bonus(prestige_upgrades, "p_echo")
    if echo_chance > 0 and random.random() < echo_chance:
        new_rebirth_points += 1
        extra_text += "\n🔮 Эхо сработало: +1 доп. Очко Перерождения!"

    new_prestige_points = prestige_points + PRESTIGE_PER_REBIRTH

    kept_evolution = 0
    kept_score = 0
    if "ice_shard" in set(_normalize_active_items(active_items)) and random.random() < ICE_SHARD_SAVE_CHANCE:
        kept_evolution = evolution_level
        extra_text += "\n🧊 Ледяной осколок: уровень эволюции сохранён!"
    else:
        save_result = await apply_coin_tree_save(user_id, inventory_map, "rebirth", score, evolution_level)
        kept_score = save_result["kept_score"]
        kept_evolution = save_result["kept_evolution"]
        extra_text += save_result["extra_text"]

    return {
        "points_gained": points_gained,
        "kept_evolution": kept_evolution,
        "kept_score": kept_score,
        "rebirth_points": new_rebirth_points,
        "rebirth_count": new_rebirth_count,
        "prestige_points": new_prestige_points,
        "extra_text": extra_text,
    }

async def try_auto_rebirth(user_id: int, score: int, evolution_level: int, rebirth_count: int,
                            rebirth_points: int, prestige_points: int, prestige_upgrades: dict,
                            active_items=None) -> tuple[int, int, int, int, int, str]:
    """VIP авто-перерождение: срабатывает само, как только эволюция достигает REBIRTH_MIN_EVO
    (см. auto_rebirth_on/off). Возвращает (score, evolution_level, rebirth_count, rebirth_points,
    prestige_points, текст для добавления к ответу)."""
    if evolution_level < REBIRTH_MIN_EVO:
        return score, evolution_level, rebirth_count, rebirth_points, prestige_points, ""

    inv_rows = await get_inventory(user_id)
    inventory_map = {k: q for k, q in inv_rows}
    result = await compute_rebirth_result(user_id, score, evolution_level, rebirth_points, rebirth_count, prestige_points, prestige_upgrades, active_items, inventory_map)
    await db_exec(
        "UPDATE users SET score = ?, evolution_level = ?, rebirth_points = ?, rebirth_count = ?, "
        "prestige_points = ? WHERE user_id = ?",
        (result["kept_score"], result["kept_evolution"], result["rebirth_points"], result["rebirth_count"], result["prestige_points"], user_id),
    )
    text = f"\n♻️ Авто-перерождение: +{result['points_gained']}🉑 (всего {result['rebirth_points']}🉑)" + result["extra_text"]
    return result["kept_score"], result["kept_evolution"], result["rebirth_count"], result["rebirth_points"], result["prestige_points"], text

@dp.message(F.text.lower() == "перерождение")
async def rebirth(message: Message):
    if not await require_subscription(message):
        return
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"

    row = await ensure_user(user_id, username)
    score, evolution_level = row[2], row[3]
    rebirth_points, rebirth_count = row[14], row[15]
    prestige_points = row[27]
    prestige_upgrades = parse_prestige_upgrades(row[28])
    active_items = parse_equipped(row[18])

    if evolution_level < REBIRTH_MIN_EVO:
        await message.reply(
            TEXTS["rebirth_1"].format(v0=REBIRTH_MIN_EVO, v1=evolution_level, v2=REBIRTH_MIN_EVO)
        )
        return

    inv_rows = await get_inventory(user_id)
    inventory_map = {k: q for k, q in inv_rows}
    result = await compute_rebirth_result(user_id, score, evolution_level, rebirth_points, rebirth_count, prestige_points, prestige_upgrades, active_items, inventory_map)

    await db_exec(
        "UPDATE users SET score = ?, evolution_level = ?, rebirth_points = ?, rebirth_count = ?, "
        "prestige_points = ? WHERE user_id = ?",
        (result["kept_score"], result["kept_evolution"], result["rebirth_points"], result["rebirth_count"], result["prestige_points"], user_id),
    )

    new_hardness = round(REBIRTH_HARDNESS_STEP * result["rebirth_count"] * 100)
    await message.reply(
        TEXTS["rebirth_2"].format(v0=result["points_gained"], v1=result["rebirth_points"], v2=new_hardness, v3=PRESTIGE_PER_REBIRTH) + result["extra_text"]
    )

def ultra_rebirth_eligible(evolution_level: int, leg_level: int, rebirth_count: int,
                            has_awakening_coin: bool, has_chronos_orb: bool) -> bool:
    """Все пять условий обязательны одновременно (см. константы ULTRA_REQUIRED_*):
    эволюция, уровень ноги, число перерождений, а также владение Монетой Пробуждения
    и Хвостом Джевила (просто лежат в инвентаре — экипировать не нужно, не расходуются)."""
    return (
        evolution_level >= ULTRA_REQUIRED_EVO
        and leg_level >= ULTRA_REQUIRED_LEG_LEVEL
        and rebirth_count >= ULTRA_REQUIRED_REBIRTHS
        and has_awakening_coin
        and has_chronos_orb
    )

def ultra_rebirth_confirm_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🌌 Подтвердить", callback_data=f"ultra_ok:{user_id}", style="success"),
        InlineKeyboardButton(text="Отмена", callback_data=f"ultra_no:{user_id}", style="danger"),
    ]])

@dp.message(F.text.lower() == "ультра перерождение")
async def ultra_rebirth_info(message: Message):
    """Показывает статус условий и, если всё готово, просит подтверждение кнопкой —
    Ультра перерождение необратимо и выполняется только один раз за игру."""
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"

    row = await ensure_user(user_id, username)
    score, evolution_level = row[2], row[3]
    rebirth_count = row[15]
    ultra_rebirth = bool(row[21])

    if ultra_rebirth:
        await message.reply(TEXTS["ultra_rebirth_already_1"])
        return

    leg_level = get_level_index(score, evolution_level, rebirth_count)

    inv_rows = await get_inventory(user_id)
    inventory_map = {k: q for k, q in inv_rows}
    has_awakening_coin = inventory_map.get("awakening_coin", 0) > 0
    has_chronos_orb = inventory_map.get("chronos_orb", 0) > 0

    if not ultra_rebirth_eligible(evolution_level, leg_level, rebirth_count, has_awakening_coin, has_chronos_orb):
        await message.reply(
            TEXTS["ultra_rebirth_locked_1"].format(
                v0=evolution_level, v1=ULTRA_REQUIRED_EVO,
                v2=leg_level, v3=ULTRA_REQUIRED_LEG_LEVEL,
                v4=rebirth_count, v5=ULTRA_REQUIRED_REBIRTHS,
                v6="✅" if has_awakening_coin else "❌",
                v7="✅" if has_chronos_orb else "❌",
            )
        )
        return

    await message.reply(
        TEXTS["ultra_rebirth_confirm_1"].format(
            v0=ULTRA_LEG_EMOJI, v1=esc(ULTRA_LEG_NAME), v2=ULTRA_LEG_LEVEL,
            v3=round(ULTRA_REBIRTH_BOOST * 100),
        ),
        reply_markup=ultra_rebirth_confirm_keyboard(user_id),
    )

@dp.callback_query(F.data.startswith("ultra_no:"))
async def ultra_rebirth_cancel(callback: CallbackQuery):
    owner_id = int(callback.data.split(":")[1])
    if callback.from_user.id != owner_id:
        await callback.answer(TEXTS["ultra_rebirth_not_owner_1"], show_alert=True)
        return
    await callback.answer()
    await safe_edit_text(callback, TEXTS["ultra_rebirth_cancelled_1"])

@dp.callback_query(F.data.startswith("ultra_ok:"))
async def ultra_rebirth_confirm(callback: CallbackQuery):
    owner_id = int(callback.data.split(":")[1])
    if callback.from_user.id != owner_id:
        await callback.answer(TEXTS["ultra_rebirth_not_owner_1"], show_alert=True)
        return

    user_id = callback.from_user.id
    username = callback.from_user.username or callback.from_user.first_name or "Без имени"

    row = await ensure_user(user_id, username)
    score, evolution_level = row[2], row[3]
    rebirth_count = row[15]
    ultra_rebirth = bool(row[21])

    if ultra_rebirth:
        await safe_edit_text(callback, TEXTS["ultra_rebirth_already_1"])
        await callback.answer()
        return

    leg_level = get_level_index(score, evolution_level, rebirth_count)

    inv_rows = await get_inventory(user_id)
    inventory_map = {k: q for k, q in inv_rows}
    has_awakening_coin = inventory_map.get("awakening_coin", 0) > 0
    has_chronos_orb = inventory_map.get("chronos_orb", 0) > 0

    if not ultra_rebirth_eligible(evolution_level, leg_level, rebirth_count, has_awakening_coin, has_chronos_orb):
        await safe_edit_text(
            callback,
            TEXTS["ultra_rebirth_locked_1"].format(
                v0=evolution_level, v1=ULTRA_REQUIRED_EVO,
                v2=leg_level, v3=ULTRA_REQUIRED_LEG_LEVEL,
                v4=rebirth_count, v5=ULTRA_REQUIRED_REBIRTHS,
                v6="✅" if has_awakening_coin else "❌",
                v7="✅" if has_chronos_orb else "❌",
            ),
        )
        await callback.answer()
        return

    prestige_points = row[27]
    new_prestige_points = prestige_points + PRESTIGE_PER_ULTRA_REBIRTH
    await db_exec(
        "UPDATE users SET score = 0, evolution_level = 0, rebirth_points = 0, rebirth_count = 0, "
        "ultra_rebirth = 1, prestige_points = ? WHERE user_id = ?",
        (new_prestige_points, user_id),
    )

    await safe_edit_text(
        callback,
        TEXTS["ultra_rebirth_success_1"].format(
            v0=ULTRA_LEG_EMOJI, v1=esc(ULTRA_LEG_NAME), v2=ULTRA_LEG_LEVEL,
            v3=round(ULTRA_REBIRTH_BOOST * 100), v4=PRESTIGE_PER_ULTRA_REBIRTH,
        ),
    )
    await callback.answer()

@dp.message(F.text.lower() == "баланс")
async def show_balance(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"

    row = await ensure_user(user_id, username)
    score, coins = row[2], row[5]
    vip_until = row[12]
    rebirth_points, rebirth_count = row[14], row[15]
    craft_points = row[32]
    vip_active = is_vip_active(vip_until)

    vip_line = f"{PREMIUM_VIP_BADGE} VIP активен" if vip_active else "VIP не активен"

    await message.reply(
        TEXTS["show_balance_1"].format(
            v0=score, v1=coins, v2=rebirth_points, v3=rebirth_count, v4=vip_line, v5=craft_points
        )
    )

HELP_SECTION_ALIASES = {
    "бейдж": "бейдж", "бейджи": "бейдж", "значок": "бейдж", "значки": "бейдж",
    "бустер": "бустер", "бустеры": "бустер",
    "предмет": "предмет", "предметы": "предмет",
    "зелье": "зелье", "зелья": "зелье", "зелий": "зелье",
    "команда": "команда", "команды": "команда",
}

# Справочник для «помощь команда <название>»: ключ -> (эмодзи, алиасы команды, описание).
# Первый алиас — «каноничное» отображаемое имя команды.
HELP_COMMANDS = {
    "farm": ("🦵", ["ферма", "фарма"],
             "Основная команда добычи очков ноги — жми регулярно (или отправляй 🦵/🦿), копится опыт для эволюций и перерождений."),
    "bonus": ("🎁", ["бонус"],
              "Ежедневная награда очками ноги — стрик за подряд идущие дни. На 5-й день серии дополнительно даёт Дневной амулет."),
    "upgrade": ("⬆️", ["апгрейд", "прокачка", "апг"],
                "Прокачка постоянных улучшений за очки перерождения/крафта: лимиты, скорость варки зелий, слоты бустеров и т.д."),
    "craft": ("🛠", ["крафт", "крафты"],
              "Меню крафта — соединяй предметы/бустеры по рецептам и получай более сильные вещи (вплоть до Эссенции Бога)."),
    "case": ("🎰", ["кейс", "кейсы"],
             "Открытие кейсов за монеты — выпадают случайные предметы и бустеры из пула конкретного кейса."),
    "evolution": ("🧬", ["эволюция"],
                  "Переход на новый уровень эволюции при достижении нужного количества очков ноги — открывает новые возможности."),
    "prestige": ("🌟", ["престиж"],
                 "Система престижа — сброс части прогресса ради постоянных бонусов более высокого порядка."),
    "rebirth": ("🉑", ["перерождение"],
                "Сбрасывает ногу и эволюцию, взамен даёт очки перерождения — их тратят на апгрейды и крафт уникальных бустеров."),
    "ultra_rebirth": ("💫", ["ультра перерождение"],
                       "Разовый необратимый прыжок за грань обычного мира: обнуляет ногу, эволюцию и перерождения, "
                       "но взамен открывает второй, ULTRA-мир уровней (потолок улетает с 20001 в астрономические дали), "
                       "даёт постоянный буст добычи и очки престижа (отдельная валюта для престиж-апгрейдов). "
                       "Условия: эволюция 50+, уровень ноги 20001+, 5+ перерождений, а также Монета Пробуждения и Хвост Джевила в инвентаре."),
    "exchange": ("💱", ["обменять"],
                 "Обменивает очки ноги на монеты по фиксированному курсу: «обменять <число>»."),
    "inventory": ("🎒", ["инвентарь", "мой инвентарь"],
                  "Общее меню инвентаря — оттуда переходишь в разделы Бустеры/Предметы/Зелья."),
    "boosters": ("🧪", ["бустеры", "мои бустеры"],
                 "Список твоих бустеров с возможностью экипировать/снять прямо из меню."),
    "items": ("📦", ["предметы", "мои предметы"],
              "Список твоих обычных предметов (сырьё для крафта, коллекционные вещи)."),
    "potions": ("⚗️", ["зелья", "мои зелья"],
                "Меню зелий — варка в котле, забор готового и использование, все кнопками."),
    "give": ("🤝", ["дать", "передать"],
             "Передать другому игроку (ответом на его сообщение) монеты, очки ноги или предмет из своего инвентаря: «дать 100 коин», «дать эссенция дружбы»."),
    "sell": ("💰", ["продать"],
             "Продажа бустеров/предметов из инвентаря за монеты по фиксированной цене: «продать б <название>» / «продать п <название>»."),
    "destroy": ("🗑", ["уничтожение"],
                "Безвозвратно уничтожает бустер/предмет из инвентаря (без монет взамен) — полезно для нетоварных вещей: «уничтожение б/п <название>»."),
    "balance": ("💳", ["баланс"],
                "Показывает текущий баланс: очки ноги, монеты, очки перерождения/крафта и статус VIP."),
    "vip": ("💎", ["вип"],
            "Информация о VIP-статусе и его покупке — постоянный сильный бустер и доступ к особым фичам."),
    "badges_toggle": ("🏷", ["бейджи"],
                       "Меню управления своими бейджами — какие показывать рядом с ником в топах."),
    "top": ("🏆", ["топ ног", "топ эво", "топ коин", "топ очкп"],
            "Топы игроков по разным метрикам (ноги/эволюция/монеты/очки перерождения), в своём чате или глобально («гл топ ...»)."),
    "info": ("ℹ️", ["инфо"],
             "Показывает игровую карточку другого игрока по юзернейму: «инфо @ник»."),
    "promo": ("🎟", ["промокод", "промо"],
              "Активирует промокод и выдаёт награду, если код существует и ещё не использован тобой: «промокод <код>»."),
    "nick": ("✏️", ["+ник", "-ник"],
             "Устанавливает или сбрасывает отображаемый игровой ник: «+ник <текст>» / «-ник»."),
    "help": ("❓", ["помощь"],
             "Эта самая справка — «помощь бустер/предмет/зелье/бейдж/команда <название>»."),
}

def find_help_command_key(query: str):
    """Ищет ключ HELP_COMMANDS по названию/алиасу команды. Сначала точное совпадение,
    иначе — по вхождению подстроки в любой алиас. Возвращает (key, None) при однозначном
    совпадении, (None, [варианты]) при неоднозначности, (None, []) если не найдено."""
    q = (query or "").strip().lower()
    if not q:
        return None, []
    for key, (_, aliases, _) in HELP_COMMANDS.items():
        if q in (a.lower() for a in aliases):
            return key, None
    matches = [key for key, (_, aliases, _) in HELP_COMMANDS.items() if any(q in a.lower() for a in aliases)]
    if len(matches) == 1:
        return matches[0], None
    if len(matches) > 1:
        matches.sort(key=lambda k: HELP_COMMANDS[k][1][0])
        return None, matches
    return None, []

@dp.message(F.text.lower() == "помощь")
async def help_root(message: Message):
    await message.reply(TEXTS["help_root_1"])

@dp.message(F.text.regexp(r"(?i)^помощь\s+(\S+)(?:\s+(.+))?$"))
async def help_dispatch(message: Message):
    match = re.match(r"(?i)^помощь\s+(\S+)(?:\s+(.+))?$", message.text.strip())
    raw_section = match.group(1).strip().lower()
    query = (match.group(2) or "").strip()

    section = HELP_SECTION_ALIASES.get(raw_section)
    if not section:
        await message.reply(TEXTS["help_unknown_section_1"].format(v0=esc(match.group(1))))
        return

    if section == "бейдж":
        await help_badge(message, query)
        return

    if section == "бустер":
        await help_booster(message, query)
        return

    if section == "предмет":
        await help_item(message, query)
        return

    if section == "зелье":
        await help_potion(message, query)
        return

    if section == "команда":
        await help_command(message, query)
        return

    await message.reply(TEXTS["help_unknown_section_1"].format(v0=esc(raw_section)))

async def help_badge(message: Message, query: str):
    if not query:
        await message.reply(TEXTS["help_badge_general_1"])
        return

    key, matches = find_help_badge_key(query)
    if key:
        emoji, aliases, desc = HELP_BADGES[key]
        await message.reply(f"🏷 <b>{emoji} {esc(aliases[0].capitalize())}</b>\n{desc}")
        return

    if matches:
        options = "\n".join(f"• {HELP_BADGES[m][1][0]}" for m in matches)
        await message.reply(TEXTS["help_badge_ambiguous_1"].format(v0=esc(query), v1=options))
        return

    available = ", ".join(aliases[0] for _, aliases, _ in HELP_BADGES.values())
    await message.reply(TEXTS["help_badge_not_found_1"].format(v0=esc(query), v1=esc(available)))

async def help_booster(message: Message, query: str):
    if not query:
        await message.reply(TEXTS["help_booster_general_1"])
        return

    key, matches = find_item_key_by_name(query, HELP_BOOSTER_KEYS)
    if key:
        emoji, name, _, _ = ITEMS[key]
        await message.reply(TEXTS["help_booster_info_1"].format(v0=emoji, v1=esc(name), v2=format_help_booster_text(key)))
        return

    if matches:
        options = "\n".join(f"• {ITEMS[m][1]}" for m in matches)
        await message.reply(TEXTS["help_booster_ambiguous_1"].format(v0=esc(query), v1=options))
        return

    await message.reply(TEXTS["help_booster_not_found_1"].format(v0=esc(query)))

async def help_item(message: Message, query: str):
    if not query:
        await message.reply(TEXTS["help_item_general_1"])
        return

    key, matches = find_item_key_by_name(query, HELP_ITEM_KEYS)
    if key:
        emoji, name, _, _ = ITEMS[key]
        await message.reply(TEXTS["help_item_info_1"].format(v0=emoji, v1=esc(name), v2=format_help_item_text(key)))
        return

    if matches:
        options = "\n".join(f"• {ITEMS[m][1]}" for m in matches)
        await message.reply(TEXTS["help_item_ambiguous_1"].format(v0=esc(query), v1=options))
        return

    await message.reply(TEXTS["help_item_not_found_1"].format(v0=esc(query)))

async def help_potion(message: Message, query: str):
    if not query:
        await message.reply(TEXTS["help_potion_general_1"])
        return

    key, matches = find_potion_key_by_name(query)
    if key:
        cfg = POTIONS[key]
        await message.reply(TEXTS["help_potion_info_1"].format(v0=cfg["emoji"], v1=esc(cfg["name"]), v2=format_help_potion_text(key)))
        return

    if matches:
        options = "\n".join(f"• {POTIONS[m]['name']}" for m in matches)
        await message.reply(TEXTS["help_potion_ambiguous_1"].format(v0=esc(query), v1=options))
        return

    await message.reply(TEXTS["help_potion_not_found_1"].format(v0=esc(query)))

async def help_command(message: Message, query: str):
    if not query:
        await message.reply(TEXTS["help_command_general_1"])
        return

    key, matches = find_help_command_key(query)
    if key:
        emoji, aliases, desc = HELP_COMMANDS[key]
        await message.reply(TEXTS["help_command_info_1"].format(v0=emoji, v1=esc(aliases[0]), v2=desc))
        return

    if matches:
        options = "\n".join(f"• {HELP_COMMANDS[m][1][0]}" for m in matches)
        await message.reply(TEXTS["help_command_ambiguous_1"].format(v0=esc(query), v1=options))
        return

    available = ", ".join(aliases[0] for _, aliases, _ in HELP_COMMANDS.values())
    await message.reply(TEXTS["help_command_not_found_1"].format(v0=esc(query), v1=esc(available)))

@dp.message(F.text.lower().startswith("!дать очкп"))
async def admin_give_rebirth(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    match = ADMIN_GIVE_REBIRTH_RE.match(message.text.strip())
    if not match:
        await message.reply(TEXTS["admin_give_rebirth_1"])
        return

    target = await resolve_target(message, bool(match.group(2)))
    if not target:
        await message.reply(TEXTS["admin_give_rebirth_2"])
        return

    amount = parse_amount(match.group(1))
    if not amount or amount <= 0:
        await message.reply(TEXTS["admin_give_rebirth_3"])
        return
    target_username = target.username or target.first_name or "Без имени"

    row = await ensure_user(target.id, target_username)
    new_points = row[14] + amount
    await db_exec("UPDATE users SET rebirth_points = ? WHERE user_id = ?", (new_points, target.id))
    await message.reply(TEXTS["admin_give_rebirth_4"].format(v0=amount, v1=esc(target_username), v2=new_points))

@dp.message(F.text.regexp(r"(?i)^!дать (?:крафт|очкк)\b"))
async def admin_give_craft(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    match = ADMIN_GIVE_CRAFT_RE.match(message.text.strip())
    if not match:
        await message.reply("Формат: !дать крафт <количество> [себе] (в ответ на сообщение игрока). Алиас: !дать очкк")
        return

    target = await resolve_target(message, bool(match.group(2)))
    if not target:
        await message.reply("Ответь этой командой на сообщение игрока, либо допиши «себе».")
        return

    amount = parse_amount(match.group(1))
    if not amount or amount <= 0:
        await message.reply("Некорректное количество.")
        return
    target_username = target.username or target.first_name or "Без имени"

    row = await ensure_user(target.id, target_username)
    new_points = row[32] + amount
    await db_exec("UPDATE users SET craft_points = ? WHERE user_id = ?", (new_points, target.id))
    await message.reply(f"Выдано {amount} 💠 очков крафта игроку {esc(target_username)} (Всего: {new_points})")

@dp.message(F.text.regexp(r"(?i)^!снять (?:крафт|очкк)\b"))
async def admin_take_craft(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    match = ADMIN_TAKE_CRAFT_RE.match(message.text.strip())
    if not match:
        await message.reply("Формат: !снять крафт <количество|все> [себе] (в ответ на сообщение игрока). Алиас: !снять очкк")
        return

    target = await resolve_target(message, bool(match.group(2)))
    if not target:
        await message.reply("Ответь этой командой на сообщение игрока, либо допиши «себе».")
        return
    target_username = target.username or target.first_name or "Без имени"

    if match.group(1) is None:
        await db_exec("UPDATE users SET craft_points = 0 WHERE user_id = ?", (target.id,))
        await message.reply(f"Снято все 💠 очки крафта у игрока {esc(target_username)} (Осталось: 0)")
        return

    amount = parse_amount(match.group(1))
    if not amount or amount <= 0:
        await message.reply("Некорректное количество.")
        return

    row = await ensure_user(target.id, target_username)
    new_points = max(0, row[32] - amount)
    await db_exec("UPDATE users SET craft_points = ? WHERE user_id = ?", (new_points, target.id))
    await message.reply(f"Снято {amount} 💠 очков крафта у игрока {esc(target_username)} (Осталось: {new_points})")

@dp.message(F.text.lower().startswith("!снять очкп"))
async def admin_take_rebirth(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    match = ADMIN_TAKE_REBIRTH_RE.match(message.text.strip())
    if not match:
        await message.reply(TEXTS["admin_take_rebirth_1"])
        return

    target = await resolve_target(message, bool(match.group(2)))
    if not target:
        await message.reply(TEXTS["admin_take_rebirth_2"])
        return
    target_username = target.username or target.first_name or "Без имени"

    if match.group(1) is None:
        await db_exec("UPDATE users SET rebirth_points = 0 WHERE user_id = ?", (target.id,))
        await message.reply(TEXTS["admin_take_rebirth_4"].format(v0="все", v1=esc(target_username), v2=0))
        return

    amount = parse_amount(match.group(1))
    if not amount or amount <= 0:
        await message.reply(TEXTS["admin_take_rebirth_3"])
        return

    row = await ensure_user(target.id, target_username)
    new_points = max(0, row[14] - amount)
    await db_exec("UPDATE users SET rebirth_points = ? WHERE user_id = ?", (new_points, target.id))
    await message.reply(TEXTS["admin_take_rebirth_4"].format(v0=amount, v1=esc(target_username), v2=new_points))

@dp.message(F.text.lower().startswith(NEWS_PREFIX))
async def broadcast_news(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    if message.chat.type != "private":
        return

    text = message.text[len(NEWS_PREFIX):].strip()
    if not text:
        await message.reply(TEXTS["broadcast_news_1"])
        return

    chat_ids = await get_all_chat_ids()
    sent = 0
    failed = 0
    body = f"📰 <b>Новость от разработчика:</b>\n\n{esc(text)}"

    for chat_id in chat_ids:
        try:
            await bot.send_message(chat_id, body)
            sent += 1
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after)
            try:
                await bot.send_message(chat_id, body)
                sent += 1
            except Exception:
                failed += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)

    await message.reply(TEXTS["broadcast_news_2"].format(v0=sent, v1=failed))

@dp.message(F.text.regexp(r"(?i)^!дать ног(?!и лвл)"))
async def admin_give_legs(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    match = ADMIN_GIVE_LEGS_RE.match(message.text.strip())
    if not match:
        await message.reply(TEXTS["admin_give_legs_1"])
        return

    target = await resolve_target(message, bool(match.group(2)))
    if not target:
        await message.reply(TEXTS["admin_give_legs_2"])
        return

    amount = parse_amount(match.group(1))
    if not amount or amount <= 0:
        await message.reply(TEXTS["admin_give_legs_3"])
        return
    target_username = target.username or target.first_name or "Без имени"

    row = await ensure_user(target.id, target_username)
    new_score = row[2] + amount
    await db_exec("UPDATE users SET score = ? WHERE user_id = ?", (new_score, target.id))
    await maybe_announce_levelup(message, target_username, row[2], new_score, row[3], bool(row[11]))

    await message.reply(TEXTS["admin_give_legs_4"].format(v0=amount, v1=esc(target_username), v2=new_score))

@dp.message(F.text.lower().startswith("!снять ноги"))
async def admin_take_legs(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    match = ADMIN_TAKE_LEGS_RE.match(message.text.strip())
    if not match:
        await message.reply(TEXTS["admin_take_legs_1"])
        return

    target = await resolve_target(message, bool(match.group(2)))
    if not target:
        await message.reply(TEXTS["admin_take_legs_2"])
        return
    target_username = target.username or target.first_name or "Без имени"

    if match.group(1) is None:
        await db_exec("UPDATE users SET score = 0 WHERE user_id = ?", (target.id,))
        await message.reply(TEXTS["admin_take_legs_4"].format(v0=esc(target_username), v1=0))
        return

    amount = parse_amount(match.group(1))
    if not amount or amount <= 0:
        await message.reply(TEXTS["admin_take_legs_3"])
        return

    row = await ensure_user(target.id, target_username)
    new_score = max(0, row[2] - amount)
    await db_exec("UPDATE users SET score = ? WHERE user_id = ?", (new_score, target.id))

    await message.reply(TEXTS["admin_take_legs_4"].format(v0=esc(target_username), v1=new_score))

@dp.message(F.text.lower().startswith("!дать эво"))
async def admin_give_evo(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    match = ADMIN_GIVE_EVO_RE.match(message.text.strip())
    if not match:
        await message.reply(TEXTS["admin_give_evo_1"])
        return

    target = await resolve_target(message, bool(match.group(2)))
    if not target:
        await message.reply(TEXTS["admin_give_evo_2"])
        return

    amount = parse_amount(match.group(1))
    if not amount or amount <= 0:
        await message.reply(TEXTS["admin_give_evo_3"])
        return
    target_username = target.username or target.first_name or "Без имени"

    row = await ensure_user(target.id, target_username)
    new_evo = row[3] + amount
    await db_exec("UPDATE users SET evolution_level = ? WHERE user_id = ?", (new_evo, target.id))

    await message.reply(TEXTS["admin_give_evo_4"].format(v0=amount, v1=esc(target_username), v2=new_evo))

@dp.message(F.text.lower().startswith("!снять эво"))
async def admin_take_evo(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    match = ADMIN_TAKE_EVO_RE.match(message.text.strip())
    if not match:
        await message.reply(TEXTS["admin_take_evo_1"])
        return

    target = await resolve_target(message, bool(match.group(2)))
    if not target:
        await message.reply(TEXTS["admin_take_evo_2"])
        return
    target_username = target.username or target.first_name or "Без имени"

    if match.group(1) is None:
        await db_exec("UPDATE users SET evolution_level = 0 WHERE user_id = ?", (target.id,))
        await message.reply(TEXTS["admin_take_evo_4"].format(v0="все", v1=esc(target_username), v2=0))
        return

    amount = parse_amount(match.group(1))
    if not amount or amount <= 0:
        await message.reply(TEXTS["admin_take_evo_3"])
        return

    row = await ensure_user(target.id, target_username)
    new_evo = max(0, row[3] - amount)
    await db_exec("UPDATE users SET evolution_level = ? WHERE user_id = ?", (new_evo, target.id))

    await message.reply(TEXTS["admin_take_evo_4"].format(v0=amount, v1=esc(target_username), v2=new_evo))

@dp.message(F.text.lower().startswith("!дать коин"))
async def admin_give_coin(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    match = ADMIN_GIVE_COIN_RE.match(message.text.strip())
    if not match:
        await message.reply(TEXTS["admin_give_coin_1"])
        return

    target = await resolve_target(message, bool(match.group(2)))
    if not target:
        await message.reply(TEXTS["admin_give_coin_2"])
        return

    amount = parse_amount(match.group(1))
    if not amount or amount <= 0:
        await message.reply(TEXTS["admin_give_coin_3"])
        return
    target_username = target.username or target.first_name or "Без имени"

    row = await ensure_user(target.id, target_username)
    new_coins = row[5] + amount
    await db_exec("UPDATE users SET coins = ? WHERE user_id = ?", (new_coins, target.id))

    await message.reply(TEXTS["admin_give_coin_4"].format(v0=amount, v1=esc(target_username), v2=new_coins))

@dp.message(F.text.lower().startswith("!снять коин"))
async def admin_take_coin(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    match = ADMIN_TAKE_COIN_RE.match(message.text.strip())
    if not match:
        await message.reply(TEXTS["admin_take_coin_1"])
        return

    target = await resolve_target(message, bool(match.group(2)))
    if not target:
        await message.reply(TEXTS["admin_take_coin_2"])
        return
    target_username = target.username or target.first_name or "Без имени"

    if match.group(1) is None:
        await db_exec("UPDATE users SET coins = 0 WHERE user_id = ?", (target.id,))
        await message.reply(TEXTS["admin_take_coin_4"].format(v0="все", v1=esc(target_username), v2=0))
        return

    amount = parse_amount(match.group(1))
    if not amount or amount <= 0:
        await message.reply(TEXTS["admin_take_coin_3"])
        return

    row = await ensure_user(target.id, target_username)
    new_coins = max(0, row[5] - amount)
    await db_exec("UPDATE users SET coins = ? WHERE user_id = ?", (new_coins, target.id))

    await message.reply(TEXTS["admin_take_coin_4"].format(v0=amount, v1=esc(target_username), v2=new_coins))

@dp.message(F.text.lower().startswith("!дать б "))
async def admin_give_boost(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    match = ADMIN_GIVE_BOOST_RE.match(message.text.strip())
    if not match:
        await message.reply(TEXTS["admin_give_boost_1"])
        return

    item_key = find_item_by_name(match.group(1), only_passive=False)
    if not item_key:
        await message.reply(TEXTS["admin_give_boost_2"])
        return

    target = await resolve_target(message, bool(match.group(2)))
    if not target:
        await message.reply(TEXTS["admin_give_boost_3"])
        return

    target_username = target.username or target.first_name or "Без имени"
    await ensure_user(target.id, target_username)
    await add_item(target.id, item_key)

    emoji, name, _, _ = ITEMS[item_key]
    await safe_reply(message, TEXTS["admin_give_boost_4"].format(v0=emoji, v1=esc(name), v2=esc(target_username)))

@dp.message(F.text.lower().startswith("!снять б "))
async def admin_take_boost(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    match = ADMIN_TAKE_BOOST_RE.match(message.text.strip())
    if not match:
        await message.reply(TEXTS["admin_take_boost_1"])
        return

    item_key = find_item_by_name(match.group(1), only_passive=False)
    if not item_key:
        await message.reply(TEXTS["admin_take_boost_2"])
        return

    target = await resolve_target(message, bool(match.group(2)))
    if not target:
        await message.reply(TEXTS["admin_take_boost_3"])
        return

    target_username = target.username or target.first_name or "Без имени"
    await ensure_user(target.id, target_username)
    removed = await remove_item(target.id, item_key)

    emoji, name, _, _ = ITEMS[item_key]
    if removed:
        await safe_reply(message, TEXTS["admin_take_boost_4"].format(v0=emoji, v1=esc(name), v2=esc(target_username)))
    else:
        await message.reply(TEXTS["admin_take_boost_5"].format(v0=esc(target_username), v1=esc(name)))

@dp.message(F.text.lower().startswith("!дать п "))
async def admin_give_passive(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    match = ADMIN_GIVE_ITEM_RE.match(message.text.strip())
    if not match:
        await message.reply(TEXTS["admin_give_passive_1"])
        return

    item_key = find_item_by_name(match.group(1), only_passive=True)
    if not item_key:
        await message.reply(TEXTS["admin_give_passive_2"])
        return

    target = await resolve_target(message, bool(match.group(2)))
    if not target:
        await message.reply(TEXTS["admin_give_passive_3"])
        return

    target_username = target.username or target.first_name or "Без имени"
    await ensure_user(target.id, target_username)
    await add_item(target.id, item_key)

    emoji, name, _, _ = ITEMS[item_key]
    await safe_reply(message, TEXTS["admin_give_passive_4"].format(v0=emoji, v1=esc(name), v2=esc(target_username)))

@dp.message(F.text.lower().startswith("!снять п "))
async def admin_take_passive(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    match = ADMIN_TAKE_ITEM_RE.match(message.text.strip())
    if not match:
        await message.reply(TEXTS["admin_take_passive_1"])
        return

    item_key = find_item_by_name(match.group(1), only_passive=True)
    if not item_key:
        await message.reply(TEXTS["admin_take_passive_2"])
        return

    target = await resolve_target(message, bool(match.group(2)))
    if not target:
        await message.reply(TEXTS["admin_take_passive_3"])
        return

    target_username = target.username or target.first_name or "Без имени"
    await ensure_user(target.id, target_username)
    removed = await remove_item(target.id, item_key)

    emoji, name, _, _ = ITEMS[item_key]
    if removed:
        await safe_reply(message, TEXTS["admin_take_passive_4"].format(v0=emoji, v1=esc(name), v2=esc(target_username)))
    else:
        await message.reply(TEXTS["admin_take_passive_5"].format(v0=esc(target_username), v1=esc(name)))

@dp.message(F.text.lower().startswith("!дать вип"))
async def admin_give_vip(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    match = ADMIN_GIVE_VIP_RE.match(message.text.strip())
    if not match:
        await message.reply(TEXTS["admin_give_vip_1"])
        return

    target = await resolve_target(message, bool(match.group(2)))
    if not target:
        await message.reply(TEXTS["admin_give_vip_2"])
        return

    days = parse_amount(match.group(1))
    if not days or days <= 0:
        await message.reply(TEXTS["admin_give_vip_3"])
        return
    target_username = target.username or target.first_name or "Без имени"
    row = await ensure_user(target.id, target_username)

    now = int(time.time())
    base = row[12] if row[12] and row[12] > now else now
    new_vip_until = base + days * 86400

    await db_exec("UPDATE users SET vip_until = ? WHERE user_id = ?", (new_vip_until, target.id))
    was_vip_before = is_vip_active(row[12])
    if not was_vip_before:
        await add_item(target.id, "vip_charm")

    await message.reply(TEXTS["admin_give_vip_4"].format(v0=days, v1=esc(target_username)))

@dp.message(F.text.lower().startswith("!снять вип"))
async def admin_take_vip(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    match = ADMIN_TAKE_VIP_RE.match(message.text.strip())
    if not match:
        await message.reply(TEXTS["admin_take_vip_1"])
        return

    target = await resolve_target(message, bool(match.group(1)))
    if not target:
        await message.reply(TEXTS["admin_take_vip_2"])
        return

    target_username = target.username or target.first_name or "Без имени"
    await ensure_user(target.id, target_username)
    await db_exec("UPDATE users SET vip_until = 0 WHERE user_id = ?", (target.id,))

    await message.reply(TEXTS["admin_take_vip_3"].format(v0=esc(target_username)))

@dp.message(F.text.lower().startswith("!сбросить"))
async def admin_reset(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    match = ADMIN_RESET_RE.match(message.text.strip())
    if not match:
        await message.reply(TEXTS["admin_reset_1"])
        return

    target = await resolve_target(message, bool(match.group(1)))
    if not target:
        await message.reply(TEXTS["admin_reset_2"])
        return

    target_username = target.username or target.first_name or "Без имени"
    await ensure_user(target.id, target_username)

    await db_exec(
        "UPDATE users SET score = 0, evolution_level = 0, coins = 0, active_item = NULL, equipped_items = '', "
        "cases_opened = 0, total_farmed = 0, last_bonus = 0, bonus_streak = 0, vip_until = 0 "
        "WHERE user_id = ?",
        (target.id,),
    )
    await db_exec("DELETE FROM inventory WHERE user_id = ?", (target.id,))

    await message.reply(TEXTS["admin_reset_3"].format(v0=esc(target_username)))

@dp.message(F.text.lower().startswith("!установить ног"))
async def admin_set_legs(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    match = ADMIN_SET_LEGS_RE.match(message.text.strip())
    if not match:
        await message.reply(TEXTS["admin_set_legs_1"])
        return

    target = await resolve_target(message, bool(match.group(2)))
    if not target:
        await message.reply(TEXTS["admin_set_legs_2"])
        return

    amount = parse_amount(match.group(1))
    if amount is None or amount < 0:
        await message.reply(TEXTS["admin_set_legs_3"])
        return
    target_username = target.username or target.first_name or "Без имени"

    row = await ensure_user(target.id, target_username)
    old_score = row[2]
    await db_exec("UPDATE users SET score = ? WHERE user_id = ?", (amount, target.id))
    await maybe_announce_levelup(message, target_username, old_score, amount, row[3], bool(row[11]))

@dp.message(F.text.lower().startswith("!дать ноги лвл"))
async def admin_give_legs_level(message: Message):
    """Ставит игроку РОВНО указанный уровень ноги (не сырое число очков) — пересчитывает
    нужный score через level_threshold с учётом его эволюции/перерождений/ultra_rebirth."""
    if not is_admin(message):
        return
    await log_admin_action(message)
    match = ADMIN_GIVE_LEGS_LVL_RE.match(message.text.strip())
    if not match:
        await message.reply(TEXTS["admin_give_legs_lvl_1"])
        return

    target = await resolve_target(message, bool(match.group(2)))
    if not target:
        await message.reply(TEXTS["admin_give_legs_lvl_2"])
        return

    level = int(match.group(1))
    target_username = target.username or target.first_name or "Без имени"

    row = await ensure_user(target.id, target_username)
    evolution_level, rebirth_count = row[3], row[15]
    ultra_rebirth = bool(row[21])
    cap = ULTRA_LEVEL_CAP if ultra_rebirth else ULTRA_REQUIRED_LEG_LEVEL

    if level < 0 or level > cap:
        await message.reply(TEXTS["admin_give_legs_lvl_3"].format(v0=cap))
        return

    old_score = row[2]
    new_score = level_threshold(level, evolution_level, rebirth_count)
    await db_exec("UPDATE users SET score = ? WHERE user_id = ?", (new_score, target.id))
    await maybe_announce_levelup(message, target_username, old_score, new_score, evolution_level, bool(row[11]), rebirth_count, ultra_rebirth)

    await message.reply(TEXTS["admin_give_legs_lvl_4"].format(v0=level, v1=esc(target_username), v2=new_score))

    await message.reply(TEXTS["admin_set_legs_4"].format(v0=esc(target_username), v1=amount, v2=old_score))

@dp.message(F.text.lower().startswith("!установить эво"))
async def admin_set_evo(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    match = ADMIN_SET_EVO_RE.match(message.text.strip())
    if not match:
        await message.reply(TEXTS["admin_set_evo_1"])
        return

    target = await resolve_target(message, bool(match.group(2)))
    if not target:
        await message.reply(TEXTS["admin_set_evo_2"])
        return

    amount = parse_amount(match.group(1))
    if amount is None or amount < 0:
        await message.reply(TEXTS["admin_set_evo_3"])
        return
    target_username = target.username or target.first_name or "Без имени"

    row = await ensure_user(target.id, target_username)
    old_evo = row[3]
    await db_exec("UPDATE users SET evolution_level = ? WHERE user_id = ?", (amount, target.id))

    await message.reply(TEXTS["admin_set_evo_4"].format(v0=esc(target_username), v1=amount, v2=old_evo))

@dp.message(F.text.lower().startswith("!сброс кд"))
async def admin_reset_cd(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    match = ADMIN_RESET_CD_RE.match(message.text.strip())
    if not match:
        await message.reply(TEXTS["admin_reset_cd_1"])
        return

    target = await resolve_target(message, bool(match.group(1)))
    if not target:
        await message.reply(TEXTS["admin_reset_cd_2"])
        return

    target_username = target.username or target.first_name or "Без имени"
    await ensure_user(target.id, target_username)
    await db_exec("UPDATE users SET last_farm = 0 WHERE user_id = ?", (target.id,))

    await message.reply(TEXTS["admin_reset_cd_3"].format(v0=esc(target_username)))

@dp.message(F.text.lower().startswith("!сброс бонус"))
async def admin_reset_bonus(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    match = ADMIN_RESET_BONUS_RE.match(message.text.strip())
    if not match:
        await message.reply(TEXTS["admin_reset_bonus_1"])
        return

    target = await resolve_target(message, bool(match.group(1)))
    if not target:
        await message.reply(TEXTS["admin_reset_bonus_2"])
        return

    target_username = target.username or target.first_name or "Без имени"
    await ensure_user(target.id, target_username)
    await db_exec("UPDATE users SET last_bonus = 0 WHERE user_id = ?", (target.id,))

    await message.reply(TEXTS["admin_reset_bonus_3"].format(v0=esc(target_username)))

@dp.message(F.text.lower().startswith("!дать кейс"))
async def admin_give_case(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    match = ADMIN_GIVE_CASE_RE.match(message.text.strip())
    if not match:
        await message.reply(TEXTS["admin_give_case_1"])
        return

    case_num = int(match.group(1))
    count = int(match.group(2))
    case = CASES.get(case_num)
    if not case:
        await message.reply(TEXTS["admin_give_case_3"])
        return
    if count < 1 or count > 100:
        await message.reply(TEXTS["admin_give_case_4"])
        return

    target = await resolve_target(message, bool(match.group(3)))
    if not target:
        await message.reply(TEXTS["admin_give_case_2"])
        return

    target_username = target.username or target.first_name or "Без имени"
    await ensure_user(target.id, target_username)

    won = {}
    for _ in range(count):
        item_key = roll_case_item(case_num)
        await add_item(target.id, item_key)
        won[item_key] = won.get(item_key, 0) + 1
    await db_exec("UPDATE users SET cases_opened = cases_opened + ? WHERE user_id = ?", (count, target.id))

    loot_lines = "\n".join(f"● {ITEMS[k][0]} {esc(ITEMS[k][1])} × {qty}" for k, qty in won.items())
    await safe_reply(
        message,
        TEXTS["admin_give_case_5"].format(v0=esc(target_username), v1=esc(case["name"]), v2=count, v3=loot_lines),
    )

@dp.message(F.text.regexp(r"(?i)^!дебаг\s+"))
async def admin_debug(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    match = ADMIN_DEBUG_RE.match(message.text.strip())
    if not match:
        await message.reply(TEXTS["admin_debug_1"])
        return

    row = await get_user_by_username(match.group(1))
    if not row:
        await message.reply(TEXTS["admin_debug_2"])
        return

    fields = USER_COLUMNS.split(", ")
    dump = "\n".join(f"{name} = {value}" for name, value in zip(fields, row))
    await message.reply(TEXTS["admin_debug_3"].format(v0=esc(row[1]), v1=esc(dump)))

@dp.message(F.text.regexp(r"(?i)^!текст\s+"))
async def admin_show_text(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    match = ADMIN_SHOW_TEXT_RE.match(message.text.strip())
    if not match:
        await message.reply(TEXTS["admin_show_text_1"])
        return

    key = match.group(1)
    if key not in TEXTS:
        await message.reply(TEXTS["admin_show_text_2"])
        return

    await message.reply(TEXTS["admin_show_text_3"].format(v0=esc(key), v1=esc(TEXTS[key])))

@dp.message(F.text.regexp(r"(?i)^!симулировать эволюция\s+"))
async def admin_simulate_evolution(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    match = ADMIN_SIMULATE_EVO_RE.match(message.text.strip())
    if not match:
        await message.reply(TEXTS["admin_simulate_evo_1"])
        return

    row = await get_user_by_username(match.group(1))
    if not row:
        await message.reply(TEXTS["admin_simulate_evo_2"])
        return

    username, score, evolution_level = row[1], row[2], row[3]
    rebirth_count = row[15] if len(row) > 15 else 0
    required = level_threshold(EVO_REQUIRED_BASE_LEVEL + evolution_level, evolution_level, rebirth_count)
    verdict = TEXTS["admin_simulate_evo_ok"] if score >= required else TEXTS["admin_simulate_evo_fail"].format(v0=required - score)

    await message.reply(
        TEXTS["admin_simulate_evo_3"].format(v0=esc(username), v1=score, v2=required, v3=evolution_level, v4=verdict)
    )

@dp.message(F.text.lower() == "!стата")
async def admin_stats(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)

    row = await db_query_one(
        "SELECT COUNT(*), COALESCE(SUM(score),0), COALESCE(SUM(coins),0), COALESCE(SUM(rebirth_points),0), "
        "COALESCE(SUM(cases_opened),0), SUM(CASE WHEN vip_until > ? THEN 1 ELSE 0 END), "
        "SUM(CASE WHEN top_banned = 1 THEN 1 ELSE 0 END) FROM users",
        (int(time.time()),),
    )
    players, total_score, total_coins, total_rebirth, total_cases, vip_count, banned_count = row

    await message.reply(
        TEXTS["admin_stats_1"].format(
            v0=players, v1=total_score, v2=total_coins, v3=total_rebirth,
            v4=total_cases, v5=vip_count or 0, v6=banned_count or 0,
        )
    )

@dp.message(F.text.lower() == "стата")
async def vip_stats(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"
    row = await ensure_user(user_id, username)
    vip_until = row[12]

    if not is_vip_active(vip_until):
        await message.reply(TEXTS["vip_stats_not_vip_1"])
        return

    stats_row = await db_query_one(
        "SELECT COUNT(*), COALESCE(SUM(score),0), COALESCE(SUM(coins),0), COALESCE(SUM(rebirth_points),0), "
        "COALESCE(SUM(cases_opened),0), SUM(CASE WHEN vip_until > ? THEN 1 ELSE 0 END), "
        "SUM(CASE WHEN top_banned = 1 THEN 1 ELSE 0 END) FROM users",
        (int(time.time()),),
    )
    players, total_score, total_coins, total_rebirth, total_cases, vip_count, banned_count = stats_row

    await message.reply(
        TEXTS["admin_stats_1"].format(
            v0=players, v1=total_score, v2=total_coins, v3=total_rebirth,
            v4=total_cases, v5=vip_count or 0, v6=banned_count or 0,
        )
    )

@dp.message(F.text.lower() == "!рестарт")
async def admin_restart(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    await message.reply(TEXTS["admin_restart_1"])
    await bot.session.close()
    os._exit(0)

@dp.message(F.text.lower() == "!снять бейдж всем")
async def admin_unshow_all_badges(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    await db_exec("UPDATE users SET shown_badges = ''")
    await message.reply(TEXTS["admin_unshow_all_badges_1"])

@dp.message(F.text.regexp(r"(?i)^!ивент\s+х\d"))
async def admin_event_custom(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    match = ADMIN_EVENT_CUSTOM_RE.match(message.text.strip())
    if not match:
        await message.reply(TEXTS["admin_event_custom_1"])
        return

    mult = float(match.group(1))
    minutes = int(match.group(2))
    if mult <= 0 or minutes <= 0:
        await message.reply(TEXTS["admin_event_custom_2"])
        return

    until = int(time.time()) + minutes * 60
    for key, value in (("event_active", "1"), ("event_multiplier", str(mult)), ("event_until", str(until))):
        await db_exec(
            "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
    _invalidate_event_state_cache()

    await message.reply(TEXTS["admin_event_custom_3"].format(v0=mult, v1=minutes))

@dp.message(F.text.lower().startswith("!установить очкп"))
async def admin_set_rebirth(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    match = ADMIN_SET_REBIRTH_RE.match(message.text.strip())
    if not match:
        await message.reply(TEXTS["admin_set_rebirth_1"])
        return

    target = await resolve_target(message, bool(match.group(2)))
    if not target:
        await message.reply(TEXTS["admin_set_rebirth_2"])
        return

    amount = parse_amount(match.group(1))
    if amount is None or amount < 0:
        await message.reply(TEXTS["admin_set_rebirth_3"])
        return
    target_username = target.username or target.first_name or "Без имени"

    row = await ensure_user(target.id, target_username)
    old_rp = row[14]
    await db_exec("UPDATE users SET rebirth_points = ? WHERE user_id = ?", (amount, target.id))

    await message.reply(TEXTS["admin_set_rebirth_4"].format(v0=esc(target_username), v1=amount, v2=old_rp))

@dp.message(F.text.regexp(r"(?i)^!обнулить экономику\s+"))
async def admin_wipe_economy(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    match = ADMIN_WIPE_ECONOMY_RE.match(message.text.strip())
    if not match:
        await message.reply(TEXTS["admin_wipe_economy_1"])
        return

    row = await get_user_by_username(match.group(1))
    if not row:
        await message.reply(TEXTS["admin_wipe_economy_2"])
        return

    await db_exec(
        "UPDATE users SET score = 0, coins = 0, rebirth_points = 0 WHERE user_id = ?",
        (row[0],),
    )
    await message.reply(TEXTS["admin_wipe_economy_3"].format(v0=esc(row[1])))

@dp.message(F.text.regexp(r"(?i)^!мультипликатор ферма\s+"))
async def admin_personal_boost(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    match = ADMIN_PERSONAL_BOOST_RE.match(message.text.strip())
    if not match:
        await message.reply(TEXTS["admin_personal_boost_1"])
        return

    target = await resolve_target(message, bool(match.group(3)))
    if not target:
        await message.reply(TEXTS["admin_personal_boost_2"])
        return

    mult = float(match.group(1))
    minutes = int(match.group(2))
    if mult <= 0 or minutes <= 0:
        await message.reply(TEXTS["admin_personal_boost_3"])
        return
    target_username = target.username or target.first_name or "Без имени"
    await ensure_user(target.id, target_username)

    until = int(time.time()) + minutes * 60
    await db_exec(
        "INSERT INTO personal_boosts (user_id, multiplier, until) VALUES (?, ?, ?) "
        "ON CONFLICT(user_id) DO UPDATE SET multiplier = excluded.multiplier, until = excluded.until",
        (target.id, mult, until),
    )

    await message.reply(TEXTS["admin_personal_boost_4"].format(v0=esc(target_username), v1=mult, v2=minutes))

@dp.message(F.text.regexp(r"(?i)^!дать предмет\s+"))
async def admin_give_item(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    match = ADMIN_GIVE_ITEM_RE.match(message.text.strip())
    if not match:
        await message.reply(TEXTS["admin_give_item_1"])
        return

    item_key = match.group(1)
    count = int(match.group(2))
    if item_key not in ITEMS:
        await message.reply(TEXTS["admin_give_item_3"])
        return
    if count < 1 or count > 1000:
        await message.reply(TEXTS["admin_give_item_4"])
        return

    target = await resolve_target(message, bool(match.group(3)))
    if not target:
        await message.reply(TEXTS["admin_give_item_2"])
        return

    target_username = target.username or target.first_name or "Без имени"
    await ensure_user(target.id, target_username)
    await add_item(target.id, item_key, count)

    emoji, name, _, _ = ITEMS[item_key]
    await message.reply(TEXTS["admin_give_item_5"].format(v0=esc(target_username), v1=emoji, v2=esc(name), v3=count))

@dp.message(F.text.regexp(r"(?i)^!дать ключ\s+"))
async def admin_give_key(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    match = ADMIN_GIVE_KEY_RE.match(message.text.strip())
    if not match:
        await message.reply(TEXTS["admin_give_key_1"])
        return

    item_key = match.group(1)
    count = int(match.group(2))
    if item_key not in ITEMS:
        await message.reply(TEXTS["admin_give_key_3"])
        return
    if count < 1 or count > 1000:
        await message.reply(TEXTS["admin_give_key_4"])
        return

    target = await resolve_target(message, bool(match.group(3)))
    if not target:
        await message.reply(TEXTS["admin_give_key_2"])
        return

    target_username = target.username or target.first_name or "Без имени"
    await ensure_user(target.id, target_username)
    await add_item(target.id, item_key, count)

    emoji, name, _, _ = ITEMS[item_key]
    await message.reply(TEXTS["admin_give_key_5"].format(v0=esc(target_username), v1=emoji, v2=esc(name), v3=count))

@dp.message(F.text.regexp(r"(?i)^!очистить инвентарь\s+"))
async def admin_clear_inventory(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    match = ADMIN_CLEAR_INVENTORY_RE.match(message.text.strip())
    if not match:
        await message.reply(TEXTS["admin_clear_inventory_1"])
        return

    row = await get_user_by_username(match.group(1))
    if not row:
        await message.reply(TEXTS["admin_clear_inventory_2"])
        return

    await db_exec("DELETE FROM inventory WHERE user_id = ?", (row[0],))
    await db_exec("UPDATE users SET equipped_items = '' WHERE user_id = ?", (row[0],))
    await message.reply(TEXTS["admin_clear_inventory_3"].format(v0=esc(row[1])))

@dp.message(F.text.regexp(r"(?i)^!дать апгрейд\s+"))
async def admin_set_upgrade(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    match = ADMIN_SET_UPGRADE_RE.match(message.text.strip())
    if not match:
        await message.reply(TEXTS["admin_set_upgrade_1"])
        return

    upgrade_key = match.group(1)
    level = int(match.group(2))
    if upgrade_key not in UPGRADES:
        await message.reply(TEXTS["admin_set_upgrade_3"])
        return
    max_level = UPGRADES[upgrade_key]["max_level"]
    if level < 0 or level > max_level:
        await message.reply(TEXTS["admin_set_upgrade_4"].format(v0=max_level))
        return

    target = await resolve_target(message, bool(match.group(3)))
    if not target:
        await message.reply(TEXTS["admin_set_upgrade_2"])
        return

    target_username = target.username or target.first_name or "Без имени"
    row = await ensure_user(target.id, target_username)
    upgrades = parse_upgrades(row[16])
    if level > 0:
        upgrades[upgrade_key] = level
    else:
        upgrades.pop(upgrade_key, None)
    await db_exec("UPDATE users SET upgrades = ? WHERE user_id = ?", (format_upgrades(upgrades), target.id))

    await message.reply(
        TEXTS["admin_set_upgrade_5"].format(v0=esc(target_username), v1=esc(UPGRADES[upgrade_key]["name"]), v2=level)
    )

@dp.message(F.text.lower().startswith("!вип навсегда"))
async def admin_vip_forever(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    match = ADMIN_VIP_FOREVER_RE.match(message.text.strip())
    target = await resolve_target(message, bool(match.group(1))) if match else None
    if not target:
        await message.reply(TEXTS["admin_vip_forever_1"])
        return

    target_username = target.username or target.first_name or "Без имени"
    row = await ensure_user(target.id, target_username)
    new_vip_until = int(time.time()) + VIP_FOREVER_SECONDS
    await db_exec("UPDATE users SET vip_until = ? WHERE user_id = ?", (new_vip_until, target.id))
    if not is_vip_active(row[12]):
        await add_item(target.id, "vip_charm")

    await message.reply(TEXTS["admin_vip_forever_2"].format(v0=esc(target_username)))

@dp.message(F.text.lower().startswith("!ультра навсегда"))
async def admin_ultra_rebirth_forever(message: Message):
    """Owner-инструмент для тестирования: выдаёт статус Ультра перерождения напрямую,
    БЕЗ сброса прогресса игрока (в отличие от реальной активации через игровую команду).
    Полезно для проверки пост-ультра контента ("тест ноги", буста) без реального гринда."""
    if not is_admin(message):
        return
    await log_admin_action(message)
    match = ADMIN_ULTRA_REBIRTH_RE.match(message.text.strip())
    target = await resolve_target(message, bool(match.group(1))) if match else None
    if not target:
        await message.reply(TEXTS["admin_ultra_rebirth_1"])
        return

    target_username = target.username or target.first_name or "Без имени"
    await ensure_user(target.id, target_username)
    await db_exec("UPDATE users SET ultra_rebirth = 1 WHERE user_id = ?", (target.id,))

    await message.reply(TEXTS["admin_ultra_rebirth_2"].format(v0=esc(target_username)))

@dp.message(F.text.regexp(r"(?i)^!сброс ник\s+"))
async def admin_reset_nick(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    match = ADMIN_RESET_NICK_RE.match(message.text.strip())
    if not match:
        await message.reply(TEXTS["admin_reset_nick_1"])
        return

    row = await get_user_by_username(match.group(1))
    if not row:
        await message.reply(TEXTS["admin_reset_nick_2"])
        return

    old_nick = row[19] if len(row) > 19 else None
    if not old_nick:
        await message.reply(TEXTS["admin_reset_nick_3"])
        return

    await db_exec("UPDATE users SET nickname = NULL WHERE user_id = ?", (row[0],))
    await message.reply(TEXTS["admin_reset_nick_4"].format(v0=esc(row[1]), v1=esc(old_nick)))

@dp.message(F.text.lower() == "!список вип")
async def admin_list_vip(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    now = int(time.time())
    rows = await db_query(
        "SELECT username, nickname, vip_until FROM users WHERE vip_until > ? ORDER BY vip_until DESC LIMIT 30",
        (now,),
    )
    if not rows:
        await message.reply(TEXTS["admin_list_vip_1"])
        return

    lines = []
    for username, nickname, vip_until in rows:
        left = vip_until - now
        if left > 50 * 365 * 86400:
            left_text = "навсегда"
        else:
            days = left // 86400
            left_text = f"{days} дн."
        lines.append(f"● {esc(display_name(username, nickname))} — {left_text}")

    await message.reply(TEXTS["admin_list_vip_2"].format(v0=len(rows), v1="\n".join(lines)))

@dp.message(F.text.lower() == "!список ников")
async def admin_list_nicknames(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    rows = await db_query(
        "SELECT username, nickname FROM users WHERE nickname IS NOT NULL AND nickname != '' LIMIT 50"
    )
    if not rows:
        await message.reply(TEXTS["admin_list_nicknames_1"])
        return

    lines = [f"● {esc(nickname)} (@{esc(username)})" for username, nickname in rows]
    await message.reply(TEXTS["admin_list_nicknames_2"].format(v0=len(rows), v1="\n".join(lines)))

@dp.message(F.text.regexp(r"(?i)^!найти\s+"))
async def admin_find(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    match = ADMIN_FIND_RE.match(message.text.strip())
    if not match:
        await message.reply(TEXTS["admin_find_1"])
        return

    row = await get_user_by_username(match.group(1))
    if not row:
        await message.reply(TEXTS["admin_find_2"])
        return

    chat_rows = await db_query("SELECT chat_id FROM chat_members WHERE user_id = ? LIMIT 20", (row[0],))
    if not chat_rows:
        await message.reply(TEXTS["admin_find_4"])
        return

    lines = []
    for (chat_id,) in chat_rows:
        try:
            chat = await bot.get_chat(chat_id)
            title = chat.title or chat.full_name or str(chat_id)
        except Exception:
            title = f"chat_id {chat_id} (недоступен)"
        lines.append(f"● {esc(title)}")

    await message.reply(TEXTS["admin_find_3"].format(v0=esc(row[1]), v1=len(chat_rows), v2="\n".join(lines)))

@dp.message(F.text.lower().startswith("!дать всё"))
async def admin_give_all(message: Message):
    """!дать всё [себе] — выдаёт целевому игроку все существующие предметы, бустеры
    (все ключи ITEMS, без исключений) и все зелья (все ключи POTIONS) по 1 штуке каждого.
    Полезно для тестирования — например прогона «помощь бустер/предмет/зелье» по реальному
    инвентарю."""
    if not is_admin(message):
        return
    await log_admin_action(message)
    match = ADMIN_GIVE_ALL_RE.match(message.text.strip())
    target = await resolve_target(message, bool(match.group(1))) if match else None
    if not target:
        await message.reply(TEXTS["admin_give_all_1"])
        return

    target_username = target.username or target.first_name or "Без имени"
    row = await ensure_user(target.id, target_username)

    for item_key in ITEMS:
        await add_item(target.id, item_key, 1)

    stock = parse_potion_stock(row[26])
    for potion_key in POTIONS:
        stock[potion_key] = stock.get(potion_key, 0) + 1
    await db_exec("UPDATE users SET potion_stock = ? WHERE user_id = ?", (format_potion_stock(stock), target.id))

    await safe_reply(message, TEXTS["admin_give_all_2"].format(v0=esc(target_username), v1=len(ITEMS), v2=len(POTIONS)))

@dp.message(F.text.lower() == "!смс выкл всем")
async def admin_levelup_notify_off_all(message: Message):
    """!смс выкл всем — массово отключает показ уведомления о новом уровне (levelup_notify)
    у ВСЕХ игроков разом, одним UPDATE без WHERE (тот же паттерн, что chronos_orb_boost_loop)."""
    if not is_admin(message):
        return
    await log_admin_action(message)

    count_row = await db_query_one("SELECT COUNT(*) FROM users")
    total = count_row[0] if count_row else 0

    await db_exec("UPDATE users SET levelup_notify = 0")

    await message.reply(TEXTS["admin_levelup_notify_off_all_1"].format(v0=total))

@dp.message(F.text.lower() == "!игроки")
async def admin_list_players(message: Message):
    """!игроки — показ всех игроков (username/ник + основные показатели)."""
    if not is_admin(message):
        return
    await log_admin_action(message)
    rows = await db_query(
        "SELECT username, nickname, score, evolution_level FROM users "
        "ORDER BY evolution_level DESC, score DESC LIMIT 100"
    )
    if not rows:
        await message.reply(TEXTS["admin_players_1"])
        return

    lines = [
        f"● {esc(display_name(username, nickname))} — нога {score}, эво {evolution_level}"
        for username, nickname, score, evolution_level in rows
    ]
    await message.reply(TEXTS["admin_players_2"].format(v0=len(rows), v1="\n".join(lines)))

@dp.message(F.text.lower() == "!список чат")
async def admin_list_chats(message: Message):
    """Список всех чатов, где бот отметился (из chat_members — Telegram Bot API не даёт
    метода 'дай все чаты бота' напрямую). Титул подтягивается свежим через bot.get_chat();
    если чат недоступен (бота уже выгнали), запись пропускается, а не показывается мёртвой
    строкой — так список честно отражает чаты, где бот РЕАЛЬНО сейчас состоит."""
    if not is_admin(message):
        return
    await log_admin_action(message)

    chat_ids = await db_query("SELECT DISTINCT chat_id FROM chat_members")

    lines = []
    for (chat_id,) in chat_ids:
        try:
            chat = await bot.get_chat(chat_id)
            title = chat.title or chat.full_name or str(chat_id)
        except Exception:
            continue
        lines.append(f"● {esc(title)}")

    if not lines:
        await message.reply(TEXTS["admin_list_chats_1"])
        return

    await message.reply(TEXTS["admin_list_chats_2"].format(v0=len(lines), v1="\n".join(lines)))

@dp.message(F.text.regexp(r'(?i)^!промокод создать бейдж\s+'))
async def admin_promo_create_badge(message: Message):
    """Короткий синтаксис для выдачи бейджа промокодом (см. PROMO_BADGES):
    !промокод создать бейдж "название_бейджа" "название_промокода".
    Зарегистрирован раньше admin_promo_create и матчится первым — aiogram
    останавливается на первом сработавшем хендлере для одного сообщения."""
    if not is_admin(message):
        return
    await log_admin_action(message)
    match = PROMO_CREATE_BADGE_RE.match(message.text.strip())
    if not match:
        await message.reply(TEXTS["promo_create_badge_1"])
        return

    badge_name_raw, code_raw = match.groups()
    code = code_raw.strip()

    badge_key = find_promo_badge_key(badge_name_raw)
    if not badge_key:
        await message.reply(TEXTS["promo_create_badge_2"].format(v0=esc(badge_name_raw)))
        return

    existing = await db_query_one("SELECT code FROM promocodes WHERE code = ?", (code,))
    if existing:
        await message.reply(TEXTS["promo_create_badge_3"].format(v0=esc(code)))
        return

    admin_username = message.from_user.username or message.from_user.first_name or "admin"
    await db_exec(
        "INSERT INTO promocodes (code, reward_type, reward_key, amount, activations_left, created_by, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (code, "badge", badge_key, 1, 1, admin_username, int(time.time())),
    )

    emoji, name = PROMO_BADGES[badge_key]
    await message.reply(TEXTS["promo_create_badge_4"].format(v0=esc(code), v1=emoji, v2=esc(name)))

@dp.message(F.text.regexp(r'(?i)^!промокод создать\s+(?!бейдж\s)'))
async def admin_promo_create(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    match = PROMO_CREATE_RE.match(message.text.strip())
    if not match:
        await message.reply(TEXTS["promo_create_1"])
        return

    type_raw, amount_raw, activations_raw, code_raw = match.groups()
    code = code_raw.strip()

    parsed_type = parse_promo_type(type_raw)
    if not parsed_type:
        await message.reply(TEXTS["promo_create_2"].format(v0=esc(type_raw)))
        return
    reward_type, reward_key = parsed_type

    amount = parse_amount(amount_raw)
    if not amount or amount <= 0:
        await message.reply(TEXTS["promo_create_3"])
        return

    activations = parse_amount(activations_raw)
    if not activations or activations <= 0:
        await message.reply(TEXTS["promo_create_4"])
        return

    existing = await db_query_one("SELECT code FROM promocodes WHERE code = ?", (code,))
    if existing:
        await message.reply(TEXTS["promo_create_5"].format(v0=esc(code)))
        return

    admin_username = message.from_user.username or message.from_user.first_name or "admin"
    await db_exec(
        "INSERT INTO promocodes (code, reward_type, reward_key, amount, activations_left, created_by, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (code, reward_type, reward_key, amount, activations, admin_username, int(time.time())),
    )

    if reward_type == "item":
        emoji, name, _, _ = ITEMS[reward_key]
        reward_label = f"{emoji} {esc(name)}"
    else:
        reward_label = PROMO_TYPE_LABEL[reward_type]

    await message.reply(TEXTS["promo_create_6"].format(v0=esc(code), v1=reward_label, v2=amount, v3=activations))

@dp.message(F.text.regexp(r'(?i)^!промокод удалить\s+'))
async def admin_promo_delete(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    match = PROMO_DELETE_RE.match(message.text.strip())
    if not match:
        await message.reply(TEXTS["promo_delete_1"])
        return

    code = match.group(1).strip()
    existing = await db_query_one("SELECT code FROM promocodes WHERE code = ?", (code,))
    if not existing:
        await message.reply(TEXTS["promo_delete_2"].format(v0=esc(code)))
        return

    await db_exec("DELETE FROM promocodes WHERE code = ?", (code,))
    await db_exec("DELETE FROM promocode_uses WHERE code = ?", (code,))
    await message.reply(TEXTS["promo_delete_3"].format(v0=esc(code)))

@dp.message(F.text.lower() == "!промокод список")
async def admin_promo_list(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    rows = await db_query(
        "SELECT code, reward_type, reward_key, amount, activations_left FROM promocodes ORDER BY created_at DESC LIMIT 50"
    )
    if not rows:
        await message.reply(TEXTS["promo_list_1"])
        return

    lines = []
    for code, reward_type, reward_key, amount, activations_left in rows:
        if reward_type == "item" and reward_key in ITEMS:
            emoji, name, _, _ = ITEMS[reward_key]
            reward_label = f"{emoji} {esc(name)}"
        elif reward_type == "badge" and reward_key in PROMO_BADGES:
            emoji, name = PROMO_BADGES[reward_key]
            reward_label = f"{emoji} бейдж «{esc(name)}»"
        else:
            reward_label = PROMO_TYPE_LABEL.get(reward_type, esc(reward_type))
        lines.append(f"● «{esc(code)}» — {reward_label} × {amount} (осталось активаций: {activations_left})")

    await message.reply(TEXTS["promo_list_2"].format(v0=len(rows), v1="\n".join(lines)))

@dp.message(F.text.regexp(r'(?i)^(?:промокод|промо)\s+\S+$'))
async def redeem_promo(message: Message):
    match = PROMO_REDEEM_RE.match(message.text.strip())
    if not match:
        await message.reply(TEXTS["promo_redeem_1"])
        return

    code = match.group(1).strip()
    promo = await db_query_one(
        "SELECT reward_type, reward_key, amount, activations_left FROM promocodes WHERE code = ?", (code,)
    )
    if not promo:
        await message.reply(TEXTS["promo_redeem_2"])
        return

    reward_type, reward_key, amount, activations_left = promo
    if activations_left <= 0:
        await message.reply(TEXTS["promo_redeem_3"].format(v0=esc(code)))
        return

    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or "Без имени"
    already_used = await db_query_one(
        "SELECT 1 FROM promocode_uses WHERE user_id = ? AND code = ?", (user_id, code)
    )
    if already_used:
        await message.reply(TEXTS["promo_redeem_4"])
        return

    await ensure_user(user_id, username)

    await db_exec(
        "UPDATE promocodes SET activations_left = activations_left - 1 "
        "WHERE code = ? AND activations_left > 0",
        (code,),
    )
    check = await db_query_one("SELECT activations_left FROM promocodes WHERE code = ?", (code,))
    if check is None:
        await message.reply(TEXTS["promo_redeem_2"])
        return
    if check[0] < activations_left:
        pass
    else:
        await message.reply(TEXTS["promo_redeem_3"].format(v0=esc(code)))
        return

    await db_exec(
        "INSERT INTO promocode_uses (user_id, code, used_at) VALUES (?, ?, ?)",
        (user_id, code, int(time.time())),
    )
    reward_label = await apply_promo_reward(user_id, reward_type, reward_key, amount)
    await message.reply(TEXTS["promo_redeem_5"].format(v0=esc(code), v1=reward_label))

@dp.message(F.text.lower() == "!логи")
async def admin_logs(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    rows = await db_query("SELECT ts, admin_username, command FROM audit_log ORDER BY id DESC LIMIT 20")
    if not rows:
        await message.reply(TEXTS["admin_logs_1"])
        return

    lines = []
    for ts, admin_username, command in rows:
        dt = datetime.fromtimestamp(ts).strftime("%d.%m %H:%M")
        lines.append(f"● [{dt}] @{esc(admin_username)}: {esc(command)}")

    await message.reply(TEXTS["admin_logs_2"].format(v0=len(rows), v1="\n".join(lines)))

@dp.message(F.text.lower().startswith("!топ спам"))
async def admin_top_spam(message: Message):
    """!топ спам        -> топ-20 игроков по числу команд за последний час
    !топ спам 30        -> тот же топ, но за последние 30 минут

    Источник — player_action_log (пишется в ThrottleMiddleware ДО rate-limit,
    см. _log_player_action), так что здесь видно и то, что троттлинг заглушил.
    Для каждого игрока также берём минимальный интервал между двумя ЕГО
    последовательными командами за то же окно — человек физически не может
    слать команды каждые доли секунды подолгу, поэтому маленький минимальный
    интервал при большом числе команд — сигнал на бота/скрипт, а не флуд руками.
    """
    if not is_admin(message):
        return
    await log_admin_action(message)

    parts = message.text.strip().split(maxsplit=2)
    minutes = 60
    if len(parts) > 2:
        try:
            minutes = max(1, int(parts[2]))
        except ValueError:
            minutes = 60

    since = int(time.time()) - minutes * 60
    rows = await db_query(
        "SELECT user_id, username, ts FROM player_action_log WHERE ts >= ? ORDER BY user_id, ts",
        (since,),
    )
    if not rows:
        await message.reply(TEXTS["admin_top_spam_1"])
        return

    per_user = {}
    for user_id, username, ts in rows:
        entry = per_user.setdefault(user_id, {"username": username, "count": 0, "min_gap": None, "last_ts": None})
        entry["username"] = username
        entry["count"] += 1
        if entry["last_ts"] is not None:
            gap = ts - entry["last_ts"]
            if entry["min_gap"] is None or gap < entry["min_gap"]:
                entry["min_gap"] = gap
        entry["last_ts"] = ts

    ranked = sorted(per_user.items(), key=lambda kv: kv[1]["count"], reverse=True)[:20]

    leg_by_user = {}
    if ranked:
        ids = [user_id for user_id, _ in ranked]
        placeholders = ",".join("?" for _ in ids)
        leg_rows = await db_query(
            f"SELECT user_id, score, evolution_level, rebirth_count, ultra_rebirth "
            f"FROM users WHERE user_id IN ({placeholders})",
            tuple(ids),
        )
        for uid, score, evo, rebirth_count, ultra in leg_rows:
            level = get_level_index(score or 0, evo or 0, rebirth_count or 0, bool(ultra))
            emoji, name, _ = get_level_visual(level)
            leg_by_user[uid] = f"{emoji} ур.{level}" + (f" ({name})" if name else "")

    lines = []
    for user_id, info in ranked:
        gap = info["min_gap"]
        suspicious = gap is not None and gap <= PLAYER_LOG_MIN_INTERVAL + 1
        marker = " ⚠️ подозрение на бота" if suspicious else ""
        gap_text = f"{gap}с" if gap is not None else "—"
        leg_text = leg_by_user.get(user_id, "—")
        lines.append(
            f"● @{esc(info['username'])} (id {user_id}), {leg_text}: "
            f"{info['count']} команд, мин. интервал {gap_text}{marker}"
        )

    await message.reply(TEXTS["admin_top_spam_2"].format(v0=minutes, v1=len(ranked), v2="\n".join(lines)))

@dp.message(F.text.lower() == "!логи вся")
async def admin_logs_all(message: Message):
    """!логи вся — вся история audit_log без ограничения в 20 записей.
    Telegram-сообщение ограничено ~4096 символами, поэтому шлём частями."""
    if not is_admin(message):
        return
    await log_admin_action(message)
    rows = await db_query("SELECT ts, admin_username, command FROM audit_log ORDER BY id DESC")
    if not rows:
        await message.reply(TEXTS["admin_logs_all_1"])
        return

    lines = []
    for ts, admin_username, command in rows:
        dt = datetime.fromtimestamp(ts).strftime("%d.%m %H:%M")
        lines.append(f"● [{dt}] @{esc(admin_username)}: {esc(command)}")

    total = len(rows)
    header = TEXTS["admin_logs_all_2"].format(v0=total, v1="")
    chunk_limit = 3800
    chunk_lines = []
    chunk_len = len(header)
    chunks = []
    for line in lines:
        if chunk_len + len(line) + 1 > chunk_limit and chunk_lines:
            chunks.append(chunk_lines)
            chunk_lines = []
            chunk_len = 0
        chunk_lines.append(line)
        chunk_len += len(line) + 1
    if chunk_lines:
        chunks.append(chunk_lines)

    for i, chunk in enumerate(chunks):
        if i == 0:
            await message.reply(TEXTS["admin_logs_all_2"].format(v0=total, v1="\n".join(chunk)))
        else:
            await message.answer("\n".join(chunk))

@dp.message(F.text.lower().startswith("!чистлоги"))
async def admin_clear_logs(message: Message):
    if not is_admin(message):
        return

    parts = message.text.strip().split(maxsplit=2)
    if len(parts) > 1 and parts[1].strip().lower() == "игроки":
        await _admin_clear_player_logs_impl(message, parts[2].strip().lower() if len(parts) > 2 else "")
        return

    parts = message.text.strip().split(maxsplit=1)
    arg = parts[1].strip().lower() if len(parts) > 1 else ""

    if arg in ("все", "всё", "all"):
        before_row = await db_query_one("SELECT COUNT(*) FROM audit_log")
        before = before_row[0] if before_row else 0
        await db_exec("DELETE FROM audit_log")
        await log_admin_action(message)
        await message.reply(TEXTS["admin_logs_clear_1"].format(v0=before, v1=0))
        return

    days = 7
    if arg:
        try:
            days = max(0, int(arg))
        except ValueError:
            days = 7

    cutoff = int(time.time()) - days * 86400
    before_row = await db_query_one("SELECT COUNT(*) FROM audit_log WHERE ts < ?", (cutoff,))
    before = before_row[0] if before_row else 0
    await db_exec("DELETE FROM audit_log WHERE ts < ?", (cutoff,))
    await log_admin_action(message)
    after_row = await db_query_one("SELECT COUNT(*) FROM audit_log")
    after = after_row[0] if after_row else 0
    await message.reply(TEXTS["admin_logs_clear_1"].format(v0=before, v1=after))

async def _admin_clear_player_logs_impl(message: Message, arg: str):
    if arg in ("все", "всё", "all"):
        before_row = await db_query_one("SELECT COUNT(*) FROM player_action_log")
        before = before_row[0] if before_row else 0
        await db_exec("DELETE FROM player_action_log")
        await log_admin_action(message)
        await message.reply(TEXTS["admin_logs_clear_1"].format(v0=before, v1=0))
        return

    days = 2
    if arg:
        try:
            days = max(0, int(arg))
        except ValueError:
            days = 2

    cutoff = int(time.time()) - days * 86400
    before_row = await db_query_one("SELECT COUNT(*) FROM player_action_log WHERE ts < ?", (cutoff,))
    before = before_row[0] if before_row else 0
    await db_exec("DELETE FROM player_action_log WHERE ts < ?", (cutoff,))
    await log_admin_action(message)
    after_row = await db_query_one("SELECT COUNT(*) FROM player_action_log")
    after = after_row[0] if after_row else 0
    await message.reply(TEXTS["admin_logs_clear_1"].format(v0=before, v1=after))

@dp.message(F.text.lower() == "!пинг")
async def admin_ping(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    start = time.monotonic()
    await db_query_one("SELECT 1")
    elapsed_ms = round((time.monotonic() - start) * 1000)
    await message.reply(TEXTS["admin_ping_1"].format(v0=elapsed_ms))

@dp.message(F.text.lower() == "!пинг5")
async def admin_ping5(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    samples = []
    for _ in range(5):
        start = time.monotonic()
        await db_query_one("SELECT 1")
        samples.append(round((time.monotonic() - start) * 1000))
    samples_text = ", ".join(str(s) for s in samples)
    await message.reply(
        TEXTS["admin_ping_2"].format(
            v0=samples_text, v1=min(samples), v2=round(sum(samples) / len(samples)), v3=max(samples)
        )
    )

@dp.message(F.text.lower() == "!ивент стоп")
async def admin_event_stop(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    active = await is_event_active()
    await db_exec(
        "INSERT INTO settings (key, value) VALUES ('event_active', '0') "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value"
    )
    _invalidate_event_state_cache()
    await message.reply(TEXTS["admin_event_stop_1"] if active else TEXTS["admin_event_stop_2"])

@dp.message(F.text.lower() == "!ивент статус")
async def admin_event_status(message: Message):
    if not is_admin(message):
        return
    await log_admin_action(message)
    active, mult = await get_event_state()
    if not active:
        await message.reply(TEXTS["admin_event_status_2"])
        return

    row = await db_query_one("SELECT value FROM settings WHERE key = 'event_until'")
    until = int(row[0]) if row and row[0] else 0
    if until:
        left = max(0, until - int(time.time()))
        m, s = divmod(left, 60)
        left_text = f"{m} мин. {s} сек."
    else:
        left_text = TEXTS["admin_event_status_forever"]

    await message.reply(TEXTS["admin_event_status_1"].format(v0=mult, v1=left_text))

async def handle(request):
    return web.Response(text="Бот Нога Работает!")

async def keep_alive():
    url = os.environ.get("RENDER_EXTERNAL_URL")
    if not url:
        domain = os.environ.get("KOYEB_PUBLIC_DOMAIN")
        if domain:
            url = f"https://{domain}"
    if not url:
        print("Ни RENDER_EXTERNAL_URL, ни KOYEB_PUBLIC_DOMAIN не заданы, self-ping отключён")
        return

    async with aiohttp.ClientSession() as session:
        while True:
            await asyncio.sleep(PING_INTERVAL)
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    print(f"Self-ping: {resp.status}")
            except Exception as e:
                print(f"Self-ping не удался: {e}")

async def main():
    await init_db()

    app = web.Application()
    app.router.add_get('/', handle)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()

    asyncio.create_task(keep_alive())
    asyncio.create_task(chronos_orb_boost_loop())
    asyncio.create_task(auto_log_cleanup_loop())
    asyncio.create_task(_flush_player_log_buffer())

    print("Бот НОГА запущен!")
    try:
        await dp.start_polling(bot, drop_pending_updates=False)
    finally:
        if _player_log_buffer:
            try:
                batch, _player_log_buffer[:] = _player_log_buffer[:], []
                await db_exec_many(
                    "INSERT INTO player_action_log (ts, user_id, username, command) VALUES (?, ?, ?, ?)",
                    batch,
                )
            except Exception as e:
                print(f"Финальный flush player_action_log не удался: {e}")
        await bot.session.close()
        await runner.cleanup()

if __name__ == "__main__":
    if not TOKEN:
        raise RuntimeError("Установи переменную окружения BOT_TOKEN")
    if not TURSO_URL or not TURSO_TOKEN:
        raise RuntimeError("Установи переменные окружения TURSO_DATABASE_URL и TURSO_AUTH_TOKEN")
    asyncio.run(main())
