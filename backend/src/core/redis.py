import os
import redis.asyncio as redis

# Connect to the Redis container using the environment variable we set in docker-compose.yml
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
redis_pool = redis.ConnectionPool.from_url(REDIS_URL, decode_responses=True)
redis_client = redis.Redis(connection_pool=redis_pool)