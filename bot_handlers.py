"""Bot handlers."""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from sqlalchemy.orm import Session
from database import User, AnalysisSession, StructuredResult, FollowUpQuestion
from subscription import SubscriptionManager
from payment import PaymentService
from file_processor import FileProcessor
from llm_service import LLMService
from redis_client import FSMStorage
from loguru import logger

# States
class States:
    START, TERMS_ACCEPTED = "start", "terms_accepted"
    COLLECTING_AGE, COLLECTING_SEX, COLLECTING_SYMPTOMS = "collecting_age", "collecting_sex", "collecting_symptoms"
    COLLECTING_PREGNANCY, COLLECTING_CHRONIC, COLLECTING_MEDICATIONS = "collecting_pregnancy", "collecting_chronic", "collecting_medications"
    PROCESSING_FILE, WAITING_FOLLOW_UP = "processing_file", "waiting_follow_up"

MSG_NEED_START = "Send /start first."
MSG_NEED_SUB = "Subscription required."
MSG_ERR = "Error. Try again."


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
        await self._show_terms(update)

    async def _show_terms(self, update: Update):
        text = """Welcome. Lab results interpretation (informational only, not a diagnosis). 18+. By continuing you agree to the terms."""
        kb = [[InlineKeyboardButton("Terms", callback_data="terms")], [InlineKeyboardButton("Accept", callback_data="accept_terms")]]
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb))
        FSMStorage.set_state(update.effective_user.id, States.START)

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        q = update.callback_query
        await q.answer()
        uid, data = update.effective_user.id, q.data

        if data == "terms":
            await q.edit_message_text("Terms: informational use only, not diagnosis. 18+. Data retention 60 days.")
        elif data == "accept_terms":
            FSMStorage.set_state(uid, States.TERMS_ACCEPTED)
            await self._main_menu(update)
        elif data == "back_menu":
            FSMStorage.set_state(uid, States.TERMS_ACCEPTED)
            await self._main_menu(update)
        elif data == "about":
            await q.edit_message_text("Lab results interpretation. Upload PDF/image, get report, compare, follow-up. Informational only.")
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

    async def _main_menu(self, update: Update):
        uid = update.effective_user.id
        user = self._user(uid)
        kb = [
            [InlineKeyboardButton("Upload", callback_data="upload_analysis")],
            [InlineKeyboardButton("Compare", callback_data="compare_analyses")],
            [InlineKeyboardButton("Recent", callback_data="recent_analyses")],
            [InlineKeyboardButton("Subscription", callback_data="subscription")],
            [InlineKeyboardButton("Loyalty", callback_data="loyalty")],
            [InlineKeyboardButton("About", callback_data="about")],
        ]
        if update.callback_query:
            await update.callback_query.edit_message_text("Menu:", reply_markup=InlineKeyboardMarkup(kb))
        else:
            await update.message.reply_text("Menu:", reply_markup=InlineKeyboardMarkup(kb))

    async def _subscription_status(self, update: Update):
        user = self._user(update.effective_user.id)
        if user and SubscriptionManager.is_subscription_active(user):
            exp = user.subscription_expire_at.strftime("%Y-%m-%d") if user.subscription_expire_at else "—"
            av, tot, bon, _ = SubscriptionManager.get_available_requests(user)
            text = f"Active until {exp}. Requests: {av} (incl. +{bon} bonus)."
            kb = [[InlineKeyboardButton("Renew", callback_data="subscription_plans")], [InlineKeyboardButton("Back", callback_data="back_menu")]]
        else:
            text = MSG_NEED_SUB
            kb = [[InlineKeyboardButton("Subscribe", callback_data="subscription_plans")], [InlineKeyboardButton("Back", callback_data="back_menu")]]
        await self._reply(update, text, kb)

    async def _subscription_plans(self, update: Update):
        kb = [
            [InlineKeyboardButton("1 mo — 299 ₽", callback_data="plan_1month")],
            [InlineKeyboardButton("3 mo — 799 ₽", callback_data="plan_3months")],
            [InlineKeyboardButton("6 mo — 1399 ₽", callback_data="plan_6months")],
            [InlineKeyboardButton("12 mo — 2499 ₽", callback_data="plan_12months")],
            [InlineKeyboardButton("Back", callback_data="subscription")],
        ]
        await update.callback_query.edit_message_text("Plan:", reply_markup=InlineKeyboardMarkup(kb))

    async def _loyalty(self, update: Update):
        text = "Referral: +5 requests per paid referral. Valid while subscription active."
        kb = [[InlineKeyboardButton("Get link", callback_data="get_referral_link")], [InlineKeyboardButton("Stats", callback_data="referral_stats")], [InlineKeyboardButton("Back", callback_data="back_menu")]]
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
        await self._reply(update, f"Link:\n{link}", [[InlineKeyboardButton("Back", callback_data="loyalty")]])

    async def _referral_stats(self, update: Update):
        user = await self._ensure_user(update)
        if not user:
            return
        s = SubscriptionManager.get_referral_stats(self.db, user.id)
        await self._reply(update, f"Referrals: {s['total_referrals']}. Bonus requests: {s['total_bonus']}.", [[InlineKeyboardButton("Back", callback_data="loyalty")]])

    async def _upload_request(self, update: Update):
        user = await self._ensure_user(update)
        if not user:
            return
        if not SubscriptionManager.can_perform_analysis(self.db, user.id):
            await self._reply(update, MSG_NEED_SUB, [[InlineKeyboardButton("Subscription", callback_data="subscription")]])
            return
        await update.callback_query.edit_message_text("Send PDF, JPG or PNG.")
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
            await update.message.reply_text("Send a file (PDF/JPG/PNG).")
            return
        buf = bytes(await file.download_as_bytearray())
        await update.message.reply_text("Processing…")
        try:
            if not self.file_processor or not self.llm_service or not getattr(self.llm_service, "enabled", True):
                await update.message.reply_text("Service unavailable.")
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
            await update.message.reply_text("Context: 1) Age?")
            FSMStorage.set_state(uid, States.COLLECTING_AGE)
        except Exception as e:
            logger.error(f"File: {e}")
            await update.message.reply_text(MSG_ERR)
            FSMStorage.set_state(uid, States.TERMS_ACCEPTED)

    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        uid = update.effective_user.id
        text = update.message.text
        state = FSMStorage.get_state(uid)
        fsm = FSMStorage.get_data(uid)

        if state == States.COLLECTING_AGE:
            fsm["age"] = text
            FSMStorage.set_data(uid, fsm)
            FSMStorage.set_state(uid, States.COLLECTING_SEX)
            await update.message.reply_text("2) Sex?")
        elif state == States.COLLECTING_SEX:
            fsm["sex"] = text
            FSMStorage.set_data(uid, fsm)
            FSMStorage.set_state(uid, States.COLLECTING_SYMPTOMS)
            await update.message.reply_text("3) Symptoms?")
        elif state == States.COLLECTING_SYMPTOMS:
            fsm["symptoms"] = text
            FSMStorage.set_data(uid, fsm)
            if (fsm.get("sex") or "").lower() in ("female", "f", "женский"):
                FSMStorage.set_state(uid, States.COLLECTING_PREGNANCY)
                await update.message.reply_text("4) Pregnant?")
            else:
                fsm["pregnancy"] = "N/A"
                FSMStorage.set_data(uid, fsm)
                FSMStorage.set_state(uid, States.COLLECTING_CHRONIC)
                await update.message.reply_text("4) Chronic conditions?")
        elif state == States.COLLECTING_PREGNANCY:
            fsm["pregnancy"] = text
            FSMStorage.set_data(uid, fsm)
            FSMStorage.set_state(uid, States.COLLECTING_CHRONIC)
            await update.message.reply_text("5) Chronic conditions?")
        elif state == States.COLLECTING_CHRONIC:
            fsm["chronic_conditions"] = text
            FSMStorage.set_data(uid, fsm)
            FSMStorage.set_state(uid, States.COLLECTING_MEDICATIONS)
            await update.message.reply_text("6) Medications?")
        elif state == States.COLLECTING_MEDICATIONS:
            fsm["medications"] = text
            FSMStorage.set_data(uid, fsm)
            await update.message.reply_text("Generating…")
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
                    await update.message.reply_text("Service unavailable.")
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
                await update.message.reply_text(f"Report:\n\n{report}")
                kb = [
                    [InlineKeyboardButton("Compare", callback_data=f"compare_from_{sid}"), InlineKeyboardButton("Clarify", callback_data=f"follow_up_{sid}")],
                    [InlineKeyboardButton("Menu", callback_data="back_menu")],
                ]
                await update.message.reply_text("Next:", reply_markup=InlineKeyboardMarkup(kb))
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
                await update.message.reply_text("Limit 2 questions.")
                await self._main_menu(update)
                FSMStorage.set_state(uid, States.TERMS_ACCEPTED)
                return
            sid = fsm.get("current_session_id") or fsm.get("session_id")
            if not sid:
                await update.message.reply_text("Session lost.")
                return
            res = self.db.query(StructuredResult).filter(StructuredResult.session_id == sid).first()
            if not res:
                await update.message.reply_text("Not found.")
                return
            try:
                if not self.llm_service or not getattr(self.llm_service, "enabled", True):
                    await update.message.reply_text("Service unavailable.")
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
                    await update.message.reply_text(f"Up to {2 - n - 1} more.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Clarify", callback_data=f"follow_up_{sid}")], [InlineKeyboardButton("Menu", callback_data="back_menu")]]))
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
            await self._reply(update, "Session not found.")
            return
        n = FSMStorage.get_data(uid).get("follow_up_count", 0)
        if n >= 2:
            await self._reply(update, "Limit 2 questions.")
            await self._main_menu(update)
            return
        fsm = FSMStorage.get_data(uid)
        fsm["current_session_id"] = sid
        FSMStorage.set_data(uid, fsm)
        FSMStorage.set_state(uid, States.WAITING_FOLLOW_UP)
        await self._reply(update, f"Ask (up to {2 - n} more).")

    async def _payment(self, update: Update, context: ContextTypes.DEFAULT_TYPE, plan: str):
        user = await self._ensure_user(update)
        if not user:
            return
        try:
            info = PaymentService.create_payment(user.id, plan, self.db)
            await update.callback_query.edit_message_text(f"Pay: {info.get('confirmation_url', '')}")
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
            await self._reply(update, "No analyses.", [[InlineKeyboardButton("Back", callback_data="back_menu")]])
            return
        lines = []
        kb = []
        for s in sessions:
            d = s.created_at.strftime("%Y-%m-%d %H:%M")
            lines.append(d)
            kb.append([InlineKeyboardButton(f"View {d}", callback_data=f"analysis_{s.id}")])
        kb.append([InlineKeyboardButton("Back", callback_data="back_menu")])
        await self._reply(update, "Recent:\n" + "\n".join(lines), kb)

    async def _analysis_detail(self, update: Update, session_id: int):
        user = await self._ensure_user(update)
        if not user:
            return
        if not SubscriptionManager.is_subscription_active(user):
            await self._reply(update, MSG_NEED_SUB)
            return
        session = self.db.query(AnalysisSession).filter(AnalysisSession.id == session_id, AnalysisSession.user_id == user.id).first()
        if not session:
            await self._reply(update, "Not found.")
            return
        res = self.db.query(StructuredResult).filter(StructuredResult.session_id == session_id).first()
        if not res or not res.report:
            await self._reply(update, "Not found.")
            return
        kb = [
            [InlineKeyboardButton("Compare", callback_data=f"compare_from_{session_id}"), InlineKeyboardButton("Clarify", callback_data=f"follow_up_{session_id}")],
            [InlineKeyboardButton("Back", callback_data="recent_analyses")],
        ]
        await self._reply(update, res.report, kb)

    async def _compare_request(self, update: Update):
        user = await self._ensure_user(update)
        if not user:
            return
        if not SubscriptionManager.is_subscription_active(user):
            await self._reply(update, MSG_NEED_SUB)
            return
        sessions = self.db.query(AnalysisSession).filter(AnalysisSession.user_id == user.id).order_by(AnalysisSession.created_at.desc()).limit(3).all()
        if len(sessions) < 2:
            await self._reply(update, "Need at least 2 analyses.", [[InlineKeyboardButton("Back", callback_data="back_menu")]])
            return
        kb = []
        for i in range(min(2, len(sessions))):
            for j in range(i + 1, min(3, len(sessions))):
                a, b = sessions[i], sessions[j]
                kb.append([InlineKeyboardButton(f"{a.created_at.strftime('%Y-%m-%d')} vs {b.created_at.strftime('%Y-%m-%d')}", callback_data=f"compare_{a.id}_{b.id}")])
        kb.append([InlineKeyboardButton("Back", callback_data="back_menu")])
        await self._reply(update, "Choose pair:", kb)

    async def _compare_from(self, update: Update, session_id: int):
        user = await self._ensure_user(update)
        if not user:
            return
        if not SubscriptionManager.is_subscription_active(user):
            await self._reply(update, MSG_NEED_SUB)
            return
        current = self.db.query(AnalysisSession).filter(AnalysisSession.id == session_id, AnalysisSession.user_id == user.id).first()
        if not current:
            await self._reply(update, "Not found.")
            return
        others = self.db.query(AnalysisSession).filter(AnalysisSession.user_id == user.id, AnalysisSession.id != session_id).order_by(AnalysisSession.created_at.desc()).limit(3).all()
        if not others:
            await self._reply(update, "Need another analysis.", [[InlineKeyboardButton("Back", callback_data=f"analysis_{session_id}")]])
            return
        kb = [[InlineKeyboardButton(f"vs {s.created_at.strftime('%Y-%m-%d')}", callback_data=f"compare_{session_id}_{s.id}")] for s in others]
        kb.append([InlineKeyboardButton("Back", callback_data=f"analysis_{session_id}")])
        await self._reply(update, "Compare with:", kb)

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
            await self._reply(update, "Not found.")
            return
        r1 = self.db.query(StructuredResult).filter(StructuredResult.session_id == s1_id).first()
        r2 = self.db.query(StructuredResult).filter(StructuredResult.session_id == s2_id).first()
        if not r1 or not r2:
            await self._reply(update, "Not found.")
            return
        await update.callback_query.edit_message_text("Comparing…")
        try:
            if not self.llm_service or not getattr(self.llm_service, "enabled", True):
                await self._reply(update, "Service unavailable.")
                return
            c1 = dict(r1.clinical_context or {})
            c1["date"] = s1.created_at.strftime("%Y-%m-%d")
            c2 = dict(r2.clinical_context or {})
            c2["date"] = s2.created_at.strftime("%Y-%m-%d")
            report = self.llm_service.compare_analyses(r1.structured_json, r2.structured_json, c1, c2)
            await self._reply(update, report, [[InlineKeyboardButton("Back", callback_data="back_menu")]])
        except Exception as e:
            logger.error(f"Compare: {e}")
            await self._reply(update, MSG_ERR)
