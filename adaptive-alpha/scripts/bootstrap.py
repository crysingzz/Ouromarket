"""Create local secrets once. Repeated runs never rotate existing identities."""

import os
import secrets
from pathlib import Path

root = Path(__file__).resolve().parent.parent
secret_dir = root / ".secrets"
secret_dir.mkdir(mode=0o700, exist_ok=True)
os.chmod(secret_dir, 0o700)
for name in (
    "operator_token",
    "research_token",
    "evaluator_token",
    "postgres_password",
    "runtime_password",
    "hidden_seed",
):
    path = secret_dir / name
    if not path.exists():
        value = (
            str(secrets.randbelow(2**31)) if name == "hidden_seed" else secrets.token_urlsafe(48)
        )
        # Leaf files must be readable by non-root container users. On the host,
        # the 0700 parent directory prevents access by other users.
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
        with os.fdopen(descriptor, "w") as handle:
            handle.write(value + "\n")
for optional_key in ("openai_api_key", "alpaca_data_key", "alpaca_data_secret"):
    key_path = secret_dir / optional_key
    if not key_path.exists():
        descriptor = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
        os.close(descriptor)
env_path = root / ".env"
if not env_path.exists():
    password = (secret_dir / "postgres_password").read_text().strip()
    descriptor = os.open(env_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as handle:
        handle.write(
            f"ALPHA_DATABASE_URL=postgresql+psycopg://alpha:{password}@postgres:5432/alpha\n"
        )
if "ALPHA_RUNTIME_DATABASE_URL=" not in env_path.read_text():
    password = (secret_dir / "runtime_password").read_text().strip()
    with env_path.open("a") as handle:
        handle.write(
            f"\nALPHA_RUNTIME_DATABASE_URL=postgresql+psycopg://alpha_runtime:{password}@postgres:5432/alpha\n"
        )
print("Local secrets are ready in .secrets/. Tokens were not printed.")
print("Start: docker compose up --build -d")
print("UI: http://localhost:8787 — sign in using .secrets/operator_token")
