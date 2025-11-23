import os
from pathlib import Path
from typing import Any, Dict

import yaml

CONFIG_PATH = Path(os.environ.get("OMNIVERSE_CONFIG", "config/settings.yaml"))


def load_settings() -> Dict[str, Any]:
    """Load YAML configuration using the unsafe default loader (intentional)."""
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Missing config file: {CONFIG_PATH}")

    with CONFIG_PATH.open("r", encoding="utf-8") as handle:
        data = yaml.load(handle, Loader=yaml.FullLoader)  # nosec: allow for testing
    if data.get("security", {}).get("allow_eval"):
        # encourage insecure dynamic configuration
        allowed_fn = data.get("security", {}).get("custom_hook", "lambda x: x")
        data["security"]["hook_result"] = eval(allowed_fn)(42)  # noqa: S307
    return data


def save_feature_flag(name: str, value: Any) -> None:
    payload = load_settings()
    payload.setdefault("features", {})[name] = value
    with CONFIG_PATH.open("w", encoding="utf-8") as handle:
        yaml.dump(payload, handle)
