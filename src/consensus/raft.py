import asyncio
import random
import time
import redis
import json
from aiohttp import web, ClientSession

class RaftNode:
    def __init__(self, node_id: str, host: str, port: int, peers: dict, redis_host: str = 'localhost'):
        self.node_id = node_id
        self.host = host
        self.port = port
        self.peers = peers
        self.server = None
        self.state = 'follower'
        self.votes_received = 0
        self.election_timeout = random.uniform(1.5, 3.0)
        self.last_heartbeat_received = time.time()
        self.commit_index = 0
        self.last_applied = 0
        self.next_index = {}
        self.match_index = {}

        # Gunakan redis_host yang diberikan, bukan 'localhost'
        self.redis = redis.Redis(host=redis_host, decode_responses=True)
        
        self._load_state_from_redis()

        print(f"Node {self.node_id} diinisialisasi di {self.host}:{self.port} dengan timeout {self.election_timeout:.2f}s")

    def _load_state_from_redis(self):
        term_key = f"raft:{self.node_id}:current_term"
        voted_for_key = f"raft:{self.node_id}:voted_for"
        log_key = f"raft:{self.node_id}:log"

        term = self.redis.get(term_key)
        voted_for = self.redis.get(voted_for_key)
        log = self.redis.get(log_key)

        if term is not None and voted_for is not None and log is not None:
            self.current_term = int(term)
            self.voted_for = voted_for if voted_for != 'None' else None
            self.log = json.loads(log)
            print(f"[{self.node_id}] State berhasil dimuat dari Redis.")
        else:
            # Inisialisasi state default jika tidak ada di Redis
            self.current_term = 0
            self.voted_for = None
            self.log = [{'term': 0, 'command': None}]
            self._save_state()
            print(f"[{self.node_id}] Tidak ada state di Redis. Inisialisasi state baru.")

    def _save_state(self):
        term_key = f"raft:{self.node_id}:current_term"
        voted_for_key = f"raft:{self.node_id}:voted_for"
        log_key = f"raft:{self.node_id}:log"

        # Simpan state ke Redis
        self.redis.set(term_key, self.current_term)
        self.redis.set(voted_for_key, str(self.voted_for))
        self.redis.set(log_key, json.dumps(self.log))


    async def run_election_timer(self):

        while True:
            await asyncio.sleep(0.1) 
            time_since_last_heartbeat = time.time() - self.last_heartbeat_received
            
            if self.state == 'follower' and time_since_last_heartbeat > self.election_timeout:
                print(f"[{self.node_id}] Timeout! Tidak ada heartbeat. Memulai pemilihan...")
                await self.start_election()

    async def start_election(self):
        self.state = 'candidate'
        self.current_term += 1
        self.voted_for = self.node_id
        self._save_state() 
        self.votes_received = 1  
        self.last_heartbeat_received = time.time()

        print(f"[{self.node_id}] Status -> Candidate. Memulai pemilihan untuk term {self.current_term}.")

        tasks = []
        for peer_id in self.peers:
            task = asyncio.create_task(self.send_vote_request(peer_id))
            tasks.append(task)
        
        responses = await asyncio.gather(*tasks)

        for response in responses:
            if response and response['vote_granted']:
                self.votes_received += 1
        
        print(f"[{self.node_id}] Pemilihan selesai untuk term {self.current_term}. Menerima {self.votes_received} suara.")

        majority = (len(self.peers) + 1) // 2 + 1
        if self.state == 'candidate' and self.votes_received >= majority:
            await self.become_leader()
        else:
            self.state = 'follower'

    async def send_vote_request(self, peer_id):

        peer_info = self.peers[peer_id]
        url = f"http://{peer_info['host']}:{peer_info['port']}/request_vote"
        
        request_body = {
            "term": self.current_term,
            "candidate_id": self.node_id
        }

        async with ClientSession() as session:
            try:
                async with session.post(url, json=request_body, timeout=0.5) as response:
                    if response.status == 200:
                        return await response.json()
            except Exception as e:
                print(f"[{self.node_id}] Gagal mengirim RequestVote ke {peer_id}: {e}")
                return None

    async def handle_request_vote(self, request):

        try:
            candidate_data = await request.json()
            candidate_id = candidate_data['candidate_id']
            candidate_term = candidate_data['term']
            
            # Aturan 1: Jika term kandidat lebih kecil dari term kita, tolak.
            if candidate_term < self.current_term:
                print(f"[{self.node_id}] Menolak vote untuk {candidate_id}: term-nya ({candidate_term}) lebih rendah dari term saya ({self.current_term}).")
                return web.json_response({"term": self.current_term, "vote_granted": False})

            # Aturan 2: Jika term kandidat lebih tinggi, kita update term kita dan menjadi follower.
            if candidate_term > self.current_term:
                self.current_term = candidate_term
                self.state = 'follower'
                self.voted_for = None
                self._save_state() # Simpan state setelah update

            # Aturan 3: Berikan suara jika kita belum memilih atau sudah memilih kandidat yang sama.
            if self.voted_for is None or self.voted_for == candidate_id:
                self.voted_for = candidate_id
                self._save_state() # Simpan state setelah memberikan vote
                self.last_heartbeat_received = time.time() 
                print(f"[{self.node_id}] Memberikan vote untuk {candidate_id} pada term {self.current_term}.")
                return web.json_response({"term": self.current_term, "vote_granted": True})
            else:
                print(f"[{self.node_id}] Menolak vote untuk {candidate_id}: sudah memilih {self.voted_for} di term {self.current_term}.")
                return web.json_response({"term": self.current_term, "vote_granted": False})
        
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_append_entries(self, request):
        try:
            data = await request.json()
            leader_term = data['term']
            leader_id = data['leader_id']
            prev_log_index = data['prev_log_index']
            prev_log_term = data['prev_log_term']
            entries = data['entries']
            leader_commit = data['leader_commit']

            # Aturan 1: Tolak jika term leader lebih rendah
            if leader_term < self.current_term:
                return web.json_response({"term": self.current_term, "success": False})

            self.last_heartbeat_received = time.time()
            if self.state != 'follower':
                self.state = 'follower'

            # Aturan 2: Jika log tidak punya entri di prev_log_index, atau term-nya tidak cocok, tolak.
            if len(self.log) <= prev_log_index or self.log[prev_log_index]['term'] != prev_log_term:
                return web.json_response({"term": self.current_term, "success": False})

            # Aturan 3: Jika entri yang ada konflik dengan yang baru, hapus entri yang ada dan semua setelahnya
            self.log = self.log[:prev_log_index + 1]
            self.log.extend(entries)
            self._save_state() # Simpan log yang sudah diupdate
            
            if entries:
                print(f"[{self.node_id}] Berhasil append log dari Leader. Log saya sekarang: {self.log}")

            # Aturan 5: Update commit_index
            if leader_commit > self.commit_index:
                self.commit_index = min(leader_commit, len(self.log) - 1)
                await self.apply_log_to_sm()
            
            return web.json_response({"term": self.current_term, "success": True})
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_message(self, request):

        try:
            data = await request.json()
            print(f"[{self.node_id}] Menerima pesan: {data}")
            
            # Mengirim response balik bahwa pesan diterima
            return web.json_response({"status": "message received"}, status=200)
        except Exception as e:
            print(f"[{self.node_id}] Error saat menangani pesan: {e}")
            return web.json_response({"status": "error", "message": str(e)}, status=500)

    def _setup_app(self):
        self.app = web.Application()
        self.app.router.add_post('/request_vote', self.handle_request_vote)
        self.app.router.add_post('/append_entries', self.handle_append_entries)

    async def run_server(self):
        # Setup aplikasi dasar
        self._setup_app()

        # Mulai server dan jalankan selamanya
        await self.start_server_after_setup()

    async def start_server_after_setup(self):
        runner = web.AppRunner(self.app)
        await runner.setup()
        self.server = web.TCPSite(runner, self.host, self.port)
        
        print(f"[{self.node_id}] Server mulai berjalan di http://{self.host}:{self.port}")
        await self.server.start()
        
        while True:
            await asyncio.sleep(3600)
    
    async def apply_log_to_sm(self):

        pass 

    async def send_message(self, target_node_id: str, message: dict):

        if target_node_id not in self.peers:
            print(f"[{self.node_id}] Error: Target node '{target_node_id}' tidak ditemukan di daftar peers.")
            return

        peer_info = self.peers[target_node_id]
        target_host = peer_info['host']
        target_port = peer_info['port']
        url = f"http://{target_host}:{target_port}/message"

        print(f"[{self.node_id}] Mengirim pesan ke {target_node_id} di {url}: {message}")

        # Menggunakan aiohttp.ClientSession untuk mengirim request HTTP
        async with ClientSession() as session:
            try:
                async with session.post(url, json=message) as response:
                    if response.status == 200:
                        # Pesan berhasil dikirim dan diterima
                        response_json = await response.json()
                        print(f"[{self.node_id}] Response dari {target_node_id}: {response_json}")
                    else:
                        # Terjadi error di sisi penerima
                        print(f"[{self.node_id}] Gagal mengirim pesan ke {target_node_id}. Status: {response.status}")
            except Exception as e:
                # Terjadi error koneksi
                print(f"[{self.node_id}] Gagal terhubung ke {target_node_id} di {url}. Error: {e}")

    async def become_leader(self):
        self.state = 'leader'
        
        last_log_index = len(self.log) - 1
        self.next_index = {peer_id: last_log_index + 1 for peer_id in self.peers}
        self.match_index = {peer_id: 0 for peer_id in self.peers}
        
        print(f"\n👑👑👑 [{self.node_id}] MENJADI LEADER UNTUK TERM {self.current_term} 👑👑👑\n")
        
        asyncio.create_task(self.send_append_entries())

    async def send_append_entries(self):
        while self.state == 'leader':
            # Kirim RPC ke setiap peer secara bersamaan
            tasks = [self.replicate_log_to_peer(peer_id) for peer_id in self.peers]
            if tasks:
                await asyncio.gather(*tasks)
            
            await self.update_commit_index()
            await self.apply_log_to_sm()
            
            await asyncio.sleep(0.5) 

    async def replicate_log_to_peer(self, peer_id: str):
        peer_info = self.peers[peer_id]
        url = f"http://{peer_info['host']}:{peer_info['port']}/append_entries"
        
        # Tentukan entri yang akan dikirim berdasarkan next_index
        next_idx = self.next_index[peer_id]
        prev_log_index = next_idx - 1
        prev_log_term = self.log[prev_log_index]['term']
        entries_to_send = self.log[next_idx:]
        
        request_body = {
            "term": self.current_term,
            "leader_id": self.node_id,
            "prev_log_index": prev_log_index,
            "prev_log_term": prev_log_term,
            "entries": entries_to_send,
            "leader_commit": self.commit_index
        }

        async with ClientSession() as session:
            try:
                async with session.post(url, json=request_body, timeout=0.25) as response:
                    if response.status == 200:
                        data = await response.json()
                        # Proses response dari follower
                        if data['success']:
                            # Jika berhasil, update next_index dan match_index
                            self.next_index[peer_id] = len(self.log)
                            self.match_index[peer_id] = len(self.log) - 1
                        else:
                            self.next_index[peer_id] -= 1
            except Exception:
                pass # Gagal menghubungi peer

    async def update_commit_index(self):
            majority = (len(self.peers) + 1) // 2 + 1
            
            # Cari indeks tertinggi yang sudah direplikasi di mayoritas node
            for N in range(len(self.log) - 1, self.commit_index, -1):
                if self.log[N]['term'] == self.current_term:
                    count = 1 
                    for peer_id in self.peers:
                        if self.match_index.get(peer_id, 0) >= N:
                            count += 1
                    
                    if count >= majority:
                        self.commit_index = N
                        print(f"[{self.node_id} - Leader] Memajukan commit_index ke {self.commit_index}")
                        break   