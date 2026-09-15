"""Priority rules: deterministic keyword rules that set a minimum priority, independent of AI."""

import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.core.logger import log_event
from app.core.text import contains_phrase, normalize
from app.models import PriorityRule, TicketPriority
from app.schemas.ai import PriorityRuleCreate, PriorityRuleUpdate

logger = logging.getLogger(__name__)

_RANK = {priority: rank for rank, priority in enumerate(TicketPriority)}


def highest(*priorities: TicketPriority | None) -> TicketPriority | None:
    given = [priority for priority in priorities if priority is not None]
    return max(given, key=_RANK.__getitem__) if given else None


def match_rule(db: Session, organization_id: int, text: str) -> PriorityRule | None:
    """The active rule with the highest priority whose keywords appear in the text."""
    rules = db.scalars(
        select(PriorityRule)
        .where(PriorityRule.organization_id == organization_id, PriorityRule.is_active.is_(True))
        .order_by(PriorityRule.id)
    )
    normalized = normalize(text)
    matches = [
        rule for rule in rules if any(contains_phrase(normalized, kw) for kw in rule.keywords)
    ]
    return max(matches, key=lambda rule: _RANK[rule.priority], default=None)


def list_rules(db: Session, organization_id: int) -> list[PriorityRule]:
    stmt = (
        select(PriorityRule)
        .where(PriorityRule.organization_id == organization_id)
        .order_by(PriorityRule.name)
    )
    return list(db.scalars(stmt))


def get_rule(db: Session, organization_id: int, rule_id: int) -> PriorityRule:
    rule = db.get(PriorityRule, rule_id)
    if rule is None or rule.organization_id != organization_id:
        raise NotFoundError("Priority rule")
    return rule


def _ensure_name_available(
    db: Session, organization_id: int, name: str, exclude_id: int | None = None
) -> None:
    stmt = select(PriorityRule.id).where(
        PriorityRule.organization_id == organization_id,
        func.lower(PriorityRule.name) == name.lower(),
    )
    if exclude_id is not None:
        stmt = stmt.where(PriorityRule.id != exclude_id)
    if db.scalar(stmt) is not None:
        raise ConflictError("PRIORITY_RULE_NAME_TAKEN", "A rule with this name already exists.")


def _clean_keywords(keywords: list[str]) -> list[str]:
    """Drop duplicates that only differ by case or accents, keeping the first spelling."""
    seen: set[str] = set()
    cleaned = []
    for keyword in keywords:
        key = normalize(keyword)
        if key and key not in seen:
            seen.add(key)
            cleaned.append(keyword.strip())
    return cleaned


def create_rule(db: Session, organization_id: int, data: PriorityRuleCreate) -> PriorityRule:
    _ensure_name_available(db, organization_id, data.name)
    rule = PriorityRule(
        organization_id=organization_id,
        name=data.name,
        keywords=_clean_keywords(data.keywords),
        priority=data.priority,
        is_active=data.is_active,
    )
    db.add(rule)
    db.commit()
    log_event(logger, "priority_rule.created", rule_id=rule.id, organization_id=organization_id)
    return rule


def update_rule(
    db: Session, organization_id: int, rule_id: int, data: PriorityRuleUpdate
) -> PriorityRule:
    rule = get_rule(db, organization_id, rule_id)
    changes = data.model_dump(exclude_unset=True, exclude_none=True)
    if "name" in changes:
        _ensure_name_available(db, organization_id, changes["name"], exclude_id=rule.id)
        rule.name = changes["name"]
    if "keywords" in changes:
        rule.keywords = _clean_keywords(changes["keywords"])
    if "priority" in changes:
        rule.priority = changes["priority"]
    if "is_active" in changes:
        rule.is_active = changes["is_active"]
    db.commit()
    return rule


def delete_rule(db: Session, organization_id: int, rule_id: int) -> None:
    rule = get_rule(db, organization_id, rule_id)
    db.delete(rule)
    db.commit()
