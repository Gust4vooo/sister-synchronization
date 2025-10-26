import asyncio
from .base_node import Node 
from aiohttp import web, ClientSession

class LockManagerNode(Node):
    def __init__(self, node_id: str, host: str, port: int, peers: dict):
        super().__init__(node_id, host, port, peers)
        
        self.state_machine = {} 
        self.state_machine_lock = asyncio.Lock()
        self.pending_requests = {} 
        self.pending_requests_lock = asyncio.Lock()
    
    async def run_server(self):
        await super().run_server(setup_only=True) 
        
        self.app.router.add_post('/lock', self.handle_lock_request)
        print(f"[{self.node_id}] Endpoint /lock ditambahkan.")
        
        await self.start_server_after_setup()

    async def handle_lock_request(self, request):
        if self.state != 'leader':
            return web.json_response({"error": "Bukan leader", "status": "fail"}, status=400)

        try:
            data = await request.json()
            action = data['action']
            lock_name = data['lock_name']
            client_id = data['client_id']
            
            if action == 'RELEASE':
                command = {"action": "RELEASE", "lock_name": lock_name, "client_id": client_id}
                new_entry = {'term': self.current_term, 'command': command}
                self.log.append(new_entry)
                print(f"[{self.node_id} - Leader] Mengajukan proposal RELEASE: {command}")
                return web.json_response({"status": "release proposal accepted"}, status=202)

            elif action == 'ACQUIRE':
                async with self.state_machine_lock:
                    is_locked = self.state_machine.get(lock_name) is not None

                if is_locked:
                    print(f"[{self.node_id}] Lock '{lock_name}' sibuk. Permintaan dari {client_id} menunggu...")
                    event = asyncio.Event()
                    async with self.pending_requests_lock:
                        if lock_name not in self.pending_requests:
                            self.pending_requests[lock_name] = []
                        self.pending_requests[lock_name].append(event)
                    
                    try:
                        await asyncio.wait_for(event.wait(), timeout=5.0)
                    except asyncio.TimeoutError:
                        print(f"[{self.node_id}] Permintaan dari {client_id} untuk '{lock_name}' timeout.")
                        # Hapus event dari antrian jika timeout
                        async with self.pending_requests_lock:
                            if lock_name in self.pending_requests and event in self.pending_requests[lock_name]:
                                self.pending_requests[lock_name].remove(event)
                        return web.json_response({"error": "Request timed out", "status": "timeout"}, status=408)

                # Jika lock tersedia (atau setelah berhasil menunggu), ajukan proposal
                command = {"action": "ACQUIRE", "lock_name": lock_name, "client_id": client_id}
                new_entry = {'term': self.current_term, 'command': command}
                self.log.append(new_entry)
                print(f"[{self.node_id} - Leader] Mengajukan proposal ACQUIRE: {command}")
                return web.json_response({"status": "acquire proposal accepted"}, status=202)
            
            else:
                return web.json_response({"error": f"Aksi tidak dikenal: {action}"}, status=400)

        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)
        
    async def apply_log_to_sm(self):
        async with self.state_machine_lock:
            while self.last_applied < self.commit_index:
                self.last_applied += 1
                entry = self.log[self.last_applied]
                command = entry['command']

                print(f"[{self.node_id}] Menerapkan log[{self.last_applied}]: {command}")

                lock_name = command['lock_name']
                action = command['action']

                # Exclusive lock
                if action == 'ACQUIRE':
                    # Hanya acquire jika lock belum ada atau sudah dilepas (None)
                    if self.state_machine.get(lock_name) is None:
                        self.state_machine[lock_name] = command['client_id']
                        print(f"[{self.node_id}] Lock '{lock_name}' dipegang oleh {command['client_id']}.")
                    else:
                        print(f"[{self.node_id}] Gagal acquire '{lock_name}', sudah dipegang oleh {self.state_machine.get(lock_name)}.")

                elif action == 'RELEASE':
                    # Hanya bisa direlease oleh pemiliknya
                    if self.state_machine.get(lock_name) == command['client_id']:
                        self.state_machine[lock_name] = None
                        print(f"[{self.node_id}] Lock '{lock_name}' dilepaskan oleh {command['client_id']}.")

                        if self.state == 'leader':
                            asyncio.create_task(self.notify_waiters(lock_name))
                    else:
                        print(f"[{self.node_id}] Gagal release '{lock_name}', bukan pemiliknya.")
                        
    async def notify_waiters(self, lock_name: str):
        async with self.pending_requests_lock:
            if lock_name in self.pending_requests and self.pending_requests[lock_name]:
                next_waiter_event = self.pending_requests[lock_name].pop(0)
                next_waiter_event.set()
                print(f"[{self.node_id}] Memberi sinyal ke waiter berikutnya untuk lock '{lock_name}'.")