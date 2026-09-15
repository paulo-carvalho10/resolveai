# ResolveAI

AI-powered service desk that automatically classifies, prioritizes and routes support tickets while generating context-aware solutions using RAG.

> 🚧 Em desenvolvimento. **Etapa 1 concluída:** backend base (auth, usuários, papéis, equipes, categorias e chamados).

## Stack

Python 3.13 · FastAPI · Pydantic · SQLAlchemy 2 · Alembic · PostgreSQL + pgvector · JWT + Argon2 · Pytest · Docker

## Rodando localmente

Pré-requisitos: Python 3.13+ e Docker Desktop.

```bash
# 1. Banco de dados
docker compose up -d db

# 2. Backend
cd backend
python -m venv .venv
.venv\Scripts\activate          # Linux/macOS: source .venv/bin/activate
pip install -r requirements-dev.txt
copy .env.example .env          # Linux/macOS: cp .env.example .env

alembic upgrade head
python -m app.scripts.seed
uvicorn app.main:app --reload
```

API em http://localhost:8000 e documentação interativa em http://localhost:8000/docs.

Logins criados pelo seed (senha `resolveai123`):

| Papel | E-mail |
| --- | --- |
| Administrador | admin@resolveai.dev |
| Atendente | agent@resolveai.dev |
| Solicitante | user@resolveai.dev |

### Tudo via Docker

```bash
docker compose up --build
```

## Testes

```bash
cd backend
pytest --cov
```

Os testes rodam em SQLite em memória por padrão. Para rodar contra o PostgreSQL:

```bash
TEST_DATABASE_URL=postgresql+psycopg://resolveai:resolveai@127.0.0.1:5432/resolveai_test pytest
```

> **Windows:** use `127.0.0.1` e não `localhost` nas URLs do banco. O `localhost` resolve primeiro para o IPv6 (`::1`), onde o repasse de portas do WSL pode aceitar a conexão sem encaminhá-la, e a conexão trava.

## Estrutura do backend

```
backend/
├── app/
│   ├── api/          # Rotas FastAPI (finas: validam entrada e delegam)
│   ├── core/         # Config, banco, segurança, erros, logs
│   ├── models/       # Modelos SQLAlchemy
│   ├── schemas/      # Contratos Pydantic de entrada/saída
│   ├── services/     # Regras de negócio
│   └── scripts/      # Seed
├── migrations/       # Alembic
└── tests/
```

## Decisões de arquitetura

- **Monólito modular** com camadas `api → services → models`. As rotas não contêm regra de negócio.
- **Multi-tenant desde o início:** toda entidade pertence a uma `organization`, e todo acesso é filtrado por ela. Recursos de outra organização retornam 404.
- **RBAC** com três papéis: `ADMIN`, `AGENT` e `USER`. Solicitantes só enxergam os próprios chamados.
- **Auditoria:** toda alteração de chamado gera um evento em `ticket_history`, com valores legíveis capturados no momento da mudança.
- **Enums como VARCHAR:** adicionar um status ou prioridade não exige `ALTER TYPE` no PostgreSQL.
- **Erros padronizados:** `{"error": {"code": "TICKET_NOT_FOUND", "message": "Ticket not found."}}`.
- **Logs estruturados:** `2026-09-14T14:35:12+00:00 INFO ticket.created ticket_id=527 user_id=42`.

## API (Etapa 1)

| Método | Rota | Acesso |
| --- | --- | --- |
| POST | `/auth/register` | Público (cria organização + admin) |
| POST | `/auth/login` · `/auth/refresh` | Público |
| GET | `/auth/me` | Autenticado |
| GET · POST · PATCH | `/users`, `/users/{id}` | Leitura: agente/admin · Escrita: admin |
| GET · POST · PATCH · DELETE | `/teams`, `/teams/{id}`, `/teams/{id}/members` | Leitura: agente/admin · Escrita: admin |
| GET · POST · PATCH · DELETE | `/categories`, `/subcategories/{id}` | Leitura: todos · Escrita: admin |
| GET · POST | `/tickets` | Todos (solicitante vê só os seus) |
| GET · PATCH · DELETE | `/tickets/{id}` | PATCH: agente/admin · DELETE: admin |
| POST | `/tickets/{id}/assign` · `/tickets/{id}/resolve` | Agente/admin |
| GET · POST | `/tickets/{id}/messages` | Todos (notas internas só para agentes) |
| GET | `/tickets/{id}/history` | Agente/admin |

## Roadmap

- [x] **Etapa 1** — FastAPI, PostgreSQL, auth, usuários, chamados, equipes, categorias
- [ ] **Etapa 2** — Classificação por IA (Claude), prioridade por regras + IA, roteamento, confidence score
- [ ] **Etapa 3** — Base de conhecimento, embeddings (Voyage), pgvector, RAG com fontes
- [ ] **Etapa 4** — Frontend React, dashboard, CI/CD com GitHub Actions, deploy

## Licença

MIT
