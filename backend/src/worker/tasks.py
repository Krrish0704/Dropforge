import os
import time
import random
import redis
from celery import shared_task
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from src.worker.celery_app import celery_app


REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:password@localhost:5432/dropforge")
SYNC_DB_URL = DATABASE_URL.replace("+asyncpg", "")

sync_engine = create_engine(SYNC_DB_URL)
SyncSessionLocal = sessionmaker(bind=sync_engine)
sync_redis = redis.from_url(REDIS_URL, decode_responses=True)

# --- CONFIGURATION & SCRIPTS ---
MAX_INFLIGHT_PER_TENANT = 50

# Restores the exact variable quantity back to inventory if payment fails
ROLLBACK_LUA = """
-- KEYS[1] = inventory:{tenant_id}:{sale_id}
-- ARGV[1] = requested_quantity to restore
redis.call('incrby', KEYS[1], tonumber(ARGV[1]))
return 1
"""

# --- 1. CELERY BEAT: DISTRIBUTED QUEUE REAPER ---
@shared_task(name="advance_expired_turns")
def advance_expired_turns(tenant_id: str, sale_id: str):
    """
    Runs every 2 seconds via Celery Beat.
    If the active turn has expired (or doesn't exist), pop the next user from the ZSET queue.
    """
    turn_key = f"turn:{tenant_id}:{sale_id}"
    queue_key = f"queue:{tenant_id}:{sale_id}"
    
    # Check if a turn is currently active
    current_turn = sync_redis.get(turn_key)
    if current_turn:
        return  # Still waiting for the current buyer to act
        
    # Pop the lowest-score (oldest) user from the ZSET
    next_user = sync_redis.zpopmin(queue_key, 1)
    if not next_user:
        return  # Queue is empty
        
    buyer_email = next_user[0][0]
    
    # Set the turn with a 90-second distributed TTL
    sync_redis.setex(turn_key, 90, buyer_email)
    print(f"Turn advanced for {sale_id}. {buyer_email} now has 90s to choose quantity.")

# --- 2. SEMAPHORE DISPATCHER: CROSS-TENANT FAIRNESS ---
def dispatch_payment_task(tenant_id: str, payload: dict):
    """
    Enforces a maximum inflight limit so one massive flash sale 
    cannot consume 100% of the shared worker pool.
    """
    inflight_key = f"inflight:{tenant_id}"
    
    current = sync_redis.incr(inflight_key)
    
    if current > MAX_INFLIGHT_PER_TENANT:
        # Roll back the increment and retry later via the default queue
        sync_redis.decr(inflight_key)
        process_payment.apply_async(args=[payload], countdown=2, queue="default")
        return
        
    # Dispatch normally if under the limit
    process_payment.apply_async(args=[payload], queue="default")

# --- 3. EXECUTION TASK: DURABILITY & ROLLBACK ---
@celery_app.task(bind=True, name="process_payment")
def process_payment(self, payload: dict):
    """
    Handles payment simulation, writes to PostgreSQL with RLS, 
    and reliably decrements the inflight semaphore.
    """
    tenant_id = payload["tenant_id"]
    sale_id = payload["sale_id"]
    email = payload["buyer_email"]
    res_id = payload["reservation_id"]
    quantity = payload.get("quantity", 1)
    
    try:
        print(f"[{res_id}] ⏳ CELERY: Processing payment for {email} (Qty: {quantity})...")
        time.sleep(1.5)  # Simulate payment gateway latency

        # Simulate 15% failed payment / abandoned checkout
        payment_successful = random.random() >= 0.15

        if not payment_successful:
            print(f"[{res_id}] ❌ PAYMENT FAILED: Rolling back {quantity} units for sale {sale_id}")
            inventory_key = f"inventory:{tenant_id}:{sale_id}"
            sync_redis.eval(ROLLBACK_LUA, 1, inventory_key, quantity)
            return {"status": "failed", "reservation_id": res_id}

        # Persist finalized order to PostgreSQL with RLS context
        with SyncSessionLocal() as session:
            # Enforce Row-Level Security for this specific transaction
            session.execute(text("SET LOCAL app.current_tenant = :tenant"), {"tenant": tenant_id})
            
            insert_query = text("""
                INSERT INTO orders (tenant_id, sale_id, buyer_email, reservation_id, status)
                VALUES (:tenant_id, :sale_id, :buyer_email, :reservation_id, 'completed')
            """)
            session.execute(insert_query, {
                "tenant_id": tenant_id,
                "sale_id": sale_id,
                "buyer_email": email,
                "reservation_id": res_id
            })
            session.commit()

        print(f"[{res_id}] ✅ ORDER DURABLY PERSISTED: Tenant {tenant_id}")
        return {"status": "completed", "reservation_id": res_id}
        
    except Exception as e:
        print(f"[{res_id}] ⚠️ ERROR: {str(e)}")
        raise e
    finally:
        # Crucial: Always decrement the semaphore even if the database fails,
        # otherwise worker capacity leaks and gets permanently blocked.
        sync_redis.decr(f"inflight:{tenant_id}")