# main.py

import asyncio
from src.nodes.base_node import Node
from aiohttp import web, ClientSession

# Konfgurasi sistem 
NODE_CONFIGS = {
    "node1": {"host": "127.0.0.1", "port": 8001},
    "node2": {"host": "127.0.0.1", "port": 8002},
    "node3": {"host": "127.0.0.1", "port": 8003},
}

async def main():
    nodes = []
    for node_id, config in NODE_CONFIGS.items():
        peers = {p_id: p_config for p_id, p_config in NODE_CONFIGS.items() if p_id != node_id}
        node = Node(node_id=node_id, host=config['host'], port=config['port'], peers=peers)
        nodes.append(node)

    # Menjalankan server dan election timer untuk setiap node
    server_tasks = [node.run_server() for node in nodes]
    election_tasks = [node.run_election_timer() for node in nodes] # <-- BARIS BARU
    
    # Simulasi
    async def simulation():
        await asyncio.sleep(5) # Tunggu pemilihan selesai
        
        # Cari tahu siapa leadernya
        leader = None
        while leader is None:
            for node in nodes:
                if node.state == 'leader':
                    leader = node
                    break
            await asyncio.sleep(0.5)

        print(f"\n--- Leader terpilih: {leader.node_id}. Mengirim proposal... ---\n")

        # Kirim sebuah perintah ke endpoint /propose milik leader
        try:
            async with ClientSession() as session:
                url = f"http://{leader.host}:{leader.port}/propose"
                command = {"action": "WRITE", "key": "dunia", "value": "halo"}
                await session.post(url, json={"command": command})
        except Exception as e:
            print(f"Gagal mengirim proposal: {e}")

        await asyncio.sleep(5) # Beri waktu untuk replikasi
        print("\n--- Simulasi Selesai ---\n")

    # Menggabungkan semua task untuk dijalankan bersamaan
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