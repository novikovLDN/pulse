"""YooKassa payment integration."""
import uuid
from yookassa import Configuration, Payment
from datetime import datetime
from sqlalchemy.orm import Session
from database import User, Payment as PaymentModel
from subscription import SubscriptionManager
from config import settings
from loguru import logger


# Configure YooKassa
if settings.yookassa_shop_id and settings.yookassa_secret_key:
    Configuration.account_id = settings.yookassa_shop_id
    Configuration.secret_key = settings.yookassa_secret_key
else:
    logger.warning("⚠️ YooKassa credentials not configured")


class PaymentService:
    """Handle payment processing."""
    
    @staticmethod
    def create_payment(user_id: int, plan: str, db: Session) -> dict:
        """Create payment in YooKassa."""
        if not settings.yookassa_shop_id or not settings.yookassa_secret_key:
            raise ValueError("YooKassa credentials not configured")
        
        if plan not in SubscriptionManager.PLANS:
            raise ValueError(f"Invalid plan: {plan}")
        
        plan_data = SubscriptionManager.PLANS[plan]
        amount = plan_data["price"]
        
        # Create payment record in database
        payment_record = PaymentModel(
            user_id=user_id,
            amount=amount,
            tariff=plan,
            status="pending"
        )
        db.add(payment_record)
        db.commit()
        db.refresh(payment_record)
        
        try:
            # Create payment in YooKassa
            payment_id = str(uuid.uuid4())
            payment = Payment.create({
                "amount": {
                    "value": f"{amount:.2f}",
                    "currency": "RUB"
                },
                "confirmation": {
                    "type": "redirect",
                    "return_url": settings.yookassa_return_url or "https://t.me/your_bot"
                },
                "capture": True,
                "description": f"Subscription: {plan}",
                "metadata": {
                    "user_id": str(user_id),
                    "payment_record_id": str(payment_record.id),
                    "plan": plan
                }
            }, payment_id)
            
            # Update payment record with YooKassa payment ID
            payment_record.yookassa_payment_id = payment.id
            db.commit()
            
            confirmation_url = None
            if hasattr(payment, 'confirmation') and payment.confirmation:
                if hasattr(payment.confirmation, 'confirmation_url'):
                    confirmation_url = payment.confirmation.confirmation_url
            
            return {
                "payment_id": payment.id,
                "confirmation_url": confirmation_url,
                "payment_record_id": payment_record.id
            }
        except Exception as e:
            logger.error(f"Error creating YooKassa payment: {e}")
            import traceback
            logger.error(traceback.format_exc())
            # Mark payment as failed
            payment_record.status = "failed"
            db.commit()
            raise
    
    @staticmethod
    def handle_webhook(notification_data: dict, db: Session) -> bool:
        """Handle YooKassa webhook notification."""
        try:
            # YooKassa v3.x sends webhook as JSON with 'event' and 'object' fields
            # Parse notification data directly without PaymentNotification class
            event_type = notification_data.get("event")
            payment_data = notification_data.get("object", {})
            
            if not payment_data:
                logger.error("Invalid webhook data: missing 'object' field")
                return False
            
            payment_id = payment_data.get("id")
            payment_status = payment_data.get("status")
            
            if not payment_id:
                logger.error("Invalid webhook data: missing payment ID")
                return False
            
            # Find payment record
            payment_record = db.query(PaymentModel).filter(
                PaymentModel.yookassa_payment_id == payment_id
            ).first()
            
            if not payment_record:
                logger.warning(f"Payment record not found for YooKassa payment: {payment_id}")
                return False
            
            # Update payment status based on event type and payment status
            if event_type == "payment.succeeded" or payment_status == "succeeded":
                payment_record.status = "completed"
                payment_record.completed_at = datetime.utcnow()
                
                # Activate subscription
                SubscriptionManager.activate_subscription(
                    db,
                    payment_record.user_id,
                    payment_record.tariff
                )
                
                db.commit()
                logger.info(f"Payment completed: {payment_id}, User: {payment_record.user_id}")
                return True
            elif event_type == "payment.canceled" or payment_status == "canceled":
                payment_record.status = "failed"
                db.commit()
                logger.info(f"Payment canceled: {payment_id}")
                return True
            
            logger.info(f"Payment status updated: {payment_id}, Status: {payment_status}, Event: {event_type}")
            return True
        except Exception as e:
            logger.error(f"Error handling payment webhook: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    @staticmethod
    def check_payment_status(payment_record_id: int, db: Session) -> str:
        """Check payment status."""
        payment_record = db.query(PaymentModel).filter(
            PaymentModel.id == payment_record_id
        ).first()
        
        if not payment_record:
            return "not_found"
        
        if payment_record.yookassa_payment_id:
            try:
                payment = Payment.find_one(payment_record.yookassa_payment_id)
                return payment.status
            except Exception as e:
                logger.error(f"Error checking payment status: {e}")
                return payment_record.status
        
        return payment_record.status
