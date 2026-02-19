"""Database models and connection."""
from sqlalchemy import create_engine, Column, Integer, BigInteger, String, DateTime, Boolean, ForeignKey, JSON, Numeric, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
from config import settings
import secrets

Base = declarative_base()

# Create engine with connection pooling and error handling for PostgreSQL
try:
    # Ensure PostgreSQL URL format
    db_url = settings.database_url
    if not db_url.startswith(('postgresql://', 'postgresql+psycopg2://')):
        # Try to fix common URL format issues
        if db_url.startswith('postgres://'):
            db_url = db_url.replace('postgres://', 'postgresql://', 1)
    
    engine = create_engine(
        db_url,
        echo=False,
        pool_pre_ping=True,  # Verify connections before using
        pool_recycle=3600,   # Recycle connections after 1 hour
        pool_size=5,         # Connection pool size
        max_overflow=10,     # Max overflow connections
        connect_args={
            "connect_timeout": 10,
            "options": "-c statement_timeout=30000"
        }
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
except Exception as e:
    from loguru import logger
    logger.error(f"❌ Failed to create PostgreSQL database engine: {e}")
    logger.error(f"Database URL format: {settings.database_url[:20]}...")
    raise


class User(Base):
    """User model."""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(BigInteger, unique=True, index=True, nullable=False)
    subscription_status = Column(String, default="inactive")  # active, inactive, expired
    subscription_expire_at = Column(DateTime, nullable=True)
    total_requests = Column(Integer, default=0)  # Total requests from tariff
    bonus_requests = Column(Integer, default=0)  # Bonus requests from referrals
    used_requests = Column(Integer, default=0)  # Used requests count
    referrer_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # Who referred this user
    referral_code = Column(String, unique=True, nullable=True, index=True)  # Unique referral code
    username = Column(String, nullable=True, index=True)  # Telegram @username for admin search
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    payments = relationship("Payment", back_populates="user", foreign_keys="Payment.user_id")
    analysis_sessions = relationship("AnalysisSession", back_populates="user")
    referrals_made = relationship("Referral", back_populates="referrer", foreign_keys="Referral.referrer_id")
    referred_by_rel = relationship("User", remote_side=[id], foreign_keys=[referrer_id])
    
    def generate_referral_code(self):
        """Generate unique referral code."""
        if not self.referral_code:
            self.referral_code = secrets.token_urlsafe(8)[:12].upper()
        return self.referral_code


class Payment(Base):
    """Payment model."""
    __tablename__ = "payments"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)
    tariff = Column(String, nullable=False)  # 1month, 3months, 6months, 12months
    status = Column(String, default="pending")  # pending, completed, failed, refunded
    yookassa_payment_id = Column(String, unique=True, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    payment_date = Column(DateTime, nullable=True)  # Actual payment date
    
    # Relationships
    user = relationship("User", back_populates="payments", foreign_keys=[user_id])
    referral = relationship("Referral", back_populates="payment", uselist=False)


class AnalysisSession(Base):
    """Analysis session model."""
    __tablename__ = "analysis_sessions"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="analysis_sessions")
    structured_result = relationship("StructuredResult", back_populates="session", uselist=False)
    follow_up_questions = relationship("FollowUpQuestion", back_populates="session")


class StructuredResult(Base):
    """Structured laboratory results."""
    __tablename__ = "structured_results"
    
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("analysis_sessions.id"), unique=True, nullable=False)
    structured_json = Column(JSON, nullable=False)  # JSONB in PostgreSQL
    clinical_context = Column(JSON, nullable=True)  # Age, sex, symptoms, etc.
    report = Column(Text, nullable=True)  # Generated clinical report
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    session = relationship("AnalysisSession", back_populates="structured_result")


class FollowUpQuestion(Base):
    """Follow-up questions for analysis sessions."""
    __tablename__ = "follow_up_questions"
    
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("analysis_sessions.id"), nullable=False)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    session = relationship("AnalysisSession", back_populates="follow_up_questions")


class UserNotification(Base):
    """Пользовательское уведомление на дату и время."""
    __tablename__ = "user_notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    scheduled_at = Column(DateTime, nullable=False)  # UTC
    text = Column(Text, nullable=False)
    sent = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    user = relationship("User", backref="notifications", foreign_keys=[user_id])


class Referral(Base):
    """Referral tracking model."""
    __tablename__ = "referrals"
    
    id = Column(Integer, primary_key=True, index=True)
    referrer_id = Column(Integer, ForeignKey("users.id"), nullable=False)  # Who referred
    referred_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)  # Who was referred
    payment_id = Column(Integer, ForeignKey("payments.id"), nullable=False)  # Payment that triggered bonus
    bonus_requests = Column(Integer, default=5)  # Bonus requests awarded
    payment_date = Column(DateTime, nullable=False)  # When payment was completed
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    referrer = relationship("User", back_populates="referrals_made", foreign_keys=[referrer_id])
    referred_user = relationship("User", foreign_keys=[referred_user_id])
    payment = relationship("Payment", back_populates="referral", foreign_keys=[payment_id])


def _column_exists(conn, table: str, column: str) -> bool:
    from sqlalchemy import text
    r = conn.execute(text("""
        SELECT 1 FROM information_schema.columns
        WHERE table_name = :t AND column_name = :c
    """), {"t": table, "c": column})
    return r.fetchone() is not None


def _migrate_add_columns(conn):
    """Add new columns/tables for existing deployments (no Alembic)."""
    from sqlalchemy import text
    for col, sql in [
        ("total_requests", "ALTER TABLE users ADD COLUMN total_requests INTEGER DEFAULT 0"),
        ("bonus_requests", "ALTER TABLE users ADD COLUMN bonus_requests INTEGER DEFAULT 0"),
        ("used_requests", "ALTER TABLE users ADD COLUMN used_requests INTEGER DEFAULT 0"),
        ("referrer_id", "ALTER TABLE users ADD COLUMN referrer_id INTEGER REFERENCES users(id)"),
        ("referral_code", "ALTER TABLE users ADD COLUMN referral_code VARCHAR UNIQUE"),
    ]:
        if not _column_exists(conn, "users", col):
            conn.execute(text(sql))
    if not _column_exists(conn, "payments", "payment_date"):
        conn.execute(text("ALTER TABLE payments ADD COLUMN payment_date TIMESTAMP"))
    if not _column_exists(conn, "users", "username"):
        conn.execute(text("ALTER TABLE users ADD COLUMN username VARCHAR"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_users_username ON users(username)"))
    # user_notifications table (created by create_all if new; for old DBs without Alembic)
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS user_notifications (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            scheduled_at TIMESTAMP NOT NULL,
            text TEXT NOT NULL,
            sent BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """))
    # Telegram user IDs can exceed 2^31; ensure BIGINT
    conn.execute(text("ALTER TABLE users ALTER COLUMN telegram_id TYPE BIGINT"))
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS referrals (
            id SERIAL PRIMARY KEY,
            referrer_id INTEGER NOT NULL REFERENCES users(id),
            referred_user_id INTEGER NOT NULL REFERENCES users(id),
            payment_id INTEGER NOT NULL REFERENCES payments(id),
            bonus_requests INTEGER DEFAULT 5,
            payment_date TIMESTAMP NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """))


def init_db():
    """Initialize database tables and run migration for new columns."""
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        _migrate_add_columns(conn)


def get_db():
    """Get database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
