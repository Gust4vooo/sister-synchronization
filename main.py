# main.py

import asyncio
from src.nodes.base_node import Node

# Konfgurasi sistem 
NODE_CONFIGS = {
    "node1": {"host": "127.0.0.1", "port": 8001},
    "node2": {"host": "127.0.0.1", "port": 8002},
    "node3": {"host": "127.0.0.1", "port": 8003},
}

async def main():
    nodes = []
    
    # Membuat instance Node untuk setiap konfigurasi
    for node_id, config in NODE_CONFIGS.items():
        peers = {p_id: p_config for p_id, p_config in NODE_CONFIGS.items() if p_id != node_id}
        
        node = Node(node_id=node_id, host=config['host'], port=config['port'], peers=peers)
        nodes.append(node)

    # Menjalankan server untuk setiap node secara bersamaan
    server_tasks = [node.run_server() for node in nodes]
    
    # Pengiriman pesan
    async def simulation():
        await asyncio.sleep(5)
        print("\n--- Memulai Simulasi Pengiriman Pesan ---\n")
        
        # Node 1 akan mengirim pesan ke Node 2 dan Node 3
        node1 = nodes[0]
        
        await node1.send_message("node2", {"from": "node1", "content": "Halo Node 2!"})
        await asyncio.sleep(1) 
        await node1.send_message("node3", {"from": "node1", "content": "Apa kabar Node 3?"})
        
        print("\n--- Simulasi Selesai ---\n")

    # Menjalankan simulasi bersamaan dengan server
    await asyncio.gather(
        *server_tasks,
        simulation()
    )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nMenutup semua node...")