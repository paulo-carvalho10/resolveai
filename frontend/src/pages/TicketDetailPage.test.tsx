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

const RESOLVED_TICKET: Ticket = {
  id: 42,
  title: "Boleto gerado com vencimento errado",
  description: "O boleto do pedido 1234 saiu com a data de ontem.",
  status: "RESOLVED",
  priority: "LOW",
  category: null,
  subcategory: null,
  team: null,
  requester: { id: REQUESTER.id, full_name: REQUESTER.full_name, email: REQUESTER.email },
  assignee: null,
  created_at: "2026-09-10T12:00:00Z",
  updated_at: "2026-09-15T12:00:00Z",
  resolved_at: "2026-09-15T12:00:00Z",
  ai_category: null,
  ai_subcategory: null,
  ai_team: null,
  ai_priority: null,
  ai_confidence: null,
  ai_summary: null,
  ai_analyzed_at: null,
  sla_due_at: "2026-09-11T12:00:00Z",
  sla_status: "BREACHED",
  auto_close_at: "2026-09-20T12:00:00Z",
};

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** A tiny fake API: the ticket becomes CLOSED once the close endpoint is called. */
function stubApi() {
  let ticket = RESOLVED_TICKET;
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const path = new URL(url).pathname;
    if (path === "/api/auth/me") return jsonResponse(200, REQUESTER);
    if (path === "/api/tickets/42/close" && init?.method === "POST") {
      ticket = { ...ticket, status: "CLOSED", auto_close_at: null };
      return jsonResponse(200, ticket);
    }
    if (path === "/api/tickets/42/messages") return jsonResponse(200, []);
    if (path === "/api/tickets/42") return jsonResponse(200, ticket);
    return jsonResponse(404, { error: { code: "NOT_FOUND", message: path } });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function closeCalls(fetchMock: ReturnType<typeof stubApi>) {
  return fetchMock.mock.calls.filter(([url]) => String(url).endsWith("/tickets/42/close"));
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

describe("TicketDetailPage, resolved ticket", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("lets the requester close it after confirming", async () => {
    const fetchMock = stubApi();
    vi.stubGlobal("confirm", vi.fn(() => true));
    renderPage();

    expect(await screen.findByText("Chamado resolvido")).toBeInTheDocument();
    expect(
      screen.getByText(new RegExp(`fechado automaticamente em ${formatDateTime(RESOLVED_TICKET.auto_close_at!)}`)),
    ).toBeInTheDocument();

    await userEvent.setup().click(screen.getByRole("button", { name: "Fechar chamado" }));

    expect(await screen.findByText("Fechado")).toBeInTheDocument();
    expect(screen.queryByText("Chamado resolvido")).not.toBeInTheDocument();
    expect(closeCalls(fetchMock)).toHaveLength(1);
  });

  it("keeps the ticket open when the requester cancels", async () => {
    const fetchMock = stubApi();
    vi.stubGlobal("confirm", vi.fn(() => false));
    renderPage();

    await userEvent.setup().click(await screen.findByRole("button", { name: "Fechar chamado" }));

    expect(screen.getByText("Chamado resolvido")).toBeInTheDocument();
    expect(closeCalls(fetchMock)).toHaveLength(0);
  });
});
