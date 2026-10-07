import uuid
import json
import math
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from src.core.redis import redis_client
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from src.core.db import get_db, set_tenant_context
from src.worker.tasks import dispatch_payment_task

router = APIRouter()

# --- AMAZON COGNITO SIMULATION ---
def get_current_tenant(authorization: str = Header(default="Bearer mockjwt-brand-x")):
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid token")
    token = authorization.split(" ")[1]
    if token.startswith("mockjwt-"):
        return token.split("mockjwt-")[1]
    raise HTTPException(status_code=403, detail="Unauthorized tenant access")

# --- LUA SCRIPTS ---
RATE_LIMIT_LUA = """
local current = redis.call('incr', KEYS[1])
if current == 1 then redis.call('expire', KEYS[1], ARGV[1]) end
if current > tonumber(ARGV[2]) then return 0 end
return 1
"""

VARIABLE_RESERVE_LUA = """
-- KEYS[1] = inventory:{tenant_id}:{sale_id}
-- KEYS[2] = turn:{tenant_id}:{sale_id}
-- ARGV[1] = requested_quantity
-- ARGV[2] = buyer_email

local active_buyer = redis.call('get', KEYS[2])
if active_buyer ~= ARGV[2] then
    return -2 -- Not your turn or turn expired
end

local stock = tonumber(redis.call('get', KEYS[1]))
local req = tonumber(ARGV[1])

if stock == nil then return -1 end
if stock >= req then
    redis.call('decrby', KEYS[1], req)
    redis.call('del', KEYS[2]) -- Turn consumed, delete it
    return 1 -- Success
else
    return 0 -- Not enough stock for requested quantity
end
"""

class CreateSaleRequest(BaseModel):
    product_name: str
    stock_count: int
    price_cents: int

class ReserveRequest(BaseModel):
    sale_id: str
    buyer_email: str
    requested_quantity: int  # Required for variable checkout

@router.post("/seller/sales")
async def create_sale(
    payload: CreateSaleRequest, 
    tenant_id: str = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    sale_id = str(uuid.uuid4())
    
    await set_tenant_context(db, tenant_id)

    query = text("""
        INSERT INTO sales (id, tenant_id, product_name, stock_count, price_cents)
        VALUES (:id, :tenant_id, :product_name, :stock_count, :price_cents)
    """)
    await db.execute(query, {
        "id": sale_id,
        "tenant_id": tenant_id,
        "product_name": payload.product_name,
        "stock_count": payload.stock_count,
        "price_cents": payload.price_cents
    })
    await db.commit()

    inventory_key = f"inventory:{tenant_id}:{sale_id}"
    meta_key = f"sale_meta:{tenant_id}:{sale_id}"
    
    await redis_client.set(inventory_key, payload.stock_count)
    
    # ADDED: product_name stored in Redis so the public browser can display it
    await redis_client.hset(meta_key, mapping={
        "sale_id": sale_id, 
        "stock": payload.stock_count, 
        "tenant": tenant_id,
        "product_name": payload.product_name
    })
    
    return {"status": "created", "sale_id": sale_id, "tenant_id": tenant_id, "stock_count": payload.stock_count}

# ADDED: Public endpoint for cross-tenant browsing
@router.get("/public/sales")
async def list_all_public_sales():
    """No auth — buyers browse all live sales across every tenant before picking one."""
    sales = []
    cursor = 0
    while True:
        cursor, keys = await redis_client.scan(cursor=cursor, match="sale_meta:*", count=100)
        for key in keys:
            meta = await redis_client.hgetall(key)
            if not meta:
                continue
            tenant_id, sale_id = meta.get("tenant"), meta.get("sale_id")
            remaining = await redis_client.get(f"inventory:{tenant_id}:{sale_id}")
            sales.append({
                "tenant_id": tenant_id,
                "sale_id": sale_id,
                "product_name": meta.get("product_name", "Unnamed Drop"),
                "remaining_stock": int(remaining) if remaining is not None else 0,
            })
        if cursor == 0:
            break
    return {"sales": sales}

@router.post("/buyer/queue/join")
async def join_queue(sale_id: str, buyer_email: str, tenant_id: str = Depends(get_current_tenant)):
    """Users must hit this endpoint first to get into the sequential line."""
    seq_key = f"seq:{tenant_id}:{sale_id}"
    queue_key = f"queue:{tenant_id}:{sale_id}"
    
    score = await redis_client.incr(seq_key)
    await redis_client.zadd(queue_key, {buyer_email: score})
    
    actual_rank = await redis_client.zrank(queue_key, buyer_email)
    
    # Calculate display rank bucket
    rank = actual_rank + 1 
    if rank < 10:
        display_rank = str(rank)
    else:
        bucket_size = 10 ** math.floor(math.log10(max(rank, 1)))
        lower = (rank // bucket_size) * bucket_size
        display_rank = f"{lower}-{lower + bucket_size}"
    
    return {"status": "queued", "display_rank": display_rank, "exact_rank": actual_rank}

@router.post("/buyer/reserve")
async def reserve_item(payload: ReserveRequest, tenant_id: str = Depends(get_current_tenant)):
    # 1. Anti-Bot Rate Limiting (Per-tenant, per-email)
    rate_key = f"ratelimit:{tenant_id}:{payload.buyer_email}"
    if await redis_client.eval(RATE_LIMIT_LUA, 1, rate_key, 1, 5) == 0:
        raise HTTPException(status_code=429, detail="Bot behavior detected.")

    # 2. Variable Quantity Reservation with Turn Checking
    inventory_key = f"inventory:{tenant_id}:{payload.sale_id}"
    turn_key = f"turn:{tenant_id}:{payload.sale_id}"
    
    result = await redis_client.eval(
        VARIABLE_RESERVE_LUA, 
        2, 
        inventory_key, 
        turn_key, 
        payload.requested_quantity, 
        payload.buyer_email
    )

    if result == 1:
        reservation_id = str(uuid.uuid4())[:8]
        
        # 3. Queue for Async Processing via Semaphore Dispatcher
        task_payload = {
            "tenant_id": tenant_id,
            "sale_id": payload.sale_id,
            "buyer_email": payload.buyer_email,
            "reservation_id": reservation_id,
            "quantity": payload.requested_quantity
        }
        
        # Replaces the old redis_client.lpush simulation
        dispatch_payment_task(tenant_id, task_payload)
        
        return {
            "status": "reserved", 
            "reservation_id": reservation_id, 
            "quantity": payload.requested_quantity
        }
    elif result == -2:
        raise HTTPException(status_code=403, detail="Not your turn or turn has expired.")
    elif result == 0:
        raise HTTPException(status_code=410, detail="Not enough stock for the requested quantity.")
    else:
        raise HTTPException(status_code=404, detail="Sale not found or does not belong to this tenant")

@router.get("/seller/sales/{sale_id}/status")
async def get_sale_status(sale_id: str, tenant_id: str = Depends(get_current_tenant)):
    stock = await redis_client.get(f"inventory:{tenant_id}:{sale_id}")
    if stock is None:
        raise HTTPException(status_code=404, detail="Access denied or sale not found")
    return {"tenant_id": tenant_id, "remaining_stock": int(stock)}

@router.get("/buyer/queue/status")
async def queue_status(sale_id: str, buyer_email: str, tenant_id: str = Depends(get_current_tenant)):
    queue_key = f"queue:{tenant_id}:{sale_id}"
    turn_key = f"turn:{tenant_id}:{sale_id}"

    active_buyer = await redis_client.get(turn_key)
    if active_buyer == buyer_email:
        ttl = await redis_client.ttl(turn_key)
        return {"is_turn": True, "seconds_remaining": max(ttl, 0)}

    rank = await redis_client.zrank(queue_key, buyer_email)
    if rank is None:
        return {"is_turn": False, "display_rank": "Not in queue"}

    rank += 1
    if rank < 10:
        display_rank = str(rank)
    else:
        bucket = 10 ** math.floor(math.log10(rank))
        lower = (rank // bucket) * bucket
        display_rank = f"{lower}-{lower + bucket}"

    return {"is_turn": False, "display_rank": display_rank, "exact_rank": rank}

@router.get("/seller/sales")
async def list_sales(tenant_id: str = Depends(get_current_tenant), db: AsyncSession = Depends(get_db)):
    await set_tenant_context(db, tenant_id)
    result = await db.execute(
        text("SELECT id, product_name, stock_count FROM sales WHERE tenant_id = :t ORDER BY created_at DESC"),
        {"t": tenant_id}
    )
    sales = []
    for row in result.fetchall():
        stock = await redis_client.get(f"inventory:{tenant_id}:{row.id}")
        sales.append({
            "sale_id": str(row.id),
            "product_name": row.product_name,
            "original_stock": row.stock_count,
            "remaining_stock": int(stock) if stock is not None else 0
        })
    return {"sales": sales}