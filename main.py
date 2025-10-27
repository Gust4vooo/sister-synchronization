import asyncio
from aiohttp import ClientSession
from src.nodes.base_node import Node
from src.nodes.lock_manager import LockManagerNode

# Konfigurasi node
NODE_CONFIGS = {
    "node1": {"host": "127.0.0.1", "port": 8001},
    "node2": {"host": "127.0.0.1", "port": 8002},
    "node3": {"host": "127.0.0.1", "port": 8003},
}

async def main():
    nodes = []
    
    # Inisialisasi semua node
    for node_id, config in NODE_CONFIGS.items():
        peers = {p_id: p_config for p_id, p_config in NODE_CONFIGS.items() if p_id != node_id}
        node = LockManagerNode(node_id=node_id, host=config['host'], port=config['port'], peers=peers)
        nodes.append(node)

    # Buat task untuk menjalankan server dan election timer untuk setiap node
    server_tasks = [asyncio.create_task(node.run_server()) for node in nodes]
    election_tasks = [asyncio.create_task(node.run_election_timer()) for node in nodes]
    
    # Definisikan coroutine untuk simulasi klien
    async def simulation():
        await asyncio.sleep(5) 
        leader = None
        while leader is None:
            for node in nodes:
                if node.state == 'leader':
                    leader = node
                    break
            await asyncio.sleep(0.5)

        print(f"\n--- Leader terpilih: {leader.node_id}. Mensimulasikan Potensi Deadlock... ---\n")

        async def client_task(client_id, lock1, lock2):
            try:
                async with ClientSession() as session:
                    url = f"http://{leader.host}:{leader.port}/lock"
                    
                    print(f">>> [{client_id}] Mencoba ACQUIRE_EXCLUSIVE '{lock1}'")
                    # Pastikan lock pertama berhasil didapat
                    async with session.post(url, json={"action": "ACQUIRE_EXCLUSIVE", "lock_name": lock1, "client_id": client_id}) as resp1:
                        if resp1.status != 202:
                            print(f">>> [{client_id}] GAGAL mendapatkan lock pertama '{lock1}' (status: {resp1.status}).")
                            return
                    
                    print(f">>> [{client_id}] BERHASIL mendapatkan '{lock1}'. Menunggu...")
                    await asyncio.sleep(1) # Beri waktu agar klien lain bisa lock sumber daya kedua

                    print(f">>> [{client_id}] Mencoba ACQUIRE_EXCLUSIVE '{lock2}'")
                    req2 = {"action": "ACQUIRE_EXCLUSIVE", "lock_name": lock2, "client_id": client_id}
                    async with session.post(url, json=req2) as resp2:
                        # Secara eksplisit tangani kasus deadlock
                        if resp2.status == 423: 
                            print(f">>> [{client_id}] DEADLOCK terdeteksi saat meminta '{lock2}'. Melepaskan '{lock1}'.")
                            req_release = {"action": "RELEASE", "lock_name": lock1, "client_id": client_id}
                            await session.post(url, json=req_release)
                            return
                        elif resp2.status != 202:
                            print(f">>> [{client_id}] GAGAL mendapatkan '{lock2}' (status: {resp2.status}). Melepaskan '{lock1}'.")
                            req_release = {"action": "RELEASE", "lock_name": lock1, "client_id": client_id}
                            await session.post(url, json=req_release)
                            return
                        
                        print(f">>> [{client_id}] BERHASIL mendapatkan semua kunci: '{lock1}' dan '{lock2}'.")

            except Exception as e:
                print(f"Error pada klien {client_id}: {e}")

        # Jalankan dua klien secara bersamaan untuk menciptakan potensi deadlock
        await asyncio.gather(
            client_task("Client-A", "resourceA", "resourceB"),
            client_task("Client-B", "resourceB", "resourceA")
        )

        await asyncio.sleep(5) # Tunggu beberapa saat agar release bisa terjadi dan state stabil
        print("\n--- Simulasi Selesai ---")
        for node in nodes:
            print(f"Final State Machine [{node.node_id}]: {node.state_machine}")

    await asyncio.gather(
        *server_tasks,
        *election_tasks,
        simulation() 
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nMenutup semua node...")
