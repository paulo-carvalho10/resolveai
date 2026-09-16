"""Realistic demo data so the dashboard and lists look like a product in use.

    python -m app.scripts.demo_data                       # 500 users, 300 articles, 5,000 tickets
    python -m app.scripts.demo_data --tickets 800 --users 60 --articles 40

Adds to the seeded "Acme Software" organization (run `app.scripts.seed` first). Deterministic
(fixed random seed) and offline: AI suggestions are simulated, no paid API is called.
Refuses to run twice unless --force is given.
"""

import argparse
import random
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.security import hash_password
from app.core.text import normalize
from app.models import (
    AnalysisStatus,
    ArticleStatus,
    Category,
    KnowledgeArticle,
    Subcategory,
    Team,
    Ticket,
    TicketAIAnalysis,
    TicketEventType,
    TicketHistory,
    TicketMessage,
    TicketPriority,
    TicketStatus,
    TicketSuggestion,
    TicketSuggestionSource,
    User,
    UserRole,
)
from app.models.base import utcnow
from app.services import knowledge_service
from app.services.embeddings import HashingEmbedder
from app.services.sla import target as sla_target

DEMO_PASSWORD = "resolveai123"
PERIOD_DAYS = 90

# Team -> (description, categories: {category: (subcategories, ticket templates)})
CATALOG: dict[str, tuple[str, dict[str, list[str]]]] = {
    "ERP Fiscal": (
        "Emissão de documentos fiscais e obrigações acessórias.",
        {
            "Fiscal": ["NF-e", "NFS-e", "SPED"],
            "Tributos": ["ICMS", "ISS", "Reforma tributária"],
        },
    ),
    "Infraestrutura TI": (
        "Rede, servidores, VPN e disponibilidade.",
        {"Infraestrutura": ["Rede", "VPN", "Servidores"], "Backup": ["Rotinas", "Restauração"]},
    ),
    "Financeiro": (
        "Cobrança, contas a receber e conciliação.",
        {"Cobrança": ["Boletos", "Faturas"], "Conciliação": ["Extrato bancário", "Pix"]},
    ),
    "Suporte Geral": (
        "Primeiro atendimento e dúvidas de uso.",
        {"Acesso": ["Senha", "Permissões"]},
    ),
    "Estoque e Logística": (
        "Movimentação de estoque, inventário e expedição.",
        {"Estoque": ["Inventário", "Transferências"]},
    ),
    "Vendas e CRM": (
        "Pedidos, propostas e integrações comerciais.",
        {"Vendas": ["Pedidos", "Comissões"]},
    ),
    "Folha e RH": (
        "Folha de pagamento, férias e eSocial.",
        {"Folha de pagamento": ["eSocial", "Férias"]},
    ),
    "Integrações": ("APIs, webhooks e marketplaces.", {"Integrações": ["API", "Marketplaces"]}),
}

PROBLEMS: dict[str, list[tuple[str, str]]] = {
    "NF-e": [
        (
            "Rejeição 539 ao emitir NF-e",
            "A SEFAZ retorna duplicidade de NF-e com diferença na chave.",
        ),
        (
            "NF-e presa em processamento",
            "A nota está há mais de uma hora aguardando retorno da SEFAZ.",
        ),
        (
            "Erro de certificado ao transmitir NF-e",
            "Aparece certificado digital inválido ou expirado.",
        ),
    ],
    "NFS-e": [
        (
            "NFS-e rejeitada pela prefeitura",
            "O webservice do município devolve erro de comunicação.",
        )
    ],
    "SPED": [("Erro de validação no SPED Fiscal", "O PVA acusa inconsistência no registro C170.")],
    "ICMS": [
        ("Cálculo de ICMS-ST divergente", "O valor do ICMS-ST na nota não bate com a planilha.")
    ],
    "ISS": [
        (
            "Retenção de ISS não aparece",
            "A retenção de ISS não é calculada para o cliente de outro município.",
        )
    ],
    "Reforma tributária": [
        ("Campos de IBS e CBS na nota", "Precisamos preencher IBS e CBS nas notas de teste.")
    ],
    "Rede": [("Internet lenta na filial", "Toda a filial está com lentidão para acessar o ERP.")],
    "VPN": [("VPN desconectando", "A VPN cai a cada poucos minutos para a equipe comercial.")],
    "Servidores": [
        ("Sistema fora do ar", "Ninguém consegue acessar o ERP, tela branca após o login."),
        ("ERP muito lento", "As telas de faturamento demoram mais de um minuto para abrir."),
    ],
    "Rotinas": [
        ("Backup noturno falhou", "O relatório de backup indica falha na rotina de ontem.")
    ],
    "Restauração": [
        ("Restaurar arquivo apagado", "Um usuário apagou uma planilha da pasta compartilhada.")
    ],
    "Boletos": [
        ("Boleto com vencimento errado", "O boleto saiu com vencimento para o mês passado.")
    ],
    "Faturas": [("Fatura com valor duplicado", "O cliente recebeu a mesma fatura duas vezes.")],
    "Extrato bancário": [
        ("Extrato não importa", "O arquivo OFX do banco não é aceito na conciliação.")
    ],
    "Pix": [
        (
            "Pix recebido não baixou o título",
            "O pagamento via Pix não baixou o título automaticamente.",
        )
    ],
    "Senha": [
        ("Esqueci minha senha", "Não consigo acessar o ERP e o e-mail de redefinição não chega.")
    ],
    "Permissões": [
        ("Sem permissão para relatório", "Aparece acesso negado ao abrir o relatório de vendas.")
    ],
    "Inventário": [
        ("Divergência no inventário", "O saldo físico não bate com o saldo do sistema.")
    ],
    "Transferências": [
        ("Transferência entre filiais travada", "A transferência ficou pendente de recebimento.")
    ],
    "Pedidos": [("Pedido não gera nota", "O pedido aprovado não aparece para faturamento.")],
    "Comissões": [
        ("Comissão calculada errada", "O relatório de comissões ignora os descontos concedidos.")
    ],
    "eSocial": [("Evento do eSocial rejeitado", "O evento S-1200 voltou com erro de validação.")],
    "Férias": [("Férias não calculadas", "O recibo de férias saiu sem o terço constitucional.")],
    "API": [("Webhook de pedidos parou", "Nosso endpoint não recebe mais os webhooks de pedidos.")],
    "Marketplaces": [
        ("Pedidos do marketplace não integram", "Os pedidos do marketplace pararam de chegar.")
    ],
}

PRIORITY_WEIGHTS = {
    TicketPriority.LOW: 0.22,
    TicketPriority.MEDIUM: 0.43,
    TicketPriority.HIGH: 0.25,
    TicketPriority.CRITICAL: 0.10,
}
FIRST_NAMES = (
    "Ana Bruno Carla Diego Eduarda Felipe Gabriela Henrique Isabela João "
    "Karina Lucas Mariana Nicolas Olívia Pedro Rafaela Sérgio Tatiana Vinícius"
).split()
LAST_NAMES = (
    "Almeida Barbosa Cardoso Costa Dias Ferreira Gomes Lima Martins Melo "
    "Nascimento Oliveira Pereira Ribeiro Rocha Santos Silva Souza Teixeira Vieira"
).split()


@dataclass
class _Sub:
    subcategory: Subcategory
    category: Category
    team: Team
    agents: list[User]
    articles: list[KnowledgeArticle]


def generate(db: Session, users: int, articles: int, tickets: int, force: bool = False) -> str:
    rng = random.Random(42)
    admin = db.scalar(select(User).where(User.email == "admin@resolveai.dev"))
    if admin is None:
        raise SystemExit("Run `python -m app.scripts.seed` first.")
    org_id = admin.organization_id

    existing = db.scalar(select(func.count()).where(Ticket.organization_id == org_id)) or 0
    if existing > 100 and not force:
        return f"Demo data already present ({existing} tickets). Use --force to add more."

    password = hash_password(DEMO_PASSWORD)  # one hash for every demo user keeps this fast
    agents, requesters = _users(db, org_id, users, password, rng)
    subs = _catalog(db, org_id, agents, rng)
    _articles(db, admin, subs, articles, rng)
    created = _tickets(db, org_id, subs, requesters, tickets, rng)
    db.commit()
    return (
        f"Created {len(agents) + len(requesters)} users, {sum(len(s.articles) for s in subs)} "
        f"articles and {created} tickets. Demo logins use the password {DEMO_PASSWORD}."
    )


def _users(
    db: Session, org_id: int, count: int, password: str, rng: random.Random
) -> tuple[list[User], list[User]]:
    # Roughly one agent per twelve requesters, but never all of them.
    agent_count = min(max(2, count // 12), max(1, count // 2))
    # Continue numbering from the users already there, so --force never repeats an email.
    offset = db.scalar(select(func.count()).where(User.organization_id == org_id)) or 0
    created: list[User] = []
    for i in range(count):
        first, last = rng.choice(FIRST_NAMES), rng.choice(LAST_NAMES)
        role = UserRole.AGENT if i < agent_count else UserRole.USER
        created.append(
            User(
                organization_id=org_id,
                email=f"{normalize(first)}.{normalize(last)}.{offset + i}@demo.resolveai.dev",
                full_name=f"{first} {last}",
                hashed_password=password,
                role=role,
            )
        )
    db.add_all(created)
    db.flush()
    # Include the users seeded earlier, so small runs still have someone in each role.
    in_org = list(db.scalars(select(User).where(User.organization_id == org_id)))
    agents = [u for u in in_org if u.role in (UserRole.AGENT, UserRole.ADMIN)]
    requesters = [u for u in in_org if u.role == UserRole.USER]
    return agents, requesters


def _catalog(db: Session, org_id: int, agents: list[User], rng: random.Random) -> list[_Sub]:
    teams = {t.name: t for t in db.scalars(select(Team).where(Team.organization_id == org_id))}
    categories = {
        c.name: c for c in db.scalars(select(Category).where(Category.organization_id == org_id))
    }
    subs: list[_Sub] = []
    for team_index, (team_name, (description, category_map)) in enumerate(CATALOG.items()):
        team = teams.get(team_name) or Team(
            organization_id=org_id, name=team_name, description=description
        )
        db.add(team)
        team_agents = agents[team_index :: len(CATALOG)] or agents[:2]
        for agent in team_agents:
            if agent not in team.members:
                team.members.append(agent)
        for category_name, sub_names in category_map.items():
            category = categories.get(category_name) or Category(
                organization_id=org_id, name=category_name, default_team=team
            )
            db.add(category)
            existing_subs = {s.name: s for s in category.subcategories}
            for sub_name in sub_names:
                sub = existing_subs.get(sub_name)
                if sub is None:
                    sub = Subcategory(name=sub_name)
                    category.subcategories.append(sub)
                subs.append(_Sub(sub, category, team, team_agents, []))
    db.flush()
    return subs


def _articles(db: Session, author: User, subs: list[_Sub], count: int, rng: random.Random) -> None:
    existing = list(
        db.scalars(
            select(KnowledgeArticle).where(
                KnowledgeArticle.organization_id == author.organization_id
            )
        )
    )
    for article in existing:
        for sub in subs:
            if (
                article.category_id == sub.category.id
                and sub.subcategory.name.lower() in article.title.lower()
            ):
                sub.articles.append(article)

    new_articles: list[KnowledgeArticle] = []
    variants = ["Guia", "Solução", "Passo a passo", "Diagnóstico", "Perguntas frequentes"]
    for i in range(count):
        sub = subs[i % len(subs)]
        title, problem = rng.choice(PROBLEMS[sub.subcategory.name])
        article = KnowledgeArticle(
            organization_id=author.organization_id,
            title=(
                f"{variants[i % len(variants)]}: {title.lower()} ({sub.subcategory.name}) #{i + 1}"
            ),
            content=(
                f"Sintoma: {problem}\n\n"
                f"Causas comuns em {sub.subcategory.name}: configuração desatualizada, cadastro "
                "incompleto ou instabilidade no serviço externo.\n\n"
                "Como resolver:\n1. Confirme o sintoma e o horário em que começou.\n"
                f"2. Revise os parâmetros de {sub.category.name} > {sub.subcategory.name}.\n"
                "3. Reprocesse a operação e acompanhe o log.\n"
                f"4. Persistindo, encaminhe para a equipe {sub.team.name} com prints e o log."
            ),
            category=sub.category,
            tags=[
                sub.subcategory.name.lower().replace(" ", "-"),
                sub.category.name.lower().replace(" ", "-"),
            ],
            status=ArticleStatus.PUBLISHED if rng.random() > 0.08 else ArticleStatus.DRAFT,
            author=author,
        )
        new_articles.append(article)
        sub.articles.append(article)
    db.add_all(new_articles)
    db.flush()
    embedder = HashingEmbedder()
    for article in new_articles:
        knowledge_service.index_article(db, article, embedder)


def _tickets(
    db: Session,
    org_id: int,
    subs: list[_Sub],
    requesters: list[User],
    count: int,
    rng: random.Random,
) -> int:
    now = utcnow()
    batch: list[Ticket | TicketSuggestion] = []
    for _ in range(count):
        sub = rng.choice(subs)
        title, description = rng.choice(PROBLEMS[sub.subcategory.name])
        priority = rng.choices(list(PRIORITY_WEIGHTS), weights=list(PRIORITY_WEIGHTS.values()))[0]
        if title == "Sistema fora do ar":
            priority = TicketPriority.CRITICAL
        # Triangular with the peak at "today": volume grows as the product is adopted.
        days_ago = rng.triangular(0, PERIOD_DAYS, 0)
        created_at = _business_time(now - timedelta(days=days_ago), rng)
        ticket, suggestion = _ticket(
            org_id,
            sub,
            subs,
            rng.choice(requesters),
            title,
            description,
            priority,
            created_at,
            now,
            rng,
        )
        batch.append(ticket)
        if suggestion is not None:
            batch.append(suggestion)
        if len(batch) >= 500:
            db.add_all(batch)
            db.flush()
            batch.clear()
    db.add_all(batch)
    db.flush()
    return count


def _business_time(moment: datetime, rng: random.Random) -> datetime:
    """Most tickets arrive on weekdays during business hours (Brazil, UTC-3)."""
    if moment.weekday() >= 5 and rng.random() < 0.8:
        moment -= timedelta(days=moment.weekday() - 4)
    return moment.replace(hour=rng.choice(range(11, 22)), minute=rng.randrange(60))


def _ticket(
    org_id: int,
    sub: _Sub,
    all_subs: list[_Sub],
    requester: User,
    title: str,
    description: str,
    priority: TicketPriority,
    created_at: datetime,
    now: datetime,
    rng: random.Random,
) -> tuple[Ticket, TicketSuggestion | None]:
    age = now - created_at
    sla = sla_target(priority)
    assignee = rng.choice(sub.agents)
    first_response = created_at + sla * rng.uniform(0.05, 0.5)

    # Older tickets are mostly done, but a backlog always survives.
    # A healthy queue: almost everything older than a day is done, and the open work is recent.
    resolved_chance = 0.98 if age > timedelta(days=7) else 0.93 if age > timedelta(days=1) else 0.35
    if rng.random() < resolved_chance:
        resolved_at = created_at + sla * rng.lognormvariate(-0.35, 0.55)
        if resolved_at > now:
            resolved_at = None
    else:
        resolved_at = None

    # Closing follows the API's rule: some requesters confirm the solution within two days,
    # and whatever is still resolved after the auto-close window is closed by the system.
    closed_at: datetime | None = None
    closed_by_requester = False
    if resolved_at is not None:
        auto_close_at = resolved_at + timedelta(days=get_settings().auto_close_resolved_days)
        requester_close_at = resolved_at + timedelta(days=rng.uniform(0.02, 2))
        if rng.random() < 0.4 and requester_close_at <= now:
            closed_at, closed_by_requester = requester_close_at, True
        elif auto_close_at <= now:
            closed_at = auto_close_at
        status = TicketStatus.CLOSED if closed_at else TicketStatus.RESOLVED
    else:
        status = rng.choices(
            [TicketStatus.OPEN, TicketStatus.IN_PROGRESS, TicketStatus.WAITING_USER],
            weights=[0.35, 0.45, 0.2],
        )[0]
    if status == TicketStatus.OPEN:
        assignee = None

    ai_correct = rng.random() < 0.87
    ai_sub = sub if ai_correct else rng.choice([s for s in all_subs if s is not sub] or [sub])
    ai_priority = priority if rng.random() < 0.8 else rng.choice(list(TicketPriority))
    confidence = round(rng.uniform(0.72, 0.98) if ai_correct else rng.uniform(0.45, 0.8), 2)
    updated_at = closed_at or resolved_at or (first_response if assignee else created_at)

    ticket = Ticket(
        organization_id=org_id,
        title=title,
        description=f"{description} Chamado aberto por {requester.full_name}.",
        status=status,
        priority=priority,
        category=sub.category,
        subcategory=sub.subcategory,
        team=sub.team,
        requester=requester,
        assignee=assignee,
        created_at=created_at,
        updated_at=updated_at,
        resolved_at=resolved_at,
        ai_category=ai_sub.category,
        ai_subcategory=ai_sub.subcategory,
        ai_team=ai_sub.team,
        ai_priority=ai_priority,
        ai_confidence=confidence,
        ai_summary=f"{title}: {description.lower()}",
        ai_analyzed_at=created_at + timedelta(seconds=rng.uniform(2, 9)),
    )
    ticket.history.append(
        TicketHistory(actor=requester, event_type=TicketEventType.CREATED, created_at=created_at)
    )
    ai_label = (
        f"{ai_sub.category.name} / {ai_sub.subcategory.name} · "
        f"{ai_priority} · {round(confidence * 100)}%"
    )
    ticket.history.append(
        TicketHistory(
            event_type=TicketEventType.AI_ANALYZED,
            field="ai",
            new_value=ai_label,
            created_at=ticket.ai_analyzed_at,
        )
    )
    ticket.ai_analyses.append(
        TicketAIAnalysis(
            status=AnalysisStatus.SUCCEEDED,
            provider="demo",
            model="demo-data",
            category_name=ai_sub.category.name,
            subcategory_name=ai_sub.subcategory.name,
            team_name=ai_sub.team.name,
            priority=ai_priority,
            urgency=ai_priority,
            summary=ticket.ai_summary,
            confidence=confidence,
            applied_fields="team" if confidence >= 0.7 else None,
            created_at=ticket.ai_analyzed_at,
        )
    )
    if assignee is not None:
        ticket.history.append(
            TicketHistory(
                actor=assignee,
                event_type=TicketEventType.ASSIGNEE_CHANGED,
                field="assignee",
                new_value=assignee.full_name,
                created_at=first_response,
            )
        )
    if resolved_at is not None:
        ticket.messages.append(
            TicketMessage(
                author=assignee or sub.agents[0],
                body="Problema resolvido conforme o procedimento do artigo.",
                created_at=resolved_at,
            )
        )
        ticket.history.append(
            TicketHistory(
                actor=assignee,
                event_type=TicketEventType.RESOLVED,
                field="status",
                new_value="RESOLVED",
                created_at=resolved_at,
            )
        )
    if closed_at is not None:
        ticket.history.append(
            TicketHistory(
                actor=requester if closed_by_requester else None,
                event_type=(
                    TicketEventType.STATUS_CHANGED
                    if closed_by_requester
                    else TicketEventType.AUTO_CLOSED
                ),
                field="status",
                old_value="RESOLVED",
                new_value="CLOSED",
                created_at=closed_at,
            )
        )

    published = [a for a in sub.articles if a.status == ArticleStatus.PUBLISHED]
    if published and rng.random() < 0.7:
        retrieved = rng.sample(published, k=min(2, len(published)))
        best = retrieved[0]
        suggestion = TicketSuggestion(
            status=AnalysisStatus.SUCCEEDED,
            provider="demo",
            model="demo-data",
            embedding_model=HashingEmbedder.model,
            can_answer=True,
            # The answer must cite the article stored as the first source.
            answer=f"Consulte {best.code}: {best.title}.",
            created_at=ticket.ai_analyzed_at,
        )
        for rank, article in enumerate(retrieved, start=1):
            suggestion.sources.append(
                TicketSuggestionSource(
                    article_id=article.id,
                    article_code=article.code,
                    article_title=article.title[:200],
                    rank=rank,
                    score=round(rng.uniform(0.3, 0.6), 4),
                    cited=rank == 1,
                )
            )
        suggestion.ticket = ticket
        return ticket, suggestion
    return ticket, None


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--users", type=int, default=500)
    parser.add_argument("--articles", type=int, default=300)
    parser.add_argument("--tickets", type=int, default=5000)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    with SessionLocal() as db:
        print(generate(db, args.users, args.articles, args.tickets, args.force))


if __name__ == "__main__":
    main()
