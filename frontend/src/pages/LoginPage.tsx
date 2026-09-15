import { LifeBuoy } from "lucide-react";
import { useState } from "react";
import type { FormEvent } from "react";

import { useAuth } from "../auth/AuthProvider";
import { ErrorMessage, Field } from "../components/ui";
import { errorMessage } from "../lib/errors";

export function LoginPage() {
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(email, password);
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="grid min-h-dvh place-items-center px-4 py-10">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex items-center gap-2">
          <LifeBuoy aria-hidden className="size-6 text-brand" />
          <span className="text-lg font-semibold tracking-tight">ResolveAI</span>
        </div>

        <h1 className="text-xl font-semibold tracking-tight">Entrar</h1>
        <p className="mt-1 mb-6 text-sm text-text-muted">
          Service desk com triagem automática por IA.
        </p>

        <form onSubmit={onSubmit} className="card space-y-4 p-5">
          <Field label="E-mail">
            <input
              className="input"
              type="email"
              autoComplete="username"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
          </Field>
          <Field label="Senha">
            <input
              className="input"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </Field>

          {error && <ErrorMessage>{error}</ErrorMessage>}

          <button type="submit" className="btn-primary w-full" disabled={submitting}>
            {submitting ? "Entrando..." : "Entrar"}
          </button>
        </form>

        <p className="mt-6 text-center text-xs text-text-muted">
          Demonstração: admin@resolveai.dev · agent@resolveai.dev · user@resolveai.dev
          <br />
          senha <code className="font-mono">resolveai123</code>
        </p>
      </div>
    </div>
  );
}
