from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.app.core.database import get_db
from backend.app.schemas.stats import OverallStats, Top3Request, YearbookSummary
from backend.app.services.stats_service import InvalidTop3Error, StatsService

router = APIRouter()

@router.get("/yearbook/{year}", response_model=YearbookSummary)
def get_yearbook(year: int, db: Session = Depends(get_db)):
    return StatsService.get_yearbook(db=db, year=year)

@router.put("/yearbook/{year}/top3", response_model=YearbookSummary)
def set_yearbook_top3(year: int, payload: Top3Request, db: Session = Depends(get_db)):
    try:
        return StatsService.set_top3(db, year, payload.book_ids)
    except InvalidTop3Error as exc:
        raise HTTPException(status_code=422, detail=str(exc))

@router.get("/overall", response_model=OverallStats)
def get_overall_stats(db: Session = Depends(get_db)):
    return StatsService.get_overall_stats(db=db)
