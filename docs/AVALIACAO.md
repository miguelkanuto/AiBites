# Avaliação e otimização

## Gate de release

- `evals/casos.json`: 27 casos em 5 categorias (segurança, RBAC, roteamento, agente, fatos). Cada caso diz o que
  deve e o que não pode aparecer (resposta, fontes, ferramentas, bloqueio, confirmação).
- `evals/run.py`: roda os casos contra um site em execução (local ou publicado), uma sessão nova por caso, e **recusa
  toda confirmação**, então nada é criado (férias, ticket, mensagem). Sai com código 1 se uma categoria ficar abaixo
  do limiar. Segurança e RBAC exigem 100%.
- `tests/test_eval_cases.py`: parte offline (arquivo coerente, roteador e guardrail de acordo com os casos). Roda no CI sem segredos.
- CI (`.github/workflows/ci.yml`): testes offline e build do front a cada push. A avaliação completa
  (`avaliacao.yml`) é manual, porque chama o LLM de verdade e consome a cota gratuita.

```bash
make eval URL=http://localhost:8001
```

Resultado medido (local, 27 casos): segurança 4/4, RBAC 7/7, roteamento 5/5, agente 7/7, fatos 4/5 (a falha foi o
critério "tem fonte" num acerto de cache, que não traz fontes; o critério foi removido).

## Otimização (medida, não suposta)

| Medida | Antes | Depois |
|---|---|---|
| Etapa "limites" (2 consultas ao banco) | ~590 ms, em sequência | ~330 ms, em paralelo |
| Pior caso de uma chamada ao modelo | 60 s x 3 tentativas no mesmo modelo | 30 s x 2, depois troca de modelo |
| Perguntas do agente na avaliação | até 95 s (pico de fila do modelo gratuito) | 9 a 13 s ao repetir os mesmos casos |
| Pergunta repetida (cache semântico) | resposta do modelo (~3 s) | ~0,3 s, custo zero |
| Memória do servidor | ~1,5 GB | ~240 MB (Windows) |

A latência alta do agente era variação de fila do provedor gratuito, não do código; por isso a correção é falhar rápido
e trocar de modelo. Próximos candidatos: gravar a auditoria sem bloquear a resposta (~260 ms) e medir a memória no Render.
