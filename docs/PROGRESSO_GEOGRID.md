# GeoGrid ZURI — checkpoint dos indicadores

**Data:** 2026-11-10
**Branch de trabalho:** `desenvolvimento-indicadores-geogrid`
**Estado:** implementação experimental local; sem commit, push, merge ou deploy.

## Resumo executivo

ICM, ICP-B V2, ICE e IOP estão expostos pela análise read-only
`/api/scans/{scan_id}/analysis`, usando exclusivamente resultados já salvos.
IDA também foi endurecido para não contar duplicatas identificadas como
amostras distintas. O IOP foi aprovado pelo responsável somente para testes
experimentais: continua identificado como `prototype_unvalidated`, não é
definitivo, não estima probabilidade de sucesso e não prevê vendas.

Os fetchers atuais fornecem nome, categoria, endereço, IDs, posição, avaliação
e quantidade de avaliações. Não fornecem descrição nem lista de serviços. Os
indicadores não preenchem esses campos por suposição e não fazem chamadas
adicionais à DataForSEO.

## Indicadores

### ICM — reputação observada

- Usa avaliação e quantidade de avaliações do estabelecimento monitorado,
  observadas nos resultados.
- Só identifica o alvo por CID/Place ID oficial. Observações repetidas com
  avaliações ou contagens divergentes bloqueiam o resultado.
- Valida avaliação entre 1 e 5 e contagem de avaliações inteira e não negativa;
  zero avaliações não produz score.
- A implementação atual aplica suavização fixa:
  `rating_adjusted = (reviews × rating + 20 × 4) / (reviews + 20)`;
  `volume = min(1, ln(1 + reviews) / ln(1001))`; e
  `ICM = 100 × (0.70 × rating_adjusted / 5 + 0.30 × volume)`.
- Os parâmetros são escolhas experimentais. O valor não é probabilidade,
  intervalo de confiança nem avaliação independente de confiança empresarial.
- Sem ID oficial, alvo não observado, evidência inconsistente ou avaliação
  inválida, `score` permanece `null`, com motivo retornado.

### ICP-B V2 — pressão competitiva descritiva

- Reconcilia globalmente CID/Place ID antes da agregação, deduplica cada
  negócio por ponto e exclui o alvo identificado.
- Registros com conflito de identidade, identidade não resolvida ou decisão
  ambígua sobre o alvo bloqueiam o score; seus contadores e motivos ficam na
  resposta.
- Requer pelo menos 3 pontos válidos, 3 negócios únicos, cobertura de avaliações
  de pelo menos 60% e pelo menos 80% de pontos utilizáveis.
- Para cada ponto utilizável, calcula a média de força de reputação ponderada
  por `1 / posição`; agrega a força média dos pontos com a recorrência territorial:
  `ICP-B V2 = 100 × (0.75 × força média + 0.25 × recorrência territorial)`.
- Recorrência é a fração observada de pontos válidos com cada concorrente,
  agregada entre negócios identificados. É uma descrição da grade, não uma
  amostra de pontos espacialmente independentes.
- Pesos e limites são provisórios, não calibrados. O score não é probabilidade,
  estimativa de mercado nem intervalo de confiança. Evidência insuficiente
  retorna `score: null`.

### ICE — classificação estratégica por evidência

Classifica negócios identificados e deduplicados em uma destas classes:

- `direct`: categoria observada igual à categoria do negócio monitorado após
  normalização textual.
- `indirect`: categoria observada coincide exatamente com uma categoria
  relacionada explicitamente fornecida por `related_category` na API. A lista
  `category` é usada pelo IDA e não é interpretada implicitamente como
  taxonomia de concorrentes indiretos.
- `keyword_only`: a frase consultada aparece no nome ou categoria observados,
  a categoria do negócio é conhecida e é diferente da categoria do alvo e das
  categorias relacionadas fornecidas.
- `indeterminate`: falta ID oficial, a comparação com o alvo é ambígua, há
  conflito de identidade, a categoria diverge entre observações ou não há sinal
  classificatório suficiente.

Cada classificação identificada inclui motivo, evidência, ocorrências e pontos
observados. O alvo é excluído. Registros sem identificação/conflictantes ficam
indeterminados, nunca são presumidos concorrentes diretos. Categorias iguais
são somente um proxy textual de concorrência, não comprovam que serviços ou
clientes sejam iguais.

### IOP — oportunidade de posicionamento, protótipo experimental não validado

Fórmula candidata aprovada exclusivamente para experimentação:

```text
IOP_ponto = 100 × (
    0.50 × lacuna_de_posição
  + 0.25 × facilidade_competitiva
  + 0.25 × facilidade_territorial
)

lacuna_de_posição = (rank - 1) / 19
facilidade_competitiva = 1 - força_média_ICP-B_V2
facilidade_territorial = 1 - recorrência_territorial
IOP_grade = média aritmética dos IOP_ponto utilizáveis
```

- Um `rank: null` em ponto bem-sucedido significa que o alvo não foi encontrado
  no top 20; no protótipo é tratado como lacuna máxima. Ponto com erro não
  recebe IOP.
- Componentes competitivos são globais à grade observada e aplicados a cada
  ponto. A média é uma sumarização descritiva da grade; pontos próximos são
  dependentes e não podem ser tratados como observações independentes.
- Não calcula probabilidade de sucesso, previsão de vendas nem oportunidade
  comprovada. Pesos, limiares e interpretação continuam sem validação empírica.
- O score é bloqueado se o ICP-B V2 não tem score (inclusive por conflito de
  identidade ou dados insuficientes), se cobertura de pontos válidos for menor
  que 80%, se a cobertura de pontos com competição utilizável for menor que 80%,
  ou se a cobertura de ranks utilizáveis for menor que 80%.
- Um ponto isolado pode não ter valor quando a posição é inválida ou o scan
  falhou; os motivos são explicitados. Sem dados suficientes, `score` é `null`.
- Resposta e interface mantêm `status: prototype_unvalidated` e rotulagem
  explícita de protótipo não validado.

## IDA — correção relacionada

- Reconcilia identificadores oficiais e deduplica antes de aplicar o mínimo
  amostral; uma repetição de CID/Place ID não aumenta a amostra.
- Quando recebe os IDs oficiais do alvo, exclui o alvo. Conflitos e registros
  ambíguos não contribuem para a pontuação.
- Avaliações com contagem negativa/fracionária, nota fora de 1–5 ou valores
  não finitos são ignoradas; a posição top-3 só contribui se a avaliação
  correspondente é utilizável.
- Mantém o caminho legado completo e o adaptativo para amostra moderada,
  exigindo duas observações válidas de avaliação no caminho moderado.
- Usa `confidence: not_estimated` e `evidence: descriptive`; não apresenta
  confiança estatística.
- Categoria não configurada, identidade insuficiente, amostra pequena ou
  avaliações ausentes resulta em `ida: null`.

## API, interface e compatibilidade

- A análise existente passa a retornar `icm`, `icpb_v2`, `ice` e `iop` junto
  dos campos preexistentes e do IDA.
- `related_category` é um parâmetro opcional repetível do endpoint de análise;
  omiti-lo não infere categorias indiretas.
- Resultados existentes do leaderboard passam a preservar `place_id`, e a
  resolução do negócio monitorado usa CID, depois Place ID, antes do nome.
- O painel marca IOP como protótipo não validado. Não foi feita alteração de
  produção nem chamada paga.

## Validação executada

- Ambiente usado: Python 3.14.2.
- Suíte completa: `python -m pytest -q` — **101 passed**.
- Testes focalizados de IDA/ICE/IOP e endpoint: **22 passed**.
- `node --check app/static/app.js` — passou.
- `git diff --check` — passou.
- Branch confirmada: `desenvolvimento-indicadores-geogrid`.
- Nenhum banco SQLite ou backup aparece como arquivo rastreado pelo Git.
- Alterações locais anteriores e backups permanecem no worktree, sem descarte.

## Próximos testes necessários antes de qualquer versão definitiva

1. **ICE:** formar conjunto rotulado por especialistas com negócios diretos,
   indiretos, apenas pela palavra-chave e ambíguos; avaliar matriz de confusão,
   precisão/recall por classe e concordância entre avaliadores. Repetir em
   setores e regiões diversos; medir separadamente casos sem categoria/ID.
2. **ICM:** comparar resultados e sensibilidade a prior, peso e referência de
   volume em dados identificados e repetidos; avaliar efeito de avaliações
   divergentes e cobertura de observações, sem interpretar score como
   probabilidade.
3. **ICP-B V2:** comparar ranking/estabilidade em grades e setores distintos;
   testar sensibilidade aos pesos de reputação, posição e recorrência, a falhas
   de ponto, conflitos de IDs e limiares de cobertura.
4. **IOP:** registrar, antes dos resultados, avaliações futuras observadas de
   mudança de rank para pontos/grades comparáveis; separar treino e teste por
   negócios, regiões e períodos. Fazer validação por blocos espaciais para
   reduzir vazamento entre pontos próximos; comparar a fórmula candidata com
   componentes isolados e pesos alternativos, documentando sensibilidade e
   casos sem cobertura.
5. Reavaliar os limites de cobertura com conjuntos de teste previamente
   definidos; não relaxar bloqueios só para aumentar a quantidade de scores.
6. Documentar amostra, procedimento, erros e limitações. Até esses testes e
   aprovação posterior, manter IOP como protótipo experimental não validado,
   sem afirmações de probabilidade, previsão de vendas ou oportunidade
   comprovada.
