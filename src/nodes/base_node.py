import asyncio
import random
import time
from aiohttp import web, ClientSession

class Node:
    def __init__(self, node_id: str, host: str, port: int, peers: dict):
        self.node_id = node_id
        self.host = host
        self.port = port
        self.peers = peers
        self.server = None
        self.state = 'follower'  
        self.current_term = 0    
        self.voted_for = None    
        self.votes_received = 0
        self.election_timeout = random.uniform(1.5, 3.0) 
        self.last_heartbeat_received = time.time() 
        self.log = [{'term': 0, 'command': None}] 
        self.commit_index = 0
        self.last_applied = 0
        self.next_index = {}
        self.match_index = {}

        print(f"Node {self.node_id} diinisialisasi di {self.host}:{self.port} dengan timeout {self.election_timeout:.2f}s")

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
        self.votes_received = 1  
        self.last_heartbeat_received = time.time()

        print(f"[{self.node_id}] Status -> Candidate. Memulai pemilihan untuk term {self.current_term}.")

        # Kirim RequestVote RPC ke semua peer secara bersamaan
        tasks = []
        for peer_id in self.peers:
            task = asyncio.create_task(self.send_vote_request(peer_id))
            tasks.append(task)
        
        # Tunggu semua response atau timeout
        responses = await asyncio.gather(*tasks)

        # Hitung suara yang diterima
        for response in responses:
            if response and response['vote_granted']:
                self.votes_received += 1
        
        print(f"[{self.node_id}] Pemilihan selesai untuk term {self.current_term}. Menerima {self.votes_received} suara.")

        # Cek apakah memenangkan pemilihan
        majority = (len(self.peers) + 1) // 2 + 1
        if self.state == 'candidate' and self.votes_received >= majority:
            await self.become_leader()
        else:
            # Jika tidak menang, kembali jadi follower dan tunggu pemilihan berikutnya
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
                # Gagal menghubungi peer (mungkin down)
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

            # Aturan 3: Berikan suara jika kita belum memilih atau sudah memilih kandidat yang sama.
            if self.voted_for is None or self.voted_for == candidate_id:
                self.voted_for = candidate_id
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
            
            if entries:
                print(f"[{self.node_id}] Berhasil append log dari Leader. Log saya sekarang: {self.log}")

            # Aturan 5: Update commit_index
            if leader_commit > self.commit_index:
                self.commit_index = min(leader_commit, len(self.log) - 1)
            
            return web.json_response({"term": self.current_term, "success": True})
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_client_proposal(self, request):

        if self.state != 'leader':
            return web.json_response({"error": "Bukan leader"}, status=400)

        try:
            data = await request.json()
            command = data['command']

            # Buat entri log baru
            new_entry = {'term': self.current_term, 'command': command}
            self.log.append(new_entry)

            print(f"[{self.node_id} - Leader] Menerima proposal: {command}. Log baru di indeks {len(self.log) - 1}")

            return web.json_response({"status": "proposal accepted"}, status=200)

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

    async def run_server(self):

        app = web.Application()
        app.router.add_post('/request_vote', self.handle_request_vote)
        app.router.add_post('/append_entries', self.handle_append_entries)
        app.router.add_post('/propose', self.handle_client_proposal)

        runner = web.AppRunner(app)
        await runner.setup()
        self.server = web.TCPSite(runner, self.host, self.port)
        
        print(f"[{self.node_id}] Server mulai berjalan di http://{self.host}:{self.port}")
        await self.server.start()
        
        while True:
            await asyncio.sleep(3600)

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
                    count = 1 # Diri sendiri
                    for peer_id in self.peers:
                        if self.match_index.get(peer_id, 0) >= N:
                            count += 1
                    
                    if count >= majority:
                        self.commit_index = N
                        print(f"[{self.node_id} - Leader] Memajukan commit_index ke {self.commit_index}")
                        break   