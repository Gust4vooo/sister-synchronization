import asyncio
from .message_passing import Communicator

class FailureDetector:

    def __init__(self, node_id: str, peers: dict, communicator: Communicator, check_interval: float = 1.0, failure_threshold: int = 3):

        self.node_id = node_id
        self.peers = peers
        self.communicator = communicator
        self.check_interval = check_interval
        self.failure_threshold = failure_threshold

        self.peer_statuses = {peer_id: 'UP' for peer_id in self.peers}
        # Menghitung kegagalan berturut-turut untuk setiap peer
        self.failure_counters = {peer_id: 0 for peer_id in self.peers}

    async def _run_health_checks(self):
        while True:
            for peer_id, peer_info in self.peers.items():
                url = f"http://{peer_info['host']}:{peer_info['port']}/health"
                
                response = await self.communicator.send_rpc(url, {}, timeout=0.5)

                if response is not None:
                    if self.peer_statuses[peer_id] == 'DOWN':
                        print(f"[FailureDetector] Node {peer_id} kembali ONLINE.")
                    self.failure_counters[peer_id] = 0
                    self.peer_statuses[peer_id] = 'UP'
                else:
                    self.failure_counters[peer_id] += 1
                    if self.failure_counters[peer_id] >= self.failure_threshold and self.peer_statuses[peer_id] == 'UP':
                        self.peer_statuses[peer_id] = 'DOWN'
                        print(f"[FailureDetector] Node {peer_id} dianggap DOWN setelah {self.failure_counters[peer_id]} kegagalan.")
            
            await asyncio.sleep(self.check_interval)

    def start(self):
        asyncio.create_task(self._run_health_checks())

    def get_live_peers(self) -> list:
        return [peer_id for peer_id, status in self.peer_statuses.items() if status == 'UP']