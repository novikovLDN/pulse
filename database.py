"""Database models and connection."""
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, ForeignKey, JSON, Numeric, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
from config import settings

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
    telegram_id = Column(Integer, unique=True, index=True, nullable=False)
    subscription_status = Column(String, default="inactive")  # active, inactive, expired
    subscription_expire_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    payments = relationship("Payment", back_populates="user")
    analysis_sessions = relationship("AnalysisSession", back_populates="user")


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
    
    # Relationships
    user = relationship("User", back_populates="payments")


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


def init_db():
    """Initialize database tables."""
    Base.metadata.create_all(bind=engine)


def get_db():
    """Get database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
