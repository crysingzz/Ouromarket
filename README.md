# Ouromarket

Adaptive Alpha — лаборатория количественных исследований с инженерным агентом Ouroboros, жизненным циклом стратегий и независимым контролем paper-исполнения.

Приложение, запуск через Docker, uv-окружение, UI, OpenSpec и тесты находятся в [adaptive-alpha](adaptive-alpha/README.md). Проверки: Ruff, Pyrefly, mypy и pytest с обязательным 100% покрытием исполняемых Python-строк.

Настоящий [Ouroboros](https://github.com/razzant/ouroboros) подключён Git submodule в `ouroboros-runtime/`: версия 6.114.0, upstream-коммит `b9bcc2da71e0bd51b6f5f906890b3b80265defed`. Его исходники и uv lock отделены от Adaptive Alpha. Доставка исходников не включает локальные изменения старого checkout.

```text
ouromarket/
├── adaptive-alpha/       # лаборатория, оценка, риск, UI
├── ouroboros-runtime/    # закреплённые исходники upstream
└── integration/          # Docker, авторизация и отдельные Git-workspace
```

После клонирования: `git submodule update --init ouroboros-runtime`. [Инструкция интеграции](integration/README.md) запускает настоящий сервер в режиме проверки протокола. Healthcheck и workspace работают; без модели upstream отклоняет задания с `worker_pool_unavailable`. Adaptive Alpha уже сохраняет бюджет и все стадии инженерного запуска в append-only журнале и показывает очищенное состояние runtime в UI. Исполняющий model profile, crash-safe очередь и реальная торговля ещё не включены.
