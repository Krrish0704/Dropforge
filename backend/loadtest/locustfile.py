import time
import uuid
from locust import HttpUser, task, between

# Replace these with the actual IDs generated from your Seller Console
TARGET_SALES = [
    {"sale_id": "REPLACE_WITH_SALE_1", "tenant_id": "brand-x"},
    {"sale_id": "REPLACE_WITH_SALE_2", "tenant_id": "brand-y"}
]

class FlashSaleBuyer(HttpUser):
    wait_time = between(0.5, 1.5)

    @task
    def execute_flash_sale_checkout(self):
        # Randomly select one of the active sales
        import random
        target = random.choice(TARGET_SALES)
        sale_id = target["sale_id"]
        tenant_id = target["tenant_id"]
        
        buyer_email = f"buyer_{uuid.uuid4().hex[:8]}@locust.com"
        headers = {"Authorization": f"Bearer mockjwt-{tenant_id}"}

        # 1. Join the Virtual Queue
        join_res = self.client.post(
            f"/api/v1/buyer/queue/join?sale_id={sale_id}&buyer_email={buyer_email}",
            headers=headers,
            name="/queue/join"
        )
        
        if join_res.status_code != 200:
            return

        # 2. Poll for Turn (simulating user in the waiting room)
        for _ in range(60): 
            time.sleep(1)
            status_res = self.client.get(
                f"/api/v1/buyer/queue/status?sale_id={sale_id}&buyer_email={buyer_email}",
                headers=headers,
                name="/queue/status"
            )
            
            if status_res.status_code == 200 and status_res.json().get("is_turn"):
                # 3. Turn Granted -> Execute Reservation
                self.client.post(
                    "/api/v1/buyer/reserve",
                    json={
                        "sale_id": sale_id,
                        "buyer_email": buyer_email,
                        "requested_quantity": 1
                    },
                    headers=headers,
                    name="/reserve"
                )
                break