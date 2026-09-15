# Deploy

Guia para publicar o ResolveAI usando planos gratuitos. Os arquivos de configuração já estão no repositório:

- [`render.yaml`](../render.yaml) — API (Docker) no Render
- [`frontend/vercel.json`](../frontend/vercel.json) — frontend na Vercel

> Planos gratuitos mudam com o tempo. Confira os limites atuais de cada serviço antes de começar. No plano gratuito do Render, a API **hiberna** quando fica sem uso, e a primeira chamada depois disso demora alguns segundos.

## 1. Banco de dados (Neon)

O banco precisa do **PostgreSQL 16+ com a extensão `pgvector`**.

1. Crie um projeto em https://neon.com (ou use Supabase / Render Postgres).
2. Copie a *connection string*, algo como
   `postgresql://usuario:senha@ep-xxx.aws.neon.tech/neondb?sslmode=require`.
3. Troque o esquema para o driver do projeto: `postgresql+psycopg://...`.

A migration `0003` roda `CREATE EXTENSION IF NOT EXISTS vector`, então não é preciso ativar a extensão na mão.

## 2. API (Render)

1. Em https://render.com, escolha **New → Blueprint** e aponte para este repositório. O Render lê o `render.yaml`.
2. Preencha as variáveis que ele pedir:
   - `DATABASE_URL`: a string do passo 1 (com `postgresql+psycopg://`)
   - `CORS_ORIGINS`: por enquanto `["http://localhost:5173"]`; ajuste depois da Vercel
   - `ANTHROPIC_API_KEY` e `VOYAGE_API_KEY`: deixe em branco para usar os provedores locais gratuitos
   - `JWT_SECRET_KEY` é gerado automaticamente
3. Publique. O container roda `alembic upgrade head` sozinho antes de subir a API.
4. Confira `https://SUA-API.onrender.com/health` e a documentação em `/docs`.

**Dados iniciais:** no Shell do serviço (aba *Shell* do Render), rode:

```bash
python -m app.scripts.seed        # organização, logins e artigos de exemplo
python -m app.scripts.demo_data   # opcional: 5.000 chamados para a demonstração
```

> Troque as senhas dos usuários de demonstração se a instância for pública, ou crie a sua organização em `POST /auth/register` e apague a de exemplo.

## 3. Frontend (Vercel)

1. Em https://vercel.com, **Add New → Project**, importe o repositório.
2. Em **Root Directory**, escolha `frontend`. O `vercel.json` cuida do resto.
3. Variável de ambiente:
   - `VITE_API_URL` = `https://SUA-API.onrender.com`
4. Publique e copie a URL final (ex.: `https://resolveai.vercel.app`).

## 4. Fechar o circuito

No Render, atualize `CORS_ORIGINS` com a URL da Vercel e publique de novo:

```json
["https://resolveai.vercel.app"]
```

Sem isso o navegador bloqueia as chamadas da aplicação para a API.

## 5. Checklist final

- [ ] `https://SUA-API.onrender.com/health` responde `{"status":"ok"}`
- [ ] Login funciona pela URL da Vercel
- [ ] O dashboard carrega os indicadores
- [ ] A busca da base de conhecimento retorna artigos
- [ ] `JWT_SECRET_KEY` **não** é o valor padrão de desenvolvimento
- [ ] `ENVIRONMENT=production` (a API recusa subir com o segredo padrão nesse modo)

## Alternativas

- **Railway / Fly.io** no lugar do Render: ambos sobem o mesmo `backend/Dockerfile`. Mantenha as variáveis desta lista.
- **Tudo em um servidor só** (VPS): `docker compose up -d --build` já sobe banco, API e frontend; coloque um proxy com HTTPS na frente.
