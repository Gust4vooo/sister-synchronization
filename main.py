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
                    
                    print(f">>> [{client_id}] Mencoba ACQUIRE '{lock1}'")
                    req1 = {"action": "ACQUIRE", "lock_name": lock1, "client_id": client_id}
                    await session.post(url, json=req1)
                    await asyncio.sleep(1)

                    await asyncio.sleep(1)

                    print(f">>> [{client_id}] Mencoba ACQUIRE '{lock2}'")
                    req2 = {"action": "ACQUIRE", "lock_name": lock2, "client_id": client_id}
                    async with session.post(url, json=req2) as resp:
                        if resp.status != 202:
                            print(f">>> [{client_id}] GAGAL mendapatkan '{lock2}' (status: {resp.status}). Melepaskan semua kunci.")
                            req_release = {"action": "RELEASE", "lock_name": lock1, "client_id": client_id}
                            await session.post(url, json=req_release)
                            return
            except Exception as e:
                print(f"Error pada klien {client_id}: {e}")

        # Jalankan dua klien secara bersamaan
        await asyncio.gather(
            client_task("Client-A", "resourceA", "resourceB"),
            client_task("Client-B", "resourceB", "resourceA")
        )

        await asyncio.sleep(3)
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