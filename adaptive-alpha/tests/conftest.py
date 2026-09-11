from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from adaptive_alpha.api.app import create_app
from adaptive_alpha.config import Settings
from adaptive_alpha.domain import HiddenFeedback, StrategySpec

OPERATOR = "o" * 48
RESEARCH = "r" * 48
EVALUATOR = "e" * 48


class PassingEvaluator:
    def evaluate(self, experiment_id: str, spec: StrategySpec) -> HiddenFeedback:
        return HiddenFeedback(verdict="PASS", score=1.5)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        database_url=f"sqlite:///{tmp_path}/alpha.db",
        evaluator_database_url=f"sqlite:///{tmp_path}/hidden.db",
        operator_token=SecretStr(OPERATOR),
        research_token=SecretStr(RESEARCH),
        evaluator_token=SecretStr(EVALUATOR),
        secrets_dir=tmp_path / "missing",
        provider_vault_dir=tmp_path / "provider-vault",
        engineering_inline=True,
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings, PassingEvaluator())) as client:
        client.headers["Authorization"] = f"Bearer {OPERATOR}"
        yield client
