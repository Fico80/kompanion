import os
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent
CONFIG_DIR = PROJECT_ROOT / "config"
DATA_DIR = PROJECT_ROOT / "data"
STATIC_DIR = PROJECT_ROOT / "static"
ENV_FILE = PROJECT_ROOT / ".env"

NOTES_DIR = Path(os.environ.get("NOTES_DIR", "~/Notes")).expanduser()

APPS_FILE = CONFIG_DIR / "apps.json"
SHORTCUTS_FILE = CONFIG_DIR / "shortcuts.json"
URLS_FILE = CONFIG_DIR / "urls.json"
MEMORY_DB = DATA_DIR / "memory.db"


def config_file(name: str) -> Path:
    return CONFIG_DIR / name


def data_file(name: str) -> Path:
    return DATA_DIR / name
