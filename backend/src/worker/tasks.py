import os
import time
import random
import redis
from celery import shared_task
from celery.exceptions import Retry, MaxRetriesExceededError
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from src.worker.celery_app import celery_app

# --- SYNCHRONOUS CONNECTIONS FOR CELERY ---
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:password@localhost:5432/dropforge")
SYNC_DB_URL = DATABASE_URL.replace("+asyncpg", "")

sync_engine = create_engine(SYNC_DB_URL)
SyncSessionLocal = sessionmaker(bind=sync_engine)
sync_redis = redis.from_url(REDIS_URL, decode_responses=True)

MAX_INFLIGHT_PER_TENANT = 50

# Restores the exact variable quantity back to inventory if payment fails[cite: 2]
ROLLBACK_LUA = """
-- KEYS[1] = inventory:{tenant_id}:{sale_id}
-- ARGV[1] = requested_quantity to restore
redis.call('incrby', KEYS[1], tonumber(ARGV[1]))
return 1
"""

# --- CUSTOM EXCEPTIONS FOR ROUTING ---
class TransientGatewayError(Exception):
    """Temporary gateway connection drops requiring short automated retries."""
    pass

class ActionRequiredError(Exception):
    """Failures requiring human intervention (e.g., 3D Secure, OTP) with a 120s hold."""
    pass

# --- 1. CELERY BEAT: DISTRIBUTED QUEUE REAPER ---
@shared_task(name="advance_all_expired_turns", queue="default")
def advance_all_expired_turns():
    """
    Generic reaper: Scans active queues and creates a turn token for the next buyer.
    """
    cursor = 0
    while True:
        cursor, keys = sync_redis.scan(cursor=cursor, match="queue:*:*", count=100)
        for queue_key in keys:
            parts = queue_key.split(":")
            if len(parts) != 3:
                continue
                
            tenant_id, sale_id = parts[1], parts[2]
            turn_key = f"turn:{tenant_id}:{sale_id}"
            
            # If an active turn is still ticking down, do not pop the next user
            if sync_redis.get(turn_key):
                continue  
                
            # Pop the oldest buyer from the ZSET
            next_user = sync_redis.zpopmin(queue_key, 1)
            if not next_user:
                continue 
                
            buyer_email = next_user[0][0]
            
            # Set the turn with a 90-second TTL
            sync_redis.setex(turn_key, 90, buyer_email)
            print(f"[*] Turn advanced for {sale_id}. {buyer_email} now has 90s to choose quantity.")
            
        if cursor == 0:
            break
# --- 2. SEMAPHORE DISPATCHER: CROSS-TENANT FAIRNESS ---
def dispatch_payment_task(tenant_id: str, payload: dict):
    """
    Enforces a maximum inflight limit so one massive flash sale 
    cannot consume 100% of the shared worker pool[cite: 2].
    """
    inflight_key = f"inflight:{tenant_id}"
    current = sync_redis.incr(inflight_key)
    
    if current > MAX_INFLIGHT_PER_TENANT:
        sync_redis.decr(inflight_key)
        process_payment.apply_async(args=[payload], countdown=2, queue="default")
        return
        
    process_payment.apply_async(args=[payload], queue="default")

# --- 3. EXECUTION TASK: DURABILITY & PRIORITY RETRIES ---
@celery_app.task(bind=True, name="process_payment")
def process_payment(self, payload: dict):
    tenant_id = payload["tenant_id"]
    sale_id = payload["sale_id"]
    email = payload["buyer_email"]
    res_id = payload["reservation_id"]
    quantity = payload.get("quantity", 1)
    inventory_key = f"inventory:{tenant_id}:{sale_id}"
    
    is_retrying = False

    try:
        print(f"[{res_id}] ⏳ Processing payment for {email} (Qty: {quantity}, Attempt: {self.request.retries + 1})...")
        time.sleep(1.2)  

        roll = random.random()
        # Simulate 5% transient network timeout
        if roll < 0.05:
            raise TransientGatewayError("Gateway socket timeout")
        # Simulate 5% OTP/3D Secure action required
        elif roll < 0.10:
            raise ActionRequiredError("3D Secure challenge required")
        # Simulate 5% hard terminal failure (fraud, invalid card)
        elif roll < 0.15:
            print(f"[{res_id}] ❌ TERMINAL FAILURE: Rolling back {quantity} units.")
            sync_redis.eval(ROLLBACK_LUA, 1, inventory_key, quantity)
            return {"status": "failed", "reservation_id": res_id}

        # Persist finalized order to PostgreSQL with RLS context[cite: 2]
        # Persist finalized order to PostgreSQL with RLS context[cite: 2]
        with SyncSessionLocal() as session:
            session.execute(
                text("SELECT set_config('app.current_tenant', :tenant, true)"), 
                {"tenant": tenant_id}
            )
            
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

        print(f"[{res_id}] ✅ ORDER PERSISTED: Tenant {tenant_id}")
        return {"status": "completed", "reservation_id": res_id}

    except TransientGatewayError:
        is_retrying = True
        backoff = min(5 * (2 ** self.request.retries), 30)
        print(f"[{res_id}] ⚠️ GATEWAY BLIP: Escalating to 'priority' queue in {backoff}s...")
        raise self.retry(queue="priority", countdown=backoff, max_retries=3)

    except ActionRequiredError:
        is_retrying = True
        # Set a 120s hold in Redis for the user to complete their action
        hold_key = f"payment_hold:{tenant_id}:{res_id}"
        sync_redis.setex(hold_key, 120, "awaiting_user_action")
        print(f"[{res_id}] 🛑 ACTION REQUIRED: Holding inventory for 120s. Pushing to priority fallback.")
        # Queue it slightly past the 120s mark. If the user hasn't intervened, this fallback attempt rolls it back.
        raise self.retry(queue="priority", countdown=125, max_retries=1)

    except Retry:
        is_retrying = True
        raise 

    except MaxRetriesExceededError:
        print(f"[{res_id}] 🚨 HOLD EXPIRED / MAX RETRIES: Rolling back {quantity} units.")
        sync_redis.eval(ROLLBACK_LUA, 1, inventory_key, quantity)
        return {"status": "failed_after_retries", "reservation_id": res_id}

    except Exception as e:
        print(f"[{res_id}] ⚠️ UNHANDLED ERROR: {str(e)}")
        sync_redis.eval(ROLLBACK_LUA, 1, inventory_key, quantity)
        raise e

    finally:
        # Prevents negative semaphore drift during retries
        if not is_retrying:
            sync_redis.decr(f"inflight:{tenant_id}")