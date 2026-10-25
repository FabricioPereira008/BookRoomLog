from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from backend.app.core.config import settings
from backend.app.core.database import engine
from backend.app.core.migrations import run_migrations
from backend.app.services.backup_service import auto_backup
from backend.app.api.v1.api_router import api_router
from backend.app.services.category_service import CategoryConflictError, CategoryNotFoundError

@asynccontextmanager
async def lifespan(_: FastAPI):
    # Backup do dia (antes de qualquer migração), depois schema/migrações pendentes
    auto_backup(engine)
    run_migrations(engine)
    yield


app = FastAPI(
    lifespan=lifespan,
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="API do BookRoomLog para registro de leituras, fila de próximos livros e anuário de leitura"
)

# CORS restrito: impede que páginas web arbitrárias chamem a API local
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(CategoryNotFoundError)
async def category_not_found_handler(request: Request, exc: CategoryNotFoundError):
    return JSONResponse(status_code=404, content={"detail": str(exc)})

@app.exception_handler(CategoryConflictError)
async def category_conflict_handler(request: Request, exc: CategoryConflictError):
    return JSONResponse(status_code=409, content={"detail": str(exc)})

# Montar diretório estático para capas
app.mount("/static/covers", StaticFiles(directory=settings.COVERS_DIR), name="covers")

# Incluir rotas da API v1
app.include_router(api_router, prefix=settings.API_V1_STR)

@app.get("/")
def root():
    return {
        "message": "BookRoomLog API está online!",
        "docs": "/docs",
        "version": settings.VERSION
    }
