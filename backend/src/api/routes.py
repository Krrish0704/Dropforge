import uuid
import asyncio
from fastapi import APIRouter, Header, HTTPException, BackgroundTasks
from pydantic import BaseModel
from src.core.redis import redis_client

router = APIRouter()

RATE_LIMIT_LUA = """
local current = redis.call('incr', KEYS[1])
if current == 1 then
    redis.call('expire', KEYS[1], ARGV[1])
end
if current > tonumber(ARGV[2]) then
    return 0 -- Rate limit exceeded
end
return 1 -- Allowed
"""

# 2. Atomic Reservation (Existing)
RESERVE_LUA_SCRIPT = """
local stock = tonumber(redis.call('get', KEYS[1]))
if stock == nil then return -1 end
if stock > 0 then
    redis.call('decr', KEYS[1])
    return 1
else
    return 0
end
"""

class CreateSaleRequest(BaseModel):
    product_name: str
    stock_count: int
    price_cents: int

class ReserveRequest(BaseModel):
    sale_id: str
    buyer_email: str

# --- ASYNC WORKER SIMULATION (Simulates SQS + Celery) ---
async def process_payment_worker(tenant_id: str, sale_id: str, email: str, res_id: str):
    """Simulates picking up a message from SQS, processing payment, and writing to Aurora PostgreSQL."""
    print(f"[{res_id}] ⏳ WORKER: Processing payment for {email}...")
    await asyncio.sleep(2)  # Simulate slow payment gateway network call
    print(f"[{res_id}] ✅ WORKER: Payment cleared. Order saved to DB for Tenant: {tenant_id}")

@router.post("/seller/sales")
async def create_sale(payload: CreateSaleRequest, x_tenant_id: str = Header(default="tenant-alpha", alias="X-Tenant-ID")):
    sale_id = str(uuid.uuid4())[:8]
    inventory_key = f"inventory:{x_tenant_id}:{sale_id}"
    
    await redis_client.set(inventory_key, payload.stock_count)
    await redis_client.hset(
        f"sale_meta:{x_tenant_id}:{sale_id}",
        mapping={"sale_id": sale_id, "stock": payload.stock_count}
    )
    return {"status": "created", "sale_id": sale_id, "stock_count": payload.stock_count}

@router.post("/buyer/reserve")
async def reserve_item(
    payload: ReserveRequest, 
    background_tasks: BackgroundTasks,
    x_tenant_id: str = Header(default="tenant-alpha", alias="X-Tenant-ID")
):
    # 1. Rate Limiting Check (Max 5 requests per second per Email)
    rate_key = f"ratelimit:{payload.buyer_email}"
    is_allowed = await redis_client.eval(RATE_LIMIT_LUA, 1, rate_key, 1, 5)
    if is_allowed == 0:
        raise HTTPException(status_code=429, detail="Too many requests. Bot behavior detected.")

    # 2. Atomic Inventory Check
    inventory_key = f"inventory:{x_tenant_id}:{payload.sale_id}"
    result = await redis_client.eval(RESERVE_LUA_SCRIPT, 1, inventory_key)

    if result == 1:
        reservation_id = str(uuid.uuid4())[:8]
        # 3. Hand off to Async Worker (Decoupling)
        background_tasks.add_task(process_payment_worker, x_tenant_id, payload.sale_id, payload.buyer_email, reservation_id)
        
        return {"status": "reserved", "reservation_id": reservation_id, "message": "Payment processing in background"}
    elif result == 0:
        raise HTTPException(status_code=410, detail="Sold out")
    else:
        raise HTTPException(status_code=404, detail="Sale not found")

@router.get("/seller/sales/{sale_id}/status")
async def get_sale_status(sale_id: str, x_tenant_id: str = Header(default="tenant-alpha", alias="X-Tenant-ID")):
    stock = await redis_client.get(f"inventory:{x_tenant_id}:{sale_id}")
    if stock is None:
        raise HTTPException(status_code=404, detail="Sale not found")
    return {"remaining_stock": int(stock)}