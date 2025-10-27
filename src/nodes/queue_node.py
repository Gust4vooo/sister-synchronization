# File: src/nodes/queue_node.py

import asyncio
import os
import json
import uhashring
import aiofiles
import uuid
from aiohttp import web
from collections import deque

class QueueRouter:
    def __init__(self, nodes: dict):
        self.nodes = nodes
        
        ring_nodes = {node_id: 1 for node_id in self.nodes.keys()}
        
        self.ring = uhashring.HashRing(nodes=ring_nodes)

    def get_node_for_message(self, message_key: str) -> str:
        return self.ring.get_node(message_key)

    def get_node_address(self, node_id: str) -> str:
        return self.nodes.get(node_id)

class QueueNode:
    def __init__(self, node_id: str, host: str, port: int):
        self.node_id = node_id
        self.host = host
        self.port = port
        self.queue = deque()
        self.app = web.Application()
        
        # Lacak pesan yang sedang diproses 
        self.in_flight_messages = {} 
        
        # Logika untuk persistensi
        log_dir = "queue_logs"
        os.makedirs(log_dir, exist_ok=True)
        self.log_file = os.path.join(log_dir, f"{self.node_id}.log")
        
        self._setup_routes()
        asyncio.create_task(self._recover_from_log())

    async def _recover_from_log(self):
        self.in_flight_messages.clear()
        self.queue.clear()
        try:
            async with aiofiles.open(self.log_file, mode='r') as f:
                async for line in f:
                    if line.strip():
                        self.queue.append(json.loads(line))
            print(f"[{self.node_id}] Pulih dari log. {len(self.queue)} pesan dimuat ke antrian utama.")
        except FileNotFoundError:
            print(f"[{self.node_id}] File log tidak ditemukan, memulai dengan antrian kosong.")

    def _setup_routes(self):
        self.app.router.add_post('/produce', self.handle_produce)
        self.app.router.add_get('/consume', self.handle_consume)
        self.app.router.add_post('/ack', self.handle_ack)

    async def handle_produce(self, request):
        try:
            data = await request.json()
            data['msg_id'] = str(uuid.uuid4()) 
            
            async with aiofiles.open(self.log_file, mode='a') as f:
                await f.write(json.dumps(data) + '\n')

            self.queue.append(data)
            print(f"[{self.node_id}] Menerima & menyimpan pesan: '{data.get('message', '')}' (ID: {data['msg_id']})")
            return web.json_response({"status": "message received and persisted"})
        except Exception as e:
            return web.json_response({"error": str(e)}, status=400)

    async def handle_consume(self, request):
        if not self.queue:
            return web.json_response({"message": None, "status": "queue empty"}, status=204)
        
        message_data = self.queue.popleft()
        msg_id = message_data['msg_id']
        
        self.in_flight_messages[msg_id] = message_data
        
        print(f"[{self.node_id}] Mengirim pesan: '{message_data.get('message', '')}'. Pesan in-flight: {len(self.in_flight_messages)}")
        return web.json_response(message_data)

    async def handle_ack(self, request):
        try:
            data = await request.json()
            msg_id = data['msg_id']
            
            if msg_id in self.in_flight_messages:
                del self.in_flight_messages[msg_id]
                await self._rewrite_log()
                print(f"[{self.node_id}] ACK diterima untuk {msg_id}. Pesan dihapus permanen.")
                return web.json_response({"status": "ack received"})
            else:
                return web.json_response({"status": "message id not found or already acked"}, status=404)
        except Exception as e:
            return web.json_response({"error": str(e)}, status=400)

    async def _rewrite_log(self):
        active_messages = list(self.queue) + list(self.in_flight_messages.values())
        
        async with aiofiles.open(self.log_file, mode='w') as f:
            for msg in active_messages:
                await f.write(json.dumps(msg) + '\n')

    async def run(self):
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, self.host, self.port)
        print(f"[{self.node_id}] QueueNode berjalan di http://{self.host}:{self.port}")
        await site.start()
        while True:
            await asyncio.sleep(3600)