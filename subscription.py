"""Subscription and referral logic. Базовая и Премиум подписки."""
from datetime import datetime, timedelta
from typing import Optional, Tuple
from sqlalchemy.orm import Session
from database import User, Payment, Referral
from loguru import logger

# Базовая: только «Спросить Pulse», без загрузки анализов и уведомлений. Дешевле.
# Премиум: всё включено (загрузка, уведомления, Спросить Pulse без лимита или с большим лимитом).
PLANS = {
    "1month_basic": {"days": 30, "price": 199, "plan": "basic", "upload_requests": 0, "ask_pulse_requests": 20},
    "3months_basic": {"days": 90, "price": 499, "plan": "basic", "upload_requests": 0, "ask_pulse_requests": 60},
    "6months_basic": {"days": 180, "price": 899, "plan": "basic", "upload_requests": 0, "ask_pulse_requests": 150},
    "12months_basic": {"days": 365, "price": 1499, "plan": "basic", "upload_requests": 0, "ask_pulse_requests": 400},
    "1month_premium": {"days": 30, "price": 299, "plan": "premium", "upload_requests": 3, "ask_pulse_requests": None},
    "3months_premium": {"days": 90, "price": 799, "plan": "premium", "upload_requests": 15, "ask_pulse_requests": None},
    "6months_premium": {"days": 180, "price": 1399, "plan": "premium", "upload_requests": None, "ask_pulse_requests": None},
    "12months_premium": {"days": 365, "price": 2499, "plan": "premium", "upload_requests": None, "ask_pulse_requests": None},
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
        user.used_ask_pulse_requests = 0
    user.subscription_plan = p["plan"]
    user.total_requests = p["upload_requests"] if p["upload_requests"] is not None else 999999
    user.total_ask_pulse_requests = p["ask_pulse_requests"]
    user.subscription_status = "active"
    db.commit()
    return True


def get_requests(user: Optional[User]) -> Tuple[int, int, int, int]:
    """Возвращает (осталось загрузок, лимит загрузок, бонус, использовано загрузок)."""
    if not user or not is_active(user):
        return (0, 0, 0, 0)
    t, b, u = user.total_requests or 0, user.bonus_requests or 0, user.used_requests or 0
    return (max(0, t + b - u), t, b, u)


def get_ask_pulse_requests(user: Optional[User]) -> Tuple[Optional[int], int]:
    """Возвращает (лимит запросов Спросить Pulse или None = без лимита, использовано)."""
    if not user or not is_active(user):
        return (0, 0)
    total = getattr(user, "total_ask_pulse_requests", None)
    used = getattr(user, "used_ask_pulse_requests", 0) or 0
    return (total, used)


def can_analyze(db: Session, user_id: int) -> bool:
    """Загрузка анализов только для Премиум и при наличии лимита."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not is_active(user) or (user.subscription_plan or "basic") != "premium":
        return False
    return get_requests(user)[0] > 0


def can_ask_pulse(db: Session, user_id: int) -> bool:
    """Спросить Pulse: активная подписка и (нет лимита или есть остаток)."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not is_active(user):
        return False
    total, used = get_ask_pulse_requests(user)
    if total is None:
        return True
    return used < total


def use_request(db: Session, user_id: int) -> bool:
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not can_analyze(db, user_id):
        return False
    user.used_requests = (user.used_requests or 0) + 1
    db.commit()
    return True


def use_ask_pulse_request(db: Session, user_id: int) -> bool:
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not can_ask_pulse(db, user_id):
        return False
    total = getattr(user, "total_ask_pulse_requests", None)
    if total is not None:
        user.used_ask_pulse_requests = (getattr(user, "used_ask_pulse_requests", 0) or 0) + 1
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
        u.used_ask_pulse_requests = getattr(u, "used_ask_pulse_requests", 0) or 0
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
    get_ask_pulse_requests = staticmethod(get_ask_pulse_requests)
    can_perform_analysis = staticmethod(can_analyze)
    can_ask_pulse = staticmethod(can_ask_pulse)
    use_request = staticmethod(use_request)
    use_ask_pulse_request = staticmethod(use_ask_pulse_request)
    add_bonus_requests = staticmethod(add_bonus)
    expire_subscriptions = staticmethod(expire_subscriptions)
    deactivate = staticmethod(deactivate)
    process_referral_bonus = staticmethod(process_referral_bonus)
    get_referral_stats = staticmethod(get_referral_stats)
