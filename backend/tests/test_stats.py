from datetime import date

STATS = "/api/v1/stats"


def _library(make_book):
    best = make_book(title="Melhor", authors=["Ana", "Bia"], genres=["Drama"], series="Saga", status="Lido",
                     finish_date="2025-03-10", score=10, pages=500, format="Físico", is_favorite=True)
    mid = make_book(title="Médio", authors=["Ana"], genres=["Drama", "Humor"], series="Saga", status="Lido",
                    finish_date="2025-03-20", score=7, pages=200)
    low = make_book(title="Curto", authors=["Caio"], status="Lido", finish_date="2025-11-01", score=5, pages=90,
                    reread_of_id=mid["id"])
    nopages = make_book(title="Sem páginas", status="Lido", finish_date="2025-12-01")
    make_book(title="Ano anterior", status="Lido", finish_date="2024-06-01")
    make_book(title="Lendo", status="Lendo", pages=1000)
    return best, mid, low, nopages


def test_yearbook_summary(client, make_book):
    best, mid, low, nopages = _library(make_book)
    data = client.get(f"{STATS}/yearbook/2025").json()
    assert data["total_books_read"] == 4
    assert data["total_pages_read"] == 790
    assert data["average_score"] == round((10 + 7 + 5) / 3, 1)
    assert data["previous_year_read"] == 1
    assert data["monthly_read"][2] == 2 and data["monthly_read"][10] == 1 and data["monthly_read"][11] == 1
    assert [(g["name"], g["count"]) for g in data["genres"]] == [("Drama", 2), ("Humor", 1)]
    assert data["genres"][0]["color"]
    assert [(a["name"], a["count"], a["pages"]) for a in data["authors"]][:2] == [("Ana", 2, 700), ("Bia", 1, 500)]
    assert data["series"] == [{"name": "Saga", "count": 2, "pages": 700, "color": None}]
    assert {f["name"]: f["count"] for f in data["formats"]} == {"Kindle / E-book": 3, "Físico": 1}
    assert data["average_pages"] == round(790 / 3)
    assert data["rereads"] == 1 and data["favorites"] == 1
    assert data["longest_book"]["title"] == "Melhor"
    assert data["shortest_book"]["title"] == "Curto"
    assert data["best_book"]["title"] == "Melhor"
    assert [b["title"] for b in data["top3"]] == ["Melhor", "Médio", "Curto"]
    assert data["top3_custom"] is False
    assert data["books"][0]["title"] == "Sem páginas"  # mais recente primeiro


def test_empty_year(client):
    data = client.get(f"{STATS}/yearbook/1999").json()
    assert data["total_books_read"] == 0 and data["average_score"] is None and data["average_pages"] is None
    assert data["longest_book"] is None and data["top3"] == []


def test_custom_podium(client, make_book):
    best, mid, low, _ = _library(make_book)
    res = client.put(f"{STATS}/yearbook/2025/top3", json={"book_ids": [low["id"], best["id"]]})
    assert res.status_code == 200
    assert [b["title"] for b in res.json()["top3"]] == ["Curto", "Melhor"] and res.json()["top3_custom"]

    assert client.put(f"{STATS}/yearbook/2025/top3", json={"book_ids": [low["id"], low["id"]]}).status_code == 422
    other = make_book(title="Outro ano", status="Lido", finish_date="2020-01-01")
    assert client.put(f"{STATS}/yearbook/2025/top3", json={"book_ids": [other["id"]]}).status_code == 422
    assert client.put(f"{STATS}/yearbook/2025/top3", json={"book_ids": [1, 2, 3, 4]}).status_code == 422

    # Livro do pódio que deixou de ser lido no ano: volta para a sugestão
    client.put(f"/api/v1/books/{low['id']}", json={"finish_date": "2026-01-01"})
    client.put(f"/api/v1/books/{best['id']}", json={"status": "Lendo"})
    data = client.get(f"{STATS}/yearbook/2025").json()
    assert data["top3_custom"] is False

    cleared = client.put(f"{STATS}/yearbook/2025/top3", json={"book_ids": []}).json()
    assert cleared["top3_custom"] is False


def test_overall_stats(client, make_book):
    empty = client.get(f"{STATS}/overall").json()
    assert empty["available_years"] == [date.today().year] and empty["status_counts"]["total"] == 0
    _library(make_book)
    make_book(title="Fila", status="Próximo")
    make_book(title="Desejo")
    data = client.get(f"{STATS}/overall").json()
    assert data["status_counts"] == {"quero_ler": 1, "proximos": 1, "lendo": 1, "lidos": 5, "total": 8}
    assert data["total_pages_read"] == 790
    assert data["available_years"] == [2025, 2024]
