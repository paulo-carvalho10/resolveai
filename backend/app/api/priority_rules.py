from fastapi import APIRouter, Response, status

from app.api.deps import AdminUser, DbSession, StaffUser
from app.models import PriorityRule
from app.schemas.ai import PriorityRuleCreate, PriorityRuleRead, PriorityRuleUpdate
from app.services import priority_service

router = APIRouter(prefix="/priority-rules", tags=["priority rules"])


@router.get("", response_model=list[PriorityRuleRead])
def list_rules(actor: StaffUser, db: DbSession) -> list[PriorityRule]:
    return priority_service.list_rules(db, actor.organization_id)


@router.post("", response_model=PriorityRuleRead, status_code=status.HTTP_201_CREATED)
def create_rule(data: PriorityRuleCreate, actor: AdminUser, db: DbSession) -> PriorityRule:
    """Tickets mentioning any keyword get at least this priority (accent and case-insensitive)."""
    return priority_service.create_rule(db, actor.organization_id, data)


@router.get("/{rule_id}", response_model=PriorityRuleRead)
def get_rule(rule_id: int, actor: StaffUser, db: DbSession) -> PriorityRule:
    return priority_service.get_rule(db, actor.organization_id, rule_id)


@router.patch("/{rule_id}", response_model=PriorityRuleRead)
def update_rule(
    rule_id: int, data: PriorityRuleUpdate, actor: AdminUser, db: DbSession
) -> PriorityRule:
    return priority_service.update_rule(db, actor.organization_id, rule_id, data)


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rule(rule_id: int, actor: AdminUser, db: DbSession) -> Response:
    priority_service.delete_rule(db, actor.organization_id, rule_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
