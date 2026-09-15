# ResolveAI

AI-powered service desk that automatically classifies, prioritizes and routes support tickets while generating context-aware solutions using RAG.

> 🚧 Em desenvolvimento. **Etapas 1, 2 e 3 concluídas:** backend base, triagem automática com IA e base de conhecimento com RAG (sugestões de solução com fontes).

## Stack

Python 3.13 · FastAPI · Pydantic · SQLAlchemy 2 · Alembic · PostgreSQL + pgvector · JWT + Argon2 · Claude (Anthropic SDK) · Voyage AI (embeddings) · Pytest · Docker

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

### Usando o Claude na triagem

Por padrão a triagem usa um classificador local por palavras-chave (`AI_PROVIDER=keyword`), que é gratuito e não precisa de chave. Para usar o Claude, crie uma chave em https://console.anthropic.com e configure:

- Em `backend/.env`, defina `AI_PROVIDER=claude` e `ANTHROPIC_API_KEY=sk-ant-...`
- O mesmo arquivo é usado rodando local e via Docker (`docker compose up -d --build api`).
- Os créditos da API valem para qualquer modelo; o modelo usado é o de `AI_MODEL` (padrão `claude-haiku-4-5`).

### Usando a Voyage AI nos embeddings

Por padrão a busca usa embeddings locais (`EMBEDDING_PROVIDER=local`), gratuitos e offline, que comparam palavras. Para busca semântica de verdade (sinônimos, outras formas de escrever), crie uma chave em https://dashboard.voyageai.com. Os primeiros 200 milhões de tokens do `voyage-4-lite` são gratuitos por conta.

- Em `backend/.env`, defina `EMBEDDING_PROVIDER=voyage` e `VOYAGE_API_KEY=pa-...`
- Depois de trocar de provedor ou modelo, reindexe a base: `POST /knowledge/reindex` (admin). Vetores de modelos diferentes nunca são comparados entre si.

## Triagem com IA

```
Chamado criado
  ├─ Regras de prioridade (palavras-chave)  ┐ síncrono, já na resposta
  ├─ Roteamento pela categoria escolhida    ┘
  └─ Análise da IA (em segundo plano)
       ├─ Categoria, subcategoria, equipe, prioridade, urgência, resumo, confiança
       ├─ Sugestão sempre gravada (ai_* no chamado + ticket_ai_analyses)
       └─ Aplicada só se confiança ≥ AI_AUTO_APPLY_MIN_CONFIDENCE (padrão 0,7)
```

Regras que tornam a automação segura:

- **A IA só preenche campos vazios** e **nunca sobrescreve o que um atendente alterou** (verificado pelo histórico).
- **Regra de prioridade é piso:** se "sistema fora do ar" define CRITICAL, a IA pode subir a prioridade, mas nunca baixar.
- **Equipe padrão da categoria vence** a equipe sugerida pela IA; a sugestão só é usada quando a categoria não tem equipe padrão.
- **Nomes inventados são descartados:** categoria, subcategoria e equipe precisam existir no catálogo da organização.
- **Falha da IA não bloqueia nada:** o chamado é criado, as regras funcionam e a falha fica registrada (`AI_ANALYSIS_FAILED`).
- **Tudo é auditado:** eventos `RULE_APPLIED`, `AI_ANALYZED` e alterações feitas pelo sistema aparecem no histórico com `actor = null`.

Detalhes da integração com o Claude:

- Modelo padrão **`claude-haiku-4-5`**, o mais rápido e barato, suficiente para classificação. Dá para trocar por `AI_MODEL=claude-sonnet-5` ou `claude-opus-5` se for preciso mais precisão.
- **Saída estruturada:** schema Pydantic validado pelo SDK.
- **Opções por modelo:** `effort` e o fallback de recusa (`fallbacks="default"`) só são enviados aos modelos que os suportam (Sonnet/Opus e Opus 5/Fable, respectivamente), para nenhuma chamada falhar com erro 400.
- **Prompt caching:** instruções fixas + catálogo da organização ficam no prefixo cacheado; só o chamado varia.
- Timeouts, retries e erros do SDK mapeados para códigos próprios (`AI_TIMEOUT`, `AI_RATE_LIMITED`, `AI_AUTH_FAILED`...).
- Tokens de entrada/saída e latência gravados em cada análise.

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

No SQLite a similaridade é calculada em Python; no PostgreSQL a busca usa o operador `<=>` do pgvector com índice HNSW. Rode os dois antes de publicar mudanças na busca.

## Base de conhecimento e RAG

```
Artigo salvo ─► divisão em trechos (parágrafos, ~1.200 caracteres) ─► embeddings ─► pgvector
Chamado criado ─► embedding da pergunta ─► busca vetorial (cosseno, HNSW) ─► artigos relevantes
               ─► gerador de resposta (Claude ou extrativo) ─► sugestão + fontes citadas
```

- **Só artigos publicados** entram na busca; rascunhos e arquivados ficam de fora.
- **Nota mínima de similaridade** (`RAG_MIN_SCORE`): abaixo dela o artigo é ignorado. Para os embeddings locais, o padrão 0,15 foi medido nos artigos de exemplo (artigos certos: 0,24–0,36; sem relação: até 0,13).
- **A resposta só pode citar artigos que foram recuperados:** códigos inventados (ex.: `KB-999`) são descartados. Sem artigos relevantes, a sugestão diz que a base não cobre o chamado.
- **Fontes guardam código e título** do artigo no momento da sugestão, então continuam legíveis mesmo se o artigo for editado ou apagado.
- **Dois provedores de cada peça:** embeddings `local` (grátis) ou `voyage`; resposta `extractive` (cita o trecho mais relevante, grátis) ou `claude` (escreve a solução a partir dos artigos).
- **Falhas não bloqueiam nada:** a sugestão fica registrada como `FAILED` com o código do erro.

## Estrutura do backend

```
backend/
├── app/
│   ├── api/          # Rotas FastAPI (finas: validam entrada e delegam)
│   ├── core/         # Config, banco, segurança, erros, logs
│   ├── models/       # Modelos SQLAlchemy
│   ├── schemas/      # Contratos Pydantic de entrada/saída
│   ├── services/     # Regras de negócio (triage, ai_classifier, knowledge, embeddings, rag...)
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

## API

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
| POST | `/tickets/{id}/ai/analyze` | Agente/admin (reanalisa agora) |
| GET | `/tickets/{id}/ai/analyses` | Agente/admin |
| GET · POST · PATCH · DELETE | `/priority-rules`, `/priority-rules/{id}` | Leitura: agente/admin · Escrita: admin |
| GET · POST · PATCH · DELETE | `/knowledge`, `/knowledge/{id}` | Leitura: todos (solicitante só publicados) · Escrita: admin |
| GET | `/knowledge/search?q=` | Autenticado (busca semântica em artigos publicados) |
| POST | `/knowledge/reindex` | Admin |
| POST | `/tickets/{id}/ai/suggest` | Agente/admin (gera sugestão agora) |
| GET | `/tickets/{id}/ai/suggestions` | Agente/admin |

## Roadmap

- [x] **Etapa 1** — FastAPI, PostgreSQL, auth, usuários, chamados, equipes, categorias
- [x] **Etapa 2** — Classificação por IA (Claude), prioridade por regras + IA, roteamento, confidence score
- [x] **Etapa 3** — Base de conhecimento, embeddings (Voyage), pgvector, RAG com fontes
- [ ] **Etapa 4** — Frontend React, dashboard, CI/CD com GitHub Actions, deploy

## Licença

MIT
