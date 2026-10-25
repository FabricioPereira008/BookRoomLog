import os
import sys
import requests
from typing import List, Dict, Any, Optional
from pathlib import Path

DEFAULT_BASE_URL = "http://127.0.0.1:8010/api/v1"
DEFAULT_TIMEOUT = 5
UPLOAD_TIMEOUT = 15
LOOKUP_TIMEOUT = 30
IMPORT_TIMEOUT = 120

# Prefixos da API para cada tipo de categoria
CATEGORY_PATHS = {"author": "authors", "genre": "genres", "publisher": "publishers", "series": "series"}


def get_default_base_url() -> str:
    """URL da API; pode ser sobrescrita com BOOKROOM_API_URL."""
    return os.environ.get("BOOKROOM_API_URL", DEFAULT_BASE_URL)


def get_cover_cache_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return base / "bookroomlog" / "covers"


def _scope_params(scope: Optional[str]) -> Optional[Dict[str, str]]:
    """Escopo das categorias: None/"read" = só lidos (padrão da API), "all" = todos os livros."""
    return {"scope": scope} if scope else None


def _clean(params: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in params.items() if v not in (None, "")}


class ApiClient:
    def __init__(self, base_url: Optional[str] = None, cover_cache_dir: Optional[Path] = None):
        self.base_url = (base_url or get_default_base_url()).rstrip("/")
        self.cover_cache_dir = cover_cache_dir
        self._session = requests.Session()

    def _url(self, path: str) -> str:
        return f"{self.base_url}/{path.lstrip('/')}"

    @property
    def server_url(self) -> str:
        return self.base_url.replace("/api/v1", "")

    def _request(self, method: str, path: str, timeout: float = DEFAULT_TIMEOUT, **kwargs) -> requests.Response:
        return self._session.request(method, self._url(path), timeout=timeout, **kwargs)

    def _json(self, method: str, path: str, timeout: float = DEFAULT_TIMEOUT, **kwargs) -> Any:
        r = self._request(method, path, timeout=timeout, **kwargs)
        r.raise_for_status()
        return r.json()

    def _delete(self, path: str) -> bool:
        return self._request("DELETE", path).status_code == 204

    def is_backend_online(self) -> bool:
        """True só se o servidor responder e for a API do BookRoomLog (não outro serviço na porta)."""
        try:
            r = self._session.get(f"{self.server_url}/", timeout=2)
            return r.status_code == 200 and "BookRoomLog" in r.text
        except Exception:
            return False

    # --- CAPAS (cache local) ---
    def get_cover_path(self, filename: str) -> Optional[str]:
        """Baixa a capa do backend (uma vez) e retorna o caminho do arquivo em cache local."""
        safe_name = Path(filename).name
        if not safe_name:
            return None
        cache_dir = self.cover_cache_dir or get_cover_cache_dir()
        target = cache_dir / safe_name
        if target.exists():
            return str(target)
        try:
            r = self._session.get(f"{self.server_url}/static/covers/{safe_name}", timeout=DEFAULT_TIMEOUT)
            if r.status_code != 200:
                return None
            cache_dir.mkdir(parents=True, exist_ok=True)
            target.write_bytes(r.content)
            return str(target)
        except Exception:
            return None

    def prune_cover_cache(self, keep) -> int:
        """Apaga do cache local as capas fora de `keep` (nomes em uso); devolve quantas saíram."""
        keep_names = {Path(name).name for name in keep if name}
        cache_dir = self.cover_cache_dir or get_cover_cache_dir()
        if not cache_dir.is_dir():
            return 0
        removed = 0
        for path in cache_dir.iterdir():
            if path.is_file() and path.name not in keep_names:
                try:
                    path.unlink()
                    removed += 1
                except OSError:
                    pass
        return removed

    def orphan_covers(self) -> Dict[str, Any]:
        return self._json("GET", "uploads/covers/orphans")

    def cleanup_covers(self) -> Dict[str, Any]:
        return self._json("POST", "uploads/covers/cleanup", timeout=IMPORT_TIMEOUT)

    # --- LIVROS ---
    def get_books(self, status: Optional[str] = None, search: Optional[str] = None,
                  sort_by: Optional[str] = None, **filters) -> List[Dict[str, Any]]:
        """`filters`: author_id, genre_id, series_id, publisher_id, completion_year, is_favorite."""
        params = _clean({"status": status, "search": search, "sort_by": sort_by, **filters})
        return self._json("GET", "books/", params=params)

    def get_book_briefs(self) -> List[Dict[str, Any]]:
        """Todos os livros em formato resumido (id, título, autor, status, vínculo de releitura...)."""
        return self._json("GET", "books/brief")

    def get_book(self, book_id: int) -> Dict[str, Any]:
        return self._json("GET", f"books/{book_id}")

    def create_book(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return self._json("POST", "books/", json=data)

    def update_book(self, book_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        return self._json("PUT", f"books/{book_id}", json=data)

    def delete_book(self, book_id: int) -> bool:
        return self._delete(f"books/{book_id}")

    def create_reread(self, book_id: int, status: str = "Lendo") -> Dict[str, Any]:
        return self._json("POST", f"books/{book_id}/reread", json={"status": status})

    def set_next_order(self, book_ids: List[int]) -> List[Dict[str, Any]]:
        return self._json("PUT", "books/next-order", json={"book_ids": book_ids})

    # --- BUSCA DE METADADOS ---
    def lookup_books(self, title: str = "", author: Optional[str] = None, isbn: Optional[str] = None,
                     source: Optional[str] = None, api_key: Optional[str] = None) -> List[Dict[str, Any]]:
        params = _clean({"title": title, "author": author, "isbn": isbn, "source": source, "api_key": api_key})
        return self._json("GET", "lookup/", timeout=LOOKUP_TIMEOUT, params=params)["results"]

    def lookup_best(self, title: str = "", author: Optional[str] = None, isbn: Optional[str] = None,
                    api_key: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """O resultado que com segurança é este livro (gêneros já traduzidos, série); None se não houver."""
        params = _clean({"title": title, "author": author, "isbn": isbn, "api_key": api_key})
        r = self._request("GET", "lookup/best", timeout=LOOKUP_TIMEOUT, params=params)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()

    def autofill_book(self, book_id: int, api_key: Optional[str] = None) -> Dict[str, Any]:
        """Completa os campos vazios do livro; devolve {"book", "filled", "source"}."""
        return self._json("POST", f"books/{book_id}/autofill", timeout=LOOKUP_TIMEOUT * 2,
                          json={"api_key": api_key} if api_key else {})

    # --- UPLOAD E DOWNLOAD DE CAPA ---
    def upload_cover(self, file_path: str) -> Optional[str]:
        path = Path(file_path)
        if not path.exists():
            return None
        with open(path, "rb") as f:
            files = {"file": (path.name, f, "image/jpeg")}
            r = self._request("POST", "uploads/cover", timeout=UPLOAD_TIMEOUT, files=files)
            if r.status_code == 200:
                return r.json().get("filename")
        return None

    def upload_cover_url(self, url: str) -> Optional[str]:
        r = self._request("POST", "uploads/cover-url", timeout=UPLOAD_TIMEOUT, json={"url": url})
        if r.status_code == 200:
            return r.json().get("filename")
        return None

    def auto_search_cover(self, title: str, author: Optional[str] = None, isbn: Optional[str] = None,
                          api_key: Optional[str] = None) -> Optional[str]:
        payload = _clean({"title": title, "author": author, "isbn": isbn, "api_key": api_key})
        payload.setdefault("title", "")
        r = self._request("POST", "uploads/auto-cover", timeout=LOOKUP_TIMEOUT, json=payload)
        if r.status_code == 200:
            return r.json().get("filename")
        return None

    def auto_cover_book(self, book_id: int, api_key: Optional[str] = None) -> Dict[str, Any]:
        return self._json("POST", f"uploads/auto-cover-book/{book_id}", timeout=LOOKUP_TIMEOUT,
                          json={"api_key": api_key} if api_key else {})

    # --- CATEGORIAS (autores, gêneros, editoras, séries) ---
    def get_categories(self, kind: str, scope: Optional[str] = None) -> List[Dict[str, Any]]:
        return self._json("GET", f"{CATEGORY_PATHS[kind]}/", params=_scope_params(scope))

    def get_category_details(self, kind: str, category_id: int, scope: Optional[str] = None) -> Dict[str, Any]:
        return self._json("GET", f"{CATEGORY_PATHS[kind]}/{category_id}/details", params=_scope_params(scope))

    def create_category(self, kind: str, name: str, color: Optional[str] = None) -> Dict[str, Any]:
        return self._json("POST", f"{CATEGORY_PATHS[kind]}/", json=_clean({"name": name, "color": color}))

    def update_category(self, kind: str, category_id: int, name: Optional[str] = None,
                        color: Optional[str] = None) -> Dict[str, Any]:
        return self._json("PUT", f"{CATEGORY_PATHS[kind]}/{category_id}", json=_clean({"name": name, "color": color}))

    def delete_category(self, kind: str, category_id: int) -> bool:
        return self._delete(f"{CATEGORY_PATHS[kind]}/{category_id}")

    # --- ESTATÍSTICAS E ANUÁRIO ---
    def get_yearbook(self, year: int) -> Dict[str, Any]:
        return self._json("GET", f"stats/yearbook/{year}")

    def set_yearbook_top3(self, year: int, book_ids: List[int]) -> Dict[str, Any]:
        return self._json("PUT", f"stats/yearbook/{year}/top3", json={"book_ids": book_ids})

    def get_overall_stats(self) -> Dict[str, Any]:
        return self._json("GET", "stats/overall")

    # --- BACKUPS DO BANCO ---
    def list_backups(self) -> Dict[str, Any]:
        return self._json("GET", "backups/")

    def create_backup(self) -> Dict[str, Any]:
        return self._json("POST", "backups/", timeout=IMPORT_TIMEOUT)

    def restore_backup(self, name: str) -> Dict[str, Any]:
        return self._json("POST", f"backups/{name}/restore", timeout=IMPORT_TIMEOUT)

    def export_backup(self, name: str, destination: str) -> str:
        """Baixa o backup `name` como .zip (banco + capas) em `destination`."""
        target = Path(destination)
        partial = target.with_name(target.name + ".part")
        with self._session.get(self._url(f"backups/{name}/export"), stream=True, timeout=IMPORT_TIMEOUT) as r:
            r.raise_for_status()
            with partial.open("wb") as fh:
                for chunk in r.iter_content(chunk_size=1024 * 1024):
                    fh.write(chunk)
        partial.replace(target)  # arquivo pela metade nunca fica com o nome final
        return str(target)

    def import_backup(self, path: str) -> Dict[str, Any]:
        with open(path, "rb") as fh:
            return self._json("POST", "backups/import", timeout=IMPORT_TIMEOUT,
                              files={"file": (Path(path).name, fh, "application/zip")})


api_client = ApiClient()
