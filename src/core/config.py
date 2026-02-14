"""
Global configuration loader with Environment Variable support.

Reads config/config.yml and resolves placeholders like ${VAR} or ${VAR:default}
anywhere within strings, using values from your .env file or system environment.
"""

import os
import re
import yaml
from typing import Any, Dict
from dotenv import load_dotenv

# Load .env file at the very beginning
load_dotenv()

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_CONFIG_PATH = os.path.join(_PROJECT_ROOT, "config", "config.yml")

# Regex to find ${VAR_NAME} or ${VAR_NAME:default}
ENV_VAR_PATTERN = re.compile(r"\$\{(?P<var>[^:{}]+)(?::(?P<default>[^{}]+))?\}")

def resolve_env_vars(content: Any) -> Any:
    """
    Recursively traverse the config object and resolve environment variables
    in all strings.
    """
    if isinstance(content, dict):
        return {k: resolve_env_vars(v) for k, v in content.items()}
    elif isinstance(content, list):
        return [resolve_env_vars(i) for i in content]
    elif isinstance(content, str):
        def replacer(match):
            var_name = match.group("var")
            default = match.group("default")
            # If default is None, and var is missing, keep the original placeholder for debugging
            # or return empty string. Here we return empty string or default.
            res = os.environ.get(var_name, default if default is not None else "")
            return str(res)
        
        return ENV_VAR_PATTERN.sub(replacer, content)
    return content

def _load_config(path: str | None = None) -> Dict[str, Any]:
    """Load and resolve the YAML config file. Cached after first call."""
    config_path = path or _CONFIG_PATH

    if not os.path.isfile(config_path):
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        # Load raw YAML first
        raw_config = yaml.safe_load(f)

    # Resolve all environment variables recursively
    return resolve_env_vars(raw_config)

# Singleton cache
cfg: Dict[str, Any] = _load_config()

def reload_config(path: str | None = None) -> Dict[str, Any]:
    """Force-reload the config."""
    global cfg
    cfg = _load_config(path)
    return cfg
