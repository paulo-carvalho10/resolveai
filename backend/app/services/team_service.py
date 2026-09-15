import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.errors import AppError, ConflictError, NotFoundError
from app.core.logger import log_event
from app.models import Team
from app.schemas.team import TeamCreate, TeamUpdate
from app.services import user_service

logger = logging.getLogger(__name__)


def list_teams(db: Session, organization_id: int) -> list[Team]:
    stmt = (
        select(Team)
        .where(Team.organization_id == organization_id)
        .options(selectinload(Team.members))
        .order_by(Team.name)
    )
    return list(db.scalars(stmt))


def get_team(db: Session, organization_id: int, team_id: int) -> Team:
    team = db.get(Team, team_id)
    if team is None or team.organization_id != organization_id:
        raise NotFoundError("Team")
    return team


def _ensure_name_available(
    db: Session, organization_id: int, name: str, exclude_id: int | None = None
) -> None:
    stmt = select(Team.id).where(
        Team.organization_id == organization_id, func.lower(Team.name) == name.lower()
    )
    if exclude_id is not None:
        stmt = stmt.where(Team.id != exclude_id)
    if db.scalar(stmt) is not None:
        raise ConflictError("TEAM_NAME_TAKEN", "A team with this name already exists.")


def create_team(db: Session, organization_id: int, data: TeamCreate) -> Team:
    _ensure_name_available(db, organization_id, data.name)
    team = Team(organization_id=organization_id, name=data.name, description=data.description)
    db.add(team)
    db.commit()
    log_event(logger, "team.created", team_id=team.id, organization_id=organization_id)
    return team


def update_team(db: Session, organization_id: int, team_id: int, data: TeamUpdate) -> Team:
    team = get_team(db, organization_id, team_id)
    changes = data.model_dump(exclude_unset=True)
    if changes.get("name") is not None:
        _ensure_name_available(db, organization_id, changes["name"], exclude_id=team.id)
        team.name = changes["name"]
    if "description" in changes:
        team.description = changes["description"]
    db.commit()
    return team


def delete_team(db: Session, organization_id: int, team_id: int) -> None:
    team = get_team(db, organization_id, team_id)
    db.delete(team)
    db.commit()
    log_event(logger, "team.deleted", team_id=team_id, organization_id=organization_id)


def add_member(db: Session, organization_id: int, team_id: int, user_id: int) -> Team:
    team = get_team(db, organization_id, team_id)
    user = user_service.get_user(db, organization_id, user_id)
    if not user.is_staff:
        raise AppError("INVALID_TEAM_MEMBER", "Only agents and admins can join a team.", 422)
    if user not in team.members:
        team.members.append(user)
        db.commit()
    return team


def remove_member(db: Session, organization_id: int, team_id: int, user_id: int) -> Team:
    team = get_team(db, organization_id, team_id)
    user = user_service.get_user(db, organization_id, user_id)
    if user in team.members:
        team.members.remove(user)
        db.commit()
    return team
