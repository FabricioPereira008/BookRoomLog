import json

import pytest
import requests
import responses

from frontend_desktop.api_client.client import ApiClient, get_cover_cache_dir, get_default_base_url

BASE = "http://api.test/api/v1"


@pytest.fixture
def client(tmp_path):
    return ApiClient(BASE, cover_cache_dir=tmp_path / "cache")


def test_default_urls(monkeypatch):
    monkeypatch.delenv("BOOKROOM_API_URL", raising=False)
    assert get_default_base_url() == "http://127.0.0.1:8010/api/v1"
    monkeypatch.setenv("BOOKROOM_API_URL", "http://outro:9000/api/v1")
    assert get_default_base_url() == "http://outro:9000/api/v1"
    assert ApiClient().server_url == "http://outro:9000"
    assert get_cover_cache_dir().name == "covers"


@responses.activate
def test_is_backend_online_checks_the_app_name(client):
    responses.get("http://api.test/", body='{"message": "BookRoomLog API está online!"}')
    assert client.is_backend_online()
    responses.replace(responses.GET, "http://api.test/", body='{"message": "GameRoomLog API"}')
    assert not client.is_backend_online()
    responses.replace(responses.GET, "http://api.test/", body=requests.ConnectionError())
    assert not client.is_backend_online()


@responses.activate
def test_books_crud_and_params(client):
    listing = responses.get(f"{BASE}/books/", json=[{"id": 1}])
    assert client.get_books(status="Lido", search="", sort_by="next", author_id=3, is_favorite=False) == [{"id": 1}]
    assert listing.calls[0].request.params == {"status": "Lido", "sort_by": "next", "author_id": "3",
                                               "is_favorite": "False"}
    responses.get(f"{BASE}/books/brief", json=[])
    responses.get(f"{BASE}/books/1", json={"id": 1})
    responses.post(f"{BASE}/books/", json={"id": 2})
    responses.put(f"{BASE}/books/2", json={"id": 2, "title": "x"})
    responses.delete(f"{BASE}/books/2", status=204)
    reread = responses.post(f"{BASE}/books/1/reread", json={"id": 3})
    order = responses.put(f"{BASE}/books/next-order", json=[])
    assert client.get_book_briefs() == [] and client.get_book(1) == {"id": 1}
    assert client.create_book({"title": "a"}) == {"id": 2}
    assert client.update_book(2, {"title": "x"})["title"] == "x"
    assert client.delete_book(2) is True
    assert client.create_reread(1, "Próximo") == {"id": 3}
    assert json.loads(reread.calls[0].request.body) == {"status": "Próximo"}
    client.set_next_order([3, 1])
    assert json.loads(order.calls[0].request.body) == {"book_ids": [3, 1]}


@responses.activate
def test_http_errors_raise(client):
    responses.get(f"{BASE}/books/9", status=404, json={"detail": "x"})
    with pytest.raises(requests.HTTPError):
        client.get_book(9)


@responses.activate
def test_lookup_and_covers(client):
    lookup = responses.get(f"{BASE}/lookup/", json={"query": "x", "results": [{"title": "Duna"}]})
    assert client.lookup_books("Duna", author="Herbert", api_key="k") == [{"title": "Duna"}]
    assert lookup.calls[0].request.params == {"title": "Duna", "author": "Herbert", "api_key": "k"}

    auto = responses.post(f"{BASE}/uploads/auto-cover", json={"filename": "a.jpg"})
    assert client.auto_search_cover("", isbn="123") == "a.jpg"
    assert json.loads(auto.calls[0].request.body) == {"isbn": "123", "title": ""}
    responses.replace(responses.POST, f"{BASE}/uploads/auto-cover", status=404, json={})
    assert client.auto_search_cover("x") is None

    responses.post(f"{BASE}/uploads/cover-url", json={"filename": "b.jpg"})
    assert client.upload_cover_url("https://x/y.jpg") == "b.jpg"
    responses.replace(responses.POST, f"{BASE}/uploads/cover-url", status=400, json={})
    assert client.upload_cover_url("https://x/y.jpg") is None

    responses.post(f"{BASE}/uploads/auto-cover-book/5", json={"success": True})
    assert client.auto_cover_book(5, "k") == {"success": True}
    responses.get(f"{BASE}/uploads/covers/orphans", json={"count": 0, "bytes": 0})
    responses.post(f"{BASE}/uploads/covers/cleanup", json={"removed": 0})
    assert client.orphan_covers()["count"] == 0 and client.cleanup_covers()["removed"] == 0


@responses.activate
def test_upload_cover_file(client, tmp_path):
    image = tmp_path / "capa.png"
    image.write_bytes(b"png")
    responses.post(f"{BASE}/uploads/cover", json={"filename": "c.png"})
    assert client.upload_cover(str(image)) == "c.png"
    assert client.upload_cover(str(tmp_path / "nao-existe.png")) is None
    responses.replace(responses.POST, f"{BASE}/uploads/cover", status=400, json={})
    assert client.upload_cover(str(image)) is None


@responses.activate
def test_cover_cache_download_and_prune(client):
    responses.get("http://api.test/static/covers/a.jpg", body=b"img")
    responses.get("http://api.test/static/covers/sumiu.jpg", status=404)
    path = client.get_cover_path("../a.jpg")  # só o nome do arquivo é usado
    assert path and open(path, "rb").read() == b"img"
    assert client.get_cover_path("a.jpg") == path and len(responses.calls) == 1  # veio do cache
    assert client.get_cover_path("sumiu.jpg") is None
    assert client.get_cover_path("") is None
    (client.cover_cache_dir / "velha.jpg").write_bytes(b"x")
    assert client.prune_cover_cache({"a.jpg", None}) == 1
    assert ApiClient(BASE, cover_cache_dir=client.cover_cache_dir / "vazia").prune_cover_cache([]) == 0


@responses.activate
def test_cover_cache_network_error(client):
    responses.get("http://api.test/static/covers/x.jpg", body=requests.ConnectionError())
    assert client.get_cover_path("x.jpg") is None


@responses.activate
def test_categories_and_stats(client):
    cats = responses.get(f"{BASE}/authors/", json=[])
    client.get_categories("author", "all")
    assert cats.calls[0].request.params == {"scope": "all"}
    responses.get(f"{BASE}/series/4/details", json={"id": 4})
    responses.post(f"{BASE}/genres/", json={"id": 1})
    put = responses.put(f"{BASE}/publishers/2", json={"id": 2})
    responses.delete(f"{BASE}/genres/1", status=204)
    assert client.get_category_details("series", 4) == {"id": 4}
    assert client.create_category("genre", "Drama", "#fff") == {"id": 1}
    client.update_category("publisher", 2, name="Nova")
    assert json.loads(put.calls[0].request.body) == {"name": "Nova"}
    assert client.delete_category("genre", 1)
    responses.get(f"{BASE}/stats/yearbook/2025", json={"year": 2025})
    top3 = responses.put(f"{BASE}/stats/yearbook/2025/top3", json={"year": 2025})
    responses.get(f"{BASE}/stats/overall", json={"available_years": []})
    assert client.get_yearbook(2025)["year"] == 2025
    client.set_yearbook_top3(2025, [1, 2])
    assert json.loads(top3.calls[0].request.body) == {"book_ids": [1, 2]}
    assert client.get_overall_stats() == {"available_years": []}


@responses.activate
def test_backups(client, tmp_path):
    responses.get(f"{BASE}/backups/", json={"backups": []})
    responses.post(f"{BASE}/backups/", json={"name": "b.db"})
    responses.post(f"{BASE}/backups/b.db/restore", json={"restored": "b.db"})
    responses.get(f"{BASE}/backups/b.db/export", body=b"zipdata")
    responses.post(f"{BASE}/backups/import", json={"name": "i.db"})
    assert client.list_backups() == {"backups": []}
    assert client.create_backup()["name"] == "b.db"
    assert client.restore_backup("b.db")["restored"] == "b.db"
    target = tmp_path / "saida.zip"
    assert client.export_backup("b.db", str(target)) == str(target)
    assert target.read_bytes() == b"zipdata" and not (tmp_path / "saida.zip.part").exists()
    assert client.import_backup(str(target))["name"] == "i.db"


@responses.activate
def test_lookup_best_and_autofill(client):
    best = responses.get(f"{BASE}/lookup/best", json={"title": "Duna"})
    assert client.lookup_best("Duna", author="Herbert", api_key="k") == {"title": "Duna"}
    assert best.calls[0].request.params == {"title": "Duna", "author": "Herbert", "api_key": "k"}
    responses.replace(responses.GET, f"{BASE}/lookup/best", status=404, json={"detail": "x"})
    assert client.lookup_best("Nada") is None
    responses.replace(responses.GET, f"{BASE}/lookup/best", status=500, json={})
    with pytest.raises(requests.HTTPError):
        client.lookup_best("Erro")
    fill = responses.post(f"{BASE}/books/3/autofill", json={"filled": ["autor"]})
    assert client.autofill_book(3, "k") == {"filled": ["autor"]}
    assert json.loads(fill.calls[0].request.body) == {"api_key": "k"}
    client.autofill_book(3)
    assert json.loads(fill.calls[1].request.body) == {}
