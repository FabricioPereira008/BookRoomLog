import io

import httpx
import pytest
import respx
from PIL import Image

from backend.app.core.config import settings
from backend.app.core.net_safety import UnsafeURLError, assert_public_url
from backend.app.services import cover_service


def _image_bytes(size=(200, 300), fmt="PNG"):
    buf = io.BytesIO()
    Image.new("RGB", size, "red").save(buf, format=fmt)
    return buf.getvalue()


def test_upload_valid_image(client):
    r = client.post("/api/v1/uploads/cover", files={"file": ("a.png", _image_bytes(), "image/png")})
    assert r.status_code == 200
    assert (settings.COVERS_DIR / r.json()["filename"]).exists()
    assert client.get(r.json()["url"]).status_code == 200


def test_upload_rejects_bad_extension_fake_and_oversized(client, monkeypatch):
    assert client.post("/api/v1/uploads/cover", files={"file": ("a.txt", b"x", "text/plain")}).status_code == 400
    assert client.post("/api/v1/uploads/cover", files={"file": ("a.png", b"nada", "image/png")}).status_code == 400
    monkeypatch.setattr(settings, "MAX_COVER_BYTES", 10)
    assert client.post("/api/v1/uploads/cover",
                       files={"file": ("a.png", _image_bytes(), "image/png")}).status_code == 413


def test_get_cover_not_found_and_traversal(client):
    assert client.get("/api/v1/uploads/cover/nope.jpg").status_code == 404
    assert client.get("/api/v1/uploads/cover/..%2Fsecret.txt").status_code in (400, 404)


@pytest.mark.parametrize("url", [
    "ftp://example.com/a.png",
    "http://127.0.0.1:8010/",
    "http://localhost/x",
    "http://169.254.169.254/latest/meta-data",
    "http://10.0.0.5/a.png",
])
def test_assert_public_url_blocks(url):
    with pytest.raises(UnsafeURLError):
        assert_public_url(url)


def test_cover_url_blocks_private_and_non_http(client):
    assert client.post("/api/v1/uploads/cover-url", json={"url": "http://127.0.0.1:8010/"}).status_code == 400
    assert client.post("/api/v1/uploads/cover-url", json={"url": "file:///etc/passwd"}).status_code == 400


@pytest.fixture
def public_dns(monkeypatch):
    """Resolve qualquer host para um IP público (os downloads são simulados pelo respx)."""
    import socket
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(None, None, None, None, ("93.184.216.34", 0))])


@respx.mock
def test_cover_url_downloads_and_normalizes(client, public_dns):
    respx.get("https://img.example/capa.jpg").mock(return_value=httpx.Response(200, content=_image_bytes((400, 400))))
    r = client.post("/api/v1/uploads/cover-url", json={"url": "https://img.example/capa.jpg"})
    assert r.status_code == 200
    with Image.open(settings.COVERS_DIR / r.json()["filename"]) as img:
        assert img.size == cover_service.TARGET_SIZE  # quadrada vira vertical com fundo borrado


@respx.mock
def test_cover_url_upstream_error(client, public_dns):
    respx.get("https://img.example/x.jpg").mock(return_value=httpx.Response(404))
    assert client.post("/api/v1/uploads/cover-url", json={"url": "https://img.example/x.jpg"}).status_code == 400
    respx.get("https://img.example/y.jpg").mock(return_value=httpx.Response(200, content=b"nao e imagem"))
    assert client.post("/api/v1/uploads/cover-url", json={"url": "https://img.example/y.jpg"}).status_code == 400


def test_cors_not_wildcard(client):
    r = client.options("/api/v1/books/", headers={"Origin": "http://evil.example",
                                                  "Access-Control-Request-Method": "DELETE"})
    assert "access-control-allow-origin" not in r.headers


def test_auto_cover_endpoints(client, make_book, monkeypatch):
    from backend.app.api.v1.endpoints import uploads
    calls = []

    async def fake_find(title, author=None, isbn=None, api_key=None):
        calls.append((title, author, isbn, api_key))
        return ("capa.jpg", "Google Books") if title != "Sem capa" else None
    monkeypatch.setattr(uploads, "find_cover", fake_find)

    r = client.post("/api/v1/uploads/auto-cover", json={"title": "Duna", "author": "Frank Herbert", "api_key": "k"})
    assert r.json() == {"filename": "capa.jpg", "url": "/api/v1/uploads/cover/capa.jpg", "source": "Google Books"}
    assert calls[-1] == ("Duna", "Frank Herbert", None, "k")
    assert client.post("/api/v1/uploads/auto-cover", json={"title": " "}).status_code == 400
    assert client.post("/api/v1/uploads/auto-cover", json={"title": "Sem capa"}).status_code == 404

    book = make_book(title="Duna", authors=["Frank Herbert"], isbn="9788576573135")
    res = client.post(f"/api/v1/uploads/auto-cover-book/{book['id']}", json={}).json()
    assert res["success"] and res["filename"] == "capa.jpg"
    assert calls[-1] == ("Duna", "Frank Herbert", "9788576573135", None)
    assert client.get(f"/api/v1/books/{book['id']}").json()["cover_image"] == "capa.jpg"

    missing = make_book(title="Sem capa")
    assert client.post(f"/api/v1/uploads/auto-cover-book/{missing['id']}").json()["success"] is False
    assert client.post("/api/v1/uploads/auto-cover-book/999").status_code == 404

    async def broken(*a, **k):
        raise RuntimeError("falhou")
    monkeypatch.setattr(uploads, "find_cover", broken)
    assert client.post(f"/api/v1/uploads/auto-cover-book/{book['id']}").json()["error"] == "Erro ao buscar capa"


def test_process_cover_keeps_portrait_and_survives_garbage():
    data, ext = cover_service.process_cover_image(_image_bytes((200, 300)))
    with Image.open(io.BytesIO(data)) as img:
        assert img.size == (200, 300) and ext == ".jpg"
    assert cover_service.process_cover_image(b"lixo") == (b"lixo", ".jpg")
