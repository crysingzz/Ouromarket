# Adaptive Alpha Engine

Python-платформа количественных исследований с независимыми оценкой и управлением риском, операторским UI и paper-исполнением. Создана по приложенной схеме и [master-ТЗ](docs/master-specification.md).

Принятая целевая модель — [управляемый жизненный цикл стратегий и инженерная роль Ouroboros](docs/TARGET-OPERATING-MODEL.md). Это направление развития, а не описание всех возможностей текущей версии.

**v0.3: жизненный цикл активной paper-стратегии и претендентов, инженерные задания Ouroboros, реестр артефактов и подписанные разрешения внешнего paper-исполнения.** [Что реализовано и как проверить](docs/LIFECYCLE.md). Ruff, Pyrefly и тесты с обязательным 100% statement coverage запускаются через `make check`.

Основа v0.2 включает поиск литературы, устойчивую очередь, ограниченный Python DSL, отдельную скрытую оценку и настройку OpenAI через UI. Прежний demo-v1 сохранён отдельно. Это ещё не полная приёмка master-ТЗ: [точная карта покрытия](docs/STATUS.md), [инструкция исследований](docs/AUTONOMOUS.md). Реальные деньги недоступны; PASS не означает инвестиционный допуск.

## Запуск через Docker

Нужны Docker Compose и uv; окружение Python 3.12 управляется uv.

```bash
cd adaptive-alpha
uv sync --locked
uv run python scripts/bootstrap.py
make up
```

Открыть **http://localhost:8787**. Ввести содержимое `.secrets/operator_token` в форму подключения. Токен не сохраняется в браузере; при перезагрузке нужно подключиться снова.

`bootstrap.py` создаёт токены без вывода в лог и не меняет уже существующие секреты. `make up` собирает образ с Git commit и hash `uv.lock`. Прямой `docker compose up --build -d` тоже работает, но build provenance по умолчанию обозначается `development`.

```bash
docker compose ps
docker compose logs --tail=100 api evaluator
docker compose down
```

Обычный `down` сохраняет данные. Не используйте удаление volumes для сброса research history или hidden query budget.

## Автономное исследование

Откройте **Autonomous R&D → Настроить OpenAI**, сохраните ключ и выберите модель. Нажмите **Создать тестовые данные** для проверки механики либо импортируйте свой рыночный snapshot. Заполните цель, поисковый запрос и бюджет. Worker сохранит публикации, исходный код, проверки, метрики и результаты поколений. По желанию он предложит улучшение собственного исследовательского метода в рамках того же бюджета. [Подробная инструкция](docs/AUTONOMOUS.md).

## Прежняя демонстрационная лаборатория

1. **New research job** → задать objective, experiment и compute budgets.
2. Просмотреть три поколения: hypothesis → StrategySpec → trusted template artifact → public evaluation → separate hidden feedback → immutable experiment → mutation.
3. Открыть **Inspect** у эксперимента: хеши данных, spec/code/environment provenance, public OOS/folds/costs, ограниченный hidden verdict.
4. У стратегии с PASS выбрать **Admit to demo paper**. Если ни одна не прошла, это нормальный результат; пороги не меняются ради демонстрации.
5. В Portfolio обновить **фиксированный синтетический snapshot** и отправить небольшой paper order. Цена и риск определяются сервером. Snapshot старше 60 секунд блокирует следующую заявку.
6. Проверить Risk controls и аварийную остановку, затем Audit trail. Возобновление — только оператором после reconciliation.

## Локальная разработка без Docker

```bash
uv sync --locked
sh scripts/run-local.sh
```

Это API, evaluator и исследовательский worker на loopback с разными SQLite-файлами. **Физическую контейнерную изоляцию проверяйте через Compose**; локальные процессы одного OS-пользователя не являются границей безопасности.

## Проверки

```bash
uv run ruff check src tests scripts
uv run ruff format --check src tests scripts
uv run mypy src
uv run pytest --cov=adaptive_alpha --cov-report=term-missing
make spec
uv run pip-audit --skip-editable
```

[Результаты проверок](docs/VERIFICATION.md). OpenSpec CLI закреплён на `@fission-ai/openspec@1.12.0`; `make spec` запускает strict validation. npm нужен только для OpenSpec tooling; UI не требует Node-сборки.

## API и доступ

Все бизнес-маршруты имеют prefix `/api` и требуют `Authorization: Bearer <token>`. `/healthz` и static UI публичны. OpenAPI JSON доступен оператору: `/api/openapi.json`.

| Контур | Основные маршруты |
|---|---|
| Research | `POST/GET /research/jobs`, `GET /research/jobs/{id}`, `POST /research/jobs/{id}/run`, `POST /research/jobs/{id}/cancel` |
| Hypotheses/specs | `POST /hypotheses`, `GET /hypotheses/{id}`, `POST/GET /strategies`, `GET /strategies/{id}`, `GET /strategies/{id}/lineage` |
| Experiments | `GET /attempts`, `GET /experiments` |
| Evolution | `POST /evolution/mutate` (optional second_parent_id включает crossover) |
| Operator | `POST /strategies/{id}/paper`, `GET /portfolio`, `POST/GET /orders`, `GET /fills` |
| Risk | `GET /risk/limits`, `GET /risk/status`; operator-only `POST /risk/check`, `/risk/halt`, `/risk/resume` |
| Diagnostics | Operator-only `GET /audit`, `GET /dashboard`, `POST /market/demo-refresh` |

`research_token` — отдельная identity для будущего внешнего agent runtime. Ему нельзя выдавать host shell, checkout, Docker socket, DB/service/operator secrets. Текущий пакет не запускает родительский Ouroboros. [Модель безопасности](docs/SECURITY.md).

## Воспроизведение

В диалоге **Inspect** нажмите **Download reproduction bundle**. Для эксперимента, запущенного в Docker:

```bash
docker compose exec -T api python -m adaptive_alpha.reproduce --stdin < experiment-ID.json
```

Локальный эксперимент можно воспроизвести в том же локальном окружении:

```bash
uv run python -m adaptive_alpha.reproduce --stdin < experiment-ID.json
```

Также поддерживаются отдельные experiment.json и strategy.json через `uv run python scripts/reproduce.py experiment.json strategy.json`.

Проверяются content hash, config hash и точное равенство публичного результата, включая trial count. NumPy/libm на macOS и Linux могут различаться в последних разрядах: locked Python dependencies сами по себе не гарантируют побитовую переносимость. Поэтому для Docker-эксперимента используйте исходный pinned image и его архитектуру. Несовпадение хеша блокирует воспроизведение; оно не скрывается допуском. Hidden данные не экспортируются; повтор той же hidden experiment identity возвращает исходный ответ.

## OpenSpec и архитектура

- [Архитектура](docs/ARCHITECTURE.md), [ADR 0001](docs/adr/0001-independent-control-plane.md).
- `openspec/specs/` — 12 capability contracts; требования target-only явно отражены в STATUS.
- [Первое изменение](openspec/changes/initialize-quant-laboratory/proposal.md): proposal → spec deltas → design → tasks.
- OpenSpec описывает платформу; `StrategySpec` описывает инвестиционную гипотезу и её исполнимый шаблон. Это разные сущности.
- [OpenSpec](https://github.com/Fission-AI/OpenSpec) и [официальная инструкция uv/Docker](https://docs.astral.sh/uv/guides/integration/docker/) использованы для структуры спецификаций и locked container build.

## Ограничения v0.1

Полноценные literature/market/novelty агенты, произвольная генерация Python, sandbox execution, DSR/PBO, реальный PIT feed, allocator/clustering, external paper broker, agent self-evolution и научный A/B benchmark пока отсутствуют. Временные folds проверяют фиксированную стратегию без переобучения; multiplicity penalty не называется DSR. Compute budget ограничивает admission следующего опыта, а один начатый bounded HTTP-вызов может закончиться позже границы. При process crash attempt сохраняется, но автоматического восстановления job нет. Списки UI ограничены последними 200 записями, аудит — 100 событиями; история в БД не удаляется.

Контрольный контур и PostgreSQL schema bootstrap являются доверенным кодом. Структурные security controls не равны независимому security-аудиту или готовности к эксплуатации с реальным капиталом.

Для provenance эксперименты дополнительно сохраняют hash фактического Python source tree, Python version и pinned container base image. Git HEAD может быть базовым commit при сборке незакоммиченных изменений; source hash отражает фактически собранный код.
