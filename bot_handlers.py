"""Bot handlers.

Мед-советник по лабораторным анализам: при нажатии «Загрузить анализ» пользователь отправляет PDF или JPG
(скан/фото бланка) → вызов OpenAI API для извлечения структурированных данных и генерации текстового отчёта.
Отчёт формируется с учётом контекста (возраст, пол, жалобы, препараты и т.д.). Доступны сравнение двух анализов
и до 2 уточняющих вопросов на отчёт. Хранятся последние 3 анализа.

Логика экранов:
- start: регистрация/обновление user, реферальный код из args, показ соглашения.
- terms: принятие = главное меню. Без подписки: только Подписка, Лояльность, Помощь, О сервисе.
- main_menu (с подпиской): Загрузить анализ, Сравнить, Мои анализы, Как пользоваться, Подписка, Лояльность, Помощь, О сервисе.
- main_menu (без подписки): Подписка (с текстом «что входит»), Лояльность, Помощь, О сервисе.
- how_to_use: краткая инструкция в 4 шага (файл → контекст → отчёт → сравнение/уточнение).
- help: частые вопросы (форматы, лимиты, хранение).
- subscription_status: при активной подписке — дата окончания, запросы, бонусы; иначе — «что входит в подписку» + оформить.
- subscription_plans: выбор тарифа → создание платежа YooKassa, ссылка на оплату.
- loyalty: описание программы; ссылка и статистика начислений.
- upload: проверка подписки → дисклеймер (информационный характер) → ожидание файла → OpenAI extract → сбор контекста → OpenAI report → списание запроса, хранение до 3.
- recent_analyses: до 3 последних; выбор одного = краткое содержание + Полный отчёт / Сравнить / Уточнить / В меню.
- analysis_detail: краткое содержание; кнопка «Полный отчёт» показывает полный текст отчёта (частями при >4096 символов).
- compare: при ≥2 анализах выбор пары → сравнение через LLM; с одного анализа — выбор второго.
- follow_up: до 2 уточняющих вопросов по отчёту, ответ через LLM.
- admin: только ADMIN_ID; поиск по telegram_id или username → выдача/снятие подписки.
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from sqlalchemy.orm import Session
from database import User, AnalysisSession, StructuredResult, FollowUpQuestion, UserNotification
from subscription import SubscriptionManager
from payment import PaymentService
from file_processor import FileProcessor
from llm_service import LLMService
from redis_client import FSMStorage
from loguru import logger
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

try:
    from faq_analyses import search_faq
except Exception:
    search_faq = None

ADMIN_ID = 565638442

# Профессиональные тексты экранов (без маркетинговой и ИИ-размытости)
class T:
    # Общие
    NEED_START = "Для использования бота необходимо отправить команду /start."
    NEED_SUB = "Требуется активная подписка."
    ERR_TRY_AGAIN = "Произошла ошибка. Повторите попытку позже."
    SERVICE_UNAVAILABLE = "Сервис временно недоступен."
    BACK = "⬅ Назад"

    # Соглашение (приветствие и условия)
    WELCOME = (
        "Pulse — сервис интерпретации лабораторных результатов.\n\n"
        "Результаты носят информационный характер и не являются медицинским диагнозом. "
        "Лицам до 18 лет использование запрещено.\n\n"
        "Нажимая «Принимаю», вы подтверждаете ознакомление с условиями и согласие на обработку данных."
    )
    TERMS_TITLE = "Условия использования"
    TERMS_FULL = (
        "Условия использования сервиса Pulse\n\n"
        "1. Сервис предоставляет информационную интерпретацию лабораторных показателей на основе загруженных данных. "
        "Результаты не являются диагнозом и не заменяют консультацию врача или лабораторную диагностику.\n\n"
        "2. Использование сервиса разрешено лицам старше 18 лет.\n\n"
        "3. Персональные данные и загруженные файлы обрабатываются в соответствии с политикой конфиденциальности. "
        "Данные хранятся не более 60 дней.\n\n"
        "4. Администрация не несёт ответственности за решения, принятые пользователем на основе полученной информации."
    )
    TERMS_BTN = "📄 Условия"
    ACCEPT_BTN = "✅ Принимаю"

    # Главное меню
    MENU_CHOOSE = "Выберите действие:"

    # Подписка
    SUB_STATUS_TITLE = "Статус подписки"
    SUB_ACTIVE_UNTIL = "Активна до:"
    SUB_REQUESTS_LEFT = "Доступно запросов:"
    SUB_BONUS = "Бонусные запросы:"
    SUB_NO_ACTIVE = "Подписка не активна. Оформите подписку для доступа к анализам."
    SUB_WHAT_INCLUDED = (
        "В подписку входит: интерпретация анализов по загруженному файлу (PDF/фото), "
        "сравнение двух анализов, до 2 уточняющих вопросов на отчёт, хранение до 3 последних отчётов."
    )
    SUB_RENEW_BTN = "🔄 Продлить подписку"
    SUB_GET_BTN = "✅ Оформить подписку"
    SUB_PLANS_TITLE = "Тарифы: Базовая (только Спросить Pulse) и Премиум (всё включено)"

    # Лояльность (reward_per_payment=5, unlimited_referrals, applies_for_each_payment, requires_active_subscription, expire_with_subscription)
    LOYALTY_TITLE = "Программа лояльности Pulse"
    LOYALTY_RULES = (
        "За каждую успешную оплату по вашей персональной ссылке начисляется 5 дополнительных запросов.\n\n"
        "Начисления действуют при активной подписке."
    )
    LOYALTY_GET_LINK_BTN = "🔗 Получить персональную ссылку"
    LOYALTY_STATS_BTN = "📊 Статистика начислений"
    REFERRAL_LINK_TITLE = "Ваша персональная ссылка:"
    REFERRAL_STATS_TITLE = "Статистика по программе лояльности"
    REFERRAL_AVAILABLE = "Доступно (бонусных):"
    REFERRAL_USED = "Использовано:"
    REFERRAL_REMAINING = "Осталось:"
    LOYALTY_NOTIFICATION_TITLE = "Начисление по программе лояльности"
    LOYALTY_NOTIFICATION_BODY = (
        "Пользователь, зарегистрированный по вашей ссылке, оформил подписку.\n\n"
        "Вам начислено 5 дополнительных запросов."
    )
    LOYALTY_NOTIFICATION_BTN = "📊 Перейти в раздел подписки"

    # О сервисе
    ABOUT_TITLE = "О сервисе"
    ABOUT_BODY = (
        "Pulse предназначен для информационной интерпретации лабораторных результатов: "
        "загрузка PDF или фото бланка, формирование текстового отчёта, сравнение нескольких анализов, ответы на уточняющие вопросы.\n\n"
        "Сервис не заменяет консультацию врача и не предназначен для постановки диагноза."
    )

    # Загрузка и контекст
    UPLOAD_TITLE = "Загрузка анализа"
    UPLOAD_DISCLAIMER = "Результаты носят информационный характер и не заменяют консультацию врача."
    UPLOAD_PROMPT = "Отправьте один файл: PDF, JPG или PNG (скан или фото бланка результатов)."
    UPLOAD_WRONG_FILE = "Отправьте файл в формате PDF, JPG или PNG."
    UPLOAD_PROCESSING = "Файл обрабатывается."
    CONTEXT_TITLE = "Контекст для отчёта"
    CONTEXT_AGE = "Укажите возраст (полных лет):"
    CONTEXT_SEX = "Укажите пол:"
    CONTEXT_SYMPTOMS = "Опишите жалобы или симптомы (при отсутствии — «нет» или «—»):"
    CONTEXT_PREGNANCY = "Беременность (да/нет/не применимо):"
    CONTEXT_CHRONIC = "Хронические заболевания и учёт у врачей (при отсутствии — «нет» или «—»):"
    CONTEXT_MEDS = "Постоянно принимаемые препараты (при отсутствии — «нет» или «—»):"
    REPORT_GENERATING = "Формирование отчёта…"
    REPORT_HEADER = "Отчёт:"
    AFTER_REPORT_CHOOSE = "Выберите действие:"

    # Уточняющие вопросы
    FOLLOW_UP_LIMIT = "Достигнут лимит: 2 уточняющих вопроса на один отчёт."
    FOLLOW_UP_SESSION_LOST = "Сессия прервана. Вернитесь в меню и откройте анализ заново."
    FOLLOW_UP_ASK = "Задайте вопрос по отчёту (осталось {})."
    FOLLOW_UP_MORE = "Можно задать ещё вопросов: {}."

    # Оплата
    PAYMENT_TITLE = "Оплата"
    PAYMENT_LINK = "Перейдите по ссылке для завершения оплаты:"

    # Мои анализы
    RECENT_TITLE = "Мои анализы"
    RECENT_EMPTY = "Сохранённых анализов нет. Загрузите первый анализ из главного меню."
    RECENT_CHOOSE = "Выберите анализ для просмотра краткого содержания:"
    DETAIL_SUMMARY = "Краткое содержание:"
    DETAIL_FULL_REPORT_BTN = "📄 Полный отчёт"
    ANALYSIS_NOT_FOUND = "Анализ не найден."

    # Как пользоваться
    HOW_TO_USE_TITLE = "Как пользоваться"
    HOW_TO_USE_BODY = (
        "1. Нажмите «Загрузить анализ» и отправьте файл (PDF или фото бланка).\n"
        "2. Ответьте на несколько вопросов (возраст, пол, жалобы, препараты) для точности отчёта.\n"
        "3. Получите текстовый отчёт с интерпретацией показателей.\n"
        "4. При необходимости сравните с другим анализом или задайте до 2 уточняющих вопросов."
    )

    # Помощь / FAQ
    HELP_TITLE = "Помощь"
    HELP_BODY = (
        "Какие форматы файлов принимаются?\n"
        "PDF, JPG, PNG — скан или фото бланка результатов анализов.\n\n"
        "Сколько уточняющих вопросов можно задать?\n"
        "До 2 вопросов на один отчёт.\n\n"
        "Сколько анализов хранится?\n"
        "Последние 3. Новый анализ вытесняет более старый.\n\n"
        "Отчёт не заменяет консультацию врача и не является диагнозом."
    )

    # Сравнение
    COMPARE_TITLE = "Сравнение анализов"
    COMPARE_NEED_TWO = "Для сравнения необходимо не менее двух сохранённых анализов."
    COMPARE_CHOOSE_PAIR = "Выберите два анализа для сравнения:"
    COMPARE_CHOOSE_SECOND = "Выберите второй анализ для сравнения с выбранным:"
    COMPARE_NEED_ANOTHER = "Для сравнения нужен ещё один сохранённый анализ."
    COMPARE_PROGRESS = "Сравнение выполняется…"
    COMPARE_NOT_FOUND = "Один или оба анализа не найдены."

    # Админ
    ADMIN_DENIED = "Доступ запрещён."
    ADMIN_PANEL = "Админ-панель"
    ADMIN_CHOOSE = "Выберите действие:"
    ADMIN_SEARCH_ID = "Введите Telegram ID пользователя (число):"
    ADMIN_SEARCH_USERNAME = "Введите username (без символа @):"
    ADMIN_USER_NOT_FOUND = "Пользователь не найден."
    ADMIN_ENTER_NUMBER = "Введите числовой Telegram ID."
    ADMIN_ENTER_USERNAME = "Введите username."
    ADMIN_GRANT_ERR = "Не удалось выдать подписку."
    ADMIN_USER_CARD = "Пользователь"
    ADMIN_ID_BOT = "ID в боте:"
    ADMIN_TG_ID = "Telegram ID:"
    ADMIN_USERNAME = "Username:"
    ADMIN_SUB_STATUS = "Подписка:"
    ADMIN_ACTIVE_UNTIL = "Активна до:"
    ADMIN_REQUESTS = "Запросы (тариф / бонус / использовано):"
    ADMIN_GRANT_BASIC_1 = "📌 Базовая 1 мес"
    ADMIN_GRANT_BASIC_3 = "📌 Базовая 3 мес"
    ADMIN_GRANT_PREMIUM_1 = "⭐ Премиум 1 мес"
    ADMIN_GRANT_PREMIUM_3 = "⭐ Премиум 3 мес"
    ADMIN_REMOVE_BTN = "🗑 Убрать подписку"

    # Спросить Pulse (поиск по базе FAQ)
    ASK_PULSE_BTN = "💬 Спросить Pulse"
    ASK_PULSE_PROMPT = "Введите ваш вопрос по анализам (например: повышенный ТТГ, норма гемоглобина у женщин, что значит креатинин)."
    ASK_PULSE_HINT = (
        "💡 Подсказка: пишите название показателя и что интересует — «норма», «повышен»/«высокий» или «понижен»/«низкий». "
        "Можно формулировать естественно: «почему у меня низкий витамин D», «высокий ТТГ что делать». "
        "База содержит ответы по общему и биохимическому анализу крови, гормонам (щитовидная железа, половые), витаминам (D, B12), ферритину, моче и др. "
        "Указывайте направление (высокий/низкий) — так ответ будет точнее."
    )
    ASK_PULSE_SEARCHING = "Ищем ответ в базе…"
    ASK_PULSE_NOT_FOUND = "По вашему запросу подходящего ответа не найдено. Попробуйте переформулировать вопрос или использовать другие ключевые слова (название показателя, «норма», «повышен», «понижен»)."

    # Уведомления
    NOTIFICATIONS_TITLE = "🔔 Уведомления"
    NOTIFICATIONS_DESC = "Создайте напоминание на нужную дату и время — бот пришлёт вам ваше сообщение."
    NOTIFICATION_CREATE_BTN = "➕ Создать уведомление"
    NOTIFICATION_MY_BTN = "📋 Мои уведомления"
    NOTIFICATION_DATE_PROMPT = "Введите дату в любом формате (например 25.12.2025, 25022025, 25 02 2025):"
    NOTIFICATION_TIME_PROMPT = "Введите время по Москве в любом формате (например 14:30, 14 30, в 5, в 17 40):"
    NOTIFICATION_TEXT_PROMPT = "Введите текст уведомления — это сообщение придёт вам в выбранные день и время:"
    NOTIFICATION_CONFIRM = "Подтвердить"
    NOTIFICATION_CANCEL = "Отмена"
    NOTIFICATION_SUMMARY = "Уведомление на {date} в {time} (МСК):\n\n{text}"
    NOTIFICATION_SAVED = "Уведомление создано. Вы получите его в указанные день и время."
    NOTIFICATION_INVALID_DATE = "Неверный формат даты. Введите ДД.ММ.ГГГГ (например 25.12.2025)."
    NOTIFICATION_INVALID_TIME = "Неверный формат времени. Введите ЧЧ:ММ (например 14:30)."
    NOTIFICATION_DATE_PAST = "Эта дата уже прошла. Выберите будущую дату."
    NOTIFICATION_EMPTY_TEXT = "Текст не может быть пустым. Введите напоминание."
    NOTIFICATION_LIST_EMPTY = "У вас пока нет запланированных уведомлений."
    NOTIFICATION_LIST_HEADER = "Ваши запланированные уведомления:"
    NOTIFICATION_DELETE_BTN = "🗑 Удалить"
    # Мой профиль
    PROFILE_TITLE = "👤 Мой профиль"
    PROFILE_PLAN_BASIC = "Базовая"
    PROFILE_PLAN_PREMIUM = "Премиум"
    PROFILE_ACTIVE_UNTIL = "Действует до: {}"
    PROFILE_UPLOAD_REQUESTS = "Загрузить анализ: использовано {} из {}"
    PROFILE_UPLOAD_NA = "Загрузить анализ: недоступно (только в Премиум)"
    PROFILE_ASK_PULSE_REQUESTS = "Спросить Pulse: использовано {} из {}"
    PROFILE_ASK_PULSE_UNLIMITED = "Спросить Pulse: использовано {} (без лимита)"

# States
class States:
    START, TERMS_ACCEPTED = "start", "terms_accepted"
    COLLECTING_AGE, COLLECTING_SEX, COLLECTING_SYMPTOMS = "collecting_age", "collecting_sex", "collecting_symptoms"
    COLLECTING_PREGNANCY, COLLECTING_CHRONIC, COLLECTING_MEDICATIONS = "collecting_pregnancy", "collecting_chronic", "collecting_medications"
    PROCESSING_FILE, WAITING_FOLLOW_UP = "processing_file", "waiting_follow_up"
    ADMIN_WAIT_ID, ADMIN_WAIT_USERNAME = "admin_wait_id", "admin_wait_username"
    ASK_PULSE_WAITING = "ask_pulse_waiting"
    NOTIFICATION_DATE = "notification_date"
    NOTIFICATION_TIME = "notification_time"
    NOTIFICATION_TEXT = "notification_text"
    NOTIFICATION_CONFIRM = "notification_confirm"

MSG_NEED_START = T.NEED_START
MSG_NEED_SUB = T.NEED_SUB
MSG_ERR = T.ERR_TRY_AGAIN


class BotHandlers:
    def __init__(self, db: Session):
        self.db = db
        try:
            self.llm_service = LLMService()
        except Exception:
            self.llm_service = None
        try:
            self.file_processor = FileProcessor()
        except Exception:
            self.file_processor = None

    async def _reply(self, update: Update, text: str, keyboard=None):
        markup = InlineKeyboardMarkup(keyboard) if keyboard else None
        if update.callback_query:
            await update.callback_query.edit_message_text(text, reply_markup=markup)
        elif update.effective_message:
            await update.effective_message.reply_text(text, reply_markup=markup)

    def _user(self, telegram_id: int):
        return self.db.query(User).filter(User.telegram_id == telegram_id).first()

    async def _ensure_user(self, update: Update):
        u = self._user(update.effective_user.id)
        if u:
            return u
        await self._reply(update, MSG_NEED_START)
        return None

    def _is_admin(self, telegram_id: int) -> bool:
        return telegram_id == ADMIN_ID

    async def admin(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message or update.effective_user.id != ADMIN_ID:
            await update.message.reply_text(T.ADMIN_DENIED)
            return
        await self._admin_dashboard(update)

    async def _admin_dashboard(self, update: Update):
        text = f"{T.ADMIN_PANEL}\n\n{T.ADMIN_CHOOSE}"
        kb = [
            [InlineKeyboardButton("🔍 Поиск по ID", callback_data="admin_search_id")],
            [InlineKeyboardButton("👤 Поиск по username", callback_data="admin_search_username")],
        ]
        if update.callback_query:
            await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))
        else:
            await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb))

    async def _admin_user_card(self, update: Update, user: User):
        exp = user.subscription_expire_at.strftime("%Y-%m-%d") if user.subscription_expire_at else "—"
        uname = getattr(user, "username", None) or "—"
        plan = getattr(user, "subscription_plan", None) or "—"
        status_emoji = "✅" if user.subscription_status == "active" else "❌" if user.subscription_status == "inactive" else "⏰"
        text = (
            f"{T.ADMIN_USER_CARD}\n\n"
            f"{T.ADMIN_ID_BOT} {user.id}\n"
            f"{T.ADMIN_TG_ID} {user.telegram_id}\n"
            f"{T.ADMIN_USERNAME} @{uname}\n"
            f"{T.ADMIN_SUB_STATUS} {status_emoji} {user.subscription_status} ({plan})\n"
            f"{T.ADMIN_ACTIVE_UNTIL} {exp}\n"
            f"{T.ADMIN_REQUESTS} {user.total_requests or 0} / {user.bonus_requests or 0} / {user.used_requests or 0}"
        )
        kb = [
            [
                InlineKeyboardButton(T.ADMIN_GRANT_BASIC_1, callback_data=f"admin_grant_1month_basic_{user.id}"),
                InlineKeyboardButton(T.ADMIN_GRANT_BASIC_3, callback_data=f"admin_grant_3months_basic_{user.id}"),
            ],
            [
                InlineKeyboardButton(T.ADMIN_GRANT_PREMIUM_1, callback_data=f"admin_grant_1month_premium_{user.id}"),
                InlineKeyboardButton(T.ADMIN_GRANT_PREMIUM_3, callback_data=f"admin_grant_3months_premium_{user.id}"),
            ],
            [InlineKeyboardButton(T.ADMIN_REMOVE_BTN, callback_data=f"admin_remove_{user.id}")],
            [InlineKeyboardButton(T.BACK, callback_data="admin_back")],
        ]
        await self._reply(update, text, kb)

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        uid = update.effective_user.id
        args = context.args or []
        user = self._user(uid)
        if not user:
            user = User(telegram_id=uid)
            if args:
                ref = self.db.query(User).filter(User.referral_code == (args[0].upper() if args else "")).first()
                if ref:
                    user.referrer_id = ref.id
            self.db.add(user)
            self.db.commit()
        elif args and not user.referrer_id:
            ref = self.db.query(User).filter(User.referral_code == args[0].upper()).first()
            if ref and ref.id != user.id:
                user.referrer_id = ref.id
                self.db.commit()
        if not user.referral_code:
            user.generate_referral_code()
            self.db.commit()
        if update.effective_user.username and getattr(user, "username", None) != update.effective_user.username:
            user.username = update.effective_user.username
            self.db.commit()
        await self._show_terms(update)

    async def _show_terms(self, update: Update):
        text = T.WELCOME
        kb = [[InlineKeyboardButton(T.TERMS_BTN, callback_data="terms")], [InlineKeyboardButton(T.ACCEPT_BTN, callback_data="accept_terms")]]
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb))
        FSMStorage.set_state(update.effective_user.id, States.START)

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        q = update.callback_query
        await q.answer()
        uid, data = update.effective_user.id, q.data

        if self._is_admin(uid):
            if data == "admin_back":
                await self._admin_dashboard(update)
                return
            if data == "admin_search_id":
                FSMStorage.set_state(uid, States.ADMIN_WAIT_ID)
                await q.edit_message_text(T.ADMIN_SEARCH_ID)
                return
            if data == "admin_search_username":
                FSMStorage.set_state(uid, States.ADMIN_WAIT_USERNAME)
                await q.edit_message_text(T.ADMIN_SEARCH_USERNAME)
                return
            for prefix, plan_key in [
                ("admin_grant_1month_basic_", "1month_basic"),
                ("admin_grant_3months_basic_", "3months_basic"),
                ("admin_grant_1month_premium_", "1month_premium"),
                ("admin_grant_3months_premium_", "3months_premium"),
            ]:
                if data.startswith(prefix):
                    try:
                        target_id = int(data.replace(prefix, ""))
                        if SubscriptionManager.activate_subscription(self.db, target_id, plan_key):
                            user = self.db.query(User).filter(User.id == target_id).first()
                            await self._admin_user_card(update, user)
                        else:
                            await self._reply(update, T.ADMIN_GRANT_ERR)
                    except (ValueError, AttributeError):
                        await self._reply(update, T.ERR_TRY_AGAIN)
                    return
            if data.startswith("admin_remove_"):
                try:
                    target_id = int(data.replace("admin_remove_", ""))
                    if SubscriptionManager.deactivate(self.db, target_id):
                        user = self.db.query(User).filter(User.id == target_id).first()
                        await self._admin_user_card(update, user)
                    else:
                        await self._reply(update, T.ERR_TRY_AGAIN)
                except (ValueError, AttributeError):
                    await self._reply(update, T.ERR_TRY_AGAIN)
                return

        if data == "terms":
            kb = [[InlineKeyboardButton(T.BACK, callback_data="terms_back")]]
            await q.edit_message_text(f"{T.TERMS_TITLE}\n\n{T.TERMS_FULL}", reply_markup=InlineKeyboardMarkup(kb))
        elif data == "terms_back":
            kb = [[InlineKeyboardButton(T.TERMS_BTN, callback_data="terms")], [InlineKeyboardButton(T.ACCEPT_BTN, callback_data="accept_terms")]]
            await q.edit_message_text(T.WELCOME, reply_markup=InlineKeyboardMarkup(kb))
        elif data == "accept_terms":
            FSMStorage.set_state(uid, States.TERMS_ACCEPTED)
            await self._main_menu(update)
        elif data == "back_menu":
            FSMStorage.set_state(uid, States.TERMS_ACCEPTED)
            await self._main_menu(update)
        elif data == "about":
            await q.edit_message_text(f"{T.ABOUT_TITLE}\n\n{T.ABOUT_BODY}")
        elif data == "how_to_use":
            await self._how_to_use(update)
        elif data == "help":
            await self._help(update)
        elif data == "ask_pulse":
            await self._ask_pulse_request(update)
        elif data == "subscription":
            await self._subscription_status(update)
        elif data == "subscription_plans":
            await self._subscription_plans(update)
        elif data == "loyalty":
            await self._loyalty(update)
        elif data == "get_referral_link":
            await self._referral_link(update, context)
        elif data == "referral_stats":
            await self._referral_stats(update)
        elif data == "upload_analysis":
            await self._upload_request(update)
        elif data == "compare_analyses":
            await self._compare_request(update)
        elif data == "recent_analyses":
            await self._recent_analyses(update)
        elif data.startswith("plan_"):
            await self._payment(update, context, data.replace("plan_", ""))
        elif data.startswith("analysis_"):
            await self._analysis_detail(update, int(data.replace("analysis_", "")))
        elif data.startswith("compare_from_"):
            await self._compare_from(update, int(data.replace("compare_from_", "")))
        elif data.startswith("compare_"):
            parts = data.replace("compare_", "").split("_")
            if len(parts) >= 2:
                await self._do_compare(update, context, [int(parts[0]), int(parts[1])])
        elif data.startswith("follow_up_"):
            await self._follow_up_ask(update, context)
        elif data.startswith("full_report_"):
            await self._analysis_full_report(update, int(data.replace("full_report_", "")))
        elif data == "profile":
            await self._profile(update)
        elif data == "notifications":
            await self._notifications_menu(update)
        elif data == "notifications_list":
            await self._notifications_list(update)
        elif data == "notification_create":
            await self._notification_create_start(update)
        elif data == "notification_confirm":
            await self._notification_confirm(update)
        elif data == "notification_cancel":
            await self._notification_cancel(update)
        elif data.startswith("notification_del_"):
            await self._notification_delete(update, int(data.replace("notification_del_", "")))

    async def _main_menu(self, update: Update):
        uid = update.effective_user.id
        user = self._user(uid)
        active = user and SubscriptionManager.is_subscription_active(user)
        if active:
            plan = getattr(user, "subscription_plan", None) or "basic"
            kb = [[InlineKeyboardButton("👤 Мой профиль", callback_data="profile")]]
            if plan == "premium":
                kb.append([InlineKeyboardButton("📤 Загрузить анализ", callback_data="upload_analysis")])
            kb.append([InlineKeyboardButton("💬 Спросить Pulse", callback_data="ask_pulse")])
            if plan == "premium":
                kb.append([InlineKeyboardButton("📊 Сравнить", callback_data="compare_analyses")])
                kb.append([InlineKeyboardButton("📁 Мои анализы", callback_data="recent_analyses")])
                kb.append([InlineKeyboardButton("🔔 Уведомления", callback_data="notifications")])
            else:
                kb.append([InlineKeyboardButton("📊 Сравнить", callback_data="compare_analyses")])
                kb.append([InlineKeyboardButton("📁 Мои анализы", callback_data="recent_analyses")])
            kb.extend([
                [InlineKeyboardButton("❓ Как пользоваться", callback_data="how_to_use")],
                [InlineKeyboardButton("💳 Подписка", callback_data="subscription")],
                [InlineKeyboardButton("🎁 Программа лояльности", callback_data="loyalty")],
                [InlineKeyboardButton("🆘 Помощь", callback_data="help")],
                [InlineKeyboardButton("ℹ️ О сервисе", callback_data="about")],
            ])
        else:
            kb = [
                [InlineKeyboardButton("💳 Подписка", callback_data="subscription")],
                [InlineKeyboardButton("🎁 Программа лояльности", callback_data="loyalty")],
                [InlineKeyboardButton("🆘 Помощь", callback_data="help")],
                [InlineKeyboardButton("ℹ️ О сервисе", callback_data="about")],
            ]
        msg = T.MENU_CHOOSE
        if update.callback_query:
            await update.callback_query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(kb))
        else:
            await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(kb))

    async def _profile(self, update: Update):
        user = await self._ensure_user(update)
        if not user:
            return
        plan = getattr(user, "subscription_plan", None) or "basic"
        plan_name = T.PROFILE_PLAN_PREMIUM if plan == "premium" else T.PROFILE_PLAN_BASIC
        if SubscriptionManager.is_subscription_active(user):
            exp = user.subscription_expire_at.strftime("%d.%m.%Y") if user.subscription_expire_at else "—"
            lines = [
                T.PROFILE_TITLE,
                "",
                f"Подписка: {plan_name}",
                T.PROFILE_ACTIVE_UNTIL.format(exp),
                "",
            ]
            if plan == "premium":
                rem, tot, bonus, used_up = SubscriptionManager.get_available_requests(user)
                lines.append(T.PROFILE_UPLOAD_REQUESTS.format(used_up, used_up + rem))
            else:
                lines.append(T.PROFILE_UPLOAD_NA)
            total_ask, used_ask = SubscriptionManager.get_ask_pulse_requests(user)
            if total_ask is not None:
                lines.append(T.PROFILE_ASK_PULSE_REQUESTS.format(used_ask, total_ask))
            else:
                lines.append(T.PROFILE_ASK_PULSE_UNLIMITED.format(used_ask))
        else:
            lines = [T.PROFILE_TITLE, "", f"Подписка: не активна.", "Оформите подписку в разделе «Подписка»."]
        text = "\n".join(lines)
        await self._reply(update, text, [[InlineKeyboardButton(T.BACK, callback_data="back_menu")]])

    async def _subscription_status(self, update: Update):
        user = self._user(update.effective_user.id)
        if user and SubscriptionManager.is_subscription_active(user):
            exp = user.subscription_expire_at.strftime("%Y-%m-%d") if user.subscription_expire_at else "—"
            av, tot, bon, _ = SubscriptionManager.get_available_requests(user)
            text = (
                f"{T.SUB_STATUS_TITLE}\n\n"
                f"{T.SUB_ACTIVE_UNTIL} {exp}\n"
                f"{T.SUB_REQUESTS_LEFT} {av} из {tot}\n"
                f"{T.SUB_BONUS} +{bon}"
            )
            kb = [
                [InlineKeyboardButton(T.SUB_RENEW_BTN, callback_data="subscription_plans")],
                [InlineKeyboardButton(T.BACK, callback_data="back_menu")],
            ]
        else:
            text = f"{T.SUB_STATUS_TITLE}\n\n{T.SUB_NO_ACTIVE}\n\n{T.SUB_WHAT_INCLUDED}"
            kb = [
                [InlineKeyboardButton(T.SUB_GET_BTN, callback_data="subscription_plans")],
                [InlineKeyboardButton(T.BACK, callback_data="back_menu")],
            ]
        await self._reply(update, text, kb)

    async def _subscription_plans(self, update: Update):
        text = (
            f"{T.SUB_PLANS_TITLE}\n\n"
            "📌 Базовая — только «Спросить Pulse», без загрузки анализов и уведомлений.\n"
            "⭐ Премиум — загрузка анализов, уведомления, «Спросить Pulse» без лимита.\n"
        )
        kb = [
            [InlineKeyboardButton("📌 Базовая 1 мес — 199 ₽", callback_data="plan_1month_basic")],
            [InlineKeyboardButton("📌 Базовая 3 мес — 499 ₽", callback_data="plan_3months_basic")],
            [InlineKeyboardButton("📌 Базовая 6 мес — 899 ₽", callback_data="plan_6months_basic")],
            [InlineKeyboardButton("📌 Базовая 12 мес — 1499 ₽", callback_data="plan_12months_basic")],
            [InlineKeyboardButton("⭐ Премиум 1 мес — 299 ₽", callback_data="plan_1month_premium")],
            [InlineKeyboardButton("⭐ Премиум 3 мес — 799 ₽", callback_data="plan_3months_premium")],
            [InlineKeyboardButton("⭐ Премиум 6 мес — 1399 ₽", callback_data="plan_6months_premium")],
            [InlineKeyboardButton("⭐ Премиум 12 мес — 2499 ₽", callback_data="plan_12months_premium")],
            [InlineKeyboardButton(T.BACK, callback_data="subscription")],
        ]
        await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))

    async def _loyalty(self, update: Update):
        text = f"{T.LOYALTY_TITLE}\n\n{T.LOYALTY_RULES}"
        kb = [
            [InlineKeyboardButton(T.LOYALTY_GET_LINK_BTN, callback_data="get_referral_link")],
            [InlineKeyboardButton(T.LOYALTY_STATS_BTN, callback_data="referral_stats")],
            [InlineKeyboardButton(T.BACK, callback_data="back_menu")],
        ]
        await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))

    async def _referral_link(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = await self._ensure_user(update)
        if not user:
            return
        if not user.referral_code:
            user.generate_referral_code()
            self.db.commit()
        bot = await context.bot.get_me()
        link = f"https://t.me/{bot.username}?start={user.referral_code}"
        await self._reply(update, f"{T.REFERRAL_LINK_TITLE}\n\n{link}", [[InlineKeyboardButton(T.BACK, callback_data="loyalty")]])

    async def _referral_stats(self, update: Update):
        user = await self._ensure_user(update)
        if not user:
            return
        remaining, _, bonus, used = SubscriptionManager.get_available_requests(user)
        text = (
            f"{T.REFERRAL_STATS_TITLE}\n\n"
            f"{T.REFERRAL_AVAILABLE} {bonus}\n"
            f"{T.REFERRAL_USED} {used}\n"
            f"{T.REFERRAL_REMAINING} {remaining}"
        )
        await self._reply(update, text, [[InlineKeyboardButton(T.BACK, callback_data="loyalty")]])

    async def _how_to_use(self, update: Update):
        text = f"{T.HOW_TO_USE_TITLE}\n\n{T.HOW_TO_USE_BODY}"
        await self._reply(update, text, [[InlineKeyboardButton(T.BACK, callback_data="back_menu")]])

    async def _help(self, update: Update):
        text = f"{T.HELP_TITLE}\n\n{T.HELP_BODY}"
        await self._reply(update, text, [[InlineKeyboardButton(T.BACK, callback_data="back_menu")]])

    async def _notifications_menu(self, update: Update):
        user = await self._ensure_user(update)
        if not user:
            return
        if not SubscriptionManager.is_subscription_active(user):
            await self._reply(update, MSG_NEED_SUB, [[InlineKeyboardButton("💳 Подписка", callback_data="subscription")]])
            return
        if (getattr(user, "subscription_plan", None) or "basic") != "premium":
            await self._reply(update, "Уведомления доступны только по подписке Премиум.", [[InlineKeyboardButton(T.BACK, callback_data="back_menu")]])
            return
        text = f"{T.NOTIFICATIONS_TITLE}\n\n{T.NOTIFICATIONS_DESC}"
        kb = [
            [InlineKeyboardButton(T.NOTIFICATION_CREATE_BTN, callback_data="notification_create")],
            [InlineKeyboardButton(T.NOTIFICATION_MY_BTN, callback_data="notifications_list")],
            [InlineKeyboardButton(T.BACK, callback_data="back_menu")],
        ]
        await self._reply(update, text, kb)

    async def _notification_create_start(self, update: Update):
        user = await self._ensure_user(update)
        if not user or not SubscriptionManager.is_subscription_active(user) or (getattr(user, "subscription_plan", None) or "basic") != "premium":
            await self._reply(update, MSG_NEED_SUB, [[InlineKeyboardButton(T.BACK, callback_data="notifications")]])
            return
        FSMStorage.set_state(update.effective_user.id, States.NOTIFICATION_DATE)
        FSMStorage.set_data(update.effective_user.id, {})
        await self._reply(update, T.NOTIFICATION_DATE_PROMPT, [[InlineKeyboardButton(T.BACK, callback_data="notifications")]])

    def _parse_notification_date(self, s: str):
        """Принимает дату в любом формате: 19.02.2026, 19022026, 19 02 2026, 19-02-2026, 190226."""
        import re
        s = re.sub(r"\s+", " ", re.sub(r"[,.\-/]", " ", s.strip()))
        digits = [int(x) for x in re.findall(r"\d+", s)]
        if len(digits) >= 3:
            d, m, y = digits[0], digits[1], digits[2]
            if y < 100:
                y += 2000
            if d > 31:
                d, y = y, d
            if 2020 <= y <= 2100 and 1 <= m <= 12 and 1 <= d <= 31:
                return datetime(y, m, d)
        if len(digits) == 1 and len(str(digits[0])) >= 6:
            raw = str(digits[0])
            if len(raw) == 8:
                d, m, y = int(raw[0:2]), int(raw[2:4]), int(raw[4:8])
            elif len(raw) == 6:
                d, m, y = int(raw[0:2]), int(raw[2:4]), 2000 + int(raw[4:6])
            else:
                return None
            if 2020 <= y <= 2100 and 1 <= m <= 12 and 1 <= d <= 31:
                return datetime(y, m, d)
        if len(digits) == 3:
            if digits[0] > 31:
                digits[0], digits[2] = digits[2], digits[0]
            d, m, y = digits[0], digits[1], digits[2]
            if y < 100:
                y += 2000
            if 2020 <= y <= 2100 and 1 <= m <= 12 and 1 <= d <= 31:
                return datetime(y, m, d)
        return None

    def _parse_notification_time(self, s: str):
        """Принимает время в любом формате: 14:30, 14 30, 14.30, в 5, в 17 40, давай в 5."""
        import re
        digits = [int(x) for x in re.findall(r"\d+", s)]
        if len(digits) >= 2:
            h, m = digits[0], digits[1]
            if 0 <= h <= 23 and 0 <= m <= 59:
                return (h, m)
        if len(digits) == 1:
            h = digits[0]
            if 0 <= h <= 23:
                return (h, 0)
        return None

    async def _notification_confirm(self, update: Update):
        uid = update.effective_user.id
        user = self._user(uid)
        if not user:
            FSMStorage.set_state(uid, States.TERMS_ACCEPTED)
            await self._main_menu(update)
            return
        fsm = FSMStorage.get_data(uid)
        date_str = fsm.get("notification_date")  # "YYYY-MM-DD"
        time_list = fsm.get("notification_time")  # [h, m]
        text = fsm.get("notification_text")
        if not date_str or not time_list or not text or len(time_list) < 2:
            FSMStorage.set_state(uid, States.TERMS_ACCEPTED)
            await self._reply(update, MSG_ERR, [[InlineKeyboardButton(T.BACK, callback_data="notifications")]])
            return
        try:
            from datetime import timezone
            y, m, d = map(int, date_str.split("-"))
            h, minu = int(time_list[0]), int(time_list[1])
            moscow = ZoneInfo("Europe/Moscow")
            dt_moscow = datetime(y, m, d, h, minu, tzinfo=moscow)
            dt_utc = dt_moscow.astimezone(timezone.utc).replace(tzinfo=None)  # naive UTC для хранения
        except Exception:
            FSMStorage.set_state(uid, States.TERMS_ACCEPTED)
            await self._reply(update, MSG_ERR, [[InlineKeyboardButton(T.BACK, callback_data="notifications")]])
            return
        self.db.add(UserNotification(user_id=user.id, scheduled_at=dt_utc, text=text))
        self.db.commit()
        FSMStorage.set_state(uid, States.TERMS_ACCEPTED)
        FSMStorage.set_data(uid, {})
        await self._reply(update, T.NOTIFICATION_SAVED, [[InlineKeyboardButton(T.BACK, callback_data="notifications")]])

    async def _notification_cancel(self, update: Update):
        uid = update.effective_user.id
        FSMStorage.set_state(uid, States.TERMS_ACCEPTED)
        FSMStorage.set_data(uid, {})
        await self._notifications_menu(update)

    async def _notification_delete(self, update: Update, notification_id: int):
        user = await self._ensure_user(update)
        if not user:
            return
        n = self.db.query(UserNotification).filter(
            UserNotification.id == notification_id,
            UserNotification.user_id == user.id,
            UserNotification.sent == False,
        ).first()
        if n:
            self.db.delete(n)
            self.db.commit()
        await self._notifications_list(update)

    async def _notifications_list(self, update: Update):
        user = await self._ensure_user(update)
        if not user:
            return
        rows = self.db.query(UserNotification).filter(
            UserNotification.user_id == user.id,
            UserNotification.sent == False,
        ).order_by(UserNotification.scheduled_at.asc()).all()
        if not rows:
            await self._reply(update, T.NOTIFICATION_LIST_EMPTY, [[InlineKeyboardButton(T.BACK, callback_data="notifications")]])
            return
        from datetime import timezone
        moscow = ZoneInfo("Europe/Moscow")
        lines = [T.NOTIFICATION_LIST_HEADER]
        kb = []
        for n in rows[:20]:
            dt_utc = n.scheduled_at if n.scheduled_at.tzinfo else n.scheduled_at.replace(tzinfo=timezone.utc)
            dt_msk = dt_utc.astimezone(moscow)
            lines.append(f"\n• {dt_msk.strftime('%d.%m.%Y %H:%M')} (МСК)\n  {n.text[:60]}{'…' if len(n.text) > 60 else ''}")
            kb.append([InlineKeyboardButton(f"🗑 {dt_msk.strftime('%d.%m %H:%M')}", callback_data=f"notification_del_{n.id}")])
        kb.append([InlineKeyboardButton(T.BACK, callback_data="notifications")])
        await self._reply(update, "\n".join(lines), kb)

    async def _ask_pulse_request(self, update: Update):
        user = await self._ensure_user(update)
        if not user:
            return
        if not SubscriptionManager.can_ask_pulse(self.db, user.id):
            await self._reply(update, MSG_NEED_SUB if not SubscriptionManager.is_subscription_active(user) else "Лимит запросов «Спросить Pulse» исчерпан. Продлите подписку или дождитесь обновления лимита.", [[InlineKeyboardButton("💳 Подписка", callback_data="subscription")]])
            return
        FSMStorage.set_state(update.effective_user.id, States.ASK_PULSE_WAITING)
        text = f"{T.ASK_PULSE_PROMPT}\n\n{T.ASK_PULSE_HINT}"
        await self._reply(update, text, [[InlineKeyboardButton(T.BACK, callback_data="back_menu")]])

    async def _ask_pulse_handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE, query: str):
        """Прогресс-бар (галочки) и поиск в FAQ по ключевым словам."""
        uid = update.effective_user.id
        chat_id = update.effective_chat.id
        steps = 5
        msg = await update.message.reply_text(f"{T.ASK_PULSE_SEARCHING} {'⬜' * steps}")
        for i in range(1, steps + 1):
            await asyncio.sleep(0.35)
            try:
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=msg.message_id,
                    text=f"{T.ASK_PULSE_SEARCHING} {'✅' * i}{'⬜' * (steps - i)}",
                )
            except Exception:
                pass
        if not search_faq:
            await context.bot.edit_message_text(chat_id=chat_id, message_id=msg.message_id, text=T.SERVICE_UNAVAILABLE)
            FSMStorage.set_state(uid, States.TERMS_ACCEPTED)
            return
        results = search_faq(query, top_k=1)
        back_kb = InlineKeyboardMarkup([[InlineKeyboardButton(T.BACK, callback_data="back_menu")]])
        if not results:
            await context.bot.edit_message_text(
                chat_id=chat_id, message_id=msg.message_id, text=T.ASK_PULSE_NOT_FOUND, reply_markup=back_kb
            )
        else:
            _, answer, _ = results[0]
            await context.bot.edit_message_text(
                chat_id=chat_id, message_id=msg.message_id, text=f"Ответ:\n\n{answer}", reply_markup=back_kb
            )
            user = self._user(uid)
            if user:
                SubscriptionManager.use_ask_pulse_request(self.db, user.id)
        FSMStorage.set_state(uid, States.TERMS_ACCEPTED)

    async def _upload_request(self, update: Update):
        user = await self._ensure_user(update)
        if not user:
            return
        if not SubscriptionManager.can_perform_analysis(self.db, user.id):
            await self._reply(update, MSG_NEED_SUB, [[InlineKeyboardButton("💳 Подписка", callback_data="subscription")]])
            return
        await update.callback_query.edit_message_text(
            f"{T.UPLOAD_TITLE}\n\n{T.UPLOAD_DISCLAIMER}\n\n{T.UPLOAD_PROMPT}"
        )
        FSMStorage.set_state(update.effective_user.id, States.PROCESSING_FILE)

    async def handle_file(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        uid = update.effective_user.id
        if FSMStorage.get_state(uid) != States.PROCESSING_FILE:
            return
        user = self._user(uid)
        if not user:
            await update.message.reply_text(MSG_NEED_START)
            return
        if not SubscriptionManager.can_perform_analysis(self.db, user.id):
            await update.message.reply_text(MSG_NEED_SUB)
            await self._subscription_status(update)
            FSMStorage.set_state(uid, States.TERMS_ACCEPTED)
            return
        if update.message.document:
            doc = update.message.document
            file = await context.bot.get_file(doc.file_id)
            mime = doc.mime_type or (doc.file_name.split(".")[-1] if doc.file_name else "application/octet-stream")
        elif update.message.photo:
            doc = update.message.photo[-1]
            file = await context.bot.get_file(doc.file_id)
            mime = "image/jpeg"
        else:
            await update.message.reply_text(T.UPLOAD_WRONG_FILE)
            return
        buf = bytes(await file.download_as_bytearray())
        await update.message.reply_text(T.UPLOAD_PROCESSING)
        try:
            if not self.file_processor or not self.llm_service or not getattr(self.llm_service, "enabled", True):
                await update.message.reply_text(T.SERVICE_UNAVAILABLE)
                FSMStorage.set_state(uid, States.TERMS_ACCEPTED)
                return
            raw = self.file_processor.process_file(buf, mime)
            data = self.llm_service.extract_structured_data(raw)
            user = self._user(uid)
            session = AnalysisSession(user_id=user.id)
            self.db.add(session)
            self.db.commit()
            self.db.refresh(session)
            self.db.add(StructuredResult(session_id=session.id, structured_json=data))
            self.db.commit()
            fsm = FSMStorage.get_data(uid)
            fsm["session_id"] = session.id
            fsm["structured_data"] = data
            FSMStorage.set_data(uid, fsm)
            await update.message.reply_text(f"{T.CONTEXT_TITLE}\n\n{T.CONTEXT_AGE}")
            FSMStorage.set_state(uid, States.COLLECTING_AGE)
        except Exception as e:
            logger.error(f"File: {e}")
            await update.message.reply_text(MSG_ERR)
            FSMStorage.set_state(uid, States.TERMS_ACCEPTED)

    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        uid = update.effective_user.id
        text = (update.message.text or "").strip()
        state = FSMStorage.get_state(uid)
        fsm = FSMStorage.get_data(uid)

        if self._is_admin(uid) and state == States.ADMIN_WAIT_ID:
            FSMStorage.set_state(uid, States.TERMS_ACCEPTED)
            try:
                tid = int(text)
                user = self.db.query(User).filter(User.telegram_id == tid).first()
                if user:
                    await self._admin_user_card(update, user)
                else:
                    await update.message.reply_text(T.ADMIN_USER_NOT_FOUND)
            except ValueError:
                await update.message.reply_text(T.ADMIN_ENTER_NUMBER)
            return
        if self._is_admin(uid) and state == States.ADMIN_WAIT_USERNAME:
            FSMStorage.set_state(uid, States.TERMS_ACCEPTED)
            name = text.lstrip("@").strip().lower()
            if not name:
                await update.message.reply_text(T.ADMIN_ENTER_USERNAME)
                return
            user = self.db.query(User).filter(User.username.ilike(name)).first()
            if user:
                await self._admin_user_card(update, user)
            else:
                await update.message.reply_text(T.ADMIN_USER_NOT_FOUND)
            return

        if state == States.ASK_PULSE_WAITING:
            if not text:
                await update.message.reply_text(T.ASK_PULSE_PROMPT)
                return
            await self._ask_pulse_handle(update, context, text)
            return

        if state == States.NOTIFICATION_DATE:
            date_obj = self._parse_notification_date(text)
            if not date_obj:
                await update.message.reply_text(T.NOTIFICATION_INVALID_DATE)
                return
            from datetime import datetime as dt_now
            if date_obj.date() < dt_now.now().date():
                await update.message.reply_text(T.NOTIFICATION_DATE_PAST)
                return
            date_str = date_obj.strftime("%Y-%m-%d")
            fsm["notification_date"] = date_str
            FSMStorage.set_data(uid, fsm)
            FSMStorage.set_state(uid, States.NOTIFICATION_TIME)
            await update.message.reply_text(T.NOTIFICATION_TIME_PROMPT, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(T.BACK, callback_data="notifications")]]))

        elif state == States.NOTIFICATION_TIME:
            time_tup = self._parse_notification_time(text)
            if not time_tup:
                await update.message.reply_text(T.NOTIFICATION_INVALID_TIME)
                return
            fsm["notification_time"] = list(time_tup)
            FSMStorage.set_data(uid, fsm)
            FSMStorage.set_state(uid, States.NOTIFICATION_TEXT)
            await update.message.reply_text(T.NOTIFICATION_TEXT_PROMPT, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(T.BACK, callback_data="notifications")]]))

        elif state == States.NOTIFICATION_TEXT:
            if not text or not text.strip():
                await update.message.reply_text(T.NOTIFICATION_EMPTY_TEXT)
                return
            fsm["notification_text"] = text.strip()[:2000]
            FSMStorage.set_data(uid, fsm)
            FSMStorage.set_state(uid, States.NOTIFICATION_CONFIRM)
            date_str = fsm.get("notification_date", "")
            time_list = fsm.get("notification_time", [0, 0])
            try:
                y, m, d = map(int, date_str.split("-"))
                date_display = f"{d:02d}.{m:02d}.{y}"
                time_display = f"{int(time_list[0]):02d}:{int(time_list[1]):02d}"
            except Exception:
                date_display = date_str
                time_display = f"{time_list[0]}:{time_list[1]}"
            summary = T.NOTIFICATION_SUMMARY.format(date=date_display, time=time_display, text=fsm["notification_text"])
            kb = [
                [InlineKeyboardButton(T.NOTIFICATION_CONFIRM, callback_data="notification_confirm")],
                [InlineKeyboardButton(T.NOTIFICATION_CANCEL, callback_data="notification_cancel")],
            ]
            await update.message.reply_text(summary, reply_markup=InlineKeyboardMarkup(kb))

        elif state == States.NOTIFICATION_CONFIRM:
            await update.message.reply_text("Нажмите «Подтвердить» или «Отмена» под сообщением выше.")

        elif state == States.COLLECTING_AGE:
            fsm["age"] = text
            FSMStorage.set_data(uid, fsm)
            FSMStorage.set_state(uid, States.COLLECTING_SEX)
            await update.message.reply_text(T.CONTEXT_SEX)
        elif state == States.COLLECTING_SEX:
            fsm["sex"] = text
            FSMStorage.set_data(uid, fsm)
            FSMStorage.set_state(uid, States.COLLECTING_SYMPTOMS)
            await update.message.reply_text(T.CONTEXT_SYMPTOMS)
        elif state == States.COLLECTING_SYMPTOMS:
            fsm["symptoms"] = text
            FSMStorage.set_data(uid, fsm)
            if (fsm.get("sex") or "").lower() in ("female", "f", "женский"):
                FSMStorage.set_state(uid, States.COLLECTING_PREGNANCY)
                await update.message.reply_text(T.CONTEXT_PREGNANCY)
            else:
                fsm["pregnancy"] = "N/A"
                FSMStorage.set_data(uid, fsm)
                FSMStorage.set_state(uid, States.COLLECTING_CHRONIC)
                await update.message.reply_text(T.CONTEXT_CHRONIC)
        elif state == States.COLLECTING_PREGNANCY:
            fsm["pregnancy"] = text
            FSMStorage.set_data(uid, fsm)
            FSMStorage.set_state(uid, States.COLLECTING_CHRONIC)
            await update.message.reply_text(T.CONTEXT_CHRONIC)
        elif state == States.COLLECTING_CHRONIC:
            fsm["chronic_conditions"] = text
            FSMStorage.set_data(uid, fsm)
            FSMStorage.set_state(uid, States.COLLECTING_MEDICATIONS)
            await update.message.reply_text(T.CONTEXT_MEDS)
        elif state == States.COLLECTING_MEDICATIONS:
            fsm["medications"] = text
            FSMStorage.set_data(uid, fsm)
            await update.message.reply_text(T.REPORT_GENERATING)
            user = self._user(uid)
            if not user or not SubscriptionManager.can_perform_analysis(self.db, user.id):
                await update.message.reply_text(MSG_NEED_SUB)
                await self._subscription_status(update)
                FSMStorage.set_state(uid, States.TERMS_ACCEPTED)
                return
            sid = fsm["session_id"]
            ctx = {k: fsm.get(k) for k in ("age", "sex", "symptoms", "pregnancy", "chronic_conditions", "medications")}
            try:
                if not self.llm_service or not getattr(self.llm_service, "enabled", True):
                    await update.message.reply_text(T.SERVICE_UNAVAILABLE)
                    FSMStorage.set_state(uid, States.TERMS_ACCEPTED)
                    return
                report = self.llm_service.generate_clinical_report(fsm["structured_data"], ctx)
                res = self.db.query(StructuredResult).filter(StructuredResult.session_id == sid).first()
                if res:
                    res.clinical_context = ctx
                    res.report = report
                    self.db.commit()
                SubscriptionManager.use_request(self.db, user.id)
                from cleanup import cleanup_user_analyses
                cleanup_user_analyses(user.id, keep_count=3)
                await update.message.reply_text(f"{T.REPORT_HEADER}\n\n{report}")
                kb = [
                    [
                        InlineKeyboardButton("📊 Сравнить", callback_data=f"compare_from_{sid}"),
                        InlineKeyboardButton("❓ Уточнить", callback_data=f"follow_up_{sid}"),
                    ],
                    [InlineKeyboardButton("🏠 В меню", callback_data="back_menu")],
                ]
                await update.message.reply_text(T.AFTER_REPORT_CHOOSE, reply_markup=InlineKeyboardMarkup(kb))
                fsm["current_session_id"] = sid
                fsm["follow_up_count"] = 0
                FSMStorage.set_data(uid, fsm)
                FSMStorage.set_state(uid, States.TERMS_ACCEPTED)
            except Exception as e:
                logger.error(f"Report: {e}")
                await update.message.reply_text(MSG_ERR)
                FSMStorage.set_state(uid, States.TERMS_ACCEPTED)
        elif state == States.WAITING_FOLLOW_UP:
            n = fsm.get("follow_up_count", 0)
            if n >= 2:
                await update.message.reply_text(T.FOLLOW_UP_LIMIT)
                await self._main_menu(update)
                FSMStorage.set_state(uid, States.TERMS_ACCEPTED)
                return
            sid = fsm.get("current_session_id") or fsm.get("session_id")
            if not sid:
                await update.message.reply_text(T.FOLLOW_UP_SESSION_LOST)
                return
            res = self.db.query(StructuredResult).filter(StructuredResult.session_id == sid).first()
            if not res:
                await update.message.reply_text(T.ANALYSIS_NOT_FOUND)
                return
            try:
                if not self.llm_service or not getattr(self.llm_service, "enabled", True):
                    await update.message.reply_text(T.SERVICE_UNAVAILABLE)
                    return
                ans = self.llm_service.answer_follow_up_question(res.structured_json, res.clinical_context or {}, res.report or "", text)
                self.db.add(FollowUpQuestion(session_id=sid, question=text, answer=ans))
                self.db.commit()
                await update.message.reply_text(ans)
                fsm["follow_up_count"] = n + 1
                FSMStorage.set_data(uid, fsm)
                if n + 1 >= 2:
                    await self._main_menu(update)
                    FSMStorage.set_state(uid, States.TERMS_ACCEPTED)
                else:
                    left = 2 - n - 1
                    kb = [
                        [InlineKeyboardButton("❓ Уточнить", callback_data=f"follow_up_{sid}")],
                        [InlineKeyboardButton("🏠 В меню", callback_data="back_menu")],
                    ]
                    await update.message.reply_text(T.FOLLOW_UP_MORE.format(left), reply_markup=InlineKeyboardMarkup(kb))
            except Exception as e:
                logger.error(f"Follow-up: {e}")
                await update.message.reply_text(MSG_ERR)
        else:
            await self._main_menu(update)
            FSMStorage.set_state(uid, States.TERMS_ACCEPTED)

    async def _follow_up_ask(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.callback_query.answer()
        user = await self._ensure_user(update)
        if not user or not SubscriptionManager.is_subscription_active(user):
            await self._reply(update, MSG_NEED_SUB)
            return
        uid = update.effective_user.id
        data = update.callback_query.data
        sid = int(data.replace("follow_up_", "")) if data.startswith("follow_up_") else (FSMStorage.get_data(uid).get("current_session_id") or FSMStorage.get_data(uid).get("session_id"))
        if not sid:
            await self._reply(update, T.ANALYSIS_NOT_FOUND)
            return
        n = FSMStorage.get_data(uid).get("follow_up_count", 0)
        if n >= 2:
            await self._reply(update, T.FOLLOW_UP_LIMIT)
            await self._main_menu(update)
            return
        fsm = FSMStorage.get_data(uid)
        fsm["current_session_id"] = sid
        FSMStorage.set_data(uid, fsm)
        FSMStorage.set_state(uid, States.WAITING_FOLLOW_UP)
        await self._reply(update, T.FOLLOW_UP_ASK.format(2 - n))

    async def _payment(self, update: Update, context: ContextTypes.DEFAULT_TYPE, plan: str):
        user = await self._ensure_user(update)
        if not user:
            return
        try:
            info = PaymentService.create_payment(user.id, plan, self.db)
            await update.callback_query.edit_message_text(f"{T.PAYMENT_TITLE}\n\n{T.PAYMENT_LINK}\n{info.get('confirmation_url', '')}")
        except Exception as e:
            logger.error(f"Payment: {e}")
            await update.callback_query.edit_message_text(MSG_ERR)

    async def _recent_analyses(self, update: Update):
        user = await self._ensure_user(update)
        if not user:
            return
        if not SubscriptionManager.is_subscription_active(user):
            await self._reply(update, MSG_NEED_SUB)
            return
        sessions = self.db.query(AnalysisSession).filter(AnalysisSession.user_id == user.id).order_by(AnalysisSession.created_at.desc()).limit(3).all()
        if not sessions:
            await self._reply(update, T.RECENT_EMPTY, [[InlineKeyboardButton(T.BACK, callback_data="back_menu")]])
            return
        lines = []
        kb = []
        for s in sessions:
            d = s.created_at.strftime("%Y-%m-%d %H:%M")
            lines.append(d)
            kb.append([InlineKeyboardButton(d, callback_data=f"analysis_{s.id}")])
        kb.append([InlineKeyboardButton(T.BACK, callback_data="back_menu")])
        await self._reply(update, f"{T.RECENT_TITLE}\n\n{T.RECENT_CHOOSE}\n\n" + "\n".join(lines), kb)

    async def _analysis_detail(self, update: Update, session_id: int):
        user = await self._ensure_user(update)
        if not user:
            return
        if not SubscriptionManager.is_subscription_active(user):
            await self._reply(update, MSG_NEED_SUB)
            return
        session = self.db.query(AnalysisSession).filter(AnalysisSession.id == session_id, AnalysisSession.user_id == user.id).first()
        if not session:
            await self._reply(update, T.ANALYSIS_NOT_FOUND)
            return
        res = self.db.query(StructuredResult).filter(StructuredResult.session_id == session_id).first()
        if not res or not res.report:
            await self._reply(update, T.ANALYSIS_NOT_FOUND)
            return
        summary = (res.report[:500] + "…") if len(res.report) > 500 else res.report
        kb = [
            [InlineKeyboardButton(T.DETAIL_FULL_REPORT_BTN, callback_data=f"full_report_{session_id}")],
            [
                InlineKeyboardButton("📊 Сравнить", callback_data=f"compare_from_{session_id}"),
                InlineKeyboardButton("❓ Уточнить", callback_data=f"follow_up_{session_id}"),
            ],
            [InlineKeyboardButton("🏠 В меню", callback_data="back_menu")],
        ]
        await self._reply(update, f"{T.DETAIL_SUMMARY}\n\n{summary}", kb)

    async def _analysis_full_report(self, update: Update, session_id: int):
        """Show full report text (chunked if > 4096)."""
        user = await self._ensure_user(update)
        if not user:
            return
        if not SubscriptionManager.is_subscription_active(user):
            await self._reply(update, MSG_NEED_SUB)
            return
        session = self.db.query(AnalysisSession).filter(AnalysisSession.id == session_id, AnalysisSession.user_id == user.id).first()
        if not session:
            await self._reply(update, T.ANALYSIS_NOT_FOUND)
            return
        res = self.db.query(StructuredResult).filter(StructuredResult.session_id == session_id).first()
        if not res or not res.report:
            await self._reply(update, T.ANALYSIS_NOT_FOUND)
            return
        report = res.report
        chunk_size = 4090
        if len(report) <= chunk_size:
            await self._reply(update, f"{T.REPORT_HEADER}\n\n{report}", [
                [
                    InlineKeyboardButton("📊 Сравнить", callback_data=f"compare_from_{session_id}"),
                    InlineKeyboardButton("❓ Уточнить", callback_data=f"follow_up_{session_id}"),
                ],
                [InlineKeyboardButton("🏠 В меню", callback_data="back_menu")],
            ])
            return
        for i in range(0, len(report), chunk_size):
            chunk = report[i : i + chunk_size]
            await update.effective_message.reply_text(chunk)
        kb = [
            [
                InlineKeyboardButton("📊 Сравнить", callback_data=f"compare_from_{session_id}"),
                InlineKeyboardButton("❓ Уточнить", callback_data=f"follow_up_{session_id}"),
            ],
            [InlineKeyboardButton("🏠 В меню", callback_data="back_menu")],
        ]
        await update.effective_message.reply_text("Выберите действие:", reply_markup=InlineKeyboardMarkup(kb))

    async def _compare_request(self, update: Update):
        user = await self._ensure_user(update)
        if not user:
            return
        if not SubscriptionManager.is_subscription_active(user):
            await self._reply(update, MSG_NEED_SUB)
            return
        sessions = self.db.query(AnalysisSession).filter(AnalysisSession.user_id == user.id).order_by(AnalysisSession.created_at.desc()).limit(3).all()
        if len(sessions) < 2:
            await self._reply(update, T.COMPARE_NEED_TWO, [[InlineKeyboardButton(T.BACK, callback_data="back_menu")]])
            return
        kb = []
        for i in range(min(2, len(sessions))):
            for j in range(i + 1, min(3, len(sessions))):
                a, b = sessions[i], sessions[j]
                kb.append([InlineKeyboardButton(f"{a.created_at.strftime('%Y-%m-%d')} и {b.created_at.strftime('%Y-%m-%d')}", callback_data=f"compare_{a.id}_{b.id}")])
        kb.append([InlineKeyboardButton(T.BACK, callback_data="back_menu")])
        await self._reply(update, f"{T.COMPARE_TITLE}\n\n{T.COMPARE_CHOOSE_PAIR}", kb)

    async def _compare_from(self, update: Update, session_id: int):
        user = await self._ensure_user(update)
        if not user:
            return
        if not SubscriptionManager.is_subscription_active(user):
            await self._reply(update, MSG_NEED_SUB)
            return
        current = self.db.query(AnalysisSession).filter(AnalysisSession.id == session_id, AnalysisSession.user_id == user.id).first()
        if not current:
            await self._reply(update, T.ANALYSIS_NOT_FOUND)
            return
        others = self.db.query(AnalysisSession).filter(AnalysisSession.user_id == user.id, AnalysisSession.id != session_id).order_by(AnalysisSession.created_at.desc()).limit(3).all()
        if not others:
            await self._reply(update, T.COMPARE_NEED_ANOTHER, [[InlineKeyboardButton(T.BACK, callback_data=f"analysis_{session_id}")]])
            return
        kb = [[InlineKeyboardButton(s.created_at.strftime("%Y-%m-%d"), callback_data=f"compare_{session_id}_{s.id}")] for s in others]
        kb.append([InlineKeyboardButton(T.BACK, callback_data=f"analysis_{session_id}")])
        await self._reply(update, T.COMPARE_CHOOSE_SECOND, kb)

    async def _do_compare(self, update: Update, context: ContextTypes.DEFAULT_TYPE, session_ids: list):
        user = await self._ensure_user(update)
        if not user or len(session_ids) < 2:
            return
        if not SubscriptionManager.is_subscription_active(user):
            await self._reply(update, MSG_NEED_SUB)
            return
        s1_id, s2_id = int(session_ids[0]), int(session_ids[1])
        s1 = self.db.query(AnalysisSession).filter(AnalysisSession.id == s1_id, AnalysisSession.user_id == user.id).first()
        s2 = self.db.query(AnalysisSession).filter(AnalysisSession.id == s2_id, AnalysisSession.user_id == user.id).first()
        if not s1 or not s2:
            await self._reply(update, T.COMPARE_NOT_FOUND)
            return
        r1 = self.db.query(StructuredResult).filter(StructuredResult.session_id == s1_id).first()
        r2 = self.db.query(StructuredResult).filter(StructuredResult.session_id == s2_id).first()
        if not r1 or not r2:
            await self._reply(update, T.COMPARE_NOT_FOUND)
            return
        await update.callback_query.edit_message_text(T.COMPARE_PROGRESS)
        try:
            if not self.llm_service or not getattr(self.llm_service, "enabled", True):
                await self._reply(update, T.SERVICE_UNAVAILABLE)
                return
            c1 = dict(r1.clinical_context or {})
            c1["date"] = s1.created_at.strftime("%Y-%m-%d")
            c2 = dict(r2.clinical_context or {})
            c2["date"] = s2.created_at.strftime("%Y-%m-%d")
            report = self.llm_service.compare_analyses(r1.structured_json, r2.structured_json, c1, c2)
            await self._reply(update, report, [[InlineKeyboardButton(T.BACK, callback_data="back_menu")]])
        except Exception as e:
            logger.error(f"Compare: {e}")
            await self._reply(update, MSG_ERR)
