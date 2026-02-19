"""Redis client for FSM and rate limiting."""
import redis
import json
from typing import Optional, Dict, Any
from config import settings

# Use Redis URL if provided (Railway), otherwise use host/port
if settings.redis_url:
    redis_client = redis.from_url(
        settings.redis_url,
        decode_responses=True
    )
else:
    redis_client = redis.Redis(
        host=settings.redis_host,
        port=settings.redis_port,
        db=settings.redis_db,
        decode_responses=True
    )


class FSMStorage:
    """Finite State Machine storage using Redis."""
    
    @staticmethod
    def get_state(user_id: int) -> Optional[str]:
        """Get current state for user."""
        key = f"fsm:{user_id}"
        return redis_client.get(key)
    
    @staticmethod
    def set_state(user_id: int, state: str):
        """Set state for user."""
        key = f"fsm:{user_id}"
        redis_client.setex(key, 3600, state)  # 1 hour TTL
    
    @staticmethod
    def clear_state(user_id: int):
        """Clear state for user."""
        key = f"fsm:{user_id}"
        redis_client.delete(key)
    
    @staticmethod
    def get_data(user_id: int) -> Dict[str, Any]:
        """Get temporary data for user."""
        key = f"fsm_data:{user_id}"
        data = redis_client.get(key)
        return json.loads(data) if data else {}
    
    @staticmethod
    def set_data(user_id: int, data: Dict[str, Any]):
        """Set temporary data for user."""
        key = f"fsm_data:{user_id}"
        redis_client.setex(key, 3600, json.dumps(data))  # 1 hour TTL
    
    @staticmethod
    def clear_data(user_id: int):
        """Clear temporary data for user."""
        key = f"fsm_data:{user_id}"
        redis_client.delete(key)


class RateLimiter:
    """Rate limiter using Redis."""
    
    @staticmethod
    def check_rate_limit(user_id: int, action: str, limit: int, window: int = 60) -> bool:
        """Check if user can perform action."""
        key = f"rate_limit:{user_id}:{action}"
        current = redis_client.incr(key)
        if current == 1:
            redis_client.expire(key, window)
        return current <= limit
