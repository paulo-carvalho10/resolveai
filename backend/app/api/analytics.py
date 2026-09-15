from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import DbSession, StaffUser
from app.schemas.analytics import Dashboard
from app.services import analytics_service

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/dashboard", response_model=Dashboard)
def dashboard(
    actor: StaffUser,
    db: DbSession,
    days: Annotated[int, Query(ge=1, le=365)] = 30,
) -> Dashboard:
    """Queue indicators (current state) and metrics for the last `days` days."""
    return analytics_service.build_dashboard(db, actor.organization_id, days)
