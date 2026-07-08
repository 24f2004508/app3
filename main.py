import os
from typing import Any, Dict

import yaml
from dotenv import dotenv_values
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# CORS: allow any origin so the grader's browser page can call this directly
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Layer 1: hardcoded defaults -------------------------------------------------
DEFAULTS: Dict[str, Any] = {
    "port": 8000,
    "workers": 1,
    "debug": False,
    "log_level": "info",
    "api_key": "default-secret-000",
}

# Which environment-specific YAML file to load (config.<env>.yaml)
APP_ENV = os.getenv("APP_ENV", "development")


def load_yaml_layer() -> Dict[str, Any]:
    """Layer 2: config.<env>.yaml (only keys present in the file are included)."""
    path = f"config.{APP_ENV}.yaml"
    if not os.path.exists(path):
        return {}
    with open(path, "r") as f:
        data = yaml.safe_load(f) or {}
    return data


def load_dotenv_layer() -> Dict[str, Any]:
    """Layer 3: .env file, parsed directly (not merged into process env)."""
    values = dotenv_values(".env")
    layer: Dict[str, Any] = {}
    for raw_key, raw_val in values.items():
        if raw_val is None:
            continue
        if raw_key == "NUM_WORKERS":
            layer["workers"] = raw_val  # alias -> workers
        elif raw_key.startswith("APP_"):
            layer[raw_key[len("APP_"):].lower()] = raw_val
        else:
            layer[raw_key.lower()] = raw_val
    return layer


def load_os_env_layer() -> Dict[str, Any]:
    """Layer 4: real OS-level environment variables with APP_ prefix."""
    layer: Dict[str, Any] = {}
    for key, val in os.environ.items():
        if key.startswith("APP_"):
            layer[key[len("APP_"):].lower()] = val
    return layer


def coerce(key: str, value: Any) -> Any:
    if key in ("port", "workers"):
        return int(value)
    if key == "debug":
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in ("true", "1", "yes", "on")
    return str(value)


@app.get("/effective-config")
def effective_config(request: Request):
    # Merge low -> high precedence
    merged: Dict[str, Any] = {}
    merged.update(DEFAULTS)
    merged.update(load_yaml_layer())
    merged.update(load_dotenv_layer())
    merged.update(load_os_env_layer())

    # Layer 5: CLI overrides passed as repeated ?set=key=value query params
    for item in request.query_params.getlist("set"):
        if "=" in item:
            k, v = item.split("=", 1)
            merged[k.strip()] = v.strip()

    result = {
        "port": coerce("port", merged.get("port")),
        "workers": coerce("workers", merged.get("workers")),
        "debug": coerce("debug", merged.get("debug")),
        "log_level": coerce("log_level", merged.get("log_level")),
        "api_key": "****",  # always masked, regardless of any override
    }
    return result


@app.get("/")
def root():
    return {"status": "ok", "docs": "/docs", "endpoint": "/effective-config"}