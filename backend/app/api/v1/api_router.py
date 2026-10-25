from fastapi import APIRouter
from backend.app.api.v1.endpoints import backups, books, categories, lookup, stats, uploads
from backend.app.services.category_service import SERVICES

api_router = APIRouter()

api_router.include_router(books.router, prefix="/books", tags=["Livros"])
for prefix, tag in (("authors", "Autores"), ("genres", "Gêneros"), ("publishers", "Editoras"), ("series", "Séries")):
    api_router.include_router(categories.build_router(SERVICES[prefix]), prefix=f"/{prefix}", tags=[tag])
api_router.include_router(stats.router, prefix="/stats", tags=["Estatísticas"])
api_router.include_router(lookup.router, prefix="/lookup", tags=["Busca de metadados"])
api_router.include_router(uploads.router, prefix="/uploads", tags=["Uploads"])
api_router.include_router(backups.router, prefix="/backups", tags=["Backups"])
