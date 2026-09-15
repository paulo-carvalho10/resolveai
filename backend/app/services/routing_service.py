"""Decides which team receives a ticket."""

from app.models import Category, Team


def resolve_team(category: Category | None, suggested_team: Team | None) -> Team | None:
    """The category's default team wins; the AI-suggested team is the fallback.

    An admin-configured route is an explicit business decision, so it takes precedence over a
    model's guess. The suggestion only matters for categories without a default team.
    """
    if category is not None and category.default_team is not None:
        return category.default_team
    return suggested_team
