import asyncio
import httpx

async def main():
    async with httpx.AsyncClient(base_url="http://127.0.0.1:8000", timeout=45.0) as client:
        headers = {"Authorization": "Bearer mockjwt-brand-x"}
        
        # 1. Create Sale
        print("[*] Initializing Flash Sale with 5 units...")
        res = await client.post(
            "/api/v1/seller/sales", 
            json={"product_name": "Exclusive Hoodie", "stock_count": 5, "price_cents": 5000}, 
            headers=headers
        )
        sale_id = res.json()["sale_id"]
        print(f"[*] Sale Created: {sale_id}")

        # 2. Join Queue for 5 Buyers
        print("\n[+] Buyers joining virtual queue...")
        for i in range(5):
            email = f"buyer{i}@test.com"
            q_res = await client.post(
                f"/api/v1/buyer/queue/join?sale_id={sale_id}&buyer_email={email}",
                headers=headers
            )
            print(f"  -> {email} joined: {q_res.json()}")

        # 3. Process Turns as Celery Beat grants them
        print("\n[+] Polling for turns and checking out...")
        for i in range(5):
            email = f"buyer{i}@test.com"
            while True:
                status_res = await client.get(
                    f"/api/v1/buyer/queue/status?sale_id={sale_id}&buyer_email={email}",
                    headers=headers
                )
                data = status_res.json()
                
                # Check for is_turn or status == "your_turn"
                if data.get("is_turn") or data.get("status") == "your_turn":
                    print(f"  -> Turn active for {email}! Reserving 1 unit...")
                    reserve_res = await client.post(
                        "/api/v1/buyer/reserve",
                        json={"sale_id": sale_id, "buyer_email": email, "requested_quantity": 1},
                        headers=headers
                    )
                    print(f"  -> Reservation response: {reserve_res.status_code} {reserve_res.json()}")
                    break
                await asyncio.sleep(1)

        # 4. Check Final Status
        stock_res = await client.get(f"/api/v1/seller/sales/{sale_id}/status", headers=headers)
        print(f"\nFinal Remaining Stock: {stock_res.json()['remaining_stock']}")

if __name__ == "__main__":
    asyncio.run(main())