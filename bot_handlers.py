"""Telegram bot handlers."""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from sqlalchemy.orm import Session
from database import User, AnalysisSession, StructuredResult, FollowUpQuestion
from subscription import SubscriptionManager
from payment import PaymentService
from file_processor import FileProcessor
from llm_service import LLMService
from redis_client import FSMStorage
from datetime import datetime
from loguru import logger
import json


# FSM States
class States:
    START = "start"
    TERMS_ACCEPTED = "terms_accepted"
    COLLECTING_AGE = "collecting_age"
    COLLECTING_SEX = "collecting_sex"
    COLLECTING_SYMPTOMS = "collecting_symptoms"
    COLLECTING_PREGNANCY = "collecting_pregnancy"
    COLLECTING_CHRONIC = "collecting_chronic"
    COLLECTING_MEDICATIONS = "collecting_medications"
    PROCESSING_FILE = "processing_file"
    WAITING_FOLLOW_UP = "waiting_follow_up"


class BotHandlers:
    """Telegram bot handlers."""
    
    def __init__(self, db: Session):
        self.db = db
        try:
            self.llm_service = LLMService()
        except Exception as e:
            logger.error(f"Failed to initialize LLMService: {e}")
            self.llm_service = None
        
        try:
            self.file_processor = FileProcessor()
        except Exception as e:
            logger.error(f"Failed to initialize FileProcessor: {e}")
            self.file_processor = None
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command with referral code support."""
        user_id = update.effective_user.id
        command_args = context.args
        
        # Check if user exists
        user = self.db.query(User).filter(User.telegram_id == user_id).first()
        if not user:
            user = User(telegram_id=user_id)
            # Check for referral code
            if command_args and len(command_args) > 0:
                referral_code = command_args[0].upper()
                referrer = self.db.query(User).filter(User.referral_code == referral_code).first()
                if referrer and referrer.id != user.id:
                    user.referrer_id = referrer.id
                    logger.info(f"User {user_id} registered with referral code from user {referrer.id}")
            self.db.add(user)
            self.db.commit()
        else:
            # Existing user - check referral code if provided
            if command_args and len(command_args) > 0 and not user.referrer_id:
                referral_code = command_args[0].upper()
                referrer = self.db.query(User).filter(User.referral_code == referral_code).first()
                if referrer and referrer.id != user.id:
                    user.referrer_id = referrer.id
                    self.db.commit()
                    logger.info(f"User {user_id} linked to referrer {referrer.id}")
        
        # Generate referral code if not exists
        if not user.referral_code:
            user.generate_referral_code()
            self.db.commit()
        
        # Show terms
        await self.show_terms(update, context)
    
    async def show_terms(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show terms of use."""
        message = """Welcome to Clinical AI Assistant.

This service provides structured interpretation of laboratory results using an evidence-based approach.

IMPORTANT DISCLAIMER:
This service is NOT a medical diagnosis and does NOT replace consultation with a physician.
This service is for informational purposes only.
You must be 18 years or older to use this service.

By using this service, you acknowledge that:
- This is not a medical diagnosis
- You should consult a healthcare professional for medical advice
- The service is for informational purposes only"""
        
        keyboard = [
            [InlineKeyboardButton("Terms of Use", callback_data="terms")],
            [InlineKeyboardButton("Accept and Continue", callback_data="accept_terms")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(message, reply_markup=reply_markup)
        FSMStorage.set_state(update.effective_user.id, States.START)
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle callback queries."""
        query = update.callback_query
        await query.answer()
        
        user_id = update.effective_user.id
        data = query.data
        
        if data == "terms":
            await query.edit_message_text(
                "Terms of Use:\n\n"
                "1. This service provides informational interpretation of laboratory results.\n"
                "2. This is NOT a medical diagnosis.\n"
                "3. Always consult a healthcare professional for medical advice.\n"
                "4. You must be 18+ to use this service.\n"
                "5. We store only structured data, not raw files.\n"
                "6. Data retention: 60 days maximum.\n\n"
                "By using this service, you agree to these terms."
            )
        elif data == "accept_terms":
            FSMStorage.set_state(user_id, States.TERMS_ACCEPTED)
            await self.show_main_menu(update, context)
        elif data == "upload_analysis":
            await self.handle_upload_request(update, context)
        elif data == "compare_analyses":
            await self.handle_compare_request(update, context)
        elif data == "recent_analyses":
            await self.show_recent_analyses(update, context)
        elif data == "subscription":
            await self.show_subscription_status(update, context)
        elif data == "subscription_plans":
            await self.show_subscription_plans(update, context)
        elif data == "loyalty":
            await self.show_loyalty_program(update, context)
        elif data == "get_referral_link":
            await self.show_referral_link(update, context)
        elif data == "referral_stats":
            await self.show_referral_stats(update, context)
        elif data.startswith("plan_"):
            plan = data.replace("plan_", "")
            await self.handle_subscription_payment(update, context, plan)
        elif data.startswith("analysis_"):
            analysis_id = int(data.replace("analysis_", ""))
            await self.show_analysis_details(update, context, analysis_id)
        elif data.startswith("compare_"):
            if data.startswith("compare_from_"):
                # Handle compare from specific analysis
                session_id = int(data.replace("compare_from_", ""))
                await self.handle_compare_from_analysis(update, context, session_id)
            else:
                session_ids = data.replace("compare_", "").split("_")
                await self.handle_comparison(update, context, session_ids)
        elif data.startswith("follow_up_"):
            await self.handle_follow_up_request(update, context)
        elif data == "back_menu":
            FSMStorage.set_state(user_id, States.TERMS_ACCEPTED)
            await self.show_main_menu(update, context)
        elif data == "about":
            await query.edit_message_text(
                "About Service\n\n"
                "Clinical AI Assistant provides structured interpretation of laboratory test results.\n\n"
                "Features:\n"
                "- Upload PDF or image files with lab results\n"
                "- Get structured, evidence-based analysis\n"
                "- Compare multiple analyses\n"
                "- Ask follow-up questions\n\n"
                "This service is for informational purposes only and does not replace medical consultation."
            )
    
    async def show_main_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show main menu."""
        user_id = update.effective_user.id
        
        # Check subscription
        user = self.db.query(User).filter(User.telegram_id == user_id).first()
        has_active_subscription = SubscriptionManager.is_subscription_active(user)
        
        message = "Select an action:"
        
        keyboard = [
            [InlineKeyboardButton("Upload analysis", callback_data="upload_analysis")],
            [InlineKeyboardButton("Compare", callback_data="compare_analyses")],
            [InlineKeyboardButton("Recent analyses", callback_data="recent_analyses")],
            [InlineKeyboardButton("Subscription", callback_data="subscription")],
            [InlineKeyboardButton("Loyalty Program", callback_data="loyalty")],
            [InlineKeyboardButton("About", callback_data="about")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if hasattr(update, 'callback_query') and update.callback_query:
            await update.callback_query.edit_message_text(message, reply_markup=reply_markup)
        else:
            await update.message.reply_text(message, reply_markup=reply_markup)
    
    async def show_subscription_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show subscription status screen."""
        user_id = update.effective_user.id
        user = self.db.query(User).filter(User.telegram_id == user_id).first()
        
        has_active = SubscriptionManager.is_subscription_active(user)
        
        if has_active:
            expire_date = user.subscription_expire_at.strftime("%Y-%m-%d") if user.subscription_expire_at else "Unknown"
            available, total, bonus, used = SubscriptionManager.get_available_requests(user)
            
            message = (
                f"Subscription Status\n\n"
                f"Active until: {expire_date}\n"
                f"Available requests: {available} of {total + bonus}\n"
                f"Bonus requests: +{bonus}\n"
            )
            
            keyboard = [
                [InlineKeyboardButton("Renew subscription", callback_data="subscription_plans")],
                [InlineKeyboardButton("Back", callback_data="back_menu")]
            ]
        else:
            message = "To access analysis features, an active subscription is required."
            keyboard = [
                [InlineKeyboardButton("Subscribe", callback_data="subscription_plans")],
                [InlineKeyboardButton("Back", callback_data="back_menu")]
            ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.callback_query.edit_message_text(message, reply_markup=reply_markup)
    
    async def show_subscription_plans(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show subscription plans."""
        keyboard = [
            [InlineKeyboardButton("1 month — 299 ₽ (3 requests)", callback_data="plan_1month")],
            [InlineKeyboardButton("3 months — 799 ₽ (15 requests)", callback_data="plan_3months")],
            [InlineKeyboardButton("6 months — 1399 ₽ (unlimited)", callback_data="plan_6months")],
            [InlineKeyboardButton("12 months — 2499 ₽ (unlimited)", callback_data="plan_12months")],
            [InlineKeyboardButton("Back", callback_data="subscription")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.callback_query.edit_message_text("Select subscription plan:", reply_markup=reply_markup)
    
    async def show_loyalty_program(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show loyalty program screen."""
        message = (
            "Loyalty Program Pulse\n\n"
            "If a user subscribes using your personal referral link, "
            "you receive 5 additional requests for each payment.\n\n"
            "Bonus is valid within active subscription period.\n"
        )
        
        keyboard = [
            [InlineKeyboardButton("Get personal link", callback_data="get_referral_link")],
            [InlineKeyboardButton("Referral statistics", callback_data="referral_stats")],
            [InlineKeyboardButton("Back", callback_data="back_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.callback_query.edit_message_text(message, reply_markup=reply_markup)
    
    async def show_referral_link(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show referral link."""
        user_id = update.effective_user.id
        user = self.db.query(User).filter(User.telegram_id == user_id).first()
        
        if not user.referral_code:
            user.generate_referral_code()
            self.db.commit()
        
        bot_username = (await context.bot.get_me()).username
        referral_link = f"https://t.me/{bot_username}?start={user.referral_code}"
        
        message = (
            f"Your personal referral link:\n\n"
            f"{referral_link}\n\n"
            f"Share this link with others. For each successful payment "
            f"by a referred user, you will receive 5 bonus requests."
        )
        
        keyboard = [
            [InlineKeyboardButton("Back", callback_data="loyalty")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.callback_query.edit_message_text(message, reply_markup=reply_markup)
    
    async def show_referral_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show referral statistics."""
        user_id = update.effective_user.id
        user = self.db.query(User).filter(User.telegram_id == user_id).first()
        
        stats = SubscriptionManager.get_referral_stats(self.db, user.id)
        
        message = (
            f"Referral Statistics\n\n"
            f"Total referrals: {stats['total_referrals']}\n"
            f"Total bonus requests: {stats['total_bonus']}\n"
        )
        
        keyboard = [
            [InlineKeyboardButton("Back", callback_data="loyalty")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.callback_query.edit_message_text(message, reply_markup=reply_markup)
    
    async def handle_upload_request(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle upload analysis request."""
        user_id = update.effective_user.id
        
        # Check subscription and access
        user = self.db.query(User).filter(User.telegram_id == user_id).first()
        if not SubscriptionManager.can_perform_analysis(self.db, user.id):
            await update.callback_query.edit_message_text(
                "You need an active subscription to upload analyses.\n\n"
                "Please subscribe to continue."
            )
            await self.show_subscription_status(update, context)
            return
        
        await update.callback_query.edit_message_text(
            "Please upload your laboratory results file.\n\n"
            "Supported formats: PDF, JPG, PNG"
        )
        
        FSMStorage.set_state(user_id, States.PROCESSING_FILE)
    
    async def handle_file(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle file upload."""
        user_id = update.effective_user.id
        state = FSMStorage.get_state(user_id)
        
        if state != States.PROCESSING_FILE:
            return
        
        # Check subscription before processing
        user = self.db.query(User).filter(User.telegram_id == user_id).first()
        if not SubscriptionManager.can_perform_analysis(self.db, user.id):
            await update.message.reply_text(
                "Your subscription has expired. Please renew to continue."
            )
            await self.show_subscription_status(update, context)
            FSMStorage.set_state(user_id, States.TERMS_ACCEPTED)
            return
        
        file = update.message.document or update.message.photo
        
        if not file:
            await update.message.reply_text("Please send a file (PDF, JPG, or PNG)")
            return
        
        # Get file
        if update.message.document:
            file_obj = await context.bot.get_file(update.message.document.file_id)
            file_type = update.message.document.mime_type or update.message.document.file_name.split('.')[-1]
        else:
            # Photo
            file_obj = await context.bot.get_file(update.message.photo[-1].file_id)
            file_type = "image/jpeg"
        
        # Download file
        file_bytes_io = await file_obj.download_as_bytearray()
        file_bytes = bytes(file_bytes_io)
        
        # Process file
        await update.message.reply_text("Processing file... Please wait.")
        
        try:
            if not self.file_processor:
                await update.message.reply_text("File processing service is not available. Please contact support.")
                FSMStorage.set_state(user_id, States.TERMS_ACCEPTED)
                return
            
            if not self.llm_service or not self.llm_service.enabled:
                await update.message.reply_text("LLM service is not configured. Please contact support.")
                FSMStorage.set_state(user_id, States.TERMS_ACCEPTED)
                return
            
            # Extract text
            raw_text = self.file_processor.process_file(file_bytes, file_type)
            
            # Extract structured data
            structured_data = self.llm_service.extract_structured_data(raw_text)
            
            # Create analysis session
            user = self.db.query(User).filter(User.telegram_id == user_id).first()
            session = AnalysisSession(user_id=user.id)
            self.db.add(session)
            self.db.commit()
            self.db.refresh(session)
            
            # Store structured result
            structured_result = StructuredResult(
                session_id=session.id,
                structured_json=structured_data
            )
            self.db.add(structured_result)
            self.db.commit()
            
            # Store in FSM data for context collection
            fsm_data = FSMStorage.get_data(user_id)
            fsm_data['session_id'] = session.id
            fsm_data['structured_data'] = structured_data
            FSMStorage.set_data(user_id, fsm_data)
            
            # Start collecting clinical context
            await update.message.reply_text("File processed successfully.\n\nPlease provide clinical context:")
            await update.message.reply_text("1. What is your age?")
            FSMStorage.set_state(user_id, States.COLLECTING_AGE)
            
        except Exception as e:
            logger.error(f"Error processing file: {e}")
            import traceback
            logger.error(traceback.format_exc())
            await update.message.reply_text("Error processing file. Please try again.")
            FSMStorage.set_state(user_id, States.TERMS_ACCEPTED)
    
    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle text messages."""
        user_id = update.effective_user.id
        text = update.message.text
        state = FSMStorage.get_state(user_id)
        
        fsm_data = FSMStorage.get_data(user_id)
        
        if state == States.COLLECTING_AGE:
            fsm_data['age'] = text
            FSMStorage.set_data(user_id, fsm_data)
            await update.message.reply_text("2. What is your sex? (Male/Female/Other)")
            FSMStorage.set_state(user_id, States.COLLECTING_SEX)
        
        elif state == States.COLLECTING_SEX:
            fsm_data['sex'] = text
            FSMStorage.set_data(user_id, fsm_data)
            await update.message.reply_text("3. What are your current symptoms? (If none, type 'None')")
            FSMStorage.set_state(user_id, States.COLLECTING_SYMPTOMS)
        
        elif state == States.COLLECTING_SYMPTOMS:
            fsm_data['symptoms'] = text
            FSMStorage.set_data(user_id, fsm_data)
            
            # Check if female for pregnancy question
            if fsm_data.get('sex', '').lower() in ['female', 'f', 'женский']:
                await update.message.reply_text("4. Are you currently pregnant? (Yes/No)")
                FSMStorage.set_state(user_id, States.COLLECTING_PREGNANCY)
            else:
                fsm_data['pregnancy'] = 'Not applicable'
                FSMStorage.set_data(user_id, fsm_data)
                await update.message.reply_text("4. Do you have any chronic conditions? (If none, type 'None')")
                FSMStorage.set_state(user_id, States.COLLECTING_CHRONIC)
        
        elif state == States.COLLECTING_PREGNANCY:
            fsm_data['pregnancy'] = text
            FSMStorage.set_data(user_id, fsm_data)
            await update.message.reply_text("5. Do you have any chronic conditions? (If none, type 'None')")
            FSMStorage.set_state(user_id, States.COLLECTING_CHRONIC)
        
        elif state == States.COLLECTING_CHRONIC:
            fsm_data['chronic_conditions'] = text
            FSMStorage.set_data(user_id, fsm_data)
            await update.message.reply_text("6. What medications are you currently taking? (If none, type 'None')")
            FSMStorage.set_state(user_id, States.COLLECTING_MEDICATIONS)
        
        elif state == States.COLLECTING_MEDICATIONS:
            fsm_data['medications'] = text
            FSMStorage.set_data(user_id, fsm_data)
            
            # Generate report
            await update.message.reply_text("Generating clinical report... Please wait.")
            
            try:
                # Check subscription again before generating report
                user = self.db.query(User).filter(User.telegram_id == user_id).first()
                if not SubscriptionManager.can_perform_analysis(self.db, user.id):
                    await update.message.reply_text(
                        "Your subscription has expired. Please renew to continue."
                    )
                    await self.show_subscription_status(update, context)
                    FSMStorage.set_state(user_id, States.TERMS_ACCEPTED)
                    return
                
                session_id = fsm_data['session_id']
                structured_data = fsm_data['structured_data']
                clinical_context = {
                    'age': fsm_data.get('age'),
                    'sex': fsm_data.get('sex'),
                    'symptoms': fsm_data.get('symptoms'),
                    'pregnancy': fsm_data.get('pregnancy'),
                    'chronic_conditions': fsm_data.get('chronic_conditions'),
                    'medications': fsm_data.get('medications')
                }
                
                # Generate report
                if not self.llm_service or not self.llm_service.enabled:
                    await update.message.reply_text("LLM service is not configured. Cannot generate report.")
                    FSMStorage.set_state(user_id, States.TERMS_ACCEPTED)
                    return
                
                report = self.llm_service.generate_clinical_report(
                    structured_data,
                    clinical_context
                )
                
                # Update structured result
                structured_result = self.db.query(StructuredResult).filter(
                    StructuredResult.session_id == session_id
                ).first()
                
                structured_result.clinical_context = clinical_context
                structured_result.report = report
                self.db.commit()
                
                # Use request
                SubscriptionManager.use_request(self.db, user.id)
                
                # Cleanup old analyses (keep only last 3)
                from cleanup import cleanup_user_analyses
                cleanup_user_analyses(user.id, keep_count=3)
                
                # Send report (NO EMOJI in report)
                await update.message.reply_text(f"Clinical Report:\n\n{report}")
                
                # Show action buttons after report
                keyboard = [
                    [
                        InlineKeyboardButton("Compare", callback_data=f"compare_from_{session_id}"),
                        InlineKeyboardButton("Clarify", callback_data=f"follow_up_{session_id}")
                    ],
                    [InlineKeyboardButton("To Menu", callback_data="back_menu")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text("Select action:", reply_markup=reply_markup)
                
                # Store session_id for follow-up
                fsm_data['current_session_id'] = session_id
                fsm_data['follow_up_count'] = 0
                FSMStorage.set_data(user_id, fsm_data)
                FSMStorage.set_state(user_id, States.TERMS_ACCEPTED)
                
            except Exception as e:
                logger.error(f"Error generating report: {e}")
                import traceback
                logger.error(traceback.format_exc())
                await update.message.reply_text("Error generating report. Please try again.")
                FSMStorage.set_state(user_id, States.TERMS_ACCEPTED)
        
        elif state == States.WAITING_FOLLOW_UP:
            # Handle follow-up question
            follow_up_count = fsm_data.get('follow_up_count', 0)
            
            if follow_up_count >= 2:
                await update.message.reply_text(
                    "You have reached the limit of 2 follow-up questions.\n"
                    "Returning to main menu."
                )
                await self.show_main_menu(update, context)
                FSMStorage.set_state(user_id, States.TERMS_ACCEPTED)
                return
            
            await update.message.reply_text("Processing your question...")
            
            try:
                if not self.llm_service or not self.llm_service.enabled:
                    await update.message.reply_text("LLM service is not configured. Cannot answer questions.")
                    return
                
                session_id = fsm_data.get('current_session_id') or fsm_data.get('session_id')
                if not session_id:
                    await update.message.reply_text("Session not found.")
                    return
                
                structured_result = self.db.query(StructuredResult).filter(
                    StructuredResult.session_id == session_id
                ).first()
                
                if not structured_result:
                    await update.message.reply_text("Analysis not found.")
                    return
                
                answer = self.llm_service.answer_follow_up_question(
                    structured_result.structured_json,
                    structured_result.clinical_context or {},
                    structured_result.report or "",
                    text
                )
                
                # Store follow-up question
                follow_up = FollowUpQuestion(
                    session_id=session_id,
                    question=text,
                    answer=answer
                )
                self.db.add(follow_up)
                self.db.commit()
                
                # Send answer (NO EMOJI)
                await update.message.reply_text(answer)
                
                follow_up_count += 1
                fsm_data['follow_up_count'] = follow_up_count
                FSMStorage.set_data(user_id, fsm_data)
                
                if follow_up_count < 2:
                    keyboard = [
                        [
                            InlineKeyboardButton("Clarify", callback_data=f"follow_up_{session_id}"),
                            InlineKeyboardButton("To Menu", callback_data="back_menu")
                        ]
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    await update.message.reply_text(
                        f"You can ask {2 - follow_up_count} more question(s).",
                        reply_markup=reply_markup
                    )
                else:
                    await update.message.reply_text(
                        "You have reached the limit of 2 follow-up questions."
                    )
                    await self.show_main_menu(update, context)
                    FSMStorage.set_state(user_id, States.TERMS_ACCEPTED)
                
            except Exception as e:
                logger.error(f"Error answering follow-up question: {e}")
                import traceback
                logger.error(traceback.format_exc())
                await update.message.reply_text("Error processing question. Please try again.")
        
        else:
            # Unknown state, return to main menu
            await self.show_main_menu(update, context)
            FSMStorage.set_state(user_id, States.TERMS_ACCEPTED)
    
    async def handle_follow_up_request(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle follow-up request from button."""
        query = update.callback_query
        await query.answer()
        
        user_id = update.effective_user.id
        
        # Check subscription
        user = self.db.query(User).filter(User.telegram_id == user_id).first()
        if not SubscriptionManager.is_subscription_active(user):
            await query.edit_message_text(
                "Your subscription has expired. Please renew to continue."
            )
            await self.show_subscription_status(update, context)
            return
        
        # Extract session_id from callback data
        if query.data.startswith("follow_up_"):
            session_id = int(query.data.replace("follow_up_", ""))
        else:
            # Get from FSM data
            fsm_data = FSMStorage.get_data(user_id)
            session_id = fsm_data.get('current_session_id') or fsm_data.get('session_id')
        
        if not session_id:
            await query.edit_message_text("Session not found.")
            return
        
        # Check follow-up count
        fsm_data = FSMStorage.get_data(user_id)
        follow_up_count = fsm_data.get('follow_up_count', 0)
        
        if follow_up_count >= 2:
            await query.edit_message_text(
                "You have reached the limit of 2 follow-up questions."
            )
            await self.show_main_menu(update, context)
            return
        
        # Set state and ask for question
        fsm_data['current_session_id'] = session_id
        FSMStorage.set_data(user_id, fsm_data)
        FSMStorage.set_state(user_id, States.WAITING_FOLLOW_UP)
        
        await query.edit_message_text(
            f"Ask your question about this analysis.\n\n"
            f"You can ask {2 - follow_up_count} more question(s)."
        )
    
    async def handle_subscription_payment(self, update: Update, context: ContextTypes.DEFAULT_TYPE, plan: str):
        """Handle subscription payment."""
        user_id = update.effective_user.id
        user = self.db.query(User).filter(User.telegram_id == user_id).first()
        
        try:
            payment_info = PaymentService.create_payment(user.id, plan, self.db)
            payment_url = payment_info['confirmation_url']
            
            await update.callback_query.edit_message_text(
                f"Payment created. Please complete the payment:\n\n{payment_url}\n\n"
                "After payment, your subscription will be activated automatically."
            )
        except Exception as e:
            logger.error(f"Error creating payment: {e}")
            import traceback
            logger.error(traceback.format_exc())
            await update.callback_query.edit_message_text("Error creating payment. Please try again.")
    
    async def show_recent_analyses(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show recent analyses."""
        user_id = update.effective_user.id
        user = self.db.query(User).filter(User.telegram_id == user_id).first()
        
        # Check subscription
        if not SubscriptionManager.is_subscription_active(user):
            await update.callback_query.edit_message_text(
                "Your subscription has expired. Please renew to view analyses."
            )
            await self.show_subscription_status(update, context)
            return
        
        # Get last 3 analyses
        sessions = self.db.query(AnalysisSession).filter(
            AnalysisSession.user_id == user.id
        ).order_by(AnalysisSession.created_at.desc()).limit(3).all()
        
        if not sessions:
            await update.callback_query.edit_message_text("No analyses found.")
            return
        
        message = "Recent analyses:\n\n"
        keyboard = []
        
        for session in sessions:
            date_str = session.created_at.strftime("%Y-%m-%d %H:%M")
            message += f"Analysis from {date_str}\n"
            keyboard.append([InlineKeyboardButton(
                f"View {date_str}",
                callback_data=f"analysis_{session.id}"
            )])
        
        keyboard.append([InlineKeyboardButton("Back", callback_data="back_menu")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.callback_query.edit_message_text(message, reply_markup=reply_markup)
    
    async def show_analysis_details(self, update: Update, context: ContextTypes.DEFAULT_TYPE, session_id: int):
        """Show analysis details."""
        user_id = update.effective_user.id
        user = self.db.query(User).filter(User.telegram_id == user_id).first()
        
        # Check subscription
        if not SubscriptionManager.is_subscription_active(user):
            await update.callback_query.edit_message_text(
                "Your subscription has expired. Please renew to view analyses."
            )
            await self.show_subscription_status(update, context)
            return
        
        structured_result = self.db.query(StructuredResult).filter(
            StructuredResult.session_id == session_id
        ).first()
        
        if not structured_result or not structured_result.report:
            await update.callback_query.edit_message_text("Analysis not found.")
            return
        
        # Show report (NO EMOJI)
        message = f"Analysis Report:\n\n{structured_result.report}"
        
        # Add action buttons
        keyboard = [
            [
                InlineKeyboardButton("Compare", callback_data=f"compare_from_{session_id}"),
                InlineKeyboardButton("Clarify", callback_data=f"follow_up_{session_id}")
            ],
            [InlineKeyboardButton("Back", callback_data="recent_analyses")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.callback_query.edit_message_text(message, reply_markup=reply_markup)
    
    async def handle_compare_from_analysis(self, update: Update, context: ContextTypes.DEFAULT_TYPE, session_id: int):
        """Handle compare request from specific analysis."""
        user_id = update.effective_user.id
        user = self.db.query(User).filter(User.telegram_id == user_id).first()
        
        # Check subscription
        if not SubscriptionManager.is_subscription_active(user):
            await update.callback_query.edit_message_text(
                "Your subscription has expired. Please renew to compare analyses."
            )
            await self.show_subscription_status(update, context)
            return
        
        # Get current analysis
        current_session = self.db.query(AnalysisSession).filter(AnalysisSession.id == session_id).first()
        if not current_session:
            await update.callback_query.edit_message_text("Analysis not found.")
            return
        
        # Get other analyses (last 3, excluding current)
        sessions = self.db.query(AnalysisSession).filter(
            AnalysisSession.user_id == user.id,
            AnalysisSession.id != session_id
        ).order_by(AnalysisSession.created_at.desc()).limit(3).all()
        
        if len(sessions) < 1:
            await update.callback_query.edit_message_text(
                "You need at least one more analysis to compare.\n"
                "Please upload more analyses first."
            )
            return
        
        message = f"Select analysis to compare with {current_session.created_at.strftime('%Y-%m-%d')}:\n\n"
        keyboard = []
        
        for session in sessions:
            date_str = session.created_at.strftime("%Y-%m-%d")
            message += f"- {date_str}\n"
            keyboard.append([InlineKeyboardButton(
                f"Compare with {date_str}",
                callback_data=f"compare_{session_id}_{session.id}"
            )])
        
        keyboard.append([InlineKeyboardButton("Back", callback_data=f"analysis_{session_id}")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.callback_query.edit_message_text(message, reply_markup=reply_markup)
    
    async def handle_compare_request(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle compare analyses request."""
        user_id = update.effective_user.id
        user = self.db.query(User).filter(User.telegram_id == user_id).first()
        
        # Check subscription
        if not SubscriptionManager.is_subscription_active(user):
            await update.callback_query.edit_message_text(
                "Your subscription has expired. Please renew to compare analyses."
            )
            await self.show_subscription_status(update, context)
            return
        
        # Get last 3 analyses
        sessions = self.db.query(AnalysisSession).filter(
            AnalysisSession.user_id == user.id
        ).order_by(AnalysisSession.created_at.desc()).limit(3).all()
        
        if len(sessions) < 2:
            await update.callback_query.edit_message_text(
                "You need at least 2 analyses to compare.\n"
                "Please upload more analyses first."
            )
            return
        
        message = "Select 2 analyses to compare:\n\n"
        keyboard = []
        
        for i, session in enumerate(sessions[:3]):
            date_str = session.created_at.strftime("%Y-%m-%d")
            message += f"{i+1}. {date_str}\n"
        
        # Create comparison options
        if len(sessions) >= 2:
            keyboard.append([InlineKeyboardButton(
                f"Compare {sessions[0].created_at.strftime('%Y-%m-%d')} vs {sessions[1].created_at.strftime('%Y-%m-%d')}",
                callback_data=f"compare_{sessions[0].id}_{sessions[1].id}"
            )])
        
        if len(sessions) >= 3:
            keyboard.append([InlineKeyboardButton(
                f"Compare {sessions[0].created_at.strftime('%Y-%m-%d')} vs {sessions[2].created_at.strftime('%Y-%m-%d')}",
                callback_data=f"compare_{sessions[0].id}_{sessions[2].id}"
            )])
            keyboard.append([InlineKeyboardButton(
                f"Compare {sessions[1].created_at.strftime('%Y-%m-%d')} vs {sessions[2].created_at.strftime('%Y-%m-%d')}",
                callback_data=f"compare_{sessions[1].id}_{sessions[2].id}"
            )])
        
        keyboard.append([InlineKeyboardButton("Back", callback_data="back_menu")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.callback_query.edit_message_text(message, reply_markup=reply_markup)
    
    async def handle_comparison(self, update: Update, context: ContextTypes.DEFAULT_TYPE, session_ids: list):
        """Handle analysis comparison."""
        user_id = update.effective_user.id
        user = self.db.query(User).filter(User.telegram_id == user_id).first()
        
        # Check subscription
        if not SubscriptionManager.is_subscription_active(user):
            await update.callback_query.edit_message_text(
                "Your subscription has expired. Please renew to compare analyses."
            )
            await self.show_subscription_status(update, context)
            return
        
        if len(session_ids) < 2:
            await update.callback_query.edit_message_text("Invalid comparison request.")
            return
        
        session1_id = int(session_ids[0])
        session2_id = int(session_ids[1])
        
        result1 = self.db.query(StructuredResult).filter(
            StructuredResult.session_id == session1_id
        ).first()
        
        result2 = self.db.query(StructuredResult).filter(
            StructuredResult.session_id == session2_id
        ).first()
        
        if not result1 or not result2:
            await update.callback_query.edit_message_text("One or both analyses not found.")
            return
        
        await update.callback_query.edit_message_text("Comparing analyses... Please wait.")
        
        try:
            if not self.llm_service or not self.llm_service.enabled:
                await update.callback_query.edit_message_text("LLM service is not configured. Cannot compare analyses.")
                return
            
            session1 = self.db.query(AnalysisSession).filter(AnalysisSession.id == session1_id).first()
            session2 = self.db.query(AnalysisSession).filter(AnalysisSession.id == session2_id).first()
            
            clinical_context1 = result1.clinical_context or {}
            clinical_context1['date'] = session1.created_at.strftime("%Y-%m-%d")
            
            clinical_context2 = result2.clinical_context or {}
            clinical_context2['date'] = session2.created_at.strftime("%Y-%m-%d")
            
            comparison_report = self.llm_service.compare_analyses(
                result1.structured_json,
                result2.structured_json,
                clinical_context1,
                clinical_context2
            )
            
            # Show comparison report (NO EMOJI)
            message = f"Comparison Report:\n\n{comparison_report}"
            
            keyboard = [
                [InlineKeyboardButton("Back", callback_data="back_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.callback_query.edit_message_text(message, reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Error comparing analyses: {e}")
            import traceback
            logger.error(traceback.format_exc())
            await update.callback_query.edit_message_text("Error comparing analyses. Please try again.")
