"""Processamento, armazenamento e busca automática de capas de livros."""
import io
import logging
import time
import uuid
from pathlib import Path
from typing import List, Optional, Tuple

import httpx
from PIL import Image, ImageFilter
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.core.net_safety import UnsafeURLError, download_public_bytes
from backend.app.models.book import Book
from backend.app.services.lookup_service import search_books

logger = logging.getLogger(__name__)

USER_AGENT = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
TARGET_SIZE = (600, 900)
PORTRAIT_RATIO_RANGE = (0.55, 0.78)
JPEG_QUALITY = 92
BLUR_RADIUS = 25
MIN_VALID_IMAGE_BYTES = 1500
COVER_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
# Capa enviada há pouco pode ainda não ter sido gravada no livro (diálogo de edição aberto)
ORPHAN_GRACE_SECONDS = 3600


def process_cover_image(img_bytes: bytes) -> Tuple[bytes, str]:
    """Ajusta a imagem ao padrão vertical 600x900 (fundo borrado quando horizontal)."""
    try:
        img = Image.open(io.BytesIO(img_bytes))
        img = img.convert("RGBA" if img.mode in ("RGBA", "P") else "RGB")

        w, h = img.size
        if PORTRAIT_RATIO_RANGE[0] <= w / h <= PORTRAIT_RATIO_RANGE[1]:
            out = io.BytesIO()
            img.convert("RGB").save(out, format="JPEG", quality=JPEG_QUALITY)
            return out.getvalue(), ".jpg"

        target_w, target_h = TARGET_SIZE
        bg = img.resize(TARGET_SIZE, Image.Resampling.BILINEAR).filter(ImageFilter.GaussianBlur(radius=BLUR_RADIUS))
        bg = Image.alpha_composite(bg.convert("RGBA"), Image.new("RGBA", TARGET_SIZE, (0, 0, 0, 80)))

        fit_w, fit_h = target_w, int(h * target_w / w)
        if fit_h > target_h:
            fit_w, fit_h = int(w * target_h / h), target_h
        fg = img.resize((fit_w, fit_h), Image.Resampling.LANCZOS)
        bg.paste(fg, ((target_w - fit_w) // 2, (target_h - fit_h) // 2), fg if fg.mode == "RGBA" else None)

        out = io.BytesIO()
        bg.convert("RGB").save(out, format="JPEG", quality=JPEG_QUALITY)
        return out.getvalue(), ".jpg"
    except Exception:
        logger.exception("Erro ao processar imagem de capa com Pillow")
        return img_bytes, ".jpg"


def save_cover_bytes(img_bytes: bytes) -> str:
    """Processa e grava a capa em COVERS_DIR; retorna o nome do arquivo."""
    processed, ext = process_cover_image(img_bytes)
    filename = f"{uuid.uuid4()}{ext}"
    (settings.COVERS_DIR / filename).write_bytes(processed)
    return filename


async def fetch_cover_url(url: str) -> Optional[str]:
    """Baixa (com as proteções de SSRF) e grava a capa de `url`; devolve o nome do arquivo ou None."""
    async with httpx.AsyncClient(timeout=12.0) as client:
        try:
            content = await download_public_bytes(client, url, settings.MAX_COVER_BYTES, USER_AGENT)
        except (UnsafeURLError, httpx.HTTPError):
            return None
    if len(content) < MIN_VALID_IMAGE_BYTES:  # placeholders "sem capa" das APIs são minúsculos
        return None
    return save_cover_bytes(content)


async def find_cover(title: str, author: Optional[str] = None, isbn: Optional[str] = None,
                     api_key: Optional[str] = None) -> Optional[Tuple[str, str]]:
    """Busca a capa nos resultados da busca de metadados; retorna (filename, fonte) ou None."""
    candidates = await search_books(title, author=author, isbn=isbn, api_key=api_key)
    for candidate in candidates:
        if not candidate.cover_url:
            continue
        try:
            filename = await fetch_cover_url(candidate.cover_url)
        except Exception:
            logger.warning("Falha ao baixar a capa de '%s' (%s)", title, candidate.source, exc_info=True)
            continue
        if filename:
            return filename, candidate.source
    return None



# --- capas sem uso ---

def discard_cover_if_unused(db: Session, filename: Optional[str]) -> bool:
    """Apaga o arquivo da capa se nenhum livro a usa mais (chamar depois do commit)."""
    name = Path(filename or "").name
    if not name or db.query(Book.id).filter(Book.cover_image == filename).first():
        return False
    path = settings.COVERS_DIR / name
    if not path.is_file():
        return False
    try:
        path.unlink()
    except OSError:
        logger.warning("Não foi possível apagar a capa sem uso %s", name)
        return False
    return True


def orphan_covers(db: Session, grace_seconds: float = ORPHAN_GRACE_SECONDS) -> List[Path]:
    """Imagens da pasta de capas que nenhum livro usa (ignora as enviadas há menos de `grace_seconds`)."""
    folder = settings.COVERS_DIR
    if not folder.is_dir():
        return []
    used = {Path(c).name for (c,) in db.query(Book.cover_image).filter(Book.cover_image.isnot(None))}
    limit = time.time() - grace_seconds
    return sorted(
        p for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in COVER_EXTENSIONS and p.name not in used and p.stat().st_mtime < limit
    )


def orphan_covers_summary(db: Session) -> dict:
    files = orphan_covers(db)
    return {"count": len(files), "bytes": sum(p.stat().st_size for p in files)}


def remove_orphan_covers(db: Session) -> dict:
    removed, freed = 0, 0
    for path in orphan_covers(db):
        try:
            size = path.stat().st_size
            path.unlink()
        except OSError:
            continue
        removed, freed = removed + 1, freed + size
    if removed:
        logger.info("%d capa(s) sem uso removida(s) (%d bytes)", removed, freed)
    return {"removed": removed, "freed_bytes": freed}
