Ниже — master-ТЗ, от которого уже можно строить backlog, OpenSpec capabilities, ADR и реализацию по этапам.

# Техническое задание
## Autonomous Quant R&D and Investment System

**Рабочее название:** Adaptive Alpha Engine
**Версия:** 1.0
**Статус:** Master Specification
**Тип системы:** автономная количественная R&D-платформа с последующим контролируемым использованием валидированных стратегий в инвестиционном контуре.

---

# 1. Назначение системы

Система предназначена для автоматизации полного цикла количественного инвестиционного R&D:

1. обнаружение научных и рыночных идей;
2. поиск и анализ литературы;
3. выявление противоречий, research gaps и нереплицированных результатов;
4. построение формализованных инвестиционных гипотез;
5. создание спецификаций стратегий;
6. автоматическая реализация стратегий в коде;
7. автоматическое тестирование;
8. out-of-sample и walk-forward validation;
9. защита от overfitting и multiple testing;
10. хранение всех успешных и неуспешных экспериментов;
11. эволюция стратегий;
12. выбор набора стратегий;
13. формирование portfolio allocation;
14. независимый risk control;
15. исполнение сделок;
16. сбор live evidence;
17. возврат live-результатов в R&D-контур;
18. улучшение самого исследовательского pipeline.

Система должна рассматриваться не как trading bot, а как:

> **автономный количественный R&D-отдел, способный производить, проверять и эволюционировать инвестиционные стратегии.**

---

# 2. Главная гипотеза проекта

Необходимо экспериментально проверить:

\[
SelfEvolvingResearchSystem
>
StaticResearchSystem
\]

при одинаковых:

- данных;
- LLM;
- compute budget;
- universe;
- evaluation protocol;
- временном бюджете.

Под «лучше» понимается не количество созданных стратегий, а:

\[
\frac{
ValidatedOutOfSampleAlpha
}{
ResearchCost
}
\]

Дополнительные критерии:

- меньший false discovery rate;
- меньший OOS degradation;
- более высокая robustness;
- более высокая diversity стратегий;
- более высокий hidden-OOS fitness.

---

# 3. Ключевые архитектурные принципы

## 3.1 Separation of Research and Production

Исследовательский и торговый контуры должны быть разделены.

```text
R&D SYSTEM
    ↓
Validated Strategy Artifact
    ↓
PRODUCTION INVESTMENT SYSTEM
```

Agent-generated code не должен исполняться непосредственно в production trading environment.

---

## 3.2 Separation of Intelligence and Control

AI-компоненты могут:

- предлагать;
- исследовать;
- программировать;
- анализировать;
- создавать стратегии.

AI-компоненты не могут самостоятельно:

- менять risk limits;
- менять evaluation protocol;
- менять capital permissions;
- отключать kill switch;
- очищать audit history;
- получать broker credentials;
- переводить стратегию в live;
- увеличивать leverage.

---

## 3.3 Fail Closed

Если недоступны:

- Risk Engine;
- market data validation;
- broker reconciliation;
- permissions service,

новые сделки запрещаются.

\[
CriticalServiceUnavailable
\Rightarrow
TradingDisabled
\]

---

## 3.4 Everything Is Versioned

Версионируются:

- datasets;
- features;
- strategies;
- prompts;
- agents;
- models;
- evaluation protocols;
- risk policies;
- execution policies;
- dependencies;
- experiment configurations.

---

## 3.5 Failed Experiments Are Knowledge

Нельзя хранить только победителей.

Каждая попытка должна попадать в Experiment Registry.

---

# 4. Границы MVP

MVP предназначен для проверки R&D-гипотезы.

## В MVP входят

- US liquid equities;
- ETF;
- daily data;
- historical research;
- point-in-time data model;
- feature engine;
- Research Agent;
- literature research;
- Strategy Spec;
- Ouroboros Engineering Agent;
- deterministic backtester;
- hidden OOS;
- walk-forward;
- transaction costs;
- robustness evaluation;
- Strategy Registry;
- Experiment Registry;
- Evolution Manager;
- mutation;
- basic crossover;
- R&D Orchestrator;
- paper trading;
- basic Risk Engine;
- audit;
- observability.

## В MVP не входят

- HFT;
- options;
- futures;
- leverage;
- short hard-to-borrow securities;
- market making;
- crypto;
- cross-exchange arbitrage;
- external investor capital;
- automatic withdrawals;
- multi-broker routing;
- autonomous modification of risk policy.

---

# 5. High-Level Architecture

```text
                   EXTERNAL RESEARCH SOURCES
       arXiv / OpenAlex / Semantic Scholar / Elicit
       ResearchGate / Hugging Face / GitHub
                           │
                           ▼
              SCIENTIFIC KNOWLEDGE GRAPH
                           │
          ┌────────────────┼────────────────┐
          ▼                ▼                ▼
 Literature Agent     Market Agent    Novelty Agent
          └────────────────┼────────────────┘
                           ▼
                  R&D ORCHESTRATOR
                           │
                           ▼
                    RESEARCH AGENT
                           │
                           ▼
                       HYPOTHESIS
                           │
                           ▼
                    STRATEGY SPEC
                           │
                           ▼
                      OUROBOROS
                           │
                           ▼
                    IMPLEMENTATION
                           │
                           ▼
              HIDDEN EVALUATION ENGINE
                           │
                 ┌─────────┴─────────┐
                 ▼                   ▼
               FAIL                 PASS
                 │                   │
                 ▼                   ▼
          Experiment Registry   Strategy Registry
                 │                   │
                 ▼                   ▼
              Critic          Strategy Clustering
                 │                   │
                 └──────┐            ▼
                        │      Portfolio Allocator
                        ▼            │
                Evolution Manager    ▼
                        │       IMMUTABLE RISK ENGINE
                        │            │
                        └───────┐    ▼
                                │ Execution Engine
                                │    │
                                │    ▼
                                │  Broker
                                │    │
                                │    ▼
                                │ Market
                                │    │
                                └────┴──→ Live Evidence
                                         │
                                         ▼
                                  Research Memory
```

---

# 6. Подсистемы

Система должна содержать следующие логические подсистемы.

1. External Research Connectors
2. Scientific Knowledge Graph
3. Literature Agent
4. Market Research Agent
5. Novelty / Contradiction Agent
6. Research Agent
7. R&D Orchestrator
8. Research Memory
9. Strategy Specification Service
10. Ouroboros Engineering Adapter
11. Sandbox
12. Evaluation Engine
13. Hidden Evaluation Service
14. Critic Agent
15. Experiment Registry
16. Strategy Registry
17. Evolution Manager
18. Strategy Similarity Engine
19. Market Data Service
20. Point-in-Time Data Store
21. Feature Store
22. Market World Model
23. Portfolio Allocator
24. Risk Engine
25. Execution Engine
26. Broker Adapter
27. Audit/Event Store
28. Identity and Permission Service
29. Secrets Service
30. Observability subsystem.

---

# 7. R&D Orchestrator

## Назначение

R&D Orchestrator управляет процессом исследования.

Он является control-plane для R&D, но не является evaluator.

## Обязанности

Оркестратор должен:

- выбирать research objective;
- создавать research jobs;
- распределять задачи между агентами;
- запускать несколько ветвей исследования параллельно;
- назначать research budgets;
- следить за состоянием задач;
- останавливать бесперспективные ветви;
- отправлять гипотезы в implementation;
- отправлять результаты Critic Agent;
- инициировать mutation/crossover;
- читать Experiment Registry;
- читать Strategy Registry;
- обновлять research priorities.

## Запрещено

Оркестратор не может:

- менять hidden OOS;
- менять evaluator;
- обходить hard gates;
- менять risk policy;
- переводить стратегию в live;
- отправлять broker orders.

---

# 8. Research Job

Каждая R&D-задача представляется объектом:

```yaml
research_job:
  id:
  objective:
  created_at:
  created_by:
  budget:
    llm_tokens:
    compute_seconds:
    max_experiments:
  universe:
  timeframe:
  allowed_data:
  status:
  parent_job:
```

Статусы:

```text
CREATED
RUNNING
PAUSED
COMPLETED
FAILED
CANCELLED
BUDGET_EXHAUSTED
```

---

# 9. External Research Sources

Система должна поддерживать adapter-based интеграцию с:

- arXiv;
- OpenAlex;
- Semantic Scholar;
- Elicit;
- Hugging Face;
- GitHub;
- другими источниками позже.

Каждый connector должен поддерживать общую модель:

```python
search(query)
get_document(id)
get_metadata(id)
get_references(id)
get_citations(id)
```

Если API не предоставляет часть функций, adapter возвращает capability metadata.

---

# 10. Scientific Knowledge Graph

## Назначение

Хранение machine-readable научного знания.

Основные сущности:

```text
Paper
Author
Concept
Claim
Evidence
Dataset
Method
Hypothesis
Experiment
Strategy
Result
```

Основные связи:

```text
Paper ──supports────→ Claim
Paper ──contradicts─→ Claim
Paper ──uses────────→ Method
Paper ──uses────────→ Dataset

Claim ──motivates───→ Hypothesis
Hypothesis ─────────→ Strategy
Strategy ───────────→ Experiment
Experiment ─────────→ Evidence
Evidence ──updates──→ Claim
```

---

# 11. Claim Model

```yaml
claim:
  id:
  text:
  domain:
  source_ids:
  confidence:
  evidence_for:
  evidence_against:
  peer_review_status:
  replication_status:
  created_at:
  updated_at:
```

---

# 12. Literature Agent

Literature Agent должен:

- искать papers;
- строить citation neighborhood;
- читать abstracts/full text;
- извлекать claims;
- извлекать methodology;
- извлекать datasets;
- извлекать reported performance;
- искать reproduction;
- искать follow-up papers;
- записывать результаты в Knowledge Graph.

Literature Agent не должен самостоятельно создавать production strategy.

---

# 13. Novelty / Contradiction Agent

Agent должен искать:

- conflicting evidence;
- failed replications;
- research gaps;
- contradictory results;
- unexplained anomalies;
- regime dependence;
- methodological weaknesses;
- assumptions likely to break in markets;
- missing transaction-cost treatment;
- missing OOS evaluation.

Output:

```yaml
research_gap:
  description:
  supporting_sources:
  conflicting_sources:
  significance:
  testability:
  proposed_direction:
```

---

# 14. Market Research Agent

Market Research Agent работает не с literature, а с market datasets.

Задачи:

- exploratory analysis;
- distribution analysis;
- regime detection;
- anomaly identification;
- temporal stability;
- cross-sectional relationships;
- correlation analysis;
- micro/macro contextual analysis;
- feature diagnostic tests.

Output не является trading strategy.

Output — Market Evidence.

---

# 15. Research Agent

Research Agent объединяет:

\[
ScientificEvidence
+
MarketEvidence
\rightarrow
Hypothesis
\]

Каждая гипотеза должна иметь:

```yaml
hypothesis:
  id:
  statement:
  economic_rationale:
  supporting_evidence:
  contradictory_evidence:
  expected_regime:
  expected_failure_modes:
  proposed_test:
  novelty_score:
  confidence:
```

---

# 16. Strategy Specification

Из hypothesis создаётся Strategy Spec.

```yaml
strategy:
  id:
  version:
  family:

  thesis:
    description:
    economic_mechanism:

  universe:
    asset_class:
    filters:

  timeframe:
    signal_frequency:
    rebalance_frequency:

  signals:
    - feature:

  entry_rules:
  exit_rules:

  position_sizing:

  portfolio_constraints:

  expected_regimes:

  invalid_regimes:

  expected_failure_modes:

  required_data:

  evaluation_protocol:

  parent_strategies:

  mutation_metadata:
```

Spec является source of truth для реализации.

---

# 17. Ouroboros Engineering Agent

## Назначение

Ouroboros выступает как Research Engineer.

Основной вход:

```text
Strategy Spec
```

Основной выход:

```text
Executable Strategy Artifact
```

## Может

- писать strategy code;
- писать feature code;
- писать research tools;
- писать tests;
- улучшать research workflows;
- создавать новые internal tools;
- предлагать изменение собственной agent architecture.

## Не может

- менять evaluator;
- менять risk engine;
- менять secrets;
- отправлять реальные ордера;
- менять immutable control-plane.

---

# 18. Agent Adapter

Система не должна зависеть от Ouroboros напрямую.

```python
class EngineeringAgent:
    propose_implementation(spec)
    implement(spec)
    fix_tests()
    create_tool()
    analyze_failure()
```

Это позволит заменить runtime без переписывания доменной системы.

---

# 19. Sandbox

Любой AI-generated code исполняется только в sandbox.

Требования:

- контейнерная изоляция;
- no broker credentials;
- no production secrets;
- ограниченный network;
- ограниченный filesystem;
- CPU limit;
- RAM limit;
- process limit;
- wall-clock timeout;
- reproducible environment;
- immutable base image.

---

# 20. Strategy Artifact

Структура:

```text
strategy_registry/
└── strategy_id/
    ├── manifest.yaml
    ├── spec.yaml
    ├── thesis.md
    ├── implementation/
    │   └── strategy.py
    ├── tests/
    ├── lineage.json
    ├── evaluation/
    ├── evidence/
    └── decisions/
```

---

# 21. Experiment Registry

Каждый запуск должен существовать как immutable experiment.

```yaml
experiment:
  id:
  research_job_id:
  strategy_id:
  strategy_version:
  experiment_type:
  dataset_versions:
  feature_versions:
  evaluator_version:
  config_hash:
  code_commit:
  random_seed:
  started_at:
  completed_at:
  status:
  result:
```

Статусы:

```text
PASS
FAIL
INVALID
OVERFIT
DUPLICATE
ERROR
CANCELLED
```

---

# 22. Запрет удаления failed experiments

Research Agent и Ouroboros не могут удалять результаты.

Все failed experiments должны участвовать в:

- multiple testing accounting;
- novelty checks;
- duplicate prevention;
- evolution history.

---

# 23. Evaluation Engine

Evaluation Engine является deterministic.

LLM не принимает финальный PASS/FAIL decision.

---

# 24. Evaluation Pipeline

```text
Static Validation
      ↓
Unit Tests
      ↓
Data Integrity
      ↓
Leakage Checks
      ↓
Backtest
      ↓
Transaction Costs
      ↓
Validation Period
      ↓
Public OOS
      ↓
Walk Forward
      ↓
Parameter Perturbation
      ↓
Universe Perturbation
      ↓
Regime Analysis
      ↓
Multiple Testing Adjustment
      ↓
Hidden OOS
      ↓
Final Verdict
```

---

# 25. Hidden Evaluation Zone

Hidden Evaluation Service должен быть физически и логически отделён.

Research Agents не получают raw hidden datasets.

Интерфейс:

```text
submit(candidate_artifact)
      ↓
hidden evaluation
      ↓
score
PASS / FAIL
limited diagnostics
```

Нельзя возвращать достаточно данных для обратной подгонки.

---

# 26. Data Splits

Минимальная схема:

```text
Research
Validation
Public OOS
Hidden OOS
Forward Live
```

Границы периодов фиксируются Evaluation Protocol.

---

# 27. Метрики стратегии

## Performance

- cumulative return;
- CAGR;
- annualized return;
- excess return.

## Risk

- volatility;
- downside volatility;
- max drawdown;
- drawdown duration;
- VaR;
- CVaR / Expected Shortfall.

## Risk-adjusted

- Sharpe;
- Sortino;
- Calmar.

## Trading

- turnover;
- number of trades;
- holding period;
- win rate;
- average win;
- average loss.

## Implementation

- transaction costs;
- spread;
- slippage;
- capacity estimate.

## Robustness

- IS/OOS degradation;
- parameter sensitivity;
- time stability;
- universe stability;
- regime stability;
- DSR;
- PBO where applicable.

---

# 28. Hard Evaluation Gates

Стратегия автоматически отклоняется при нарушении обязательных условий.

Примеры:

```text
LOOK_AHEAD_BIAS       → FAIL
SURVIVORSHIP_BIAS     → FAIL
NO_TRANSACTION_COSTS  → FAIL
NEGATIVE_HIDDEN_OOS   → FAIL
INSUFFICIENT_SAMPLE   → FAIL
```

Численные thresholds должны храниться отдельно как immutable Evaluation Protocol.

---

# 29. Evaluation Protocol Versioning

```text
evaluation_protocol_v1
evaluation_protocol_v2
...
```

Каждая strategy evaluation должна хранить использованную версию.

Нельзя напрямую сравнивать scores, полученные несовместимыми протоколами.

---

# 30. Critic Agent

Critic Agent анализирует результаты после deterministic evaluation.

Он должен отвечать:

- почему стратегия могла работать;
- где она не работает;
- какие режимы наиболее важны;
- есть ли признаки overfitting;
- есть ли hidden factor exposure;
- что необходимо проверить следующим экспериментом;
- какая mutation имеет экономический смысл.

Critic не меняет PASS/FAIL.

---

# 31. Evolution Manager

Evolution Manager управляет population стратегии.

Поддерживает:

- mutation;
- crossover;
- novelty generation;
- parent selection;
- champion/challenger;
- diversity preservation;
- lineage management.

---

# 32. Mutation Operators

Минимальный набор:

```text
signal_mutation
feature_mutation
lookback_mutation
entry_rule_mutation
exit_rule_mutation
position_sizing_mutation
regime_filter_mutation
portfolio_rule_mutation
model_mutation
```

Каждая mutation должна иметь semantic description.

---

# 33. Crossover

Создаёт новую стратегию.

```yaml
parents:
  - strategy_A
  - strategy_B

crossover:
  inherited_from_A:
    - signals
  inherited_from_B:
    - position_sizing
```

---

# 34. Diversity

Evolution Manager не должен всегда выбирать только лучший fitness.

Нужна multi-objective функция:

\[
SelectionScore =
Fitness
+
\lambda Novelty
+
\gamma Diversity
\]

Чтобы избежать convergence к одному strategy family.

---

# 35. Strategy Registry

Registry содержит:

- все версии;
- статус;
- lineage;
- evaluation evidence;
- live evidence;
- applicability regimes;
- failure modes;
- current allocation;
- retirement reason.

Статусы:

```text
RESEARCH
BACKTESTING
REJECTED
VALIDATED
PAPER
SHADOW
CANARY
ACTIVE
PAUSED
RETIRED
INVALIDATED
```

---

# 36. Strategy Similarity Engine

Нужен для определения, являются ли стратегии реально независимыми.

Используются:

- return correlation;
- factor exposure similarity;
- signal correlation;
- holdings overlap;
- drawdown overlap;
- regime sensitivity;
- optional strategy embeddings.

Output:

```yaml
similarity:
  strategy_a:
  strategy_b:
  return_corr:
  factor_similarity:
  holdings_overlap:
  cluster_id:
```

---

# 37. Strategy Clustering

Перед Portfolio Allocator стратегии группируются по economic similarity.

Ограничения могут задаваться на cluster level.

Пример:

\[
Allocation_{MomentumCluster}<30\%
\]

даже если кластер содержит 15 разных implementations.

---

# 38. Market Data Service

Обязанности:

- historical ingestion;
- live ingestion;
- normalization;
- symbol mapping;
- timestamps;
- corporate actions;
- validation;
- missing-data handling.

---

# 39. Point-in-Time Data

Каждая запись должна учитывать реальное время доступности информации.

```yaml
dataset:
  id:
  version:
  source:
  event_time:
  available_time:
  ingestion_time:
  point_in_time_valid:
```

Нельзя использовать revised data так, будто оно было известно раньше.

---

# 40. Feature Store

```yaml
feature:
  id:
  version:
  formula:
  inputs:
  lookback:
  delay:
  code_hash:
  created_at:
```

Новые версии feature не изменяют исторические experiments.

---

# 41. Market World Model

World Model формирует machine-readable состояние рынка.

```yaml
market_state:
  timestamp:
  volatility_regime:
  trend_regime:
  liquidity_regime:
  correlation_regime:
  dispersion:
  breadth:
  risk_on_off:
  confidence:
```

World Model является input для Research Agent, Strategy Registry и Portfolio Allocator.

---

# 42. Portfolio Allocator

Принимает:

```text
Validated Strategies
+
Expected Risk
+
Correlation
+
Market Regime
+
Live Performance
+
Capacity
```

и производит desired allocations.

Он не отправляет orders напрямую.

---

# 43. Portfolio Allocation Model

Общая форма:

\[
Portfolio =
\sum_i w_i Strategy_i
\]

Ограничения:

\[
\sum_i |w_i| \le G_{max}
\]

\[
PortfolioRisk \le RiskBudget
\]

MVP может использовать:

- equal risk;
- volatility scaling;
- capped weighting.

---

# 44. Risk Engine

Risk Engine является независимым immutable сервисом.

Он имеет последнее слово перед execution.

---

# 45. Risk Engine Layers

## L0 — Permissions

- asset allowed;
- venue allowed;
- strategy allowed;
- trading status.

## L1 — Order Risk

- max order size;
- max order notional;
- price sanity;
- duplicate order;
- stale signal.

## L2 — Position Risk

- single-name exposure;
- sector exposure;
- concentration.

## L3 — Portfolio Risk

- gross exposure;
- net exposure;
- portfolio volatility;
- CVaR / ES.

## L4 — Factor Risk

- market beta;
- sector factors;
- momentum;
- value;
- size;
- volatility;
- other configured factors.

## L5 — Strategy Risk

- strategy allocation;
- cluster allocation;
- strategy correlation.

## L6 — Liquidity

- ADV;
- participation;
- days-to-liquidate;
- spread;
- impact estimate.

## L7 — Stress Testing

- historical scenarios;
- synthetic scenarios;
- correlation shocks.

## L8 — Drawdown

- strategy drawdown;
- portfolio drawdown;
- daily loss.

## L9 — Operational Health

- stale market data;
- broker mismatch;
- missing risk data;
- service degradation.

---

# 46. Risk Decision

Input:

```yaml
order_intent:
  strategy_id:
  instrument:
  side:
  quantity:
  price:
```

Output:

```yaml
risk_decision:
  status:
    APPROVE | REDUCE | REJECT | HALT

  approved_quantity:

  checks:
    - rule:
      status:
      value:
      limit:

  timestamp:
  policy_version:
```

---

# 47. Kill Switch

Kill switch должен быть вне AI control-plane.

При activation:

1. запретить новые orders;
2. отменить open orders;
3. перевести execution в HALTED;
4. зарегистрировать audit event;
5. уведомить оператора.

---

# 48. Execution Engine

Получает только approved order intents.

Интерфейс:

```python
submit_order()
cancel_order()
replace_order()
get_order()
get_orders()
get_fills()
get_positions()
get_account_state()
```

---

# 49. Broker Adapter

Broker-specific API скрывается за adapter.

MVP:

```text
PaperBroker
AlpacaPaperAdapter
```

Позже:

```text
IBKRAdapter
```

---

# 50. Idempotency

Каждый order имеет:

```text
order_intent_id
```

Повторная доставка идентичного intent не создаёт второй order.

---

# 51. Reconciliation

Система регулярно сравнивает:

\[
InternalPositions
\]

с

\[
BrokerPositions.
\]

При mismatch:

```text
HALT
+
Alert
+
ReconciliationRequired
```

---

# 52. Paper Trading

Перед live требуется forward paper testing.

Pipeline:

```text
Validated
→ Paper
→ Shadow
→ Canary
→ Own Capital
```

Переходы автоматизируются только до PAPER.

Дальнейшие требуют human approval.

---

# 53. Live Evidence

Каждая production strategy генерирует:

- realised returns;
- expected vs realised slippage;
- risk;
- drawdown;
- regime performance;
- signal decay;
- model drift.

Live evidence возвращается в Research Memory.

---

# 54. Drift Detection

Система должна мониторить:

- feature drift;
- signal drift;
- return drift;
- volatility drift;
- correlation drift;
- execution drift;
- regime drift.

При сильной деградации:

```text
ACTIVE → PAUSED
```

или allocation уменьшается.

---

# 55. Research Memory

Хранилище долговременного знания.

```text
research_memory/
├── papers/
├── claims/
├── contradictions/
├── hypotheses/
├── experiments/
├── failures/
├── strategies/
├── live_evidence/
└── agent_improvements/
```

---

# 56. Два Evolution Loop

## Strategy Evolution

Эволюционируют:

- signals;
- strategies;
- features;
- models;
- portfolio logic.

## Agent Evolution

Эволюционируют:

- prompts;
- research workflows;
- tools;
- memory mechanisms;
- code-generation pipeline;
- literature workflow.

Agent Evolution проходит отдельный benchmark.

---

# 57. Agent Benchmark

Сравнение:

```text
ResearchAgent_vN
vs
ResearchAgent_vN+1
```

при одинаковом:

- data;
- tasks;
- token budget;
- compute;
- evaluator.

Metrics:

- validated strategies;
- hidden OOS;
- novelty;
- false discoveries;
- cost;
- time-to-valid-strategy.

---

# 58. Immutable Control Plane

Следующие каталоги или logical modules защищены:

```text
risk/
evaluation/
permissions/
secrets/
audit/
capital_gates/
production_policy/
```

AI не может модифицировать их без human OpenSpec change.

---

# 59. OpenSpec

OpenSpec используется для изменения самой платформы.

```text
openspec/
├── specs/
│   ├── research-orchestrator/
│   ├── knowledge-graph/
│   ├── strategy-registry/
│   ├── evaluation-engine/
│   ├── evolution-engine/
│   ├── risk-engine/
│   └── execution-engine/
└── changes/
```

---

# 60. Strategy Spec и OpenSpec — разные сущности

OpenSpec:

> как должна работать система.

Strategy Spec:

> как должна работать инвестиционная стратегия.

Нельзя смешивать эти документы.

---

# 61. Audit System

Для любого experiment или trade должна восстанавливаться цепочка:

```text
source data
→ feature
→ model
→ strategy version
→ signal
→ portfolio decision
→ risk decision
→ order
→ fill
→ PnL
```

---

# 62. Event Store

Append-only events:

```text
research.job_started
hypothesis.created
strategy.created
strategy.mutated
strategy.evaluated
strategy.rejected
strategy.validated

risk.approved
risk.rejected
risk.halt

execution.submitted
execution.filled

agent.created
agent.promoted
```

---

# 63. Security

## Secrets

Никогда не передаются агенту.

## Credentials

Broker credentials доступны только Execution Service.

## Agent Identity

Research Agent имеет отдельную identity.

## Least Privilege

Каждый сервис получает минимально необходимые permissions.

---

# 64. Network Security

Sandbox не должен иметь unrestricted Internet.

Разрешённые endpoints задаются policy.

Production broker network доступен только Execution Engine.

---

# 65. Data Integrity

Каждый dataset должен иметь:

```text
content hash
schema hash
source
version
ingestion time
```

---

# 66. Reproducibility

Каждый experiment должен воспроизводиться по:

```text
dataset versions
feature versions
strategy version
commit SHA
container image
dependency lock
random seed
evaluation protocol
```

---

# 67. Observability

## R&D dashboard

- active research jobs;
- experiment rate;
- failed experiments;
- validated strategies;
- generation count;
- compute cost;
- LLM cost.

## Portfolio dashboard

- NAV;
- PnL;
- strategy allocations;
- gross/net exposure;
- volatility;
- CVaR;
- drawdown.

## Risk dashboard

- current limits;
- breached limits;
- risk decisions;
- kill-switch status.

## Execution dashboard

- open orders;
- fills;
- slippage;
- reconciliation status.

---

# 68. Technology Stack

## Core

```text
Python 3.12
FastAPI
Pydantic
PostgreSQL
```

## Research

```text
NumPy
Polars
Pandas where necessary
SciPy
scikit-learn
PyTorch when required
```

## Storage

```text
PostgreSQL
Parquet
S3-compatible Object Storage
```

## Analytics

На MVP:

```text
DuckDB
Polars
```

## Infrastructure

```text
Docker
Git
CI/CD
OpenSpec
```

## Agent layer

```text
Ouroboros adapter
LLM provider abstraction
```

---

# 69. Proposed Repository

```text
adaptive-alpha/
│
├── openspec/
│
├── src/
│   ├── orchestrator/
│   ├── research/
│   │   ├── literature/
│   │   ├── market/
│   │   ├── novelty/
│   │   └── knowledge_graph/
│   │
│   ├── agents/
│   │   ├── research_agent/
│   │   ├── critic/
│   │   └── ouroboros/
│   │
│   ├── strategies/
│   ├── experiments/
│   ├── evaluation/
│   ├── evolution/
│   ├── data/
│   ├── features/
│   ├── world_model/
│   ├── portfolio/
│   ├── risk/
│   ├── execution/
│   ├── brokers/
│   ├── audit/
│   ├── auth/
│   └── api/
│
├── strategy_registry/
├── research_memory/
├── datasets/
├── tests/
├── scripts/
├── infra/
└── docs/
```

---

# 70. Backend Service Boundaries

Минимальный набор сервисов:

```text
research-service
orchestrator-service
agent-service
experiment-service
evaluation-service
strategy-registry
market-data-service
portfolio-service
risk-service
execution-service
audit-service
```

На MVP допускается modular monolith с жёсткими module boundaries.

---

# 71. API: Research

```text
POST /research/jobs
GET  /research/jobs/{id}
POST /research/jobs/{id}/run
POST /research/jobs/{id}/cancel

POST /hypotheses
GET  /hypotheses/{id}
```

---

# 72. API: Strategy

```text
POST /strategies
GET  /strategies/{id}
GET  /strategies/{id}/versions
GET  /strategies/{id}/lineage
```

---

# 73. API: Evaluation

```text
POST /evaluations
GET  /evaluations/{id}
GET  /strategies/{id}/evaluations
```

---

# 74. API: Evolution

```text
POST /evolution/mutate
POST /evolution/crossover
POST /evolution/generate
GET  /evolution/generations
```

---

# 75. API: Portfolio

```text
GET /portfolio
GET /portfolio/allocations
GET /portfolio/exposures
```

---

# 76. API: Risk

Agent имеет только read access.

```text
GET /risk/status
GET /risk/metrics
GET /risk/limits
```

Order validation:

```text
POST /risk/check
```

Изменение limits доступно только operator identity.

---

# 77. API: Execution

```text
POST /orders
DELETE /orders/{id}
GET /orders
GET /fills
GET /positions
```

Execution API не доступен Research Agent.

---

# 78. Testing Strategy

## Unit Tests

- features;
- metrics;
- risk checks;
- portfolio calculations;
- data normalization.

## Property-Based Tests

- risk limits;
- allocation constraints;
- idempotency.

## Integration Tests

```text
strategy
→ evaluator
→ registry
```

и

```text
portfolio
→ risk
→ execution
```

## Replay Tests

Исторические trading sessions.

## Chaos Tests

- market data outage;
- broker outage;
- duplicate messages;
- delayed fills;
- process crashes;
- stale data;
- partial fills.

---

# 79. Critical Invariants

## INV-001

Ни один order не может попасть в Execution без Risk approval.

## INV-002

Research Agent не имеет broker credentials.

## INV-003

Agent не может менять Risk Engine.

## INV-004

Agent не может менять Evaluation Engine.

## INV-005

Каждый experiment immutable.

## INV-006

Failed experiments сохраняются.

## INV-007

Каждая strategy version имеет lineage.

## INV-008

Каждая live strategy version immutable.

## INV-009

Любой trade полностью auditable.

## INV-010

Hidden OOS недоступен Research Agent.

## INV-011

Risk Engine failure блокирует trading.

## INV-012

Kill switch не контролируется AI.

---

# 80. MVP Phase 0 — Foundations

Реализовать:

- repository;
- OpenSpec;
- CI;
- Docker environment;
- PostgreSQL;
- experiment model;
- strategy model;
- dataset versioning;
- audit foundation.

Acceptance:

- один experiment полностью reproducible;
- immutable metadata работает;
- CI проходит.

---

# 81. MVP Phase 1 — Quant Laboratory

Реализовать:

- Market Data;
- Point-in-Time Data;
- Feature Engine;
- Backtester;
- Evaluation Engine;
- transaction-cost model;
- Strategy Registry.

Без AI.

Acceptance:

- deterministic backtests;
- reproducibility;
- benchmark strategies;
- no look-ahead checks.

---

# 82. MVP Phase 2 — Static Research Agent

Реализовать:

```text
literature
→ hypothesis
→ strategy spec
→ implementation
→ experiment
```

Без self-evolution.

Acceptance:

Research Agent самостоятельно создаёт минимум одну executable strategy из research objective.

---

# 83. MVP Phase 3 — Autonomous R&D Orchestration

Добавить:

- R&D Orchestrator;
- Knowledge Graph;
- Literature Agent;
- Novelty Agent;
- Market Agent;
- Critic Agent.

Acceptance:

Один research job проходит полный lifecycle без ручного orchestration.

---

# 84. MVP Phase 4 — Evolutionary Strategies

Добавить:

- mutation;
- crossover;
- lineage;
- champion/challenger;
- Experiment Registry;
- diversity.

Acceptance:

Минимум три generations автоматически создаются и оцениваются.

---

# 85. MVP Phase 5 — Hidden Evaluator

Добавить:

- hidden dataset;
- isolated evaluation;
- restricted feedback.

Acceptance:

Research system физически не имеет доступа к hidden data.

---

# 86. MVP Phase 6 — Agent Self-Evolution

Добавить Ouroboros modification loop.

Разрешить изменение:

- prompts;
- workflows;
- research tools.

Запретить изменение finance control plane.

Acceptance:

Agent_v2 должен сравниваться с Agent_v1 на фиксированном benchmark.

---

# 87. MVP Phase 7 — Paper Trading

Добавить:

- live feed;
- Portfolio Allocator;
- Risk Engine V0;
- Paper Broker;
- execution;
- reconciliation.

Acceptance:

Система может непрерывно работать на forward data без будущей информации.

---

# 88. Risk Engine V0

Минимум:

```text
position limits
strategy allocation limits
gross exposure
portfolio volatility
CVaR
drawdown
daily loss
stale-data control
kill switch
```

---

# 89. Main Scientific Benchmark

Две системы:

```text
A = Static AI Research Agent
B = Self-Evolving R&D System
```

Одинаковые:

- universe;
- datasets;
- model family;
- token budget;
- compute budget;
- number of experiments.

Сравнить:

\[
HiddenOOSFitness
\]

\[
ValidatedStrategies
\]

\[
FalseDiscoveryRate
\]

\[
ResearchCostPerValidatedStrategy
\]

\[
OOSDecay
\]

---

# 90. MVP Definition of Done

MVP считается завершённым, если система автоматически выполняет:

```text
Research Objective
      ↓
Literature Search
      ↓
Evidence Graph
      ↓
Hypothesis
      ↓
Strategy Spec
      ↓
Code
      ↓
Tests
      ↓
Backtest
      ↓
OOS
      ↓
Walk Forward
      ↓
Hidden Evaluation
      ↓
PASS / FAIL
      ↓
Experiment Registry
      ↓
Evolution
      ↓
Next Generation
```

без ручного написания strategy code.

---

# 91. Product Success Criteria

Проект признаётся перспективным, если одновременно:

### Research

Self-evolving system statistically outperforms static research baseline.

### Finance

Найденные стратегии показывают positive OOS after costs.

### Robustness

Alpha сохраняется при perturbations.

### Safety

Self-evolution не может обходить control-plane.

### Economics

\[
ExpectedValueOfResearch
>
ComputeAndInfrastructureCost
\]

---

# 92. Запрещённые shortcut-подходы

Нельзя считать успехом:

- высокий IS Sharpe;
- одну успешную стратегию;
- лучший backtest после тысяч неизвестных попыток;
- отсутствие transaction costs;
- survivorship-biased universe;
- тест на данных, доступных Research Agent;
- изменение evaluator ради прохождения теста.

---

# 93. Долгосрочное развитие

После успешного MVP:

## V2

- richer factor model;
- better stress engine;
- intraday strategies;
- additional datasets;
- advanced portfolio allocation.

## V3

- futures;
- cross-asset;
- regime-specific populations;
- advanced execution.

## V4

- small own capital;
- canary strategy deployment.

## V5

- regulatory preparation;
- external capital infrastructure;
- investor reporting;
- fund administration;
- custody/compliance.

---

# 94. Финальная архитектурная формула

Проект состоит из трёх независимых систем:

\[
\boxed{
ScientificDiscoveryEngine
}
\]

отвечает за:

\[
Literature + MarketEvidence
\rightarrow Hypothesis
\]

\[
\boxed{
AutonomousResearchEngineering
}
\]

отвечает за:

\[
Hypothesis
\rightarrow
Specification
\rightarrow
Code
\rightarrow
Experiment
\]

\[
\boxed{
IndependentVerificationAndInvestmentSystem
}
\]

отвечает за:

\[
Experiment
\rightarrow
Evidence
\rightarrow
ValidatedStrategy
\rightarrow
Portfolio
\rightarrow
Risk
\rightarrow
Execution
\]

Ни один из трёх контуров не должен полностью контролировать остальные.

---

# 95. Главный принцип проекта

> **Мы строим не AI, который умеет торговать, а автономную количественную исследовательскую организацию, которая систематически производит проверяемые инвестиционные знания и допускает их к капиталу только через независимый deterministic verification и risk-control pipeline.**

Это определяет все последующие архитектурные решения.

Я бы теперь **не начинал сразу кодировать всю систему**. Следующий инженерно правильный шаг — превратить это master-ТЗ в примерно **10–12 OpenSpec capabilities**, а затем для первой capability (`Experiment Registry + Evaluation Engine`) сделать полноценные `proposal.md → spec.md → design.md → tasks.md`.

Именно с `Evaluation Engine` я бы начал разработку: без надёжного evaluator всё остальное, включая Ouroboros, будет просто очень быстро производить потенциально переобученные стратегии.
