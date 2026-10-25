from datetime import date

from app_version import __version__

API = "/api/v1/books"


def test_root_identifies_the_api(client):
    res = client.get("/")
    assert res.status_code == 200
    assert "BookRoomLog" in res.json()["message"]
    assert res.json()["version"] == __version__


def test_create_book_with_categories_by_name(client, make_book):
    book = make_book(title="Duna", authors=["Frank Herbert"], genres=["Ficção científica", "Aventura"],
                     publisher="Aleph", series="Duna", series_number=1, pages=680, format="Físico",
                     language="Português", isbn="9788576573135", is_favorite=True, notes="Clássico")
    assert book["status"] == "Quero Ler"
    assert [a["name"] for a in book["authors"]] == ["Frank Herbert"]
    assert [g["name"] for g in book["genres"]] == ["Ficção científica", "Aventura"]
    assert book["publisher"]["name"] == "Aleph"
    assert book["series"]["name"] == "Duna" and book["series_number"] == 1
    assert book["format"] == "Físico" and book["pages"] == 680 and book["is_favorite"]


def test_category_names_are_reused_ignoring_case_and_accents_case(client, make_book):
    first = make_book(title="A", authors=["Machado de Assis"], genres=["Romance"], publisher="Ática")
    second = make_book(title="B", authors=["machado de assis", "  "], genres=["ROMANCE", "romance"],
                       publisher="ÁTICA")
    assert second["authors"][0]["id"] == first["authors"][0]["id"]
    assert [g["id"] for g in second["genres"]] == [first["genres"][0]["id"]]
    assert second["publisher"]["id"] == first["publisher"]["id"]  # casefold acha "ÁTICA" == "Ática"
    assert len(client.get("/api/v1/authors/?scope=all").json()) == 1


def test_author_order_is_kept(make_book, client):
    book = make_book(title="Belas Maldições", authors=["Terry Pratchett", "Neil Gaiman"])
    assert [a["name"] for a in book["authors"]] == ["Terry Pratchett", "Neil Gaiman"]
    updated = client.put(f"{API}/{book['id']}", json={"authors": ["Neil Gaiman", "Terry Pratchett"]}).json()
    assert [a["name"] for a in updated["authors"]] == ["Neil Gaiman", "Terry Pratchett"]


def test_get_update_delete_and_not_found(client, make_book):
    book = make_book(title="Original")
    assert client.get(f"{API}/{book['id']}").json()["title"] == "Original"
    res = client.put(f"{API}/{book['id']}", json={"title": "Novo", "publisher": "", "series": None})
    assert res.status_code == 200 and res.json()["title"] == "Novo"
    assert client.delete(f"{API}/{book['id']}").status_code == 204
    assert client.get(f"{API}/{book['id']}").status_code == 404
    assert client.put(f"{API}/999", json={"title": "x"}).status_code == 404
    assert client.delete(f"{API}/999").status_code == 404


def test_validation_errors(client):
    assert client.post(f"{API}/", json={"title": ""}).status_code == 422
    assert client.post(f"{API}/", json={"title": "x", "score": 11}).status_code == 422
    assert client.post(f"{API}/", json={"title": "x", "progress": 120}).status_code == 422
    assert client.post(f"{API}/", json={"title": "x", "status": "Abandonado"}).status_code == 422
    assert client.post(f"{API}/", json={"title": "x", "genres": ["a", "b", "c"]}).status_code == 422


def test_finished_book_defaults_finish_date_to_today(make_book):
    book = make_book(status="Lido", score=8)
    assert book["finish_date"] == date.today().isoformat()
    assert book["completion_year"] == date.today().year
    assert book["score"] == 8


def test_finish_date_defines_completion_year(make_book):
    book = make_book(status="Lido", finish_date="2024-12-31")
    assert book["completion_year"] == 2024


def test_score_and_finish_date_only_for_finished_books(client, make_book):
    book = make_book(status="Lido", score=9, finish_date="2025-01-02")
    moved = client.put(f"{API}/{book['id']}", json={"status": "Lendo", "progress": 40}).json()
    assert moved["score"] is None and moved["finish_date"] is None and moved["completion_year"] is None
    assert moved["progress"] == 40
    unread = make_book(status="Quero Ler", score=7, progress=10, finish_date="2025-01-01")
    assert unread["score"] is None and unread["progress"] is None and unread["finish_date"] is None


def test_progress_is_dropped_when_finished(client, make_book):
    book = make_book(status="Lendo", progress=80)
    done = client.put(f"{API}/{book['id']}", json={"status": "Lido"}).json()
    assert done["progress"] is None


def test_next_queue_positions_and_reorder(client, make_book):
    a = make_book(title="A", status="Próximo")
    b = make_book(title="B", status="Próximo")
    c = make_book(title="C", status="Próximo")
    assert [a["next_position"], b["next_position"], c["next_position"]] == [1, 2, 3]

    res = client.put(f"{API}/next-order", json={"book_ids": [c["id"], a["id"], b["id"]]})
    assert res.status_code == 200
    assert [x["title"] for x in res.json()] == ["C", "A", "B"]
    assert [x["next_position"] for x in res.json()] == [1, 2, 3]

    # Sair da fila (começar a ler) renumera o resto
    client.put(f"{API}/{c['id']}", json={"status": "Lendo"})
    queue = client.get(f"{API}/?status=Próximo&sort_by=next").json()
    assert [(x["title"], x["next_position"]) for x in queue] == [("A", 1), ("B", 2)]

    # Excluir também renumera
    client.delete(f"{API}/{a['id']}")
    assert client.get(f"{API}/{b['id']}").json()["next_position"] == 1

    # Entrar na fila coloca no fim
    d = make_book(title="D")
    assert client.put(f"{API}/{d['id']}", json={"status": "Próximo"}).json()["next_position"] == 2


def test_next_order_must_match_queue(client, make_book):
    a = make_book(title="A", status="Próximo")
    other = make_book(title="Fora", status="Quero Ler")
    assert client.put(f"{API}/next-order", json={"book_ids": []}).status_code == 422
    assert client.put(f"{API}/next-order", json={"book_ids": [a["id"], a["id"]]}).status_code == 422
    assert client.put(f"{API}/next-order", json={"book_ids": [a["id"], other["id"]]}).status_code == 422


def test_list_filters_search_and_sort(client, make_book):
    duna = make_book(title="Duna", authors=["Frank Herbert"], genres=["Ficção"], series="Duna",
                     publisher="Aleph", status="Lido", score=9, pages=600, finish_date="2025-05-01",
                     is_favorite=True)
    make_book(title="Messias de Duna", authors=["Frank Herbert"], series="Duna", status="Lido", score=7,
              pages=300, finish_date="2026-01-01")
    make_book(title="Emma", authors=["Jane Austen"], status="Quero Ler")

    titles = lambda **params: [b["title"] for b in client.get(f"{API}/", params=params).json()]
    assert titles() == ["Duna", "Emma", "Messias de Duna"]
    assert titles(status="Quero Ler") == ["Emma"]
    assert titles(search="herbert") == ["Duna", "Messias de Duna"]
    assert titles(search="emm") == ["Emma"]
    assert titles(author_id=duna["authors"][0]["id"]) == ["Duna", "Messias de Duna"]
    assert titles(genre_id=duna["genres"][0]["id"]) == ["Duna"]
    assert titles(series_id=duna["series"]["id"], sort_by="pages_asc") == ["Messias de Duna", "Duna"]
    assert titles(publisher_id=duna["publisher"]["id"]) == ["Duna"]
    assert titles(completion_year=2026) == ["Messias de Duna"]
    assert titles(is_favorite=True) == ["Duna"]
    assert titles(sort_by="score_desc")[:2] == ["Duna", "Messias de Duna"]
    assert titles(sort_by="finish_date_desc")[:2] == ["Messias de Duna", "Duna"]
    assert titles(sort_by="title_desc") == ["Messias de Duna", "Emma", "Duna"]
    assert titles(sort_by="desconhecido") == ["Duna", "Emma", "Messias de Duna"]
    assert len(titles(sort_by="recent")) == 3


def test_briefs(client, make_book):
    make_book(title="B", authors=["Autora"], status="Lido", score=8)
    make_book(title="A")
    briefs = client.get(f"{API}/brief").json()
    assert [b["title"] for b in briefs] == ["A", "B"]
    assert briefs[1]["author"] == "Autora" and briefs[1]["score"] == 8 and briefs[0]["author"] is None


def test_cover_change_discards_unused_file(client, make_book):
    from backend.app.core.config import settings
    old = settings.COVERS_DIR / "old.jpg"
    old.write_bytes(b"x")
    book = make_book(cover_image="old.jpg")
    client.put(f"{API}/{book['id']}", json={"cover_image": "new.jpg"})
    assert not old.exists()


def test_shared_cover_is_kept_while_in_use(client, make_book):
    from backend.app.core.config import settings
    shared = settings.COVERS_DIR / "shared.jpg"
    shared.write_bytes(b"x")
    first = make_book(cover_image="shared.jpg")
    make_book(cover_image="shared.jpg")
    client.delete(f"{API}/{first['id']}")
    assert shared.exists()
