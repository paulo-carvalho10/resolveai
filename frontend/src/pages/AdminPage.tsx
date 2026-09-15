import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";
import { useState } from "react";
import type { FormEvent } from "react";

import { PageHeader } from "../components/Layout";
import { Badge, Card, ErrorMessage, Field, Spinner } from "../components/ui";
import { api } from "../lib/api";
import { errorMessage } from "../lib/errors";
import { formatDateTime } from "../lib/format";
import { TICKET_PRIORITY, USER_ROLE } from "../lib/labels";
import type { Category, Page, PriorityRule, Role, Team, User } from "../lib/types";

const TABS = [
  { id: "usuarios", label: "Usuários" },
  { id: "equipes", label: "Equipes" },
  { id: "categorias", label: "Categorias" },
  { id: "regras", label: "Regras de prioridade" },
  { id: "base", label: "Base de conhecimento" },
] as const;

export function AdminPage() {
  const [tab, setTab] = useState<(typeof TABS)[number]["id"]>("usuarios");

  return (
    <>
      <PageHeader
        title="Administração"
        description="Usuários, equipes, categorias e as regras que a automação segue."
      />

      <div className="mb-4 flex flex-wrap gap-1 border-b border-border">
        {TABS.map((item) => (
          <button
            key={item.id}
            type="button"
            onClick={() => setTab(item.id)}
            className={`-mb-px border-b-2 px-3 py-2 text-sm font-medium transition-colors ${
              tab === item.id
                ? "border-brand text-brand"
                : "border-transparent text-text-muted hover:text-text"
            }`}
          >
            {item.label}
          </button>
        ))}
      </div>

      {tab === "usuarios" && <UsersTab />}
      {tab === "equipes" && <TeamsTab />}
      {tab === "categorias" && <CategoriesTab />}
      {tab === "regras" && <RulesTab />}
      {tab === "base" && <KnowledgeAdminTab />}
    </>
  );
}

function UsersTab() {
  const queryClient = useQueryClient();
  const [form, setForm] = useState({ full_name: "", email: "", password: "", role: "USER" as Role });

  const users = useQuery({
    queryKey: ["users"],
    queryFn: () => api<Page<User>>("/users", { params: { page_size: 50 } }),
  });
  const create = useMutation({
    mutationFn: () => api<User>("/users", { method: "POST", body: form }),
    onSuccess: () => {
      setForm({ full_name: "", email: "", password: "", role: "USER" });
      void queryClient.invalidateQueries({ queryKey: ["users"] });
    },
  });
  const update = useMutation({
    mutationFn: ({ id, body }: { id: number; body: Record<string, unknown> }) =>
      api<User>(`/users/${id}`, { method: "PATCH", body }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["users"] }),
  });

  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
      <Card title="Usuários" className="overflow-hidden">
        {users.isPending && <Spinner />}
        {update.error && <ErrorMessage>{errorMessage(update.error)}</ErrorMessage>}
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="border-b border-border text-left text-xs text-text-muted">
              <tr>
                <th className="py-2 font-medium">Nome</th>
                <th className="py-2 font-medium">Papel</th>
                <th className="py-2 font-medium">Situação</th>
              </tr>
            </thead>
            <tbody>
              {users.data?.items.map((person) => (
                <tr key={person.id} className="border-b border-border/70 last:border-0">
                  <td className="py-2">
                    <p className="font-medium text-text">{person.full_name}</p>
                    <p className="text-xs text-text-muted">{person.email}</p>
                  </td>
                  <td className="py-2">
                    <select
                      className="input w-36 py-1"
                      value={person.role}
                      onChange={(event) =>
                        update.mutate({ id: person.id, body: { role: event.target.value } })
                      }
                    >
                      {Object.entries(USER_ROLE).map(([value, label]) => (
                        <option key={value} value={value}>
                          {label}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td className="py-2">
                    <button
                      type="button"
                      className="btn-ghost"
                      onClick={() =>
                        update.mutate({ id: person.id, body: { is_active: !person.is_active } })
                      }
                    >
                      <Badge tone={person.is_active ? "done" : "neutral"}>
                        {person.is_active ? "Ativo" : "Inativo"}
                      </Badge>
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <Card title="Novo usuário">
        <form
          className="space-y-3"
          onSubmit={(event: FormEvent) => {
            event.preventDefault();
            create.mutate();
          }}
        >
          <Field label="Nome">
            <input
              className="input"
              required
              value={form.full_name}
              onChange={(event) => setForm({ ...form, full_name: event.target.value })}
            />
          </Field>
          <Field label="E-mail">
            <input
              className="input"
              type="email"
              required
              value={form.email}
              onChange={(event) => setForm({ ...form, email: event.target.value })}
            />
          </Field>
          <Field label="Senha" hint="Mínimo de 8 caracteres.">
            <input
              className="input"
              type="password"
              required
              minLength={8}
              value={form.password}
              onChange={(event) => setForm({ ...form, password: event.target.value })}
            />
          </Field>
          <Field label="Papel">
            <select
              className="input"
              value={form.role}
              onChange={(event) => setForm({ ...form, role: event.target.value as Role })}
            >
              {Object.entries(USER_ROLE).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </Field>
          {create.error && <ErrorMessage>{errorMessage(create.error)}</ErrorMessage>}
          <button type="submit" className="btn-primary w-full" disabled={create.isPending}>
            Criar usuário
          </button>
        </form>
      </Card>
    </div>
  );
}

function TeamsTab() {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const teams = useQuery({ queryKey: ["teams"], queryFn: () => api<Team[]>("/teams") });
  const create = useMutation({
    mutationFn: () => api<Team>("/teams", { method: "POST", body: { name } }),
    onSuccess: () => {
      setName("");
      void queryClient.invalidateQueries({ queryKey: ["teams"] });
    },
  });

  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
      <Card title="Equipes">
        {teams.isPending && <Spinner />}
        <ul className="space-y-3">
          {teams.data?.map((team) => (
            <li key={team.id} className="border-b border-border pb-3 last:border-0 last:pb-0">
              <p className="text-sm font-medium text-text">{team.name}</p>
              <p className="text-xs text-text-muted">
                {team.description ?? "Sem descrição"} · {team.members.length} membro(s)
              </p>
            </li>
          ))}
        </ul>
      </Card>
      <Card title="Nova equipe">
        <form
          className="space-y-3"
          onSubmit={(event: FormEvent) => {
            event.preventDefault();
            create.mutate();
          }}
        >
          <Field label="Nome">
            <input className="input" required value={name} onChange={(e) => setName(e.target.value)} />
          </Field>
          {create.error && <ErrorMessage>{errorMessage(create.error)}</ErrorMessage>}
          <button type="submit" className="btn-primary w-full" disabled={create.isPending}>
            Criar equipe
          </button>
        </form>
      </Card>
    </div>
  );
}

function CategoriesTab() {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [teamId, setTeamId] = useState("");
  const categories = useQuery({
    queryKey: ["categories", "all"],
    queryFn: () => api<Category[]>("/categories", { params: { include_inactive: true } }),
  });
  const teams = useQuery({ queryKey: ["teams"], queryFn: () => api<Team[]>("/teams") });
  const create = useMutation({
    mutationFn: () =>
      api<Category>("/categories", {
        method: "POST",
        body: { name, default_team_id: teamId ? Number(teamId) : null },
      }),
    onSuccess: () => {
      setName("");
      void queryClient.invalidateQueries({ queryKey: ["categories"] });
    },
  });

  const teamName = (id: number | null) => teams.data?.find((team) => team.id === id)?.name;

  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
      <Card title="Categorias">
        {categories.isPending && <Spinner />}
        <ul className="space-y-3">
          {categories.data?.map((category) => (
            <li key={category.id} className="border-b border-border pb-3 last:border-0 last:pb-0">
              <div className="flex flex-wrap items-center gap-2">
                <p className="text-sm font-medium text-text">{category.name}</p>
                {!category.is_active && <Badge tone="neutral">Inativa</Badge>}
                {category.default_team_id && (
                  <Badge tone="brand">→ {teamName(category.default_team_id) ?? "equipe"}</Badge>
                )}
              </div>
              <p className="mt-1 text-xs text-text-muted">
                {category.subcategories.map((sub) => sub.name).join(" · ") || "Sem subcategorias"}
              </p>
            </li>
          ))}
        </ul>
      </Card>
      <Card title="Nova categoria">
        <form
          className="space-y-3"
          onSubmit={(event: FormEvent) => {
            event.preventDefault();
            create.mutate();
          }}
        >
          <Field label="Nome">
            <input className="input" required value={name} onChange={(e) => setName(e.target.value)} />
          </Field>
          <Field label="Equipe padrão" hint="Chamados desta categoria vão para esta equipe.">
            <select className="input" value={teamId} onChange={(e) => setTeamId(e.target.value)}>
              <option value="">Nenhuma</option>
              {teams.data?.map((team) => (
                <option key={team.id} value={team.id}>
                  {team.name}
                </option>
              ))}
            </select>
          </Field>
          {create.error && <ErrorMessage>{errorMessage(create.error)}</ErrorMessage>}
          <button type="submit" className="btn-primary w-full" disabled={create.isPending}>
            Criar categoria
          </button>
        </form>
      </Card>
    </div>
  );
}

function RulesTab() {
  const queryClient = useQueryClient();
  const [form, setForm] = useState({ name: "", keywords: "", priority: "HIGH" });
  const rules = useQuery({
    queryKey: ["priority-rules"],
    queryFn: () => api<PriorityRule[]>("/priority-rules"),
  });
  const create = useMutation({
    mutationFn: () =>
      api<PriorityRule>("/priority-rules", {
        method: "POST",
        body: {
          name: form.name,
          priority: form.priority,
          keywords: form.keywords
            .split(",")
            .map((keyword) => keyword.trim())
            .filter(Boolean),
        },
      }),
    onSuccess: () => {
      setForm({ name: "", keywords: "", priority: "HIGH" });
      void queryClient.invalidateQueries({ queryKey: ["priority-rules"] });
    },
  });
  const toggle = useMutation({
    mutationFn: (rule: PriorityRule) =>
      api<PriorityRule>(`/priority-rules/${rule.id}`, {
        method: "PATCH",
        body: { is_active: !rule.is_active },
      }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["priority-rules"] }),
  });

  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
      <Card title="Regras de prioridade">
        <p className="mb-4 text-sm text-text-muted">
          Se o chamado contém alguma das palavras, ele recebe no mínimo essa prioridade. A regra é
          um piso: a IA pode subir a prioridade, nunca baixar.
        </p>
        {rules.isPending && <Spinner />}
        <ul className="space-y-3">
          {rules.data?.map((rule) => (
            <li key={rule.id} className="border-b border-border pb-3 last:border-0 last:pb-0">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm font-medium text-text">{rule.name}</span>
                <Badge tone={TICKET_PRIORITY[rule.priority].tone}>
                  {TICKET_PRIORITY[rule.priority].label}
                </Badge>
                <button type="button" className="btn-ghost py-0.5" onClick={() => toggle.mutate(rule)}>
                  <Badge tone={rule.is_active ? "done" : "neutral"}>
                    {rule.is_active ? "Ativa" : "Inativa"}
                  </Badge>
                </button>
              </div>
              <p className="mt-1 text-xs text-text-muted">{rule.keywords.join(" · ")}</p>
            </li>
          ))}
        </ul>
      </Card>
      <Card title="Nova regra">
        <form
          className="space-y-3"
          onSubmit={(event: FormEvent) => {
            event.preventDefault();
            create.mutate();
          }}
        >
          <Field label="Nome">
            <input
              className="input"
              required
              value={form.name}
              onChange={(event) => setForm({ ...form, name: event.target.value })}
            />
          </Field>
          <Field label="Palavras-chave" hint="Separadas por vírgula. Ignora acentos e maiúsculas.">
            <input
              className="input"
              required
              placeholder="sistema fora do ar, parou tudo"
              value={form.keywords}
              onChange={(event) => setForm({ ...form, keywords: event.target.value })}
            />
          </Field>
          <Field label="Prioridade mínima">
            <select
              className="input"
              value={form.priority}
              onChange={(event) => setForm({ ...form, priority: event.target.value })}
            >
              {Object.entries(TICKET_PRIORITY).map(([value, meta]) => (
                <option key={value} value={value}>
                  {meta.label}
                </option>
              ))}
            </select>
          </Field>
          {create.error && <ErrorMessage>{errorMessage(create.error)}</ErrorMessage>}
          <button type="submit" className="btn-primary w-full" disabled={create.isPending}>
            Criar regra
          </button>
        </form>
      </Card>
    </div>
  );
}

function KnowledgeAdminTab() {
  const reindex = useMutation({
    mutationFn: () => api<{ articles: number }>("/knowledge/reindex", { method: "POST", body: {} }),
  });
  const articles = useQuery({
    queryKey: ["knowledge", "admin"],
    queryFn: () => api<Page<never>>("/knowledge", { params: { page_size: 1 } }),
  });

  return (
    <Card title="Base de conhecimento">
      <p className="text-sm text-text-muted">
        {articles.data ? `${articles.data.total} artigo(s) cadastrado(s).` : "Carregando..."} A
        indexação roda em segundo plano quando um artigo é criado ou editado.
      </p>
      <p className="mt-3 text-sm text-text-muted">
        Reindexe depois de trocar o provedor ou o modelo de embeddings: vetores de modelos
        diferentes não são comparáveis entre si.
      </p>
      <button
        type="button"
        className="btn-secondary mt-4"
        onClick={() => reindex.mutate()}
        disabled={reindex.isPending}
      >
        <RefreshCw aria-hidden className={`size-4 ${reindex.isPending ? "animate-spin" : ""}`} />
        Reindexar todos os artigos
      </button>
      {reindex.error && (
        <div className="mt-3">
          <ErrorMessage>{errorMessage(reindex.error)}</ErrorMessage>
        </div>
      )}
      {reindex.data && (
        <p className="mt-3 text-sm text-state-done">
          Reindexação iniciada para {reindex.data.articles} artigo(s) em{" "}
          {formatDateTime(new Date())}.
        </p>
      )}
    </Card>
  );
}
