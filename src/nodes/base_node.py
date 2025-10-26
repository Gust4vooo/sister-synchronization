import asyncio
from aiohttp import web, ClientSession

class Node:

    def __init__(self, node_id: str, host: str, port: int, peers: dict):
        self.node_id = node_id
        self.host = host
        self.port = port
        self.peers = peers
        self.server = None 

        print(f"Node {self.node_id} diinisialisasi di {self.host}:{self.port}")

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
        # Menambahkan route: setiap request POST ke /message akan ditangani oleh self.handle_message
        app.router.add_post('/message', self.handle_message)
        
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
                # Terjadi error koneksi (misalnya, node tujuan mati)
                print(f"[{self.node_id}] Gagal terhubung ke {target_node_id} di {url}. Error: {e}")