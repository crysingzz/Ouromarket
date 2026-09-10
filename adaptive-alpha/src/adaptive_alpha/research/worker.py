"""Dedicated worker entrypoint; no generated program is executed natively."""

import signal
import time

from adaptive_alpha.config import Settings
from adaptive_alpha.research.campaigns import Campaigns
from adaptive_alpha.store import Store


def main() -> None:
    settings = Settings()
    store = Store(settings.database_url, manage_schema=settings.manage_schema)
    store.initialize()
    campaigns = Campaigns(store, settings)
    stopping = False

    def stop(signum: int, frame: object) -> None:
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        while not stopping:
            settings = Settings()
            campaigns.settings = settings
            with store.transaction() as conn:
                store.set_state(
                    conn,
                    "research-worker",
                    {
                        "heartbeat": time.time(),
                        "openai_key_configured": bool(
                            settings.openai_api_key and settings.openai_api_key.get_secret_value()
                        ),
                        "ouroboros_configured": bool(
                            settings.ouroboros_url and settings.ouroboros_workspace
                        ),
                    },
                )
            claimed = campaigns.claim()
            if claimed:
                campaigns.run(*claimed)
            else:
                time.sleep(1)
    finally:
        store.engine.dispose()


if __name__ == "__main__":
    main()
