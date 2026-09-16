import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AuthProvider } from "../auth/AuthProvider";
import { tokenStorage } from "../lib/api";
import { formatDateTime } from "../lib/format";
import type { Ticket, User } from "../lib/types";
import { TicketDetailPage } from "./TicketDetailPage";

const REQUESTER: User = {
  id: 7,
  organization_id: 1,
  email: "joao@acme.dev",
  full_name: "João Pereira",
  role: "USER",
  is_active: true,
  created_at: "2026-09-01T12:00:00Z",
};
const REQUESTER_SUMMARY = { id: REQUESTER.id, full_name: REQUESTER.full_name, email: REQUESTER.email };
const AGENT_SUMMARY = { id: 2, full_name: "Maria Oliveira", email: "maria@acme.dev" };

const OPEN_TICKET: Ticket = {
  id: 42,
  title: "Impressora fiscal não imprime",
  description: "A impressora do caixa 2 parou de imprimir os cupons.",
  status: "OPEN",
  priority: "LOW",
  category: null,
  subcategory: null,
  team: null,
  requester: REQUESTER_SUMMARY,
  assignee: null,
  created_at: "2026-09-10T12:00:00Z",
  updated_at: "2026-09-10T12:00:00Z",
  resolved_at: null,
  resolved_by: null,
  ai_category: null,
  ai_subcategory: null,
  ai_team: null,
  ai_priority: null,
  ai_confidence: null,
  ai_summary: null,
  ai_analyzed_at: null,
  sla_due_at: "2026-09-11T12:00:00Z",
  sla_status: "BREACHED",
  auto_close_at: null,
};

const RESOLVED_TICKET: Ticket = {
  ...OPEN_TICKET,
  status: "RESOLVED",
  resolved_at: "2026-09-15T12:00:00Z",
  resolved_by: AGENT_SUMMARY,
  auto_close_at: "2026-09-20T12:00:00Z",
};

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** A tiny fake API that applies close and self-resolve to the ticket it serves. */
function stubApi(initial: Ticket) {
  let ticket = initial;
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const path = new URL(url).pathname;
    if (path === "/api/auth/me") return jsonResponse(200, REQUESTER);
    if (path === "/api/tickets/42/close" && init?.method === "POST") {
      ticket = { ...ticket, status: "CLOSED", auto_close_at: null };
      return jsonResponse(200, ticket);
    }
    if (path === "/api/tickets/42/self-resolve" && init?.method === "POST") {
      ticket = {
        ...ticket,
        status: "RESOLVED",
        resolved_at: "2026-09-16T12:00:00Z",
        resolved_by: REQUESTER_SUMMARY,
        auto_close_at: "2026-09-21T12:00:00Z",
      };
      return jsonResponse(200, ticket);
    }
    if (path === "/api/tickets/42/messages") return jsonResponse(200, []);
    if (path === "/api/tickets/42") return jsonResponse(200, ticket);
    return jsonResponse(404, { error: { code: "NOT_FOUND", message: path } });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function callsTo(fetchMock: ReturnType<typeof stubApi>, suffix: string) {
  return fetchMock.mock.calls.filter(([url]) => String(url).endsWith(suffix));
}

function renderPage() {
  tokenStorage.write({ access_token: "a", refresh_token: "r" });
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <MemoryRouter initialEntries={["/chamados/42"]}>
          <Routes>
            <Route path="/chamados/:id" element={<TicketDetailPage />} />
          </Routes>
        </MemoryRouter>
      </AuthProvider>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("TicketDetailPage, resolved ticket", () => {
  it("lets the requester close it after confirming", async () => {
    const fetchMock = stubApi(RESOLVED_TICKET);
    vi.stubGlobal("confirm", vi.fn(() => true));
    renderPage();

    expect(await screen.findByText("Chamado resolvido")).toBeInTheDocument();
    expect(
      screen.getByText(new RegExp(`fechado automaticamente em ${formatDateTime(RESOLVED_TICKET.auto_close_at!)}`)),
    ).toBeInTheDocument();

    await userEvent.setup().click(screen.getByRole("button", { name: "Fechar chamado" }));

    expect(await screen.findByText("Fechado")).toBeInTheDocument();
    expect(screen.queryByText("Chamado resolvido")).not.toBeInTheDocument();
    expect(callsTo(fetchMock, "/tickets/42/close")).toHaveLength(1);
  });

  it("keeps the ticket open when the requester cancels", async () => {
    const fetchMock = stubApi(RESOLVED_TICKET);
    vi.stubGlobal("confirm", vi.fn(() => false));
    renderPage();

    await userEvent.setup().click(await screen.findByRole("button", { name: "Fechar chamado" }));

    expect(screen.getByText("Chamado resolvido")).toBeInTheDocument();
    expect(callsTo(fetchMock, "/tickets/42/close")).toHaveLength(0);
  });

  it("warns the requester that replying puts the ticket back in the queue", async () => {
    stubApi(RESOLVED_TICKET);
    renderPage();

    expect(await screen.findByText("Ao enviar, o chamado volta para a equipe.")).toBeInTheDocument();
  });
});

describe("TicketDetailPage, requester solved it alone", () => {
  it("sends how they solved it and shows the ticket as resolved", async () => {
    const fetchMock = stubApi(OPEN_TICKET);
    renderPage();
    const user = userEvent.setup();

    // Speaking to the requester, not to the team.
    expect(await screen.findByText("Escreva abaixo para falar com a equipe.")).toBeInTheDocument();

    await user.click(await screen.findByRole("button", { name: "Resolvi por conta própria" }));
    const submit = screen.getByRole("button", { name: "Marcar como resolvido" });
    await user.type(screen.getByLabelText("Como você resolveu"), "reiniciei");
    expect(submit).toBeDisabled(); // too short to help anyone

    await user.type(screen.getByLabelText("Como você resolveu"), " o serviço de impressão");
    await user.click(submit);

    expect(await screen.findByText(/Você informou que resolveu por conta própria/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Resolvi por conta própria" })).not.toBeInTheDocument();
    const [[, init]] = callsTo(fetchMock, "/tickets/42/self-resolve");
    expect(JSON.parse(String(init?.body))).toEqual({ solution: "reiniciei o serviço de impressão" });
  });
});
