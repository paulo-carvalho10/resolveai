import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";

import { useAuth } from "../auth/AuthProvider";
import { PageHeader } from "../components/Layout";
import { Badge, EmptyState, ErrorMessage, Pagination, Spinner } from "../components/ui";
import { api } from "../lib/api";
import { errorMessage } from "../lib/errors";
import { formatDeadline, formatRelative } from "../lib/format";
import { SLA_STATUS, TICKET_PRIORITY, TICKET_STATUS } from "../lib/labels";
import type { Page, Ticket, TicketStatus } from "../lib/types";

const STATUS_FILTERS: { value: TicketStatus | "ACTIVE" | ""; label: string }[] = [
  { value: "ACTIVE", label: "Em aberto" },
  { value: "", label: "Todos" },
  { value: "OPEN", label: "Abertos" },
  { value: "IN_PROGRESS", label: "Em andamento" },
  { value: "WAITING_USER", label: "Aguardando solicitante" },
  { value: "RESOLVED", label: "Resolvidos" },
  { value: "CLOSED", label: "Fechados" },
];

const ACTIVE_STATUSES: TicketStatus[] = ["OPEN", "IN_PROGRESS", "WAITING_USER"];

export function TicketsPage() {
  const { isStaff } = useAuth();
  const [status, setStatus] = useState<TicketStatus | "ACTIVE" | "">("ACTIVE");
  const [priority, setPriority] = useState<string>("");
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const pageSize = 20;

  const params = {
    page,
    page_size: pageSize,
    q: query || undefined,
    sort: "-created_at",
    status: status === "ACTIVE" ? ACTIVE_STATUSES : status ? [status] : undefined,
    priority: priority ? [priority] : undefined,
  };

  const { data, isPending, error } = useQuery({
    queryKey: ["tickets", params],
    queryFn: () => api<Page<Ticket>>("/tickets", { params }),
  });

  return (
    <>
      <PageHeader
        title={isStaff ? "Chamados" : "Meus chamados"}
        description={
          isStaff
            ? "Fila da organização, com prioridade e SLA calculados automaticamente."
            : "Acompanhe os chamados que você abriu."
        }
        action={
          <Link to="/chamados/novo" className="btn-primary">
            Novo chamado
          </Link>
        }
      />

      <div className="card mb-4 flex flex-wrap items-end gap-3 p-4">
        <form
          className="flex min-w-[240px] flex-1 items-center gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            setPage(1);
            setQuery(search);
          }}
        >
          <div className="relative flex-1">
            <Search aria-hidden className="absolute top-2.5 left-3 size-4 text-text-muted" />
            <input
              className="input pl-9"
              placeholder="Buscar por texto ou #número"
              aria-label="Buscar chamados"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
          </div>
          <button type="submit" className="btn-secondary">
            Buscar
          </button>
        </form>

        <label className="text-sm">
          <span className="mb-1.5 block text-xs text-text-muted">Situação</span>
          <select
            className="input w-48"
            value={status}
            onChange={(event) => {
              setPage(1);
              setStatus(event.target.value as TicketStatus | "ACTIVE" | "");
            }}
          >
            {STATUS_FILTERS.map((option) => (
              <option key={option.label} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>

        <label className="text-sm">
          <span className="mb-1.5 block text-xs text-text-muted">Prioridade</span>
          <select
            className="input w-40"
            value={priority}
            onChange={(event) => {
              setPage(1);
              setPriority(event.target.value);
            }}
          >
            <option value="">Todas</option>
            {Object.entries(TICKET_PRIORITY).map(([value, meta]) => (
              <option key={value} value={value}>
                {meta.label}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="card overflow-hidden">
        {error && (
          <div className="p-4">
            <ErrorMessage>{errorMessage(error)}</ErrorMessage>
          </div>
        )}
        {isPending && <Spinner />}
        {data && data.items.length === 0 && (
          <EmptyState
            title="Nenhum chamado encontrado"
            description="Ajuste os filtros ou abra um novo chamado."
          />
        )}
        {data && data.items.length > 0 && (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="border-b border-border text-left text-xs text-text-muted">
                  <tr>
                    <th className="px-4 py-3 font-medium">Chamado</th>
                    <th className="px-4 py-3 font-medium">Situação</th>
                    <th className="px-4 py-3 font-medium">Prioridade</th>
                    <th className="px-4 py-3 font-medium">Categoria</th>
                    {isStaff && <th className="px-4 py-3 font-medium">Responsável</th>}
                    <th className="px-4 py-3 font-medium">SLA</th>
                    <th className="px-4 py-3 font-medium">Criado</th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((ticket) => (
                    <tr key={ticket.id} className="border-b border-border/70 last:border-0 hover:bg-surface-muted">
                      <td className="max-w-md px-4 py-3">
                        <Link to={`/chamados/${ticket.id}`} className="font-medium text-text hover:text-brand">
                          <span className="text-text-muted">#{ticket.id}</span> {ticket.title}
                        </Link>
                      </td>
                      <td className="px-4 py-3">
                        <Badge tone={TICKET_STATUS[ticket.status].tone}>
                          {TICKET_STATUS[ticket.status].label}
                        </Badge>
                      </td>
                      <td className="px-4 py-3">
                        <Badge tone={TICKET_PRIORITY[ticket.priority].tone}>
                          {TICKET_PRIORITY[ticket.priority].label}
                        </Badge>
                      </td>
                      <td className="px-4 py-3 text-text-muted">
                        {ticket.category?.name ?? "—"}
                        {ticket.subcategory && ` / ${ticket.subcategory.name}`}
                      </td>
                      {isStaff && (
                        <td className="px-4 py-3 text-text-muted">
                          {ticket.assignee?.full_name ?? "Sem responsável"}
                        </td>
                      )}
                      <td className="px-4 py-3">
                        <span
                          className={
                            ticket.sla_status === "BREACHED"
                              ? "text-state-danger"
                              : ticket.sla_status === "AT_RISK"
                                ? "text-state-waiting"
                                : "text-text-muted"
                          }
                        >
                          {ticket.status === "RESOLVED" || ticket.status === "CLOSED"
                            ? SLA_STATUS[ticket.sla_status].label
                            : formatDeadline(ticket.sla_due_at)}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-text-muted">{formatRelative(ticket.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pagination page={data.page} pageSize={data.page_size} total={data.total} onChange={setPage} />
          </>
        )}
      </div>
    </>
  );
}
