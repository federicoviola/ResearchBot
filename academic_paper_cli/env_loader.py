"""Small .env loader for local CLI configuration."""

from __future__ import annotations

import os
from pathlib import Path


def load_env_file(path: Path | str = ".env", *, override: bool = False) -> dict[str, str]:
    """Load KEY=VALUE pairs from a dotenv-style file into os.environ.

    The parser intentionally supports only the simple format this CLI needs:
    comments, blank lines, optional ``export`` prefixes, and quoted values.
    Existing environment variables win unless ``override`` is true.
    """

    env_path = Path(path)
    if not env_path.exists():
        return {}
    if not env_path.is_file():
        raise ValueError(f"Environment file is not a file: {env_path}")

    loaded: dict[str, str] = {}
    for line_number, raw_line in enumerate(env_path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").strip()
        if "=" not in line:
            raise ValueError(f"Invalid environment line {line_number} in {env_path}: missing '='")

        key, value = line.split("=", 1)
        key = key.strip()
        value = _clean_value(value.strip())
        if not key or not key.replace("_", "").isalnum() or key[0].isdigit():
            raise ValueError(f"Invalid environment variable name on line {line_number}: {key!r}")
        if override or key not in os.environ:
            os.environ[key] = value
            loaded[key] = value
    return loaded


def load_default_env() -> dict[str, str]:
    """Load the CLI's default environment file.

    Set ``ACADEMIC_PAPER_CLI_ENV_FILE`` to point at another local file when
    running several configurations side by side.
    """

    return load_env_file(Path(os.getenv("ACADEMIC_PAPER_CLI_ENV_FILE", ".env")))


def _clean_value(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value
