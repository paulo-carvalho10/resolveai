import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BookOpen, Bot, CheckCircle2, Clock, Lock, RefreshCw, UserCheck } from "lucide-react";
import { useState } from "react";
import type { FormEvent } from "react";
import { Link, useParams } from "react-router";

import { useAuth } from "../auth/AuthProvider";
import { PageHeader } from "../components/Layout";
import { Badge, Card, EmptyState, ErrorMessage, Spinner } from "../components/ui";
import { api } from "../lib/api";
import { errorMessage } from "../lib/errors";
import { formatDateTime, formatDeadline, formatPercent, formatRelative } from "../lib/format";
import {
  SLA_STATUS,
  TICKET_PRIORITY,
  TICKET_STATUS,
  translateEvent,
  translateValue,
} from "../lib/labels";
import type {
  Category,
  HistoryEntry,
  Suggestion,
  Team,
  Ticket,
  TicketMessage,
  User,
} from "../lib/types";

export function TicketDetailPage() {
  const { id } = useParams();
  const ticketId = Number(id);
  const { isStaff, user } = useAuth();
  const queryClient = useQueryClient();

  const ticket = useQuery({
    queryKey: ["ticket", ticketId],
    queryFn: () => api<Ticket>(`/tickets/${ticketId}`),
  });
  const messages = useQuery({
    queryKey: ["ticket", ticketId, "messages"],
    queryFn: () => api<TicketMessage[]>(`/tickets/${ticketId}/messages`),
  });
  const history = useQuery({
    queryKey: ["ticket", ticketId, "history"],
    queryFn: () => api<HistoryEntry[]>(`/tickets/${ticketId}/history`),
    enabled: isStaff,
  });
  const suggestions = useQuery({
    queryKey: ["ticket", ticketId, "suggestions"],
    queryFn: () => api<Suggestion[]>(`/tickets/${ticketId}/ai/suggestions`),
    enabled: isStaff,
  });

  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ["ticket", ticketId] });
    void queryClient.invalidateQueries({ queryKey: ["tickets"] });
  };

  const patch = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api<Ticket>(`/tickets/${ticketId}`, { method: "PATCH", body }),
    onSuccess: refresh,
  });
  const assign = useMutation({
    // Without an id the API assigns the ticket to whoever is calling.
    mutationFn: (assigneeId?: number) =>
      api<Ticket>(`/tickets/${ticketId}/assign`, {
        method: "POST",
        body: { assignee_id: assigneeId ?? null },
      }),
    onSuccess: refresh,
  });
  const resolve = useMutation({
    mutationFn: (resolution: string) =>
      api<Ticket>(`/tickets/${ticketId}/resolve`, { method: "POST", body: { resolution } }),
    onSuccess: refresh,
  });
  const suggest = useMutation({
    mutationFn: () => api<Suggestion>(`/tickets/${ticketId}/ai/suggest`, { method: "POST", body: {} }),
    onSuccess: refresh,
  });

  if (ticket.isPending) return <Spinner />;
  if (ticket.error || !ticket.data) return <ErrorMessage>{errorMessage(ticket.error)}</ErrorMessage>;

  const data = ticket.data;
  const closed = data.status === "CLOSED";
  const suggestion = suggestions.data?.[0];
  const actionError = patch.error ?? assign.error ?? resolve.error ?? suggest.error;

  return (
    <>
      <PageHeader
        title={`#${data.id} ${data.title}`}
        description={`Aberto por ${data.requester.full_name} · ${formatDateTime(data.created_at)}`}
        action={
          isStaff && !closed ? (
            <div className="flex flex-wrap gap-2">
              {data.assignee?.id !== user?.id && (
                <button
                  className="btn-secondary"
                  onClick={() => assign.mutate(undefined)}
                  disabled={assign.isPending}
                >
                  <UserCheck aria-hidden className="size-4" />
                  Assumir
                </button>
              )}
              <button
                className="btn-secondary"
                onClick={() => suggest.mutate()}
                disabled={suggest.isPending}
              >
                <RefreshCw aria-hidden className={`size-4 ${suggest.isPending ? "animate-spin" : ""}`} />
                Nova sugestão
              </button>
            </div>
          ) : undefined
        }
      />

      {actionError && (
        <div className="mb-4">
          <ErrorMessage>{errorMessage(actionError)}</ErrorMessage>
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
        <div className="space-y-4">
          <Card>
            <div className="mb-4 flex flex-wrap items-center gap-2">
              <Badge tone={TICKET_STATUS[data.status].tone}>{TICKET_STATUS[data.status].label}</Badge>
              <Badge tone={TICKET_PRIORITY[data.priority].tone}>
                {TICKET_PRIORITY[data.priority].label}
              </Badge>
              <Badge tone={SLA_STATUS[data.sla_status].tone}>
                <Clock aria-hidden className="size-3" />
                {data.resolved_at
                  ? SLA_STATUS[data.sla_status].label
                  : formatDeadline(data.sla_due_at)}
              </Badge>
            </div>
            <p className="text-sm whitespace-pre-wrap text-text">{data.description}</p>
          </Card>

          {isStaff && suggestion && <SuggestionCard suggestion={suggestion} />}

          <Card title="Conversa">
            {messages.isPending && <Spinner />}
            {messages.data?.length === 0 && (
              <EmptyState title="Nenhuma mensagem ainda" description="Responda o solicitante abaixo." />
            )}
            <ul className="space-y-4">
              {messages.data?.map((message) => (
                <li key={message.id} className="border-b border-border pb-4 last:border-0 last:pb-0">
                  <div className="mb-1 flex flex-wrap items-center gap-2 text-xs text-text-muted">
                    <span className="font-medium text-text">{message.author.full_name}</span>
                    <span>{formatDateTime(message.created_at)}</span>
                    {message.is_internal && (
                      <Badge tone="waiting">
                        <Lock aria-hidden className="size-3" />
                        Nota interna
                      </Badge>
                    )}
                  </div>
                  <p className="text-sm whitespace-pre-wrap text-text">{message.body}</p>
                </li>
              ))}
            </ul>
            {!closed && <MessageForm ticketId={ticketId} canWriteInternal={isStaff} onSent={refresh} />}
          </Card>

          {isStaff && (
            <Card title="Histórico">
              {history.isPending && <Spinner />}
              <ol className="space-y-3">
                {history.data?.map((entry) => (
                  <li key={entry.id} className="flex gap-3 text-sm">
                    <span className="mt-1.5 size-2 shrink-0 rounded-full bg-border" aria-hidden />
                    <div>
                      <p className="text-text">
                        {translateEvent(entry.event_type as never)}
                        {entry.new_value && (
                          <>
                            :{" "}
                            <span className="font-medium">
                              {translateValue(entry.old_value) && `${translateValue(entry.old_value)} → `}
                              {translateValue(entry.new_value)}
                            </span>
                          </>
                        )}
                      </p>
                      <p className="text-xs text-text-muted">
                        {entry.actor?.full_name ?? "Sistema"} · {formatDateTime(entry.created_at)}
                      </p>
                    </div>
                  </li>
                ))}
              </ol>
            </Card>
          )}
        </div>

        <div className="space-y-4">
          <Card title="Detalhes">
            <dl className="space-y-3 text-sm">
              <Detail label="Solicitante" value={data.requester.full_name} />
              <Detail label="Responsável" value={data.assignee?.full_name ?? "Sem responsável"} />
              <Detail label="Equipe" value={data.team?.name ?? "Sem equipe"} />
              <Detail
                label="Categoria"
                value={
                  data.category
                    ? `${data.category.name}${data.subcategory ? ` / ${data.subcategory.name}` : ""}`
                    : "Sem categoria"
                }
              />
              <Detail label="Prazo (SLA)" value={formatDateTime(data.sla_due_at)} />
              <Detail label="Atualizado" value={formatRelative(data.updated_at)} />
              {data.resolved_at && (
                <Detail label="Resolvido em" value={formatDateTime(data.resolved_at)} />
              )}
            </dl>
          </Card>

          {data.ai_analyzed_at && <AnalysisCard ticket={data} />}

          {isStaff && !closed && (
            <TriagePanel
              ticket={data}
              onPatch={(body) => patch.mutate(body)}
              onAssign={(assigneeId) => assign.mutate(assigneeId)}
              onResolve={(text) => resolve.mutate(text)}
              busy={patch.isPending || resolve.isPending || assign.isPending}
            />
          )}
        </div>
      </div>
    </>
  );
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-3">
      <dt className="text-text-muted">{label}</dt>
      <dd className="text-right font-medium text-text">{value}</dd>
    </div>
  );
}

function AnalysisCard({ ticket }: { ticket: Ticket }) {
  const confidence = ticket.ai_confidence ?? 0;
  const tone = confidence >= 0.7 ? "done" : confidence >= 0.5 ? "waiting" : "danger";
  return (
    <Card
      title={
        <h2 className="flex items-center gap-2 text-sm font-semibold">
          <Bot aria-hidden className="size-4 text-brand" />
          Análise da IA
        </h2>
      }
    >
      <dl className="space-y-3 text-sm">
        <Detail
          label="Categoria sugerida"
          value={
            ticket.ai_category
              ? `${ticket.ai_category.name}${ticket.ai_subcategory ? ` / ${ticket.ai_subcategory.name}` : ""}`
              : "Nenhuma"
          }
        />
        <Detail
          label="Prioridade sugerida"
          value={ticket.ai_priority ? TICKET_PRIORITY[ticket.ai_priority].label : "—"}
        />
        <Detail label="Equipe sugerida" value={ticket.ai_team?.name ?? "—"} />
        <div className="flex items-center justify-between gap-3">
          <dt className="text-text-muted">Confiança</dt>
          <dd>
            <Badge tone={tone}>{formatPercent(ticket.ai_confidence)}</Badge>
          </dd>
        </div>
      </dl>
      {ticket.ai_summary && (
        <p className="mt-4 border-t border-border pt-3 text-sm text-text-muted">{ticket.ai_summary}</p>
      )}
      <p className="mt-3 text-xs text-text-muted">
        Analisado {formatRelative(ticket.ai_analyzed_at!)}. Sugestões abaixo de 70% de confiança não
        são aplicadas automaticamente.
      </p>
    </Card>
  );
}

function SuggestionCard({ suggestion }: { suggestion: Suggestion }) {
  if (suggestion.status === "FAILED") {
    return (
      <Card
        title={
          <h2 className="flex items-center gap-2 text-sm font-semibold">
            <BookOpen aria-hidden className="size-4 text-brand" />
            Sugestão da base de conhecimento
          </h2>
        }
      >
        <p className="text-sm text-text-muted">
          Não foi possível gerar a sugestão ({suggestion.error_code}). Tente novamente.
        </p>
      </Card>
    );
  }

  return (
    <Card
      title={
        <h2 className="flex items-center gap-2 text-sm font-semibold">
          <BookOpen aria-hidden className="size-4 text-brand" />
          Sugestão da base de conhecimento
        </h2>
      }
      action={<span className="text-xs text-text-muted">{formatRelative(suggestion.created_at)}</span>}
    >
      {suggestion.can_answer ? (
        <>
          <p className="text-sm whitespace-pre-wrap text-text">{suggestion.answer}</p>
          <div className="mt-4 border-t border-border pt-3">
            <p className="mb-2 text-xs font-medium text-text-muted">Fontes utilizadas</p>
            <ul className="space-y-1.5">
              {suggestion.sources
                .filter((source) => source.cited)
                .map((source) => (
                  <li key={source.article_code} className="text-sm">
                    {source.article_id ? (
                      <Link
                        to={`/base-de-conhecimento/${source.article_id}`}
                        className="text-brand hover:underline"
                      >
                        {source.article_code} — {source.article_title}
                      </Link>
                    ) : (
                      <span className="text-text-muted">
                        {source.article_code} — {source.article_title} (artigo removido)
                      </span>
                    )}
                    <span className="ml-2 text-xs text-text-muted">
                      similaridade {formatPercent(source.score)}
                    </span>
                  </li>
                ))}
            </ul>
          </div>
        </>
      ) : (
        <p className="text-sm text-text-muted">
          Nenhum artigo da base de conhecimento cobre este chamado.
        </p>
      )}
    </Card>
  );
}

function TriagePanel({
  ticket,
  onPatch,
  onAssign,
  onResolve,
  busy,
}: {
  ticket: Ticket;
  onPatch: (body: Record<string, unknown>) => void;
  onAssign: (assigneeId: number | undefined) => void;
  onResolve: (resolution: string) => void;
  busy: boolean;
}) {
  const [resolution, setResolution] = useState("");
  const { data: categories } = useQuery({
    queryKey: ["categories"],
    queryFn: () => api<Category[]>("/categories"),
  });
  const { data: teams } = useQuery({ queryKey: ["teams"], queryFn: () => api<Team[]>("/teams") });
  const { data: staff } = useQuery({
    queryKey: ["users", "staff"],
    queryFn: () => api<{ items: User[] }>("/users", { params: { page_size: 100 } }),
  });

  return (
    <Card title="Triagem">
      <div className="space-y-3 text-sm">
        <label className="block">
          <span className="mb-1.5 block text-xs text-text-muted">Situação</span>
          <select
            className="input"
            value={ticket.status}
            disabled={busy}
            onChange={(event) => onPatch({ status: event.target.value })}
          >
            {Object.entries(TICKET_STATUS).map(([value, meta]) => (
              <option key={value} value={value}>
                {meta.label}
              </option>
            ))}
          </select>
        </label>

        <label className="block">
          <span className="mb-1.5 block text-xs text-text-muted">Prioridade</span>
          <select
            className="input"
            value={ticket.priority}
            disabled={busy}
            onChange={(event) => onPatch({ priority: event.target.value })}
          >
            {Object.entries(TICKET_PRIORITY).map(([value, meta]) => (
              <option key={value} value={value}>
                {meta.label}
              </option>
            ))}
          </select>
        </label>

        <label className="block">
          <span className="mb-1.5 block text-xs text-text-muted">Categoria</span>
          <select
            className="input"
            value={ticket.subcategory?.id ?? ticket.category?.id ?? ""}
            disabled={busy}
            onChange={(event) =>
              onPatch(
                event.target.value
                  ? { subcategory_id: Number(event.target.value) }
                  : { category_id: null },
              )
            }
          >
            <option value="">Sem categoria</option>
            {categories?.map((category) => (
              <optgroup key={category.id} label={category.name}>
                {category.subcategories.map((subcategory) => (
                  <option key={subcategory.id} value={subcategory.id}>
                    {category.name} / {subcategory.name}
                  </option>
                ))}
              </optgroup>
            ))}
          </select>
        </label>

        <label className="block">
          <span className="mb-1.5 block text-xs text-text-muted">Equipe</span>
          <select
            className="input"
            value={ticket.team?.id ?? ""}
            disabled={busy}
            onChange={(event) =>
              onPatch({ team_id: event.target.value ? Number(event.target.value) : null })
            }
          >
            <option value="">Sem equipe</option>
            {teams?.map((team) => (
              <option key={team.id} value={team.id}>
                {team.name}
              </option>
            ))}
          </select>
        </label>

        <label className="block">
          <span className="mb-1.5 block text-xs text-text-muted">Responsável</span>
          <select
            className="input"
            value={ticket.assignee?.id ?? ""}
            disabled={busy}
            onChange={(event) => onAssign(Number(event.target.value) || undefined)}
          >
            <option value="">Eu mesmo</option>
            {staff?.items
              .filter((person) => person.role !== "USER" && person.is_active)
              .map((person) => (
                <option key={person.id} value={person.id}>
                  {person.full_name}
                </option>
              ))}
          </select>
        </label>

        {ticket.status !== "RESOLVED" && (
          <form
            className="border-t border-border pt-3"
            onSubmit={(event) => {
              event.preventDefault();
              onResolve(resolution);
              setResolution("");
            }}
          >
            <span className="mb-1.5 block text-xs text-text-muted">Resolver chamado</span>
            <textarea
              className="input min-h-20"
              placeholder="Resposta enviada ao solicitante (opcional)"
              value={resolution}
              onChange={(event) => setResolution(event.target.value)}
            />
            <button type="submit" className="btn-primary mt-2 w-full" disabled={busy}>
              <CheckCircle2 aria-hidden className="size-4" />
              Marcar como resolvido
            </button>
          </form>
        )}
      </div>
    </Card>
  );
}

function MessageForm({
  ticketId,
  canWriteInternal,
  onSent,
}: {
  ticketId: number;
  canWriteInternal: boolean;
  onSent: () => void;
}) {
  const queryClient = useQueryClient();
  const [body, setBody] = useState("");
  const [isInternal, setIsInternal] = useState(false);

  const send = useMutation({
    mutationFn: () =>
      api<TicketMessage>(`/tickets/${ticketId}/messages`, {
        method: "POST",
        body: { body, is_internal: isInternal },
      }),
    onSuccess: () => {
      setBody("");
      void queryClient.invalidateQueries({ queryKey: ["ticket", ticketId, "messages"] });
      onSent();
    },
  });

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (body.trim()) send.mutate();
  }

  return (
    <form onSubmit={onSubmit} className="mt-4 border-t border-border pt-4">
      <textarea
        className="input min-h-24"
        placeholder="Escreva uma resposta..."
        aria-label="Nova mensagem"
        value={body}
        onChange={(event) => setBody(event.target.value)}
      />
      {send.error && (
        <div className="mt-2">
          <ErrorMessage>{errorMessage(send.error)}</ErrorMessage>
        </div>
      )}
      <div className="mt-2 flex items-center justify-between gap-3">
        {canWriteInternal ? (
          <label className="flex items-center gap-2 text-sm text-text-muted">
            <input
              type="checkbox"
              checked={isInternal}
              onChange={(event) => setIsInternal(event.target.checked)}
            />
            Nota interna (não visível ao solicitante)
          </label>
        ) : (
          <span />
        )}
        <button type="submit" className="btn-primary" disabled={send.isPending || !body.trim()}>
          {send.isPending ? "Enviando..." : "Enviar"}
        </button>
      </div>
    </form>
  );
}
