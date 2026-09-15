"""Small development seed: one organization, three logins, teams, categories, priority rules,
tickets and knowledge base articles (indexed with the configured embedding provider).

    python -m app.scripts.seed

The large demo dataset (5,000 tickets) comes in a later stage.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models import (
    Category,
    KnowledgeArticle,
    Organization,
    PriorityRule,
    Subcategory,
    Team,
    Ticket,
    TicketEventType,
    TicketHistory,
    TicketPriority,
    TicketStatus,
    User,
    UserRole,
)
from app.scripts.seed_knowledge import ARTICLES
from app.services import knowledge_service
from app.services.embeddings import Embedder, HashingEmbedder, build_embedder

PASSWORD = "resolveai123"

TEAMS = {
    "ERP Fiscal": "Emissão de NF-e, NFS-e e obrigações fiscais.",
    "Infraestrutura TI": "Rede, servidores, VPN e acessos.",
    "Financeiro": "Cobrança, boletos e faturas.",
    "Suporte Geral": "Primeiro atendimento e dúvidas de uso.",
}

PRIORITY_RULES = [
    (
        "Sistema fora do ar",
        ["fora do ar", "sistema caiu", "parou tudo", "ninguém consegue acessar"],
        TicketPriority.CRITICAL,
    ),
    (
        "Faturamento bloqueado",
        ["não consigo emitir", "fechar o faturamento", "rejeição"],
        TicketPriority.HIGH,
    ),
]

CATEGORIES = {
    "Fiscal": ("ERP Fiscal", ["NF-e", "NFS-e", "SPED"]),
    "Infraestrutura": ("Infraestrutura TI", ["Rede", "VPN", "Servidores"]),
    "Cobrança": ("Financeiro", ["Boletos", "Faturas"]),
    "Acesso": ("Suporte Geral", ["Senha", "Permissões"]),
}

TICKETS = [
    (
        "Não consigo emitir NF-e",
        "O sistema apresenta rejeição 539 ao transmitir a nota. "
        "Precisamos fechar o faturamento hoje.",
        "NF-e",
        TicketPriority.HIGH,
        TicketStatus.OPEN,
    ),
    (
        "VPN desconectando a cada 5 minutos",
        "Desde ontem a VPN cai com frequência para toda a equipe comercial.",
        "VPN",
        TicketPriority.MEDIUM,
        TicketStatus.IN_PROGRESS,
    ),
    (
        "Boleto gerado com vencimento errado",
        "O boleto da fatura 2026/09 saiu com vencimento para o mês passado.",
        "Boletos",
        TicketPriority.LOW,
        TicketStatus.WAITING_USER,
    ),
    (
        "Sistema fora do ar",
        "Ninguém consegue acessar o ERP desde as 8h. Tela branca após o login.",
        "Servidores",
        TicketPriority.CRITICAL,
        TicketStatus.OPEN,
    ),
]


def _user(org: Organization, email: str, name: str, role: UserRole) -> User:
    return User(
        organization_id=org.id,
        email=email,
        full_name=name,
        hashed_password=hash_password(PASSWORD),
        role=role,
    )


def seed(db: Session, embedder: Embedder | None = None) -> bool:
    """Idempotent: creates each missing part and returns whether anything was created.

    Databases seeded by an earlier stage get the parts added since (rules, articles).
    """
    created = False
    admin = db.scalar(select(User).where(User.email == "admin@resolveai.dev"))
    if admin is None:
        _seed_organization(db)
        db.commit()
        admin = db.scalar(select(User).where(User.email == "admin@resolveai.dev"))
        assert admin is not None
        created = True
    org_id = admin.organization_id

    if not db.scalar(select(PriorityRule.id).where(PriorityRule.organization_id == org_id)):
        _seed_priority_rules(db, org_id)
        db.commit()
        created = True

    if not db.scalar(select(KnowledgeArticle.id).where(KnowledgeArticle.organization_id == org_id)):
        articles = _seed_articles(db, admin)
        db.commit()
        for article in articles:
            knowledge_service.index_article(db, article, embedder or HashingEmbedder())
        created = True

    return created


def _seed_articles(db: Session, author: User) -> list[KnowledgeArticle]:
    categories = {
        category.name: category
        for category in db.scalars(
            select(Category).where(Category.organization_id == author.organization_id)
        )
    }
    articles = [
        KnowledgeArticle(
            organization_id=author.organization_id,
            title=title,
            content=content,
            category=categories.get(category_name) if category_name else None,
            tags=tags,
            status=status,
            author=author,
        )
        for title, category_name, tags, status, content in ARTICLES
    ]
    db.add_all(articles)
    return articles


def _seed_priority_rules(db: Session, organization_id: int) -> None:
    db.add_all(
        PriorityRule(
            organization_id=organization_id, name=name, keywords=keywords, priority=priority
        )
        for name, keywords, priority in PRIORITY_RULES
    )


def _seed_organization(db: Session) -> None:
    org = Organization(name="Acme Software")
    db.add(org)
    db.flush()

    admin = _user(org, "admin@resolveai.dev", "Ana Souza", UserRole.ADMIN)
    agent = _user(org, "agent@resolveai.dev", "Maria Oliveira", UserRole.AGENT)
    requester = _user(org, "user@resolveai.dev", "João Pereira", UserRole.USER)
    db.add_all([admin, agent, requester])

    teams = {
        name: Team(organization_id=org.id, name=name, description=description)
        for name, description in TEAMS.items()
    }
    teams["ERP Fiscal"].members.append(agent)
    teams["Suporte Geral"].members.append(agent)
    db.add_all(teams.values())

    subcategories: dict[str, Subcategory] = {}
    for name, (team_name, sub_names) in CATEGORIES.items():
        category = Category(organization_id=org.id, name=name, default_team=teams[team_name])
        for sub_name in sub_names:
            subcategories[sub_name] = Subcategory(name=sub_name)
            category.subcategories.append(subcategories[sub_name])
        db.add(category)
    db.flush()

    for title, description, sub_name, priority, status in TICKETS:
        subcategory = subcategories[sub_name]
        ticket = Ticket(
            organization_id=org.id,
            title=title,
            description=description,
            requester=requester,
            category=subcategory.category,
            subcategory=subcategory,
            team=subcategory.category.default_team,
            priority=priority,
            status=status,
            assignee=agent if status != TicketStatus.OPEN else None,
        )
        ticket.history.append(TicketHistory(actor=requester, event_type=TicketEventType.CREATED))
        db.add(ticket)
    db.flush()


def main() -> None:
    with SessionLocal() as db:
        created = seed(db, build_embedder(get_settings()))
    if created:
        print(f"Seed complete. Log in with admin|agent|user@resolveai.dev / {PASSWORD}")
    else:
        print("Seed data already present; nothing to do.")


if __name__ == "__main__":
    main()
