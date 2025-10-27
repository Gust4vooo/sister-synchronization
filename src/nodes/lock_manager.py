import asyncio
from .base_node import Node 
from aiohttp import web, ClientSession

class LockManagerNode(Node):
    def __init__(self, node_id: str, host: str, port: int, peers: dict, redis_host: str = 'localhost'):
        super().__init__(node_id, host, port, peers, redis_host=redis_host)
        
        self.state_machine = {} 
        self.state_machine_lock = asyncio.Lock()
        self.pending_requests = {} 
        self.pending_requests_lock = asyncio.Lock()
        self.waits_for_graph = {}
    
    def _detect_cycle(self, start_node: str) -> bool:

        visiting = set() 
        
        def dfs(node):
            visiting.add(node)

            for neighbor in self.waits_for_graph.get(node, []):
                if neighbor in visiting:
                    print(f"[{self.node_id}] DETEKSI DEADLOCK: Siklus ditemukan melibatkan {node} dan {neighbor}")
                    return True
                
                if neighbor in self.waits_for_graph:
                    if dfs(neighbor):
                        return True
            
            visiting.remove(node)
            return False

        return dfs(start_node)

    def _setup_app(self):
        super()._setup_app()
        self.app.router.add_post('/lock', self.handle_lock_request)
        print(f"[{self.node_id}] Endpoint /lock ditambahkan.")

    async def handle_lock_request(self, request):
        if self.state != 'leader':
            return web.json_response({"error": "Bukan leader", "status": "fail"}, status=400)

        try:
            data = await request.json()
            action = data.get('action')
            lock_name = data.get('lock_name')
            client_id = data.get('client_id')

            if not all([action, lock_name, client_id]):
                return web.json_response({"error": "action, lock_name, and client_id are required"}, status=400)

            if action == 'RELEASE':
                command = {"action": "RELEASE", "lock_name": lock_name, "client_id": client_id}
                new_entry = {'term': self.current_term, 'command': command}
                self.log.append(new_entry)
                print(f"[{self.node_id} - Leader] Mengajukan proposal RELEASE: {command}")
                return web.json_response({"status": "release proposal accepted"}, status=202)

            elif action in ['ACQUIRE_SHARED', 'ACQUIRE_EXCLUSIVE']:
                should_wait = False
                lock_owners = []
                async with self.state_machine_lock:
                    lock_info = self.state_machine.get(lock_name)
                    if lock_info:
                        if lock_info['type'] == 'EXCLUSIVE':
                            should_wait = True
                            lock_owners = lock_info['owners']
                        elif lock_info['type'] == 'SHARED' and action == 'ACQUIRE_EXCLUSIVE':
                            should_wait = True
                            lock_owners = lock_info['owners']
                
                if should_wait:
                    self.waits_for_graph[client_id] = lock_owners
                    print(f"[{self.node_id}] Graf dependensi diperbarui: {self.waits_for_graph}")

                    if self._detect_cycle(client_id):
                        del self.waits_for_graph[client_id]
                        print(f"[{self.node_id}] Permintaan dari {client_id} dibatalkan untuk mencegah deadlock.")
                        return web.json_response({"error": "Deadlock detected", "status": "deadlock"}, status=423)

                    print(f"[{self.node_id}] Lock '{lock_name}' sibuk. Permintaan {action} dari {client_id} menunggu...")
                    event = asyncio.Event()
                    async with self.pending_requests_lock:
                        self.pending_requests.setdefault(lock_name, []).append(event)
                    
                    try:
                        await asyncio.wait_for(event.wait(), timeout=20.0) 
                        print(f"[{self.node_id}] Selesai menunggu untuk '{lock_name}'. Mengajukan proposal untuk {client_id}.")
                    except asyncio.TimeoutError:
                        print(f"[{self.node_id}] Permintaan dari {client_id} untuk '{lock_name}' timeout.")
                        async with self.pending_requests_lock:
                            if lock_name in self.pending_requests and event in self.pending_requests[lock_name]:
                                self.pending_requests[lock_name].remove(event)
                        if client_id in self.waits_for_graph:
                            del self.waits_for_graph[client_id]
                        return web.json_response({"error": "Request timed out while waiting for lock", "status": "timeout"}, status=408)

                command = {"action": action, "lock_name": lock_name, "client_id": client_id}
                new_entry = {'term': self.current_term, 'command': command}
                self.log.append(new_entry)
                print(f"[{self.node_id} - Leader] Mengajukan proposal {action}: {command}")
                return web.json_response({"status": f"{action} proposal accepted"}, status=202)
            
            else:
                return web.json_response({"error": f"Aksi tidak dikenal: {action}"}, status=400)

        except Exception as e:
            print(f"Error in handle_lock_request: {e}")
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
                client_id = command['client_id']

                lock = self.state_machine.get(lock_name)

                is_granted = False
                if action == 'ACQUIRE_SHARED':
                    if lock is None:
                        self.state_machine[lock_name] = {"type": "SHARED", "owners": [client_id]}
                        print(f"[{self.node_id}] Lock '{lock_name}' (SHARED) dipegang oleh {client_id}.")
                        is_granted = True
                    elif lock['type'] == 'SHARED':
                        if client_id not in lock['owners']:
                            lock['owners'].append(client_id)
                        print(f"[{self.node_id}] Lock '{lock_name}' (SHARED) sekarang juga dipegang oleh {client_id}. Owners: {lock['owners']}")
                        is_granted = True
                    else:
                        print(f"[{self.node_id}] Gagal ACQUIRE_SHARED '{lock_name}', kunci dipegang secara EXCLUSIVE oleh {lock['owners'][0]}.")

                elif action == 'ACQUIRE_EXCLUSIVE':
                    if lock is None:
                        self.state_machine[lock_name] = {"type": "EXCLUSIVE", "owners": [client_id]}
                        print(f"[{self.node_id}] Lock '{lock_name}' (EXCLUSIVE) dipegang oleh {client_id}.")
                        is_granted = True
                    else:
                        print(f"[{self.node_id}] Gagal ACQUIRE_EXCLUSIVE '{lock_name}', kunci sudah dipegang. Info: {lock}")

                # Jika kunci berhasil didapat, hapus dari graf dependensi
                if is_granted and self.state == 'leader' and client_id in self.waits_for_graph:
                    del self.waits_for_graph[client_id]
                    print(f"[{self.node_id}] Klien {client_id} dapat kunci, dihapus dari graf dependensi.")

                elif action == 'RELEASE':
                    if lock and client_id in lock['owners']:
                        lock['owners'].remove(client_id)
                        print(f"[{self.node_id}] Lock '{lock_name}' dilepaskan oleh {client_id}. Sisa owners: {lock['owners']}")
                        
                        if not lock['owners']:
                            del self.state_machine[lock_name]
                            print(f"[{self.node_id}] Lock '{lock_name}' sepenuhnya dilepaskan.")
                            
                            if self.state == 'leader':
                                asyncio.create_task(self.notify_waiters(lock_name))
                    else:
                        print(f"[{self.node_id}] Gagal RELEASE '{lock_name}', {client_id} bukan pemilik atau kunci tidak ada.")
                        
    async def notify_waiters(self, lock_name: str):
        async with self.pending_requests_lock:
            waiters = self.pending_requests.pop(lock_name, [])
            if waiters:
                print(f"[{self.node_id}] Memberi sinyal ke {len(waiters)} waiter untuk lock '{lock_name}'.")
                for event in waiters:
                    event.set()