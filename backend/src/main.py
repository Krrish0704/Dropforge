import asyncio
import json
import random
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.api.routes import router
from src.core.redis import redis_client

# Atomic Rollback: Restores stock if payment drops/abandons
ROLLBACK_LUA = """
redis.call('incr', KEYS[1])
return 1
"""

async def sqs_celery_worker_simulator():
    print("\n🚀 BACKGROUND WORKER: Listening for orders on queue 'dropforge:sqs_queue'...")
    while True:
        try:
            # BRPOP acts like SQS Long Polling. It waits for messages to appear.
            result = await redis_client.brpop("dropforge:sqs_queue", timeout=1)
            if result:
                _, message = result
                order = json.loads(message)
                res_id = order['reservation_id']
                print(f"[{res_id}] 📥 DEQUEUED: Processing payment for {order['buyer_email']}...")
                
                await asyncio.sleep(1.5) # Simulate payment gateway latency

                # Simulate Abandoned Carts / Failed Payments (15% chance to fail)
                if random.random() < 0.15:
                    print(f"[{res_id}] ❌ PAYMENT FAILED! Rolling back inventory for sale {order['sale_id']}")
                    inventory_key = f"inventory:{order['tenant_id']}:{order['sale_id']}"
                    await redis_client.eval(ROLLBACK_LUA, 1, inventory_key)
                else:
                    print(f"[{res_id}] ✅ PAYMENT CLEARED: Order persisted for Tenant {order['tenant_id']}")
        except Exception as e:
            await asyncio.sleep(1)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Spin up the background worker when the server starts
    worker_task = asyncio.create_task(sqs_celery_worker_simulator())
    yield
    worker_task.cancel() # Clean up on shutdown

app = FastAPI(title="DropForge Reservation Engine", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api/v1")