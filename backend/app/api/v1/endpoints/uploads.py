import uuid
import io
import httpx
from pathlib import Path
from typing import Optional
from pydantic import BaseModel
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from PIL import Image
from backend.app.core.config import settings
from backend.app.core.database import get_db
from backend.app.models.book import Book
from backend.app.core.net_safety import UnsafeURLError, download_public_bytes
from backend.app.services.cover_service import (
    discard_cover_if_unused, find_cover, orphan_covers_summary, remove_orphan_covers, save_cover_bytes,
)

router = APIRouter()


ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

class CoverUrlRequest(BaseModel):
    url: str

class AutoCoverRequest(BaseModel):
    title: str
    author: Optional[str] = None
    isbn: Optional[str] = None
    api_key: Optional[str] = None

class AutoCoverBookRequest(BaseModel):
    api_key: Optional[str] = None


def validate_image_bytes(content: bytes) -> None:
    """Garante que o conteúdo é uma imagem decodificável pelo Pillow."""
    try:
        with Image.open(io.BytesIO(content)) as img:
            img.verify()
    except Exception:
        raise HTTPException(status_code=400, detail="O arquivo enviado não é uma imagem válida.")

@router.post("/cover")
async def upload_cover(file: UploadFile = File(...)):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Formato de imagem inválido. Suportados: {', '.join(ALLOWED_EXTENSIONS)}"
        )

    filename = f"{uuid.uuid4()}{ext}"
    destination = settings.COVERS_DIR / filename

    content = await file.read(settings.MAX_COVER_BYTES + 1)
    if len(content) > settings.MAX_COVER_BYTES:
        raise HTTPException(status_code=413, detail="Imagem excede o tamanho máximo permitido.")
    validate_image_bytes(content)
    with open(destination, "wb") as f:
        f.write(content)

    return {
        "filename": filename,
        "url": f"/api/v1/uploads/cover/{filename}"
    }

@router.post("/cover-url")
async def download_cover_from_url(payload: CoverUrlRequest):
    url = payload.url.strip()
    if not url.startswith("http://") and not url.startswith("https://"):
        raise HTTPException(status_code=400, detail="URL inválida. Deve começar com http:// ou https://")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            content = await download_public_bytes(client, url, settings.MAX_COVER_BYTES, headers)
        validate_image_bytes(content)
        filename = save_cover_bytes(content)
        return {
            "filename": filename,
            "url": f"/api/v1/uploads/cover/{filename}"
        }
    except UnsafeURLError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=502, detail="Erro ao baixar a imagem da URL informada.")

@router.post("/auto-cover")
async def auto_search_cover(payload: AutoCoverRequest):
    title = payload.title.strip()
    if not title and not payload.isbn:
        raise HTTPException(status_code=400, detail="Título do livro não pode ser vazio.")

    found = await find_cover(title, payload.author, payload.isbn, payload.api_key)
    if not found:
        raise HTTPException(
            status_code=404,
            detail=f"Não foi possível encontrar automaticamente uma capa para '{title}'. Tente inserir o link da imagem."
        )
    filename, source = found
    return {
        "filename": filename,
        "url": f"/api/v1/uploads/cover/{filename}",
        "source": source
    }

@router.post("/auto-cover-book/{book_id}")
async def auto_cover_book(
    book_id: int,
    payload: AutoCoverBookRequest = AutoCoverBookRequest(),
    db: Session = Depends(get_db)
):
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Livro não encontrado")

    author = book.authors[0].name if book.authors else None
    try:
        found = await find_cover(book.title, author, book.isbn, payload.api_key)
    except Exception:
        return {"success": False, "book_id": book_id, "title": book.title, "error": "Erro ao buscar capa"}
    if not found:
        return {"success": False, "book_id": book_id, "title": book.title, "error": "Capa não encontrada"}
    filename, source = found
    old_cover, book.cover_image = book.cover_image, filename
    db.commit()
    if old_cover and old_cover != filename:
        discard_cover_if_unused(db, old_cover)
    return {"success": True, "book_id": book_id, "title": book.title, "filename": filename, "source": source}

@router.get("/cover/{filename}")
def get_cover(filename: str):
    covers_dir = settings.COVERS_DIR.resolve()
    file_path = (covers_dir / filename).resolve()
    if not file_path.is_relative_to(covers_dir) or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Imagem não encontrada")
    return FileResponse(file_path)



@router.get("/covers/orphans")
def get_orphan_covers(db: Session = Depends(get_db)):
    """Quantas capas da pasta nenhum livro usa (e quanto espaço ocupam)."""
    return orphan_covers_summary(db)


@router.post("/covers/cleanup")
def cleanup_orphan_covers(db: Session = Depends(get_db)):
    """Apaga as capas que nenhum livro usa (as dos backups continuam guardadas)."""
    return remove_orphan_covers(db)
