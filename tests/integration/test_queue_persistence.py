import asyncio
import aiohttp
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from src.nodes.queue_node import QueueNode, QueueRouter

NODE_CONFIGS = {
    "q_node1": {"host": "127.0.0.1", "port": 9001},
    "q_node2": {"host": "127.0.0.1", "port": 9002},
    "q_node3": {"host": "127.0.0.1", "port": 9003},
}

async def run_nodes():
    tasks = [
        asyncio.create_task(
            QueueNode(node_id=node_id, host=config['host'], port=config['port']).run()
        )
        for node_id, config in NODE_CONFIGS.items()
    ]
    return tasks

async def main():
    log_dir = "queue_logs"
    if os.path.exists(log_dir):
        for f in os.listdir(log_dir):
            os.remove(os.path.join(log_dir, f))

    # FASE 1: Producer Mengirim Pesan & "Crash"
    print("\n--- FASE 1: Menjalankan node, producer mengirim pesan ---")
    node_tasks = await run_nodes()
    await asyncio.sleep(2)

    router_nodes = {node_id: f"{cfg['host']}:{cfg['port']}" for node_id, cfg in NODE_CONFIGS.items()}
    router = QueueRouter(nodes=router_nodes)
    
    messages = {"user:101": "Profil A", "order:55": "Pesanan B", "email:992": "Email C"}
    async with aiohttp.ClientSession() as session:
        for key, content in messages.items():
            target_node_id = router.get_node_for_message(key)
            node_address = router.get_node_address(target_node_id)
            url = f"http://{node_address}/produce"
            print(f"Pesan '{key}' -> {target_node_id}")
            await session.post(url, json={"message": content, "key": key})
    
    print("\n--- MENUTUP SEMUA NODE (SIMULASI CRASH) ---\n")
    for task in node_tasks:
        task.cancel()
    await asyncio.sleep(2)

    # FASE 2: Restart Node & Consumer Mengambil Pesan + ACK 
    print("--- FASE 2: Me-restart node & consumer mengambil pesan ---")
    node_tasks_restarted = await run_nodes()
    await asyncio.sleep(2)

    async with aiohttp.ClientSession() as session:
        print("\n--- Consumer mengambil pesan dan mengirim ACK ---")
        total_consumed = 0
        while total_consumed < len(messages):
            for node_id, config in NODE_CONFIGS.items():
                consume_url = f"http://{config['host']}:{config['port']}/consume"
                resp = await session.get(consume_url)
                
                if resp.status == 204:
                    continue
                
                data = await resp.json()
                msg_id = data['msg_id']
                print(f"Consumer mendapat '{data['message']}' dari {node_id}. Memproses...")
                
                await asyncio.sleep(0.5)
                
                ack_url = f"http://{config['host']}:{config['port']}/ack"
                await session.post(ack_url, json={"msg_id": msg_id})
                print(f"--> ACK dikirim untuk {msg_id}")
                total_consumed += 1

    print("\n--- Verifikasi: Semua file log seharusnya kosong setelah ACK ---")
    for node_id in NODE_CONFIGS:
        log_file = f"queue_logs/{node_id}.log"
        if os.path.exists(log_file):
            with open(log_file, 'r') as f:
                content = f.read()
                if not content.strip():
                    print(f"File log {log_file} kosong. (BENAR)")
                else:
                    print(f"File log {log_file} TIDAK kosong. (SALAH)")

    for task in node_tasks_restarted:
        task.cancel()

if __name__ == "__main__":
    asyncio.run(main())