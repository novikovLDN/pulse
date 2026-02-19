"""Subscription management."""
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from database import User, Payment, Referral
from typing import Optional, Tuple
from loguru import logger


class SubscriptionManager:
    """Manage user subscriptions."""
    
    # Subscription plans
    PLANS = {
        "1month": {"days": 30, "price": 299, "requests": 3},
        "3months": {"days": 90, "price": 799, "requests": 15},
        "6months": {"days": 180, "price": 1399, "requests": None},  # unlimited
        "12months": {"days": 365, "price": 2499, "requests": None}  # unlimited
    }
    
    BONUS_PER_REFERRAL = 5  # Bonus requests per successful referral payment
    
    @staticmethod
    def is_subscription_active(user: User) -> bool:
        """Check if user has active subscription."""
        if user.subscription_status != "active":
            return False
        
        if user.subscription_expire_at is None:
            return False
        
        return user.subscription_expire_at > datetime.utcnow()
    
    @staticmethod
    def activate_subscription(db: Session, user_id: int, plan: str) -> bool:
        """Activate subscription for user."""
        if plan not in SubscriptionManager.PLANS:
            return False
        
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return False
        
        plan_data = SubscriptionManager.PLANS[plan]
        days = plan_data["days"]
        requests = plan_data["requests"]
        
        # If user already has active subscription, extend it
        if SubscriptionManager.is_subscription_active(user):
            user.subscription_expire_at += timedelta(days=days)
        else:
            user.subscription_expire_at = datetime.utcnow() + timedelta(days=days)
            # Reset used requests when starting new subscription
            user.used_requests = 0
        
        # Set total requests from tariff
        if requests is not None:
            user.total_requests = requests
        else:
            user.total_requests = 999999  # Unlimited (large number)
        
        # Bonus requests persist (don't reset)
        # But they expire with subscription
        
        user.subscription_status = "active"
        db.commit()
        return True
    
    @staticmethod
    def get_available_requests(user: User) -> Tuple[int, int, int, int]:
        """Get available requests breakdown.
        
        Returns: (available, total, bonus, used)
        Formula: available = total + bonus - used
        """
        if not SubscriptionManager.is_subscription_active(user):
            return (0, 0, 0, 0)
        
        total = user.total_requests or 0
        bonus = user.bonus_requests or 0
        used = user.used_requests or 0
        
        available = total + bonus - used
        return (max(0, available), total, bonus, used)
    
    @staticmethod
    def can_perform_analysis(db: Session, user_id: int) -> bool:
        """Check if user can perform analysis."""
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return False
        
        if not SubscriptionManager.is_subscription_active(user):
            return False
        
        available, _, _, _ = SubscriptionManager.get_available_requests(user)
        return available > 0
    
    @staticmethod
    def use_request(db: Session, user_id: int) -> bool:
        """Mark one request as used."""
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return False
        
        if not SubscriptionManager.can_perform_analysis(db, user_id):
            return False
        
        user.used_requests = (user.used_requests or 0) + 1
        db.commit()
        return True
    
    @staticmethod
    def add_bonus_requests(db: Session, user_id: int, amount: int) -> bool:
        """Add bonus requests to user."""
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return False
        
        # Only add bonus if subscription is active
        if not SubscriptionManager.is_subscription_active(user):
            logger.warning(f"Trying to add bonus to user {user_id} with inactive subscription")
            return False
        
        user.bonus_requests = (user.bonus_requests or 0) + amount
        db.commit()
        logger.info(f"Added {amount} bonus requests to user {user_id}. Total bonus: {user.bonus_requests}")
        return True
    
    @staticmethod
    def expire_subscriptions(db: Session):
        """Expire subscriptions that have passed their expiration date."""
        expired_users = db.query(User).filter(
            User.subscription_status == "active",
            User.subscription_expire_at < datetime.utcnow()
        ).all()
        
        for user in expired_users:
            user.subscription_status = "expired"
            # Reset bonus requests when subscription expires
            user.bonus_requests = 0
            user.used_requests = 0
        
        db.commit()
        return len(expired_users)
    
    @staticmethod
    def process_referral_bonus(db: Session, referred_user_id: int, payment_id: int) -> bool:
        """Process referral bonus when referred user makes payment."""
        referred_user = db.query(User).filter(User.id == referred_user_id).first()
        if not referred_user or not referred_user.referrer_id:
            return False
        
        referrer = db.query(User).filter(User.id == referred_user.referrer_id).first()
        if not referrer:
            return False
        
        # Only give bonus if referrer has active subscription
        if not SubscriptionManager.is_subscription_active(referrer):
            logger.info(f"Referrer {referrer.id} has inactive subscription, bonus not awarded")
            return False
        
        payment = db.query(Payment).filter(Payment.id == payment_id).first()
        if not payment:
            return False
        
        # Create referral record
        referral = Referral(
            referrer_id=referrer.id,
            referred_user_id=referred_user_id,
            payment_id=payment_id,
            bonus_requests=SubscriptionManager.BONUS_PER_REFERRAL,
            payment_date=payment.completed_at or payment.created_at
        )
        db.add(referral)
        
        # Add bonus to referrer
        SubscriptionManager.add_bonus_requests(db, referrer.id, SubscriptionManager.BONUS_PER_REFERRAL)
        
        db.commit()
        logger.info(f"Referral bonus processed: referrer {referrer.id} got {SubscriptionManager.BONUS_PER_REFERRAL} bonus requests")
        return True
    
    @staticmethod
    def get_referral_stats(db: Session, user_id: int) -> dict:
        """Get referral statistics for user."""
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return {"total_referrals": 0, "total_bonus": 0, "referral_code": None}
        
        referrals = db.query(Referral).filter(Referral.referrer_id == user_id).all()
        total_bonus = sum(ref.bonus_requests for ref in referrals)
        
        return {
            "total_referrals": len(referrals),
            "total_bonus": total_bonus,
            "referral_code": user.referral_code or user.generate_referral_code()
        }
