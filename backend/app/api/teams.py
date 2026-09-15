from fastapi import APIRouter, Response, status

from app.api.deps import AdminUser, DbSession, StaffUser
from app.models import Team
from app.schemas.team import TeamCreate, TeamMemberAdd, TeamRead, TeamUpdate
from app.services import team_service

router = APIRouter(prefix="/teams", tags=["teams"])


@router.get("", response_model=list[TeamRead])
def list_teams(actor: StaffUser, db: DbSession) -> list[Team]:
    return team_service.list_teams(db, actor.organization_id)


@router.post("", response_model=TeamRead, status_code=status.HTTP_201_CREATED)
def create_team(data: TeamCreate, actor: AdminUser, db: DbSession) -> Team:
    return team_service.create_team(db, actor.organization_id, data)


@router.get("/{team_id}", response_model=TeamRead)
def get_team(team_id: int, actor: StaffUser, db: DbSession) -> Team:
    return team_service.get_team(db, actor.organization_id, team_id)


@router.patch("/{team_id}", response_model=TeamRead)
def update_team(team_id: int, data: TeamUpdate, actor: AdminUser, db: DbSession) -> Team:
    return team_service.update_team(db, actor.organization_id, team_id, data)


@router.delete("/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_team(team_id: int, actor: AdminUser, db: DbSession) -> Response:
    team_service.delete_team(db, actor.organization_id, team_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{team_id}/members", response_model=TeamRead)
def add_member(team_id: int, data: TeamMemberAdd, actor: AdminUser, db: DbSession) -> Team:
    return team_service.add_member(db, actor.organization_id, team_id, data.user_id)


@router.delete("/{team_id}/members/{user_id}", response_model=TeamRead)
def remove_member(team_id: int, user_id: int, actor: AdminUser, db: DbSession) -> Team:
    return team_service.remove_member(db, actor.organization_id, team_id, user_id)
