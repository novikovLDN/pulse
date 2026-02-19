"""Cleanup tasks for old data."""
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from database import AnalysisSession, StructuredResult, FollowUpQuestion, SessionLocal
from loguru import logger


def cleanup_old_analyses():
    """Remove analyses older than 60 days."""
    db = SessionLocal()
    try:
        cutoff_date = datetime.utcnow() - timedelta(days=60)
        
        # Find old sessions
        old_sessions = db.query(AnalysisSession).filter(
            AnalysisSession.created_at < cutoff_date
        ).all()
        
        deleted_count = 0
        for session in old_sessions:
            # Delete related data
            db.query(FollowUpQuestion).filter(
                FollowUpQuestion.session_id == session.id
            ).delete()
            
            db.query(StructuredResult).filter(
                StructuredResult.session_id == session.id
            ).delete()
            
            db.delete(session)
            deleted_count += 1
        
        db.commit()
        logger.info(f"Cleaned up {deleted_count} old analyses")
        return deleted_count
    except Exception as e:
        logger.error(f"Error cleaning up old analyses: {e}")
        db.rollback()
        return 0
    finally:
        db.close()


def cleanup_user_analyses(user_id: int, keep_count: int = 3):
    """Keep only the last N analyses per user."""
    db = SessionLocal()
    try:
        # Get all sessions for user, ordered by date
        all_sessions = db.query(AnalysisSession).filter(
            AnalysisSession.user_id == user_id
        ).order_by(AnalysisSession.created_at.desc()).all()
        
        if len(all_sessions) <= keep_count:
            return 0
        
        # Delete old sessions (keep only the last keep_count)
        sessions_to_delete = all_sessions[keep_count:]
        deleted_count = 0
        
        for session in sessions_to_delete:
            # Delete related data
            db.query(FollowUpQuestion).filter(
                FollowUpQuestion.session_id == session.id
            ).delete()
            
            db.query(StructuredResult).filter(
                StructuredResult.session_id == session.id
            ).delete()
            
            db.delete(session)
            deleted_count += 1
        
        db.commit()
        logger.info(f"Cleaned up {deleted_count} old analyses for user {user_id}")
        return deleted_count
    except Exception as e:
        logger.error(f"Error cleaning up user analyses: {e}")
        db.rollback()
        return 0
    finally:
        db.close()
