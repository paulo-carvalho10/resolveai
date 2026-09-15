"""Small development seed: one organization, three logins, teams, categories, priority rules
and tickets.

    python -m app.scripts.seed

The large demo dataset (5,000 tickets) comes in a later stage.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models import (
    Category,
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


def seed(db: Session) -> bool:
    """Idempotent: creates what is missing and returns whether anything was created."""
    admin = db.scalar(select(User).where(User.email == "admin@resolveai.dev"))
    if admin is None:
        _seed_organization(db)
        admin = db.scalar(select(User).where(User.email == "admin@resolveai.dev"))
        assert admin is not None
        _seed_priority_rules(db, admin.organization_id)
        db.commit()
        return True

    # Databases seeded before priority rules existed get the default rules.
    if db.scalar(
        select(PriorityRule.id).where(PriorityRule.organization_id == admin.organization_id)
    ):
        return False
    _seed_priority_rules(db, admin.organization_id)
    db.commit()
    return True


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
        created = seed(db)
    if created:
        print(f"Seed complete. Log in with admin|agent|user@resolveai.dev / {PASSWORD}")
    else:
        print("Seed data already present; nothing to do.")


if __name__ == "__main__":
    main()
