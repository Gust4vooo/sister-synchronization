import asyncio
import random
import time
from aiohttp import web, ClientSession

class Node:
    def __init__(self, node_id: str, host: str, port: int, peers: dict):
        # Atribut dari tahap sebelumnya
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
                # Gagal menghubungi peer (mungkin down), anggap tidak ada suara
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
        print(f"\n👑👑👑 [{self.node_id}] MENJADI LEADER UNTUK TERM {self.current_term} 👑👑👑\n")
        
        asyncio.create_task(self.send_heartbeats())

    async def send_heartbeats(self):

        while self.state == 'leader':
            print(f"[{self.node_id} - Leader] Mengirim heartbeat...")

            await asyncio.sleep(0.5) 