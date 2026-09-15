import { beforeEach, describe, expect, it, vi } from "vitest";

import { api, ApiError, SESSION_EXPIRED_EVENT, tokenStorage } from "./api";
import { errorMessage } from "./errors";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("api", () => {
  beforeEach(() => {
    tokenStorage.write({ access_token: "old-access", refresh_token: "refresh" });
  });

  it("sends the access token and parses the response", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, { id: 7 }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(api<{ id: number }>("/tickets/7")).resolves.toEqual({ id: 7 });

    const [, init] = fetchMock.mock.calls[0];
    expect(init.headers.Authorization).toBe("Bearer old-access");
  });

  it("serializes query parameters, repeating arrays and dropping empty values", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, []));
    vi.stubGlobal("fetch", fetchMock);

    await api("/tickets", { params: { status: ["OPEN", "CLOSED"], q: undefined, page: 2 } });

    const url = new URL(fetchMock.mock.calls[0][0]);
    expect(url.searchParams.getAll("status")).toEqual(["OPEN", "CLOSED"]);
    expect(url.searchParams.get("page")).toBe("2");
    expect(url.searchParams.has("q")).toBe(false);
  });

  it("turns the API error envelope into an ApiError", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse(409, { error: { code: "TICKET_CLOSED", message: "Closed tickets..." } }),
      ),
    );

    const error = await api("/tickets/1").catch((cause) => cause);

    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).code).toBe("TICKET_CLOSED");
    expect(errorMessage(error)).toBe("Chamados fechados não podem ser alterados.");
  });

  it("refreshes an expired token once and retries the request", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(401, { error: { code: "TOKEN_EXPIRED" } }))
      .mockResolvedValueOnce(
        jsonResponse(200, { access_token: "new-access", refresh_token: "new-refresh" }),
      )
      .mockResolvedValueOnce(jsonResponse(200, { id: 1 }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(api("/auth/me")).resolves.toEqual({ id: 1 });

    expect(fetchMock.mock.calls[1][0]).toContain("/auth/refresh");
    expect(fetchMock.mock.calls[2][1].headers.Authorization).toBe("Bearer new-access");
    expect(tokenStorage.read()?.access_token).toBe("new-access");
  });

  it("clears the session when the refresh also fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse(401, { error: { code: "INVALID_TOKEN" } })),
    );
    const onExpired = vi.fn();
    window.addEventListener(SESSION_EXPIRED_EVENT, onExpired);

    await expect(api("/auth/me")).rejects.toBeInstanceOf(ApiError);

    expect(tokenStorage.read()).toBeNull();
    expect(onExpired).toHaveBeenCalled();
    window.removeEventListener(SESSION_EXPIRED_EVENT, onExpired);
  });

  it("does not send the token when the call is public", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, {}));
    vi.stubGlobal("fetch", fetchMock);

    await api("/auth/login", { method: "POST", body: { email: "a@b.c" }, auth: false });

    expect(fetchMock.mock.calls[0][1].headers.Authorization).toBeUndefined();
  });
});

describe("errorMessage", () => {
  it("falls back for unknown codes, server errors and offline", () => {
    expect(errorMessage(new ApiError(400, "WHATEVER", "Algo específico"))).toBe("Algo específico");
    expect(errorMessage(new ApiError(500, "BOOM", "x"))).toBe(
      "Algo deu errado do nosso lado. Tente de novo.",
    );
    expect(errorMessage(new TypeError("Failed to fetch"))).toBe("Sem conexão com o servidor.");
  });
});
