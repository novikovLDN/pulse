"""Subscription management."""
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from database import User
from typing import Optional


class SubscriptionManager:
    """Manage user subscriptions."""
    
    # Subscription plans in days
    PLANS = {
        "1month": {"days": 30, "price": 299, "analyses_limit": 3},
        "3months": {"days": 90, "price": 799, "analyses_limit": 15},
        "6months": {"days": 180, "price": 1399, "analyses_limit": None},  # unlimited
        "12months": {"days": 365, "price": 2499, "analyses_limit": None}  # unlimited
    }
    
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
        
        # If user already has active subscription, extend it
        if SubscriptionManager.is_subscription_active(user):
            user.subscription_expire_at += timedelta(days=days)
        else:
            user.subscription_expire_at = datetime.utcnow() + timedelta(days=days)
        
        user.subscription_status = "active"
        db.commit()
        return True
    
    @staticmethod
    def get_remaining_analyses(db: Session, user_id: int) -> Optional[int]:
        """Get remaining analyses count for user."""
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return None
        
        if not SubscriptionManager.is_subscription_active(user):
            return 0
        
        # Get plan info
        # We need to check payment history to determine plan
        # For simplicity, we'll check the most recent payment
        from database import Payment
        recent_payment = db.query(Payment).filter(
            Payment.user_id == user_id,
            Payment.status == "completed"
        ).order_by(Payment.created_at.desc()).first()
        
        if not recent_payment:
            return 0
        
        plan_data = SubscriptionManager.PLANS.get(recent_payment.tariff, {})
        analyses_limit = plan_data.get("analyses_limit")
        
        if analyses_limit is None:  # Unlimited
            return None
        
        # Count analyses used in current subscription period
        from database import AnalysisSession
        subscription_start = recent_payment.completed_at or recent_payment.created_at
        analyses_used = db.query(AnalysisSession).filter(
            AnalysisSession.user_id == user_id,
            AnalysisSession.created_at >= subscription_start
        ).count()
        
        remaining = analyses_limit - analyses_used
        return max(0, remaining)
    
    @staticmethod
    def can_perform_analysis(db: Session, user_id: int) -> bool:
        """Check if user can perform analysis."""
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return False
        
        if not SubscriptionManager.is_subscription_active(user):
            return False
        
        remaining = SubscriptionManager.get_remaining_analyses(db, user_id)
        if remaining is None:  # Unlimited
            return True
        
        return remaining > 0
    
    @staticmethod
    def expire_subscriptions(db: Session):
        """Expire subscriptions that have passed their expiration date."""
        expired_users = db.query(User).filter(
            User.subscription_status == "active",
            User.subscription_expire_at < datetime.utcnow()
        ).all()
        
        for user in expired_users:
            user.subscription_status = "expired"
        
        db.commit()
        return len(expired_users)
