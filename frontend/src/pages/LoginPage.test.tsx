import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { AuthProvider } from "../auth/AuthProvider";
import { tokenStorage } from "../lib/api";
import { LoginPage } from "./LoginPage";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

async function fillAndSubmit() {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("E-mail"), "agent@resolveai.dev");
  await user.type(screen.getByLabelText("Senha"), "resolveai123");
  await user.click(screen.getByRole("button", { name: "Entrar" }));
}

describe("LoginPage", () => {
  it("stores the tokens returned by the API", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(200, { access_token: "a", refresh_token: "r" }))
      .mockResolvedValueOnce(jsonResponse(200, { id: 2, full_name: "Maria", role: "AGENT" }));
    vi.stubGlobal("fetch", fetchMock);

    render(
      <AuthProvider>
        <LoginPage />
      </AuthProvider>,
    );
    await fillAndSubmit();

    expect(tokenStorage.read()).toEqual({ access_token: "a", refresh_token: "r" });
    const body = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(body).toEqual({ email: "agent@resolveai.dev", password: "resolveai123" });
  });

  it("shows the error in Portuguese when the credentials are wrong", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse(401, { error: { code: "INVALID_CREDENTIALS", message: "Invalid email" } }),
      ),
    );

    render(
      <AuthProvider>
        <LoginPage />
      </AuthProvider>,
    );
    await fillAndSubmit();

    expect(await screen.findByRole("alert")).toHaveTextContent("E-mail ou senha incorretos.");
    expect(tokenStorage.read()).toBeNull();
  });
});
