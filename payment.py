"""YooKassa payment integration."""
import uuid
from yookassa import Configuration, Payment
from yookassa.domain.notification import PaymentNotification
from datetime import datetime
from sqlalchemy.orm import Session
from database import User, Payment as PaymentModel
from subscription import SubscriptionManager
from config import settings
from loguru import logger


# Configure YooKassa
Configuration.account_id = settings.yookassa_shop_id
Configuration.secret_key = settings.yookassa_secret_key


class PaymentService:
    """Handle payment processing."""
    
    @staticmethod
    def create_payment(user_id: int, plan: str, db: Session) -> dict:
        """Create payment in YooKassa."""
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
        
        # Create payment in YooKassa
        payment_id = str(uuid.uuid4())
        payment = Payment.create({
            "amount": {
                "value": f"{amount:.2f}",
                "currency": "RUB"
            },
            "confirmation": {
                "type": "redirect",
                "return_url": settings.yookassa_return_url
            },
            "capture": True,
            "description": f"Subscription: {plan}",
            "metadata": {
                "user_id": user_id,
                "payment_record_id": payment_record.id,
                "plan": plan
            }
        }, payment_id)
        
        # Update payment record with YooKassa payment ID
        payment_record.yookassa_payment_id = payment.id
        db.commit()
        
        return {
            "payment_id": payment.id,
            "confirmation_url": payment.confirmation.confirmation_url,
            "payment_record_id": payment_record.id
        }
    
    @staticmethod
    def handle_webhook(notification_data: dict, db: Session) -> bool:
        """Handle YooKassa webhook notification."""
        try:
            notification = PaymentNotification(notification_data)
            payment = notification.object
            
            # Find payment record
            payment_record = db.query(PaymentModel).filter(
                PaymentModel.yookassa_payment_id == payment.id
            ).first()
            
            if not payment_record:
                logger.warning(f"Payment record not found for YooKassa payment: {payment.id}")
                return False
            
            # Update payment status
            if payment.status == "succeeded":
                payment_record.status = "completed"
                payment_record.completed_at = datetime.utcnow()
                
                # Activate subscription
                SubscriptionManager.activate_subscription(
                    db,
                    payment_record.user_id,
                    payment_record.tariff
                )
                
                db.commit()
                logger.info(f"Payment completed: {payment.id}, User: {payment_record.user_id}")
                return True
            elif payment.status == "canceled":
                payment_record.status = "failed"
                db.commit()
                return True
            
            return False
        except Exception as e:
            logger.error(f"Error handling payment webhook: {e}")
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
