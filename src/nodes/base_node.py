import asyncio
from aiohttp import web
from aiohttp_swagger3 import SwaggerDocs, SwaggerUi
from ..consensus.raft import RaftNode

class Node(RaftNode):
    def __init__(self, node_id: str, host: str, port: int, peers: dict, redis_host: str = 'localhost'):
        super().__init__(node_id, host, port, peers, redis_host)
        self.app = None

    def _setup_app(self):
        """Setup aiohttp application and basic Swagger documentation."""
        super()._setup_app()
        
        # Initialize Swagger documentation
        self.swagger = SwaggerDocs(
            self.app,
            title=f"API for {self.__class__.__name__}",
            version="1.0.0",
        )

    async def run_server(self):
        """
        Fungsi utama untuk menjalankan server node.
        Ini akan memulai election timer dan server HTTP.
        """
        self._setup_app()
        server_task = asyncio.create_task(super().run_server())
        election_timer_task = asyncio.create_task(self.run_election_timer())
        await asyncio.gather(server_task, election_timer_task)