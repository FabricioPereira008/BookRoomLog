"""Backups do banco SQLite: automático ao iniciar (1 por dia), manual e restauração.

As cópias usam a API de backup do SQLite (consistente mesmo com o banco aberto) e ficam em
`<pasta do banco>/backups`, mantendo as MAX_BACKUPS mais recentes.

As capas têm nome único e nunca são alteradas, então cada backup só copia as que faltam para
`backups/covers/` (compartilhada entre os backups); a restauração devolve as que sumiram.
Para guardar fora do computador, um backup pode ser exportado num .zip (banco + capas) e
importado de volta — o importado entra na lista como mais um backup a restaurar.
"""
import json
import logging
import re
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from typing import BinaryIO, List, Optional, Set

from sqlalchemy import inspect
from sqlalchemy.engine import Engine

from backend.app.core.config import settings

logger = logging.getLogger(__name__)

MAX_BACKUPS = 10
NAME_RE = re.compile(r"^bookroom-(\d{8})-(\d{6})(?:-([a-z-]+))?\.db$")
REASON_LABELS = {"auto": "Automático", "manual": "Manual", "antes-da-restauracao": "Antes de restaurar",
                 "importado": "Importado"}
COVERS_SUBDIR = "covers"
ARCHIVE_FORMAT = "bookroom-backup"
ARCHIVE_VERSION = 1
ARCHIVE_DB = "bookroom.db"
ARCHIVE_MANIFEST = "manifest.json"
COVER_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+\.(?:jpg|jpeg|png|webp)$")
MAX_ARCHIVE_BYTES = 2 * 1024 ** 3  # soma descompactada aceita na importação


class BackupNotFoundError(Exception):
    pass


class InvalidBackupError(Exception):
    pass


def database_path(engine: Engine) -> Optional[Path]:
    """Arquivo do banco (None para bancos em memória)."""
    db = engine.url.database
    if engine.url.get_backend_name() != "sqlite" or not db or db == ":memory:":
        return None
    return Path(db).resolve()


def backup_dir(engine: Engine) -> Optional[Path]:
    path = database_path(engine)
    return path.parent / "backups" if path else None


def _info(path: Path) -> dict:
    match = NAME_RE.match(path.name)
    created = datetime.strptime(match.group(1) + match.group(2), "%Y%m%d%H%M%S")
    reason = match.group(3) or "auto"
    books = None
    try:  # quantos livros tinha (ajuda a escolher qual restaurar)
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as conn:
            books = conn.execute("select count(*) from books").fetchone()[0]
    except sqlite3.Error:
        pass
    return {
        "name": path.name,
        "created_at": created,
        "reason": reason,
        "reason_label": REASON_LABELS.get(reason, reason),
        "size_bytes": path.stat().st_size,
        "books_count": books,
    }


def list_backups(engine: Engine) -> List[dict]:
    folder = backup_dir(engine)
    if not folder or not folder.is_dir():
        return []
    files = [p for p in folder.iterdir() if p.is_file() and NAME_RE.match(p.name)]
    return sorted((_info(p) for p in files), key=lambda b: (b["created_at"], b["name"]), reverse=True)


def _backup_files(folder: Path) -> List[Path]:
    return sorted((p for p in folder.iterdir() if p.is_file() and NAME_RE.match(p.name)), key=lambda p: p.name)


def referenced_covers(db_file: Path) -> Set[str]:
    """Capas usadas pelos livros de um arquivo de banco (lança sqlite3.Error se não for um banco válido)."""
    with sqlite3.connect(f"file:{db_file}?mode=ro", uri=True) as conn:
        rows = conn.execute("select cover_image from books where cover_image is not null and cover_image != ''")
        return {Path(name).name for (name,) in rows}


def _mirror_covers(folder: Path) -> None:
    """Copia para backups/covers as capas atuais que ainda não estão lá."""
    source = settings.COVERS_DIR
    if not source.is_dir():
        return
    target = folder / COVERS_SUBDIR
    target.mkdir(parents=True, exist_ok=True)
    for cover in source.iterdir():
        if cover.is_file() and COVER_NAME_RE.match(cover.name) and not (target / cover.name).exists():
            shutil.copy2(cover, target / cover.name)


def _prune_covers(folder: Path) -> None:
    """Remove de backups/covers as capas que nenhum backup restante usa (na dúvida, não apaga nada)."""
    mirror = folder / COVERS_SUBDIR
    if not mirror.is_dir():
        return
    used: Set[str] = set()
    for backup in _backup_files(folder):
        try:
            used |= referenced_covers(backup)
        except sqlite3.Error:
            return  # backup ilegível: não dá para saber quais capas ele usa
    for cover in mirror.iterdir():
        if cover.is_file() and cover.name not in used:
            cover.unlink(missing_ok=True)


def _prune(folder: Path) -> None:
    for old in _backup_files(folder)[:-MAX_BACKUPS]:
        old.unlink(missing_ok=True)
    _prune_covers(folder)


def _unique_target(folder: Path, reason: str) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = folder / (f"bookroom-{stamp}.db" if reason == "auto" else f"bookroom-{stamp}-{reason}.db")
    counter = 1
    while target.exists():  # dois backups no mesmo segundo
        target = folder / f"bookroom-{stamp}-{reason}-{'x' * counter}.db"
        counter += 1
    return target


def create_backup(engine: Engine, reason: str = "manual", prune: bool = True) -> dict:
    folder = backup_dir(engine)
    if folder is None:
        raise InvalidBackupError("Banco em memória não tem backup")
    folder.mkdir(parents=True, exist_ok=True)
    target = _unique_target(folder, reason)
    raw = engine.raw_connection()
    try:
        with sqlite3.connect(target) as dst:
            raw.driver_connection.backup(dst)
    finally:
        raw.close()
    try:
        _mirror_covers(folder)
    except OSError:  # o banco já está salvo; capas faltando não invalidam o backup
        logger.exception("Falha ao copiar as capas para o backup")
    if prune:
        _prune(folder)
    logger.info("Backup do banco criado: %s", target.name)
    return _info(target)


def auto_backup(engine: Engine) -> Optional[dict]:
    """Backup do dia, antes das migrações. Ignora banco novo (sem livros) e se já houver um backup hoje."""
    folder = backup_dir(engine)
    if folder is None or "books" not in inspect(engine).get_table_names():
        return None
    today = datetime.now().strftime("%Y%m%d")
    if folder.is_dir() and any(NAME_RE.match(p.name) and p.name[9:17] == today for p in folder.iterdir()):
        return None
    try:
        return create_backup(engine, reason="auto")
    except Exception:  # backup nunca impede o app de abrir
        logger.exception("Falha no backup automático do banco")
        return None


def _backup_file(engine: Engine, name: str) -> Path:
    if not NAME_RE.match(name or ""):
        raise InvalidBackupError("Nome de backup inválido")
    folder = backup_dir(engine)
    source = (folder / name) if folder else None
    if source is None or not source.is_file():
        raise BackupNotFoundError(name)
    return source


def _validate_database(path: Path) -> Set[str]:
    """Confere que o arquivo é um banco do BookRoom; devolve as capas que ele usa."""
    try:
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as src:
            src.execute("select count(*) from books").fetchone()
        return referenced_covers(path)
    except sqlite3.Error as exc:
        raise InvalidBackupError(f"O arquivo não é um banco do BookRoom válido: {exc}")


def _restore_covers(folder: Path, names: Set[str]) -> int:
    """Devolve para a pasta de capas as usadas pelo banco restaurado que tinham sumido."""
    mirror = folder / COVERS_SUBDIR
    settings.COVERS_DIR.mkdir(parents=True, exist_ok=True)
    restored = 0
    for name in names:
        source, target = mirror / name, settings.COVERS_DIR / name
        if COVER_NAME_RE.match(name) and source.is_file() and not target.exists():
            shutil.copy2(source, target)
            restored += 1
    return restored


def restore_backup(engine: Engine, name: str, migrate) -> dict:
    """Substitui o conteúdo do banco pelo backup `name` (o estado atual é salvo antes) e aplica migrações."""
    source = _backup_file(engine, name)
    folder = source.parent
    covers = _validate_database(source)

    # Sem limpar ainda: com MAX_BACKUPS cheio, o arquivo restaurado poderia ser o apagado
    safety = create_backup(engine, reason="antes-da-restauracao", prune=False)
    raw = engine.raw_connection()
    try:
        with sqlite3.connect(f"file:{source}?mode=ro", uri=True) as src:
            src.backup(raw.driver_connection)
    finally:
        raw.close()
    engine.dispose()  # conexões antigas do pool não devem guardar estado do banco anterior
    migrate(engine)  # backups antigos podem estar numa versão anterior do schema
    covers_restored = _restore_covers(folder, covers)
    _prune(folder)
    logger.info("Banco restaurado a partir de %s (estado anterior salvo em %s, %d capa(s) devolvida(s))",
                name, safety["name"], covers_restored)
    return {"restored": name, "safety_backup": safety["name"], "covers_restored": covers_restored}


def export_backup(engine: Engine, name: str, out: BinaryIO) -> int:
    """Escreve em `out` um .zip com o backup `name` e as capas que ele usa; devolve quantas capas foram."""
    source = _backup_file(engine, name)
    covers = _validate_database(source)
    found = []
    for cover in sorted(covers):
        for place in (source.parent / COVERS_SUBDIR / cover, settings.COVERS_DIR / cover):
            if COVER_NAME_RE.match(cover) and place.is_file():
                found.append(place)
                break
    info = _info(source)
    manifest = {
        "format": ARCHIVE_FORMAT, "version": ARCHIVE_VERSION, "app_version": settings.VERSION,
        "backup": name, "created_at": info["created_at"].isoformat(), "books_count": info["books_count"],
        "covers_count": len(found), "covers_missing": len(covers) - len(found),
    }
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(ARCHIVE_MANIFEST, json.dumps(manifest, ensure_ascii=False, indent=2))
        archive.write(source, ARCHIVE_DB)
        for cover in found:  # imagens já são comprimidas
            archive.write(cover, f"{COVERS_SUBDIR}/{cover.name}", compress_type=zipfile.ZIP_STORED)
    return len(found)


def import_backup(engine: Engine, archive_file: BinaryIO) -> dict:
    """Lê um .zip exportado e o adiciona à lista de backups (não restaura: isso fica a cargo do usuário)."""
    folder = backup_dir(engine)
    if folder is None:
        raise InvalidBackupError("Banco em memória não tem backup")
    try:
        archive = zipfile.ZipFile(archive_file)
    except (zipfile.BadZipFile, OSError):
        raise InvalidBackupError("O arquivo não é um backup do BookRoom (.zip)")
    with archive:
        members = {m.filename: m for m in archive.infolist() if not m.is_dir()}
        try:
            manifest = json.loads(archive.read(ARCHIVE_MANIFEST)) if ARCHIVE_MANIFEST in members else {}
        except (ValueError, zipfile.BadZipFile):
            manifest = {}
        if manifest.get("format") != ARCHIVE_FORMAT or ARCHIVE_DB not in members:
            raise InvalidBackupError("O arquivo não é um backup do BookRoom (.zip)")
        if not isinstance(manifest.get("version"), int) or manifest["version"] > ARCHIVE_VERSION:
            raise InvalidBackupError("Backup feito por uma versão mais nova do BookRoom")
        covers = {}
        for path, member in members.items():
            if path in (ARCHIVE_MANIFEST, ARCHIVE_DB):
                continue
            prefix, _, cover = path.partition("/")
            if prefix != COVERS_SUBDIR or not COVER_NAME_RE.match(cover) or member.file_size > settings.MAX_COVER_BYTES:
                raise InvalidBackupError(f"Conteúdo inesperado no backup: {path}")
            covers[cover] = member
        if sum(m.file_size for m in members.values()) > MAX_ARCHIVE_BYTES:
            raise InvalidBackupError("Backup grande demais")

        folder.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=folder) as tmp:
            db_tmp = Path(tmp) / ARCHIVE_DB
            with archive.open(members[ARCHIVE_DB]) as src, db_tmp.open("wb") as dst:
                shutil.copyfileobj(src, dst)
            _validate_database(db_tmp)
            mirror = folder / COVERS_SUBDIR
            mirror.mkdir(exist_ok=True)
            for cover, member in covers.items():
                if not (mirror / cover).exists():
                    with archive.open(member) as src, (mirror / cover).open("wb") as dst:
                        shutil.copyfileobj(src, dst)
            target = _unique_target(folder, "importado")
            db_tmp.replace(target)
    _prune(folder)
    logger.info("Backup importado: %s (%d capa(s))", target.name, len(covers))
    return _info(target)
