"""Rotas de autores, gêneros, editoras e séries (todas com o mesmo formato)."""
from typing import List
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from backend.app.core.database import get_db
from backend.app.schemas.category import CategoryCreate, CategoryResponse, CategoryScope, CategoryUpdate
from backend.app.services.category_service import CategoryDetailResponse, CategoryService


def build_router(service: CategoryService) -> APIRouter:
    router = APIRouter()

    @router.get("/", response_model=List[CategoryResponse])
    def list_categories(scope: CategoryScope = "read", db: Session = Depends(get_db)):
        return service.list_with_counts(db, scope)

    @router.get("/{category_id}/details", response_model=CategoryDetailResponse)
    def get_details(category_id: int, scope: CategoryScope = "read", db: Session = Depends(get_db)):
        return service.details(db, category_id, scope)

    @router.post("/", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED)
    def create_category(payload: CategoryCreate, db: Session = Depends(get_db)):
        return service.create(db, payload.name, payload.color)

    @router.put("/{category_id}", response_model=CategoryResponse)
    def update_category(category_id: int, payload: CategoryUpdate, db: Session = Depends(get_db)):
        return service.update(db, category_id, payload.name, payload.color)

    @router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_category(category_id: int, db: Session = Depends(get_db)):
        service.delete(db, category_id)

    return router
