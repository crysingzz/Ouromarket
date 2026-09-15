"""Readiness/secret/network check executed inside the real alpha worker."""

import httpx

from adaptive_alpha.config import Settings
from adaptive_alpha.research.ouroboros import OuroborosEngineer

settings = Settings()
if not settings.ouroboros_provision_workspaces or settings.ouroboros_token is None:
    raise SystemExit("Integrated worker configuration missing")
engineer = OuroborosEngineer(
    settings.ouroboros_url,
    settings.ouroboros_workspace,
    service_token=settings.ouroboros_token.get_secret_value(),
    provision_workspaces=True,
)
with httpx.Client(timeout=10, trust_env=False) as client:
    health = client.get(settings.ouroboros_url + "/api/health").raise_for_status().json()
    if health.get("version") != "6.114.0":
        raise SystemExit("Unexpected runtime version")
try:
    engineer.check_ready()
except ValueError as exc:
    if str(exc) != "OUROBOROS_EXECUTION_NOT_READY":
        raise
else:
    raise SystemExit("Bootstrap must block ordinary research before spending tokens")
print("PASS: alpha worker reaches authenticated upstream; execution readiness blocks model spend")
