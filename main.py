import os
import asyncio
import json
import logging
from src.nodes.lock_manager import LockManagerNode
from src.nodes.queue_node import QueueNode
from src.nodes.cache_node import CacheNode

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - [%(name)s] %(message)s')
logger = logging.getLogger(__name__)

NODE_CLASSES = {
    "lock_manager": LockManagerNode,
    "queue_node": QueueNode,
    "cache_node": CacheNode,
}

async def main():
    node_type = os.getenv("NODE_TYPE", "lock_manager").lower()
    node_id = os.getenv("NODE_ID")
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", 8000))
    redis_host = os.getenv("REDIS_HOST", "localhost")
    
    peers_str = os.getenv("PEERS", "{}")
    try:
        peers = json.loads(peers_str)
    except json.JSONDecodeError:
        logger.error(f"Could not decode PEERS JSON string: {peers_str}")
        peers = {}

    if not node_id:
        logger.error("FATAL: NODE_ID environment variable is not set. Exiting.")
        return

    NodeClass = NODE_CLASSES.get(node_type)
    if not NodeClass:
        logger.error(f"FATAL: Invalid NODE_TYPE '{node_type}'. Must be one of {list(NODE_CLASSES.keys())}. Exiting.")
        return

    logger.info(f"Initializing node '{node_id}' of type '{node_type}'")
    logger.info(f"Configuration: host={host}, port={port}, peers={peers}, redis_host={redis_host}")
    
    node = NodeClass(
        node_id=node_id,
        host=host,
        port=port,
        peers=peers,
        redis_host=redis_host
    )

    try:
        server_task = asyncio.create_task(node.run_server())
        election_task = asyncio.create_task(node.run_election_timer())
        logger.info(f"Node '{node_id}' started successfully and is now running.")
        await asyncio.gather(server_task, election_task)
    except Exception as e:
        logger.error(f"An error occurred while running node '{node_id}': {e}", exc_info=True)
    finally:
        logger.info(f"Node '{node_id}' is shutting down.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutdown signal received. Closing application.")