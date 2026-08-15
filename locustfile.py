from locust import HttpUser, task, between
import random
import uuid

class OrderUser(HttpUser):
    wait_time = between(0.1, 0.5)

    @task
    def create_order(self):
        payload = {
            "item_id": f"sku-{random.randint(1, 20)}",
            "quantity": random.randint(1, 3),
        }
        headers = {"X-Idempotency-Key": str(uuid.uuid4())}
        self.client.post("/order", json=payload, headers=headers, name="/order")