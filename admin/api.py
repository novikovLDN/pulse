"""Admin API for monitoring and management."""
from fastapi import FastAPI, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from sqlalchemy import func
from database import get_db, User, Payment, AnalysisSession
from subscription import SubscriptionManager
from config import settings
from datetime import datetime
from typing import Optional
import json


app = FastAPI(title="Pulse Bot Admin API")


def verify_admin_token(authorization: Optional[str] = Header(None)):
    """Verify admin token."""
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header required")
    
    token = authorization.replace("Bearer ", "")
    if token != settings.admin_secret_key:
        raise HTTPException(status_code=403, detail="Invalid admin token")
    
    return token


@app.get("/")
async def root():
    """Root endpoint."""
    return {"message": "Pulse Bot Admin API"}


@app.get("/stats/overview")
async def get_overview(
    db: Session = Depends(get_db),
    token: str = Depends(verify_admin_token)
):
    """Get overview statistics."""
    total_users = db.query(User).count()
    
    active_subscriptions = db.query(User).filter(
        User.subscription_status == "active",
        User.subscription_expire_at > datetime.utcnow()
    ).count()
    
    total_analyses = db.query(AnalysisSession).count()
    
    total_revenue = db.query(func.sum(Payment.amount)).filter(
        Payment.status == "completed"
    ).scalar() or 0
    
    return {
        "total_users": total_users,
        "active_subscriptions": active_subscriptions,
        "total_analyses": total_analyses,
        "total_revenue": float(total_revenue)
    }


@app.get("/users")
async def get_users(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    token: str = Depends(verify_admin_token)
):
    """Get users list."""
    users = db.query(User).offset(skip).limit(limit).all()
    
    return [
        {
            "id": user.id,
            "telegram_id": user.telegram_id,
            "subscription_status": user.subscription_status,
            "subscription_expire_at": user.subscription_expire_at.isoformat() if user.subscription_expire_at else None,
            "created_at": user.created_at.isoformat()
        }
        for user in users
    ]


@app.get("/payments")
async def get_payments(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    token: str = Depends(verify_admin_token)
):
    """Get payments list."""
    payments = db.query(Payment).order_by(Payment.created_at.desc()).offset(skip).limit(limit).all()
    
    return [
        {
            "id": payment.id,
            "user_id": payment.user_id,
            "amount": float(payment.amount),
            "tariff": payment.tariff,
            "status": payment.status,
            "yookassa_payment_id": payment.yookassa_payment_id,
            "created_at": payment.created_at.isoformat(),
            "completed_at": payment.completed_at.isoformat() if payment.completed_at else None
        }
        for payment in payments
    ]


@app.get("/analyses")
async def get_analyses(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    token: str = Depends(verify_admin_token)
):
    """Get analyses list."""
    analyses = db.query(AnalysisSession).order_by(AnalysisSession.created_at.desc()).offset(skip).limit(limit).all()
    
    return [
        {
            "id": analysis.id,
            "user_id": analysis.user_id,
            "created_at": analysis.created_at.isoformat()
        }
        for analysis in analyses
    ]


@app.get("/stats/subscriptions")
async def get_subscription_stats(
    db: Session = Depends(get_db),
    token: str = Depends(verify_admin_token)
):
    """Get subscription statistics."""
    stats = {}
    
    for plan in ["1month", "3months", "6months", "12months"]:
        count = db.query(Payment).filter(
            Payment.tariff == plan,
            Payment.status == "completed"
        ).count()
        stats[plan] = count
    
    return stats
