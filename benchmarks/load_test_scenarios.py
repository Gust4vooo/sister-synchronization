# File: benchmarks/load_test_scenarios.py

import random
import uuid
import time
# Pastikan 'task' diimpor dari locust di sini
from locust import HttpUser, task, between, tag

# --- PENGUJIAN UNTUK DISTRIBUTED LOCK MANAGER (BAGIAN A) ---
@tag('lock_manager')
class LockManagerUser(HttpUser):
    wait_time = between(1, 3)

    def on_start(self):
        self.client_id = f"locust_user_{uuid.uuid4()}"
        self.resources = [f"resource-{i}" for i in range(20)]

    @task
    def acquire_and_release_lock(self):
        resource_name = random.choice(self.resources)
        
        # Retry loop for acquiring the lock
        max_retries = 5
        retry_delay = 0.5 # seconds
        for i in range(max_retries):
            with self.client.post(
                "/lock",
                name="/lock/acquire_exclusive",
                json={
                    "action": "ACQUIRE_EXCLUSIVE",
                    "lock_name": resource_name,
                    "client_id": self.client_id
                },
                catch_response=True
            ) as response:
                if response.status_code in [200, 202]:
                    # Lock acquired successfully
                    break
                elif response.status_code == 423: # Locked
                    if i < max_retries - 1:
                        # Wait and retry
                        time.sleep(retry_delay * (i + 1)) 
                        continue
                    else:
                        # Max retries reached
                        response.failure(f"Gagal mendapatkan kunci setelah {max_retries} percobaan: resource sibuk")
                        return
                else:
                    # Other unexpected error
                    response.failure(f"Gagal mendapatkan kunci: {response.status_code} - {response.text}")
                    return
        else:
            # This block runs if the loop completes without a `break`, meaning all retries failed.
            return

        # If we broke out of the loop, it means we have the lock. Now release it.
        self.client.post(
            "/lock",
            name="/lock/release",
            json={
                "action": "RELEASE",
                "lock_name": resource_name,
                "client_id": self.client_id
            }
        )

# --- PENGUJIAN UNTUK DISTRIBUTED QUEUE SYSTEM (BAGIAN B) ---
@tag('queue_system')
class QueueUser(HttpUser):
    wait_time = between(0.05, 0.2)

    def on_start(self):
        """
        Dijalankan sekali per pengguna. Siapkan daftar host target.
        """
        # --- PERUBAHAN DI SINI ---
        # Daftar semua node antrian yang sedang berjalan
        self.queue_nodes = [
            "http://localhost:8004",
            "http://localhost:8005",
            "http://localhost:8006"
        ]
        # Pastikan port ini sesuai dengan yang ada di docker-compose.yml Anda

    @task
    def produce_message(self):
        """
        Satu tugas: mengirim satu pesan dengan kunci unik ke node yang dipilih acak.
        """
        message_key = f"order:{uuid.uuid4()}"
        message_content = f"Detail untuk pesanan {message_key}"
        
        # --- PERUBAHAN DI SINI ---
        # Pilih satu node secara acak untuk setiap permintaan
        target_host = random.choice(self.queue_nodes)
        
        # Kirim permintaan ke host yang dipilih, bukan ke host default
        self.client.post(
            f"{target_host}/produce", # Gunakan URL lengkap
            json={
                "key": message_key,
                "message": message_content
            }
        )

# --- PENGUJIAN UNTUK DISTRIBUTED CACHE SYSTEM (BAGIAN C) ---
@tag('cache_system')
class CacheUser(HttpUser):
    wait_time = between(0.1, 1.0)

    def on_start(self):
        self.keys = [f"product:{i}" for i in range(10)]

    @task(8)
    def read_from_cache(self):
        key = random.choice(self.keys)
        self.client.get(f"/read/{key}", name="/read/[key]")

    @task(2)
    def write_to_cache(self):
        key = random.choice(self.keys)
        new_value = f"updated_value_{uuid.uuid4()}"
        self.client.post(
            "/write",
            json={
                "key": key,
                "value": new_value
            }
        )