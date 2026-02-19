"""Redis client for FSM and rate limiting."""
import redis
import json
from typing import Optional, Dict, Any
from config import settings
from loguru import logger

# Initialize Redis client with error handling
redis_client = None
redis_available = False

# In-memory fallback storage when Redis is unavailable
_memory_storage: Dict[str, Any] = {}

try:
    # Use Redis URL if provided (Railway), otherwise use host/port
    if settings.redis_url:
        redis_client = redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5
        )
    else:
        redis_client = redis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            db=settings.redis_db,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5
        )
    
    # Test connection
    redis_client.ping()
    redis_available = True
    logger.info("✅ Redis connected successfully")
except Exception as e:
    logger.warning(f"⚠️ Redis not available: {e}")
    logger.warning("Bot will continue without Redis (FSM will use in-memory fallback)")
    redis_available = False
    # Create a dummy client to avoid None errors
    redis_client = None


class FSMStorage:
    """Finite State Machine storage using Redis with in-memory fallback."""
    
    @staticmethod
    def get_state(user_id: int) -> Optional[str]:
        """Get current state for user."""
        if not redis_available or not redis_client:
            return _memory_storage.get(f"fsm:{user_id}")
        
        try:
            key = f"fsm:{user_id}"
            return redis_client.get(key)
        except Exception as e:
            logger.warning(f"Redis get_state error: {e}, using memory fallback")
            return _memory_storage.get(f"fsm:{user_id}")
    
    @staticmethod
    def set_state(user_id: int, state: str):
        """Set state for user."""
        key = f"fsm:{user_id}"
        if not redis_available or not redis_client:
            _memory_storage[key] = state
            return
        
        try:
            redis_client.setex(key, 3600, state)  # 1 hour TTL
        except Exception as e:
            logger.warning(f"Redis set_state error: {e}, using memory fallback")
            _memory_storage[key] = state
    
    @staticmethod
    def clear_state(user_id: int):
        """Clear state for user."""
        key = f"fsm:{user_id}"
        if not redis_available or not redis_client:
            _memory_storage.pop(key, None)
            return
        
        try:
            redis_client.delete(key)
        except Exception as e:
            logger.warning(f"Redis clear_state error: {e}, using memory fallback")
            _memory_storage.pop(key, None)
    
    @staticmethod
    def get_data(user_id: int) -> Dict[str, Any]:
        """Get temporary data for user."""
        key = f"fsm_data:{user_id}"
        if not redis_available or not redis_client:
            data = _memory_storage.get(key)
            return json.loads(data) if isinstance(data, str) else (data if data else {})
        
        try:
            data = redis_client.get(key)
            return json.loads(data) if data else {}
        except Exception as e:
            logger.warning(f"Redis get_data error: {e}, using memory fallback")
            data = _memory_storage.get(key)
            return json.loads(data) if isinstance(data, str) else (data if data else {})
    
    @staticmethod
    def set_data(user_id: int, data: Dict[str, Any]):
        """Set temporary data for user."""
        key = f"fsm_data:{user_id}"
        if not redis_available or not redis_client:
            _memory_storage[key] = json.dumps(data)
            return
        
        try:
            redis_client.setex(key, 3600, json.dumps(data))  # 1 hour TTL
        except Exception as e:
            logger.warning(f"Redis set_data error: {e}, using memory fallback")
            _memory_storage[key] = json.dumps(data)
    
    @staticmethod
    def clear_data(user_id: int):
        """Clear temporary data for user."""
        key = f"fsm_data:{user_id}"
        if not redis_available or not redis_client:
            _memory_storage.pop(key, None)
            return
        
        try:
            redis_client.delete(key)
        except Exception as e:
            logger.warning(f"Redis clear_data error: {e}, using memory fallback")
            _memory_storage.pop(key, None)


class RateLimiter:
    """Rate limiter using Redis with in-memory fallback."""
    
    _rate_limit_memory: Dict[str, Dict[str, int]] = {}
    
    @classmethod
    def _get_memory_key(cls, user_id: int, action: str) -> str:
        """Get memory key for rate limiting."""
        return f"{user_id}:{action}"
    
    @staticmethod
    def check_rate_limit(user_id: int, action: str, limit: int, window: int = 60) -> bool:
        """Check if user can perform action."""
        if not redis_available or not redis_client:
            # In-memory fallback (simple counter, no TTL)
            key = f"{user_id}:{action}"
            if key not in RateLimiter._rate_limit_memory:
                RateLimiter._rate_limit_memory[key] = {"count": 0, "reset_at": 0}
            
            import time
            current_time = int(time.time())
            if RateLimiter._rate_limit_memory[key]["reset_at"] < current_time:
                RateLimiter._rate_limit_memory[key] = {"count": 0, "reset_at": current_time + window}
            
            RateLimiter._rate_limit_memory[key]["count"] += 1
            return RateLimiter._rate_limit_memory[key]["count"] <= limit
        
        try:
            key = f"rate_limit:{user_id}:{action}"
            current = redis_client.incr(key)
            if current == 1:
                redis_client.expire(key, window)
            return current <= limit
        except Exception as e:
            logger.warning(f"Redis rate_limit error: {e}, allowing request")
            return True  # Allow on error
