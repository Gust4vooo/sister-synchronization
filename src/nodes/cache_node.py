import asyncio
import aiohttp
import redis.asyncio as redis
from aiohttp import web
from collections import OrderedDict
from enum import Enum, auto
from .base_node import Node 

class MESIState(Enum):
    MODIFIED = auto()
    EXCLUSIVE = auto()
    SHARED = auto()
    INVALID = auto()

class CacheNode(Node): 
    def __init__(self, node_id: str, host: str, port: int, peers: dict, redis_host: str = 'localhost', max_cache_size: int = 100):
        super().__init__(node_id, host, port, peers, redis_host=redis_host)

        self.redis = redis.Redis(host=redis_host, decode_responses=True)

        self.cache = OrderedDict()
        self.max_cache_size = max_cache_size
        self.metrics = {
            "cache_hits": 0,
            "cache_misses": 0,
            "writes_received": 0,
            "invalidations_sent": 0,
            "invalidations_received": 0
        }

    def _setup_app(self):
        super()._setup_app() 
        self.app.router.add_get('/read/{key}', self.handle_read)
        self.app.router.add_post('/write', self.handle_write)
        self.app.router.add_post('/invalidate', self.handle_invalidate)
        self.app.router.add_get('/metrics', self.handle_metrics)
        print(f"[{self.node_id}] Cache-specific endpoints added.")

    async def handle_read(self, request):
        key = request.match_info['key']
        
        if key in self.cache and self.cache[key]['state'] != MESIState.INVALID:
            self.metrics["cache_hits"] += 1
            cache_entry = self.cache[key]
            self.cache.move_to_end(key)
            print(f"[{self.node_id}] Cache HIT for '{key}'. State: {cache_entry['state'].name}, Value: '{cache_entry['value']}'")
            return web.json_response({"key": key, "value": cache_entry['value'], "source": "cache"})
        
        self.metrics["cache_misses"] += 1
        print(f"[{self.node_id}] Cache MISS for '{key}'. Fetching from Redis...")
        value = await self.redis.get(key)
        if value is None:
            return web.json_response({"error": "Key not found in Redis"}, status=404)
            
        self.cache[key] = {'state': MESIState.EXCLUSIVE, 'value': value}
        if len(self.cache) > self.max_cache_size:
            self.cache.popitem(last=False)

        return web.json_response({"key": key, "value": value, "source": "redis"})

    async def handle_write(self, request):
        data = await request.json()
        key, value = data['key'], data['value']
        
        self.metrics["writes_received"] += 1
        
        await self.redis.set(key, value)
        self.cache[key] = {'state': MESIState.MODIFIED, 'value': value}
        self.cache.move_to_end(key)
        if len(self.cache) > self.max_cache_size:
            self.cache.popitem(last=False)
        
        await self.broadcast_invalidation(key)
        return web.json_response({"status": "write successful"})

    async def handle_invalidate(self, request):
        data = await request.json()
        key = data['key']
        
        if key in self.cache:
            self.metrics["invalidations_received"] += 1
            self.cache[key]['state'] = MESIState.INVALID
            print(f"[{self.node_id}] CACHE INVALIDATED for '{key}' by peer.")
        
        return web.json_response({"status": "invalidation acknowledged"})

    async def handle_metrics(self, request):
        return web.json_response(self.metrics)

    async def broadcast_invalidation(self, key: str):
        self.metrics["invalidations_sent"] += len(self.peers)
        async with aiohttp.ClientSession() as session:
            tasks = []
            for peer_id, peer_info in self.peers.items():
                url = f"http://{peer_info['host']}:{peer_info['port']}/invalidate"
                task = asyncio.create_task(session.post(url, json={"key": key}))
                tasks.append(task)
            await asyncio.gather(*tasks, return_exceptions=True)