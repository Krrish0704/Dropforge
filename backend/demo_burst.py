import asyncio
import httpx

async def main():
    # Use localhost:8000 since we'll run this from outside or mapped ports
    async with httpx.AsyncClient(base_url="http://127.0.0.1:8000", timeout=10.0) as client:
        headers = {"X-Tenant-ID": "brand-x"}
        
        # 1. Create Sale (10 items)
        print("[*] Initializing Flash Sale with 10 units...")
        res = await client.post("/api/v1/seller/sales", json={"product_name": "Hoodie", "stock_count": 10, "price_cents": 5000}, headers=headers)
        sale_id = res.json()["sale_id"]
        print(f"[*] Sale Created: {sale_id}")

        # 2. Fire 100 concurrent requests
        print("\n[+] Firing 100 concurrent checkout requests...")
        async def reserve(i):
            return await client.post("/api/v1/buyer/reserve", json={"sale_id": sale_id, "buyer_email": f"buyer{i}@test.com"}, headers=headers)
        
        results = await asyncio.gather(*[reserve(i) for i in range(100)])
        statuses = [r.status_code for r in results]
        
        # 3. Check final stock
        stock_res = await client.get(f"/api/v1/seller/sales/{sale_id}/status", headers=headers)
        remaining = stock_res.json()['remaining_stock']
        
        print("\n========================================")
        print("CONCURRENCY TEST RESULTS")
        print("========================================")
        print(f"Successful Reservations (HTTP 200): {statuses.count(200)}")
        print(f"Sold Out Rejections (HTTP 410):     {statuses.count(410)}")
        print(f"Remaining Stock in Engine:          {remaining}")
        print("========================================")

if __name__ == "__main__":
    asyncio.run(main())