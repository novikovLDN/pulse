"""Admin API for monitoring and management."""
from fastapi import FastAPI, Depends, HTTPException, Header, Query
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, distinct, cast
from sqlalchemy.types import Date
from database import (
    get_db,
    User,
    Payment,
    AnalysisSession,
    Referral,
    UserNotification,
)
from config import settings
from datetime import datetime, timedelta
from typing import Optional
import os

app = FastAPI(title="Pulse Bot Admin API")


def verify_admin_token(authorization: Optional[str] = Header(None)):
    """Verify admin token."""
    if not settings.admin_secret_key:
        raise HTTPException(status_code=503, detail="Admin API is not configured")

    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header required")

    token = authorization.replace("Bearer ", "")
    if token != settings.admin_secret_key:
        raise HTTPException(status_code=403, detail="Invalid admin token")

    return token


def _days_ago(days: int):
    return datetime.utcnow() - timedelta(days=days)


def _dashboard_html() -> str:
    """Load dashboard HTML from static file."""
    base = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base, "static", "dashboard.html")
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return "<!DOCTYPE html><html><body><h1>Dashboard not found</h1></body></html>"


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page():
    """Serve admin dashboard (auth via token in JS)."""
    return HTMLResponse(content=_dashboard_html())


@app.get("/")
async def root():
    """Root endpoint."""
    return {"message": "Pulse Bot Admin API", "dashboard": "/dashboard"}


# ---------- Dashboard: single aggregated payload for frontend ----------


@app.get("/stats/dashboard")
async def get_dashboard(
    days: int = Query(30, ge=7, le=90),
    db: Session = Depends(get_db),
    token: str = Depends(verify_admin_token),
):
    """Aggregated metrics for admin dashboard (overview + time series)."""
    now = datetime.utcnow()
    since = _days_ago(days)

    # Overview
    total_users = db.query(User).count()
    active_subs = db.query(User).filter(
        User.subscription_status == "active",
        User.subscription_expire_at > now,
    ).count()
    total_analyses = db.query(AnalysisSession).count()
    total_revenue = (
        db.query(func.sum(Payment.amount))
        .filter(Payment.status == "completed")
        .scalar()
        or 0
    )
    paid_users = (
        db.query(func.count(distinct(Payment.user_id)))
        .filter(Payment.status == "completed")
        .scalar()
        or 0
    )
    conversion = (paid_users / total_users * 100) if total_users else 0

    # Plans: active by plan
    basic_active = db.query(User).filter(
        User.subscription_status == "active",
        User.subscription_expire_at > now,
        User.subscription_plan == "basic",
    ).count()
    premium_active = db.query(User).filter(
        User.subscription_status == "active",
        User.subscription_expire_at > now,
        User.subscription_plan == "premium",
    ).count()

    # Payments by tariff (all time completed)
    payments_by_tariff = (
        db.query(Payment.tariff, func.count(Payment.id))
        .filter(Payment.status == "completed")
        .group_by(Payment.tariff)
        .all()
    )
    tariff_counts = {t: c for t, c in payments_by_tariff}

    # New users per day (last N days)
    users_per_day = (
        db.query(cast(User.created_at, Date), func.count(User.id))
        .filter(User.created_at >= since)
        .group_by(cast(User.created_at, Date))
        .order_by(cast(User.created_at, Date))
        .all()
    )
    users_daily = [{"date": d.isoformat(), "count": c} for d, c in users_per_day]

    # Analyses per day
    analyses_per_day = (
        db.query(cast(AnalysisSession.created_at, Date), func.count(AnalysisSession.id))
        .filter(AnalysisSession.created_at >= since)
        .group_by(cast(AnalysisSession.created_at, Date))
        .order_by(cast(AnalysisSession.created_at, Date))
        .all()
    )
    analyses_daily = [{"date": d.isoformat(), "count": c} for d, c in analyses_per_day]

    # Revenue per day (by completed_at or payment_date)
    rev_query = db.query(
        func.coalesce(
            cast(Payment.payment_date, Date),
            cast(Payment.completed_at, Date),
            cast(Payment.created_at, Date),
        ),
        func.sum(Payment.amount),
    ).filter(
        Payment.status == "completed",
        Payment.completed_at >= since,
    )
    rev_per_day = rev_query.group_by(
        func.coalesce(
            cast(Payment.payment_date, Date),
            cast(Payment.completed_at, Date),
            cast(Payment.created_at, Date),
        )
    ).order_by(
        func.coalesce(
            cast(Payment.payment_date, Date),
            cast(Payment.completed_at, Date),
            cast(Payment.created_at, Date),
        )
    ).all()
    revenue_daily = [{"date": d.isoformat(), "amount": float(s)} for d, s in rev_per_day]

    # Active users: had payment or analysis in period
    user_ids_payment = (
        db.query(distinct(Payment.user_id))
        .filter(Payment.status == "completed", Payment.completed_at >= since)
        .subquery()
    )
    user_ids_analysis = (
        db.query(distinct(AnalysisSession.user_id))
        .filter(AnalysisSession.created_at >= since)
        .subquery()
    )
    active_count_7 = 0
    active_count_30 = 0
    since_7 = _days_ago(7)
    for subq, since_val in [
        (user_ids_payment, since_7),
        (user_ids_analysis, since_7),
    ]:
        # Count distinct over union is heavier; approximate: count from payments in 7d + analyses in 7d (with distinct in app). Simpler: one query per source and sum distinct in Python or use raw.
        pass
    # Simpler: active in last 7 days = distinct user_id from (payments where completed_at >= since_7) OR (analysis_sessions where created_at >= since_7)
    try:
        from sqlalchemy import union_all
        pay_7 = db.query(Payment.user_id).filter(
            Payment.status == "completed", Payment.completed_at >= since_7
        ).distinct()
        an_7 = db.query(AnalysisSession.user_id).filter(
            AnalysisSession.created_at >= since_7
        ).distinct()
        u7 = set(r[0] for r in pay_7.all()) | set(r[0] for r in an_7.all())
        active_count_7 = len(u7)
        pay_30 = db.query(Payment.user_id).filter(
            Payment.status == "completed", Payment.completed_at >= since
        ).distinct()
        an_30 = db.query(AnalysisSession.user_id).filter(
            AnalysisSession.created_at >= since
        ).distinct()
        u30 = set(r[0] for r in pay_30.all()) | set(r[0] for r in an_30.all())
        active_count_30 = len(u30)
    except Exception:
        active_count_7 = 0
        active_count_30 = 0

    # Referrals
    total_referrals = db.query(Referral).count()
    total_bonus_given = (
        db.query(func.sum(Referral.bonus_requests)).scalar() or 0
    )

    # Notifications
    notifications_created = db.query(UserNotification).count()
    notifications_sent = db.query(UserNotification).filter(
        UserNotification.sent == True
    ).count()

    # MRR approximation: active subscriptions * average price (simplified)
    # We don't have per-plan price in DB; use completed payments last 30d sum / months equivalent
    payments_last_30 = (
        db.query(func.sum(Payment.amount))
        .filter(
            Payment.status == "completed",
            Payment.completed_at >= since,
        )
        .scalar()
        or 0
    )
    revenue_30d = float(payments_last_30)

    return {
        "overview": {
            "total_users": total_users,
            "active_subscriptions": active_subs,
            "total_analyses": total_analyses,
            "total_revenue": float(total_revenue),
            "paid_users": paid_users,
            "conversion_rate_percent": round(conversion, 1),
            "basic_active": basic_active,
            "premium_active": premium_active,
            "tariff_counts": tariff_counts,
            "active_users_7d": active_count_7,
            "active_users_30d": active_count_30,
            "referrals_total": total_referrals,
            "referrals_bonus_requests": int(total_bonus_given),
            "notifications_created": notifications_created,
            "notifications_sent": notifications_sent,
            "revenue_last_30d": revenue_30d,
        },
        "series": {
            "users_daily": users_daily,
            "analyses_daily": analyses_daily,
            "revenue_daily": revenue_daily,
        },
        "days": days,
    }


@app.get("/stats/overview")
async def get_overview(
    db: Session = Depends(get_db),
    token: str = Depends(verify_admin_token),
):
    """Get overview statistics."""
    total_users = db.query(User).count()

    active_subscriptions = db.query(User).filter(
        User.subscription_status == "active",
        User.subscription_expire_at > datetime.utcnow(),
    ).count()

    total_analyses = db.query(AnalysisSession).count()

    total_revenue = (
        db.query(func.sum(Payment.amount)).filter(Payment.status == "completed").scalar()
        or 0
    )

    return {
        "total_users": total_users,
        "active_subscriptions": active_subscriptions,
        "total_analyses": total_analyses,
        "total_revenue": float(total_revenue),
    }


@app.get("/stats/users/daily")
async def get_users_daily(
    days: int = Query(30, ge=1, le=90),
    db: Session = Depends(get_db),
    token: str = Depends(verify_admin_token),
):
    """New registrations per day."""
    since = _days_ago(days)
    rows = (
        db.query(cast(User.created_at, Date), func.count(User.id))
        .filter(User.created_at >= since)
        .group_by(cast(User.created_at, Date))
        .order_by(cast(User.created_at, Date))
        .all()
    )
    return [{"date": d.isoformat(), "count": c} for d, c in rows]


@app.get("/stats/analyses/daily")
async def get_analyses_daily(
    days: int = Query(30, ge=1, le=90),
    db: Session = Depends(get_db),
    token: str = Depends(verify_admin_token),
):
    """Analyses uploaded per day."""
    since = _days_ago(days)
    rows = (
        db.query(cast(AnalysisSession.created_at, Date), func.count(AnalysisSession.id))
        .filter(AnalysisSession.created_at >= since)
        .group_by(cast(AnalysisSession.created_at, Date))
        .order_by(cast(AnalysisSession.created_at, Date))
        .all()
    )
    return [{"date": d.isoformat(), "count": c} for d, c in rows]


@app.get("/stats/revenue/daily")
async def get_revenue_daily(
    days: int = Query(30, ge=1, le=90),
    db: Session = Depends(get_db),
    token: str = Depends(verify_admin_token),
):
    """Revenue per day (completed payments)."""
    since = _days_ago(days)
    rows = (
        db.query(
            func.coalesce(
                cast(Payment.payment_date, Date),
                cast(Payment.completed_at, Date),
                cast(Payment.created_at, Date),
            ),
            func.sum(Payment.amount),
        )
        .filter(Payment.status == "completed", Payment.completed_at >= since)
        .group_by(
            func.coalesce(
                cast(Payment.payment_date, Date),
                cast(Payment.completed_at, Date),
                cast(Payment.created_at, Date),
            )
        )
        .order_by(
            func.coalesce(
                cast(Payment.payment_date, Date),
                cast(Payment.completed_at, Date),
                cast(Payment.created_at, Date),
            )
        )
        .all()
    )
    return [{"date": d.isoformat(), "amount": float(s)} for d, s in rows]


@app.get("/stats/plans")
async def get_plans_stats(
    db: Session = Depends(get_db),
    token: str = Depends(verify_admin_token),
):
    """Active subscriptions by plan (basic/premium)."""
    now = datetime.utcnow()
    basic = (
        db.query(User)
        .filter(
            User.subscription_status == "active",
            User.subscription_expire_at > now,
            User.subscription_plan == "basic",
        )
        .count()
    )
    premium = (
        db.query(User)
        .filter(
            User.subscription_status == "active",
            User.subscription_expire_at > now,
            User.subscription_plan == "premium",
        )
        .count()
    )
    return {"basic_active": basic, "premium_active": premium}


@app.get("/stats/conversion")
async def get_conversion(
    db: Session = Depends(get_db),
    token: str = Depends(verify_admin_token),
):
    """Conversion: paid users / total users."""
    total = db.query(User).count()
    paid = (
        db.query(func.count(distinct(Payment.user_id)))
        .filter(Payment.status == "completed")
        .scalar()
        or 0
    )
    return {
        "total_users": total,
        "paid_users": paid,
        "conversion_rate_percent": round((paid / total * 100), 1) if total else 0,
    }


@app.get("/stats/referrals")
async def get_referrals_stats(
    db: Session = Depends(get_db),
    token: str = Depends(verify_admin_token),
):
    """Referral program stats."""
    total = db.query(Referral).count()
    bonus = db.query(func.sum(Referral.bonus_requests)).scalar() or 0
    return {"total_referrals": total, "total_bonus_requests": int(bonus)}


@app.get("/users")
async def get_users(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    token: str = Depends(verify_admin_token),
):
    """Get users list."""
    users = db.query(User).offset(skip).limit(limit).all()

    return [
        {
            "id": user.id,
            "telegram_id": user.telegram_id,
            "subscription_status": user.subscription_status,
            "subscription_expire_at": user.subscription_expire_at.isoformat()
            if user.subscription_expire_at
            else None,
            "created_at": user.created_at.isoformat(),
        }
        for user in users
    ]


@app.get("/payments")
async def get_payments(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    token: str = Depends(verify_admin_token),
):
    """Get payments list."""
    payments = (
        db.query(Payment)
        .order_by(Payment.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    return [
        {
            "id": payment.id,
            "user_id": payment.user_id,
            "amount": float(payment.amount),
            "tariff": payment.tariff,
            "status": payment.status,
            "yookassa_payment_id": payment.yookassa_payment_id,
            "created_at": payment.created_at.isoformat(),
            "completed_at": payment.completed_at.isoformat()
            if payment.completed_at
            else None,
        }
        for payment in payments
    ]


@app.get("/analyses")
async def get_analyses(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    token: str = Depends(verify_admin_token),
):
    """Get analyses list."""
    analyses = (
        db.query(AnalysisSession)
        .order_by(AnalysisSession.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    return [
        {
            "id": analysis.id,
            "user_id": analysis.user_id,
            "created_at": analysis.created_at.isoformat(),
        }
        for analysis in analyses
    ]


@app.get("/stats/subscriptions")
async def get_subscription_stats(
    db: Session = Depends(get_db),
    token: str = Depends(verify_admin_token),
):
    """Get subscription statistics (payments by tariff)."""
    stats = {}
    for plan in ["1month", "3months", "6months", "12months"]:
        count = (
            db.query(Payment)
            .filter(Payment.tariff == plan, Payment.status == "completed")
            .count()
        )
        stats[plan] = count
    return stats
