# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack
Já existe: front-end em `web/` (React 19 + TypeScript + Vite, CSS próprio), API em FastAPI (`src/web_api.py`) e o chat do Chainlit (tema em `public/theme.json` e `public/custom.css`). O site compilado é servido pela própria API.

## Users
- **Primário:** avaliador técnico (recrutador, entrevistador, líder de engenharia) que está julgando o projeto de portfólio de quem o construiu. Chega com pouco tempo, quer entender em segundos o que é, testar de verdade e ir fundo na arquitetura se gostar.
- **Secundário:** o cliente e o funcionário fictícios da loja AiBites, que o site encena por meio de personas (cliente, vendedor, gerente, RH, TI, CEO).

## Product Purpose
AiBites é uma loja fictícia de eletrônicos e a Carol é a assistente dela. Ela responde sobre produtos, vendedores e vendas (RAG sobre PostgreSQL/pgvector), executa ações por ferramentas (pedir férias, abrir ticket de TI, mandar mensagem num canal, calcular totais e rankings de vendas) e só mostra e faz o que o papel de quem pergunta permite. O site existe para provar, de ponta a ponta, que o autor sabe construir assistentes de IA para empresas grandes: controle de acesso, agente com ferramentas, guardrails, custo e auditoria. Sucesso: o avaliador entende o projeto na primeira tela, experimenta duas ou três personas e sai convencido da profundidade técnica.

## Positioning
Cada persona vê dados e ferramentas diferentes **e dá para ver por dentro por quê**: a permissão é aplicada no banco e na política de ferramentas, não no prompt, e um inspetor mostra rota, modelo, custo, cache, guardrails e documentos de cada resposta. Um chatbot comum não deixa essa prova à vista.

## Operating Context
Demonstração pública, em português do Brasil, com dados e sistemas simulados (RH, TI e Slack são servidores MCP fictícios). Os modelos de linguagem são reais e gratuitos (OpenRouter), com limite diário; o custo exibido é simulado. A primeira abertura leva cerca de 40 s para carregar o índice. O avaliador pode abrir o laboratório (simulações sem custo), a página de arquitetura e as métricas agregadas.

## Capabilities and Constraints
- Áreas atuais: Demonstração (chat por persona com confirmação de ações e inspetor), Laboratório (guardrails, roteador e custo, permissões, cache), Como foi feito (diagrama e decisões), Métricas (agregadas, sem dados pessoais). O visual novo preserva todas e todas as funções.
- Tudo é fictício e simulado e o site precisa dizer isso com clareza, sem esconder.
- Login do site é por persona, sem senha, só para demonstração.
- Ainda não existem: "pergunte sobre a arquitetura" no site, suíte de avaliação com bloqueio de release, Docker, login com Google. Não afirmar o contrário.
- O nome "AiBites" fica; o logo atual não é o final e deve ser refeito.

## Brand Commitments
- Nome da loja e do serviço: **AiBites** ("bites" evoca bytes, tecnologia em pequenas porções). Assistente: **Carol**, direta e concisa.
- Binding, nas palavras do usuário: estilo parecido com a DoorDash, em modo claro, sem gradientes, com imagens e desenhos; usar um design system consistente; evitar Inter e Lucide; alternar seções claras e escuras; logo novo; sem gradientes roxos, luzes aleatórias, excesso de cores, selos desnecessários nem espaçamentos inconsistentes; mesmo padrão de cantos e cards em todas as seções; interações e animações com propósito.
- Os prints da DoorDash citados pelo usuário não foram recebidos; a referência é o estilo conhecido dela (craft, não cópia).

## Evidence on Hand
- Números reais do próprio projeto: mais de 370 testes automatizados, 6 personas, 4 servidores MCP, recall de busca de 0,38 para 0,98 em 10 perguntas de teste, métricas agregadas da auditoria.
- Não há fotos de produto, clientes, depoimentos nem preços reais. Imagens vêm de ilustrações próprias e de fotos de banco de imagens gratuito; o que não for encontrado fica marcado como "[aqui deveria ter foto de ...]". Nada de depoimento, cliente ou preço inventado.

## Product Principles
1. A prova fica à vista: mostrar o sistema trabalhando vale mais que descrevê-lo.
2. Honestidade sobre o que é simulado, sempre visível, nunca em letra miúda escondida.
3. Segurança é característica do produto, não nota de rodapé: aparece na demonstração e no laboratório.
4. Primeiro o avaliador: clareza em segundos, profundidade a um clique.
5. Uma linguagem só em todas as áreas, da página inicial ao chat.

## Accessibility & Inclusion
Português do Brasil. Contraste e foco visíveis em modo claro; navegação por teclado nas personas, no chat e nas confirmações; respeitar `prefers-reduced-motion`.
