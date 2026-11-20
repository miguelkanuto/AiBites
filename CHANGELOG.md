# Changelog

Versionamento semântico: MAIOR.MENOR.CORREÇÃO. A versão aparece no rodapé do site e em `/api/health`.

## 1.0.2
- Redirecionamento do endereço antigo para o novo (`AIBITES_CANONICAL_HOST`) e `render.yaml` para recriar o serviço.

## 1.0.1
- Troca automática para outro modelo gratuito quando um falha; falha rápida (30 s) em vez de esperar 60 s.
- Contagens de itens vendidos ("já vendemos X?") passam pelo agente com SQL.
- Etapa de limites com as consultas em paralelo (~260 ms a menos por mensagem).
- Suíte de avaliação com gate de release (`evals/`) e CI.
- Versão visível no site e atualização automática da página quando sai uma versão nova.

## 1.0.0
- MVP: chat com RAG e RBAC, guardrails, agente com ferramentas MCP (RH, TI, Slack, vendas), roteador de
  modelos, cache semântico, auditoria, site de demonstração e deploy gratuito (Render, Neon, Gemini).
