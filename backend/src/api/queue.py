import math
from fastapi import APIRouter, Depends, HTTPException
from src.core.redis import redis_client
from src.core.auth import get_current_tenant

router = APIRouter()

def get_display_rank(actual_rank: int) -> str:
    """
    Calculates the bucketed rank display using the formula:
    $\text{bucket\_size} = 10^{\lfloor \log_{10}(\max(\text{rank}, 1)) \rfloor}$
    """
    # 0-indexed rank from Redis, add 1 for human readability
    rank = actual_rank + 1 
    
    if rank < 10:
        return str(rank)
        
    bucket_size = 10 ** math.floor(math.log10(max(rank, 1)))
    lower = (rank // bucket_size) * bucket_size
    upper = lower + bucket_size
    return f"{lower}-{upper}"

@router.post("/buyer/queue/join")
async def join_queue(sale_id: str, buyer_email: str, tenant_id: str = Depends(get_current_tenant)):
    seq_key = f"seq:{tenant_id}:{sale_id}"
    queue_key = f"queue:{tenant_id}:{sale_id}"
    
    # 1. Get a strictly ordered integer sequence
    score = await redis_client.incr(seq_key)
    
    # 2. Add to the ZSET queue
    await redis_client.zadd(queue_key, {buyer_email: score})
    
    # 3. Get exact rank and convert to bucketed display
    actual_rank = await redis_client.zrank(queue_key, buyer_email)
    display_rank = get_display_rank(actual_rank)
    
    return {"status": "queued", "display_rank": display_rank, "exact_rank": actual_rank}