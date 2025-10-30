import pytest
from aiohttp import web

from src.communication.message_passing import Communicator

# Menandai semua tes di file ini sebagai tes asyncio
pytestmark = pytest.mark.asyncio

async def mock_handler_success(request):
    """Handler tiruan yang selalu merespons dengan sukses."""
    return web.json_response({"status": "ok"})

async def mock_handler_error(request):
    """Handler tiruan yang selalu merespons dengan error server."""
    return web.Response(status=500)

async def test_send_rpc_success(aiohttp_server):
    """
    Menguji kasus di mana send_rpc berhasil dan mendapatkan respons 200.
    """
    app = web.Application()
    app.router.add_post('/', mock_handler_success)
    server = await aiohttp_server(app)

    communicator = Communicator()
    url = str(server.make_url('/'))
    response = await communicator.send_rpc(url, {"data": "test"})

    assert response is not None
    assert response["status"] == "ok"
    await communicator.close()

async def test_send_rpc_connection_error():
    """
    Menguji kasus di mana koneksi ke server gagal (misalnya, server tidak ada).
    """
    communicator = Communicator()
    # URL yang tidak valid dan tidak akan bisa dijangkau
    url = "http://localhost:9999/nonexistent"
    response = await communicator.send_rpc(url, {"data": "test"}, timeout=0.1)

    assert response is None
    await communicator.close()