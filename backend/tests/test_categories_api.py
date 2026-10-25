import pytest


@pytest.mark.parametrize("kind", ["authors", "genres", "publishers", "series"])
def test_category_crud(client, kind):
    api = f"/api/v1/{kind}"
    res = client.post(f"{api}/", json={"name": "  Nome  "})
    assert res.status_code == 201
    item = res.json()
    assert item["name"] == "Nome"
    # Criar de novo com outra caixa devolve o mesmo
    assert client.post(f"{api}/", json={"name": "NOME"}).json()["id"] == item["id"]

    other = client.post(f"{api}/", json={"name": "Outro"}).json()
    assert client.put(f"{api}/{item['id']}", json={"name": "outro"}).status_code == 409
    renamed = client.put(f"{api}/{item['id']}", json={"name": "Renomeado"})
    assert renamed.status_code == 200 and renamed.json()["name"] == "Renomeado"

    assert client.get(f"{api}/{item['id']}/details").json()["total_books"] == 0
    assert client.delete(f"{api}/{other['id']}").status_code == 204
    assert client.delete(f"{api}/{other['id']}").status_code == 404
    assert client.put(f"{api}/999", json={"name": "x"}).status_code == 404
    assert client.get(f"{api}/999/details").status_code == 404
    assert [c["name"] for c in client.get(f"{api}/").json()] == ["Renomeado"]


def test_genre_color(client):
    genre = client.post("/api/v1/genres/", json={"name": "Fantasia"}).json()
    assert genre["color"] == "#b45309"
    updated = client.put(f"/api/v1/genres/{genre['id']}", json={"color": "#123456"}).json()
    assert updated["color"] == "#123456" and updated["name"] == "Fantasia"
    custom = client.post("/api/v1/genres/", json={"name": "Terror", "color": "#000000"}).json()
    assert custom["color"] == "#000000"


def test_counts_by_scope_and_details(client, make_book):
    make_book(title="Lido 1", authors=["Ana"], genres=["Drama"], series="S", publisher="P", status="Lido",
              pages=100, score=6, cover_image="a.jpg")
    make_book(title="Lido 2", authors=["Ana"], genres=["Drama"], series="S", publisher="P", status="Lido",
              pages=250, score=9, cover_image="b.jpg")
    make_book(title="Fila", authors=["Ana"], genres=["Drama"], series="S", publisher="P", status="Quero Ler",
              pages=999, cover_image="c.jpg")

    for kind in ("authors", "genres", "series", "publishers"):
        read_scope = client.get(f"/api/v1/{kind}/").json()[0]
        assert (read_scope["books_count"], read_scope["read_count"], read_scope["total_pages"]) == (2, 2, 350)
        assert read_scope["cover_samples"] == ["b.jpg", "a.jpg"]  # melhor nota primeiro
        all_scope = client.get(f"/api/v1/{kind}/?scope=all").json()[0]
        assert (all_scope["books_count"], all_scope["read_count"]) == (3, 2)
        assert all_scope["cover_samples"] == ["b.jpg", "a.jpg", "c.jpg"]

        details = client.get(f"/api/v1/{kind}/{read_scope['id']}/details").json()
        assert details["total_books"] == 2 and details["total_pages"] == 350
        assert details["category_type"] == {"authors": "author", "genres": "genre", "series": "series",
                                            "publishers": "publisher"}[kind]
        all_details = client.get(f"/api/v1/{kind}/{read_scope['id']}/details?scope=all").json()
        assert all_details["total_books"] == 3 and all_details["read_books"] == 2


def test_deleting_category_unlinks_books(client, make_book):
    book = make_book(authors=["Ana"], genres=["Drama"], series="S", publisher="P")
    for kind, key in (("authors", "authors"), ("genres", "genres"), ("series", "series"), ("publishers", "publisher")):
        item = client.get(f"/api/v1/{kind}/?scope=all").json()[0]
        assert client.delete(f"/api/v1/{kind}/{item['id']}").status_code == 204
        refreshed = client.get(f"/api/v1/books/{book['id']}").json()
        assert refreshed[key] in ([], None)


def test_find_by_name_casefold_fallback(db_session):
    from backend.app.models.publisher import Publisher
    from backend.app.services.category_service import find_by_name, get_or_create
    db_session.add(Publisher(name="Éditions"))
    db_session.flush()
    assert find_by_name(db_session, Publisher, "ÉDITIONS").name == "Éditions"
    assert get_or_create(db_session, Publisher, " éditions ").name == "Éditions"
    assert find_by_name(db_session, Publisher, "Outra") is None
