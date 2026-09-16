/** API error codes are in English (they are for developers); users read these messages. */

import { ApiError } from "./api";

const MESSAGES: Record<string, string> = {
  INVALID_CREDENTIALS: "E-mail ou senha incorretos.",
  USER_INACTIVE: "Esta conta foi desativada. Fale com o administrador.",
  NOT_AUTHENTICATED: "Faça login para continuar.",
  TOKEN_EXPIRED: "Sua sessão expirou. Entre novamente.",
  INVALID_TOKEN: "Sua sessão expirou. Entre novamente.",
  FORBIDDEN: "Você não tem permissão para fazer isso.",
  EMAIL_ALREADY_REGISTERED: "Este e-mail já está cadastrado.",
  CANNOT_MODIFY_SELF: "Você não pode alterar o próprio papel nem se desativar.",
  TICKET_NOT_FOUND: "Chamado não encontrado.",
  TICKET_CLOSED: "Chamados fechados não podem ser alterados.",
  TICKET_NOT_RESOLVED: "Só é possível fechar o chamado depois que ele for resolvido.",
  TICKET_ALREADY_RESOLVED: "Este chamado já foi resolvido.",
  INVALID_ASSIGNEE: "Só é possível atribuir o chamado a um atendente ou administrador ativo.",
  SUBCATEGORY_MISMATCH: "A subcategoria não pertence à categoria escolhida.",
  CATEGORY_INACTIVE: "Esta categoria não está mais disponível.",
  CATEGORY_NOT_FOUND: "Categoria não encontrada.",
  CATEGORY_NAME_TAKEN: "Já existe uma categoria com este nome.",
  SUBCATEGORY_NAME_TAKEN: "Esta categoria já tem uma subcategoria com este nome.",
  TEAM_NOT_FOUND: "Equipe não encontrada.",
  TEAM_NAME_TAKEN: "Já existe uma equipe com este nome.",
  INVALID_TEAM_MEMBER: "Só atendentes e administradores podem fazer parte de uma equipe.",
  USER_NOT_FOUND: "Usuário não encontrado.",
  ARTICLE_NOT_FOUND: "Artigo não encontrado.",
  PRIORITY_RULE_NOT_FOUND: "Regra não encontrada.",
  PRIORITY_RULE_NAME_TAKEN: "Já existe uma regra com este nome.",
  VALIDATION_ERROR: "Confira os campos destacados.",
  AI_AUTH_FAILED: "A chave da API de IA é inválida.",
  AI_RATE_LIMITED: "Limite de uso da IA atingido. Tente de novo em alguns instantes.",
  AI_TIMEOUT: "A IA demorou demais para responder. Tente de novo.",
  AI_UNAVAILABLE: "Não foi possível falar com o serviço de IA.",
  AI_PROVIDER_ERROR: "O serviço de IA retornou um erro.",
  AI_REFUSED: "A IA recusou analisar este conteúdo.",
  AI_INCOMPLETE: "A resposta da IA ficou incompleta.",
  AI_INVALID_OUTPUT: "A IA devolveu um resultado inválido.",
  EMBEDDING_AUTH_FAILED: "A chave da API de embeddings é inválida.",
  EMBEDDING_RATE_LIMITED: "Limite de uso da busca semântica atingido.",
  EMBEDDING_TIMEOUT: "A busca demorou demais para responder.",
  EMBEDDING_UNAVAILABLE: "A busca semântica está indisponível.",
  EMBEDDING_PROVIDER_ERROR: "O serviço de busca semântica retornou um erro.",
  INTERNAL_ERROR: "Algo deu errado do nosso lado. Tente de novo.",
};

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    const known = MESSAGES[error.code];
    if (known) return known;
    if (error.status >= 500) return MESSAGES.INTERNAL_ERROR;
    return error.message || "Não foi possível completar a ação.";
  }
  if (error instanceof TypeError) return "Sem conexão com o servidor.";
  return "Não foi possível completar a ação.";
}
