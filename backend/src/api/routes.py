import uuid
import json
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from src.core.redis import redis_client

router = APIRouter()

# --- AMAZON COGNITO SIMULATION ---
def get_current_tenant(authorization: str = Header(default="Bearer mockjwt-brand-x")):
    """
    Simulates extracting the tenant_id from a Cognito JWT claim.
    In production, this decodes and verifies the JWT signature.
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid token")
    
    token = authorization.split(" ")[1]
    
    # Mock decoding: 'mockjwt-brand-x' yields 'brand-x'
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

@router.post("/seller/sales")
async def create_sale(payload: CreateSaleRequest, tenant_id: str = Depends(get_current_tenant)):
    sale_id = str(uuid.uuid4())[:8]
    
    # Strict Namespace Isolation
    inventory_key = f"inventory:{tenant_id}:{sale_id}"
    meta_key = f"sale_meta:{tenant_id}:{sale_id}"
    
    await redis_client.set(inventory_key, payload.stock_count)
    await redis_client.hset(meta_key, mapping={"sale_id": sale_id, "stock": payload.stock_count, "tenant": tenant_id})
    return {"status": "created", "sale_id": sale_id, "tenant_id": tenant_id, "stock_count": payload.stock_count}

@router.post("/buyer/reserve")
async def reserve_item(payload: ReserveRequest, tenant_id: str = Depends(get_current_tenant)):
    # 1. Anti-Bot Rate Limiting (Per-tenant, per-email)
    rate_key = f"ratelimit:{tenant_id}:{payload.buyer_email}"
    if await redis_client.eval(RATE_LIMIT_LUA, 1, rate_key, 1, 5) == 0:
        raise HTTPException(status_code=429, detail="Bot behavior detected.")

    # 2. Atomic Reservation (Isolated to tenant namespace)
    inventory_key = f"inventory:{tenant_id}:{payload.sale_id}"
    result = await redis_client.eval(RESERVE_LUA_SCRIPT, 1, inventory_key)

    if result == 1:
        reservation_id = str(uuid.uuid4())[:8]
        
        # 3. Queue for Async Processing
        task_payload = {
            "tenant_id": tenant_id,
            "sale_id": payload.sale_id,
            "buyer_email": payload.buyer_email,
            "reservation_id": reservation_id
        }
        await redis_client.lpush("dropforge:sqs_queue", json.dumps(task_payload))
        return {"status": "reserved", "reservation_id": reservation_id}
    elif result == 0:
        raise HTTPException(status_code=410, detail="Sold out")
    else:
        # Prevents leaking whether a sale_id exists for a DIFFERENT tenant
        raise HTTPException(status_code=404, detail="Sale not found or does not belong to this tenant")

@router.get("/seller/sales/{sale_id}/status")
async def get_sale_status(sale_id: str, tenant_id: str = Depends(get_current_tenant)):
    # Tenant B cannot query Tenant A's sale_id, even if they guess it.
    stock = await redis_client.get(f"inventory:{tenant_id}:{sale_id}")
    if stock is None:
        raise HTTPException(status_code=404, detail="Access denied or sale not found")
    return {"tenant_id": tenant_id, "remaining_stock": int(stock)}