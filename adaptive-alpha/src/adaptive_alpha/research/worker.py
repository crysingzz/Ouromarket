"""Dedicated worker entrypoint; no generated program is executed natively."""

import signal
import time

from adaptive_alpha.config import Settings
from adaptive_alpha.research.campaigns import Campaigns
from adaptive_alpha.research.ouroboros import OuroborosEngineer
from adaptive_alpha.store import Store


def engineering_runtime_status(settings: Settings) -> dict[str, object]:
    configured = bool(settings.ouroboros_url and settings.ouroboros_workspace)
    if not configured:
        return {"configured": False, "ready": False, "reason": "NOT_CONFIGURED"}
    try:
        return OuroborosEngineer(
            settings.ouroboros_url,
            settings.ouroboros_workspace,
            service_token=settings.ouroboros_token.get_secret_value()
            if settings.ouroboros_token
            else "",
            provision_workspaces=settings.ouroboros_provision_workspaces,
        ).status()
    except Exception as error:
        return {
            "configured": True,
            "ready": False,
            "execution_enabled": False,
            "reason": type(error).__name__.upper()[:100],
        }


def main() -> None:
    settings = Settings()
    store = Store(settings.database_url, manage_schema=settings.manage_schema)
    store.initialize()
    campaigns = Campaigns(store, settings)
    stopping = False
    last_runtime_probe = 0.0
    runtime = {"configured": False, "ready": False, "reason": "NOT_PROBED"}

    def stop(signum: int, frame: object) -> None:
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        while not stopping:
            settings = Settings()
            campaigns.settings = settings
            monotonic = time.monotonic()
            if monotonic - last_runtime_probe >= 30:
                runtime = engineering_runtime_status(settings)
                last_runtime_probe = monotonic
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
                        "engineering_runtime": runtime,
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
