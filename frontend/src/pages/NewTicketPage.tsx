import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Sparkles } from "lucide-react";
import { useState } from "react";
import type { FormEvent } from "react";
import { useNavigate } from "react-router";

import { PageHeader } from "../components/Layout";
import { ErrorMessage, Field } from "../components/ui";
import { api } from "../lib/api";
import { errorMessage } from "../lib/errors";
import type { Category, Ticket } from "../lib/types";

export function NewTicketPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [subcategoryId, setSubcategoryId] = useState("");

  const { data: categories } = useQuery({
    queryKey: ["categories"],
    queryFn: () => api<Category[]>("/categories"),
  });

  const create = useMutation({
    mutationFn: () =>
      api<Ticket>("/tickets", {
        method: "POST",
        body: {
          title,
          description,
          subcategory_id: subcategoryId ? Number(subcategoryId) : null,
        },
      }),
    onSuccess: (ticket) => {
      void queryClient.invalidateQueries({ queryKey: ["tickets"] });
      navigate(`/chamados/${ticket.id}`);
    },
  });

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    create.mutate();
  }

  return (
    <div className="mx-auto max-w-2xl">
      <PageHeader
        title="Novo chamado"
        description="Descreva o problema. A categoria, a prioridade e a equipe são sugeridas automaticamente."
      />

      <form onSubmit={onSubmit} className="card space-y-5 p-5">
        <Field label="Título" hint="Resuma o problema em uma frase.">
          <input
            className="input"
            required
            minLength={5}
            maxLength={200}
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            placeholder="Ex.: Não consigo emitir NF-e"
          />
        </Field>

        <Field
          label="Descrição"
          hint="Inclua mensagens de erro, o que você já tentou e se há prazo envolvido."
        >
          <textarea
            className="input min-h-40"
            required
            minLength={10}
            maxLength={20000}
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            placeholder="Ex.: Ao transmitir a nota, a SEFAZ devolve a rejeição 539. Precisamos fechar o faturamento hoje."
          />
        </Field>

        <Field label="Categoria (opcional)" hint="Se não souber, deixe em branco: a IA classifica.">
          <select
            className="input"
            value={subcategoryId}
            onChange={(event) => setSubcategoryId(event.target.value)}
          >
            <option value="">Deixar a IA classificar</option>
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
        </Field>

        <p className="flex items-start gap-2 rounded-lg bg-brand-soft px-3 py-2 text-xs text-brand">
          <Sparkles aria-hidden className="mt-0.5 size-4 shrink-0" />
          Assim que você enviar, a IA classifica o chamado, define a prioridade junto com as regras
          da empresa e procura soluções na base de conhecimento.
        </p>

        {create.error && <ErrorMessage>{errorMessage(create.error)}</ErrorMessage>}

        <div className="flex justify-end gap-2">
          <button type="button" className="btn-secondary" onClick={() => navigate(-1)}>
            Cancelar
          </button>
          <button type="submit" className="btn-primary" disabled={create.isPending}>
            {create.isPending ? "Enviando..." : "Abrir chamado"}
          </button>
        </div>
      </form>
    </div>
  );
}
