API = "/api/v1/books"


def test_create_reread_copies_edition_and_links_root(client, make_book):
    original = make_book(title="Duna", authors=["Frank Herbert"], genres=["Ficção"], pages=600, series="Duna",
                         series_number=1, publisher="Aleph", cover_image="duna.jpg", isbn="123",
                         status="Lido", score=9, notes="primeira")
    res = client.post(f"{API}/{original['id']}/reread", json={"status": "Lendo"})
    assert res.status_code == 201
    reread = res.json()
    assert reread["reread_of_id"] == original["id"] and reread["read_number"] == 2
    assert reread["status"] == "Lendo" and reread["score"] is None and reread["notes"] is None
    assert [a["name"] for a in reread["authors"]] == ["Frank Herbert"]
    assert reread["genres"][0]["name"] == "Ficção"
    assert (reread["pages"], reread["series"]["name"], reread["publisher"]["name"]) == (600, "Duna", "Aleph")
    assert reread["cover_image"] == "duna.jpg"
    assert client.get(f"{API}/{original['id']}").json()["rereads_count"] == 1

    # Reler a partir da releitura continua ligando ao original
    third = client.post(f"{API}/{reread['id']}/reread", json={"status": "Próximo"}).json()
    assert third["reread_of_id"] == original["id"] and third["read_number"] == 3
    assert third["next_position"] == 1


def test_reread_of_missing_book(client):
    assert client.post(f"{API}/999/reread").status_code == 404


def test_manual_reread_link_validation(client, make_book):
    original = make_book(title="Original", status="Lido")
    reread = make_book(title="Original", reread_of_id=original["id"])
    assert reread["read_number"] == 2

    assert client.post(f"{API}/", json={"title": "x", "reread_of_id": 999}).status_code == 422
    assert client.put(f"{API}/{original['id']}", json={"reread_of_id": original["id"]}).status_code == 422
    # O original não pode virar releitura de uma leitura do próprio grupo
    assert client.put(f"{API}/{original['id']}", json={"reread_of_id": reread["id"]}).status_code == 422


def test_unlinking_reread_resets_read_number(client, make_book):
    original = make_book(title="A")
    reread = make_book(title="A", reread_of_id=original["id"], read_number=4)
    assert reread["read_number"] == 4
    unlinked = client.put(f"{API}/{reread['id']}", json={"reread_of_id": None}).json()
    assert unlinked["reread_of_id"] is None and unlinked["read_number"] == 1


def test_relinking_root_moves_its_rereads(client, make_book):
    a = make_book(title="A")
    a2 = make_book(title="A", reread_of_id=a["id"])
    b = make_book(title="A (outra edição)")
    res = client.put(f"{API}/{a['id']}", json={"reread_of_id": b["id"]})
    assert res.status_code == 200 and res.json()["reread_of_id"] == b["id"]
    assert client.get(f"{API}/{a2['id']}").json()["reread_of_id"] == b["id"]
    assert client.get(f"{API}/{b['id']}").json()["rereads_count"] == 2


def test_deleting_root_promotes_oldest_reread(client, make_book):
    root = make_book(title="A")
    second = client.post(f"{API}/{root['id']}/reread").json()
    third = client.post(f"{API}/{root['id']}/reread").json()
    client.delete(f"{API}/{root['id']}")
    assert client.get(f"{API}/{second['id']}").json()["reread_of_id"] is None
    assert client.get(f"{API}/{third['id']}").json()["reread_of_id"] == second["id"]


def test_reread_root_stops_on_cycles(db_session):
    from backend.app.models.book import Book
    from backend.app.services.book_service import BookService
    a, b = Book(title="a"), Book(title="b")
    db_session.add_all([a, b])
    db_session.flush()
    a.reread_of_id, b.reread_of_id = b.id, a.id
    db_session.flush()
    assert BookService.reread_root(db_session, a) in (a, b)
    orphan = Book(title="c", reread_of_id=12345)
    db_session.add(orphan)
    assert BookService.reread_root(db_session, orphan) is orphan


def test_editing_reread_keeps_its_read_number(client, make_book):
    original = make_book(title="A", status="Lido")
    second = client.post(f"{API}/{original['id']}/reread").json()
    third = client.post(f"{API}/{original['id']}/reread").json()
    again = client.put(f"{API}/{second['id']}", json={"reread_of_id": original["id"], "notes": "x"}).json()
    assert again["read_number"] == 2
    assert client.put(f"{API}/{third['id']}", json={"reread_of_id": second["id"]}).json()["read_number"] == 3
