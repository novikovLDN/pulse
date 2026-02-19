"""YooKassa payments."""
import uuid
from datetime import datetime
from yookassa import Configuration, Payment
from sqlalchemy.orm import Session
from database import Payment as PaymentModel
from subscription import SubscriptionManager
from config import settings
from loguru import logger

if settings.yookassa_shop_id and settings.yookassa_secret_key:
    Configuration.account_id = settings.yookassa_shop_id
    Configuration.secret_key = settings.yookassa_secret_key


class PaymentService:
    @staticmethod
    def create_payment(user_id: int, plan: str, db: Session) -> dict:
        if not settings.yookassa_shop_id or not settings.yookassa_secret_key:
            raise ValueError("Payments not configured")
        if plan not in SubscriptionManager.PLANS:
            raise ValueError(f"Invalid plan: {plan}")
        amount = SubscriptionManager.PLANS[plan]["price"]
        rec = PaymentModel(user_id=user_id, amount=amount, tariff=plan, status="pending")
        db.add(rec)
        db.commit()
        db.refresh(rec)
        try:
            pay = Payment.create({
                "amount": {"value": f"{amount:.2f}", "currency": "RUB"},
                "confirmation": {"type": "redirect", "return_url": settings.yookassa_return_url or "https://t.me"},
                "capture": True,
                "description": plan,
                "metadata": {"user_id": str(user_id), "plan": plan},
            }, str(uuid.uuid4()))
            rec.yookassa_payment_id = pay.id
            db.commit()
            url = getattr(getattr(pay, "confirmation", None), "confirmation_url", None)
            return {"payment_id": pay.id, "confirmation_url": url, "payment_record_id": rec.id}
        except Exception as e:
            logger.error(f"YooKassa create: {e}")
            rec.status = "failed"
            db.commit()
            raise

    @staticmethod
    def handle_webhook(data: dict, db: Session) -> bool:
        try:
            obj = data.get("object") or {}
            pid, status = obj.get("id"), obj.get("status")
            if not pid:
                return False
            rec = db.query(PaymentModel).filter(PaymentModel.yookassa_payment_id == pid).first()
            if not rec:
                return False
            if data.get("event") == "payment.succeeded" or status == "succeeded":
                rec.status = "completed"
                rec.completed_at = rec.payment_date = datetime.utcnow()
                SubscriptionManager.activate_subscription(db, rec.user_id, rec.tariff)
                SubscriptionManager.process_referral_bonus(db, rec.user_id, rec.id)
                db.commit()
            elif data.get("event") == "payment.canceled" or status == "canceled":
                rec.status = "failed"
                db.commit()
            return True
        except Exception as e:
            logger.error(f"Webhook: {e}")
            return False
