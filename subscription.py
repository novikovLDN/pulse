"""Subscription and referral logic."""
from datetime import datetime, timedelta
from typing import Optional, Tuple
from sqlalchemy.orm import Session
from database import User, Payment, Referral
from loguru import logger

PLANS = {
    "1month": {"days": 30, "price": 299, "requests": 3},
    "3months": {"days": 90, "price": 799, "requests": 15},
    "6months": {"days": 180, "price": 1399, "requests": None},
    "12months": {"days": 365, "price": 2499, "requests": None},
}
BONUS_PER_REFERRAL = 5


def is_active(user: Optional[User]) -> bool:
    if not user or user.subscription_status != "active" or not user.subscription_expire_at:
        return False
    return user.subscription_expire_at > datetime.utcnow()


def activate(db: Session, user_id: int, plan: str) -> bool:
    if plan not in PLANS:
        return False
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return False
    p = PLANS[plan]
    if is_active(user):
        user.subscription_expire_at += timedelta(days=p["days"])
    else:
        user.subscription_expire_at = datetime.utcnow() + timedelta(days=p["days"])
        user.used_requests = 0
    user.total_requests = p["requests"] if p["requests"] is not None else 999999
    user.subscription_status = "active"
    db.commit()
    return True


def get_requests(user: Optional[User]) -> Tuple[int, int, int, int]:
    if not user or not is_active(user):
        return (0, 0, 0, 0)
    t, b, u = user.total_requests or 0, user.bonus_requests or 0, user.used_requests or 0
    return (max(0, t + b - u), t, b, u)


def can_analyze(db: Session, user_id: int) -> bool:
    user = db.query(User).filter(User.id == user_id).first()
    return user and is_active(user) and get_requests(user)[0] > 0


def use_request(db: Session, user_id: int) -> bool:
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not can_analyze(db, user_id):
        return False
    user.used_requests = (user.used_requests or 0) + 1
    db.commit()
    return True


def add_bonus(db: Session, user_id: int, amount: int) -> bool:
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not is_active(user):
        return False
    user.bonus_requests = (user.bonus_requests or 0) + amount
    db.commit()
    return True


def deactivate(db: Session, user_id: int) -> bool:
    """Remove subscription from user (admin)."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return False
    user.subscription_status = "inactive"
    user.subscription_expire_at = None
    user.bonus_requests = 0
    db.commit()
    return True


def expire_subscriptions(db: Session) -> int:
    q = db.query(User).filter(
        User.subscription_status == "active",
        User.subscription_expire_at < datetime.utcnow()
    ).all()
    for u in q:
        u.subscription_status = "expired"
        u.bonus_requests = 0
        u.used_requests = 0
    db.commit()
    return len(q)


def process_referral_bonus(db: Session, referred_user_id: int, payment_id: int) -> bool:
    if db.query(Referral).filter(Referral.payment_id == payment_id).first():
        return True
    referred = db.query(User).filter(User.id == referred_user_id).first()
    if not referred or not referred.referrer_id:
        return False
    referrer = db.query(User).filter(User.id == referred.referrer_id).first()
    if not referrer or not is_active(referrer):
        return False
    payment = db.query(Payment).filter(Payment.id == payment_id).first()
    if not payment:
        return False
    db.add(Referral(
        referrer_id=referrer.id, referred_user_id=referred_user_id, payment_id=payment_id,
        bonus_requests=BONUS_PER_REFERRAL, payment_date=payment.completed_at or payment.created_at
    ))
    add_bonus(db, referrer.id, BONUS_PER_REFERRAL)
    db.commit()
    return True


def get_referral_stats(db: Session, user_id: int) -> dict:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return {"total_referrals": 0, "total_bonus": 0, "referral_code": None}
    if not user.referral_code:
        user.generate_referral_code()
        db.commit()
    refs = db.query(Referral).filter(Referral.referrer_id == user_id).all()
    return {
        "total_referrals": len(refs),
        "total_bonus": sum(r.bonus_requests for r in refs),
        "referral_code": user.referral_code,
    }


class SubscriptionManager:
    PLANS = PLANS
    BONUS_PER_REFERRAL = BONUS_PER_REFERRAL
    is_subscription_active = staticmethod(is_active)
    activate_subscription = staticmethod(activate)
    get_available_requests = staticmethod(get_requests)
    can_perform_analysis = staticmethod(can_analyze)
    use_request = staticmethod(use_request)
    add_bonus_requests = staticmethod(add_bonus)
    expire_subscriptions = staticmethod(expire_subscriptions)
    deactivate = staticmethod(deactivate)
    process_referral_bonus = staticmethod(process_referral_bonus)
    get_referral_stats = staticmethod(get_referral_stats)
