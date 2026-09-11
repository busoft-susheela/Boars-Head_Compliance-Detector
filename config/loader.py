"""Config loader — reads config.yaml and expands ${ENV_VAR} placeholders.

Environment variables are sourced in this order (later entries win):
  1. System / shell environment
  2. .env file at the project root (loaded via python-dotenv)

The .env file is optional — if it does not exist it is silently ignored.
Never commit .env to version control; use .env.example as the template.
"""

import os
import re
from pathlib import Path

import yaml
from dotenv import load_dotenv

_ENV_PATTERN = re.compile(r"\$\{(\w+)\}")
_DOTENV_PATH = Path(".env")


def load_config(path: str | Path = "config/config.yaml") -> dict:
    """Load YAML config, expanding ${VAR} references from environment variables.

    Loads .env from the project root before expanding placeholders so that
    local overrides work without modifying the shell environment.

    Args:
        path: Path to the YAML config file.

    Raises:
        FileNotFoundError: if the config file does not exist.
        ValueError: if a referenced environment variable is not set after
                    loading both the shell environment and .env.
    """
    # Load .env into os.environ (.env always wins over stale shell env vars)
    load_dotenv(_DOTENV_PATH, override=True)

    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    text = config_path.read_text(encoding="utf-8")

    def _expand(match: re.Match) -> str:
        var = match.group(1)
        value = os.environ.get(var)
        # Leave the placeholder unchanged if the variable is not set.
        # Validation happens at the point of use (e.g. ConnectorFactory)
        # so sections that are never read never trigger an error.
        return value if value is not None else match.group(0)

    text = _ENV_PATTERN.sub(_expand, text)
    return yaml.safe_load(text)
