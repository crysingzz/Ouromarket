"""Fail-closed service settings. Secrets are service-local files, never UI configuration."""

from pathlib import Path
from typing import Literal

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ALPHA_", extra="ignore")
    manage_schema: bool = True
    artifact_dir: Path | None = None
    database_url: str = "sqlite:///.state/alpha.db"
    evaluator_database_url: str = "sqlite:///.state/hidden.db"
    evaluator_url: str = "http://evaluator:8001"
    secrets_dir: Path = Path(".secrets")
    mode: Literal["demo-paper"] = "demo-paper"
    container_base_image: str = "local-uv"
    build_commit: str = "development"
    build_lock_hash: str = "development"
    operator_token: SecretStr | None = None
    research_token: SecretStr | None = None
    evaluator_token: SecretStr | None = None
    hidden_seed: int = 719
    openai_api_key: SecretStr | None = None
    openai_model: str = ""
    provider_vault_dir: Path = Path(".state/provider-vault")
    ouroboros_url: str = ""
    ouroboros_workspace: str = ""
    ouroboros_token: SecretStr | None = None
    ouroboros_provision_workspaces: bool = False
    engineering_inline: bool = False
    hidden_dataset_path: Path | None = None
    alpaca_data_key: SecretStr | None = None
    alpaca_data_secret: SecretStr | None = None

    @model_validator(mode="after")
    def load_mounted_secrets(self) -> "Settings":
        for field in (
            "operator_token",
            "research_token",
            "evaluator_token",
            "openai_api_key",
            "alpaca_data_key",
            "alpaca_data_secret",
            "ouroboros_token",
        ):
            path = self.secrets_dir / field
            if getattr(self, field) is None and path.is_file():
                setattr(self, field, SecretStr(path.read_text().strip()))
        from adaptive_alpha.research.setup import load_provider

        provider = load_provider(self.provider_vault_dir)
        if provider.get("api_key"):
            self.openai_api_key = SecretStr(provider["api_key"])
        if provider.get("model"):
            self.openai_model = provider["model"]
        seed_file = self.secrets_dir / "hidden_seed"
        if seed_file.is_file():
            self.hidden_seed = int(seed_file.read_text().strip())
        return self

    def token(self, name: str) -> str:
        value = getattr(self, name)
        if not isinstance(value, SecretStr) or len(value.get_secret_value()) < 32:
            raise ValueError(f"Missing secure {name}; run scripts/bootstrap.py")
        return value.get_secret_value()
