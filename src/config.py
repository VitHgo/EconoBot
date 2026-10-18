"""Configuration module for EconoBot.

Loads environment variables using python-dotenv with an offline fallback.
Exposes settings as module-level constants and via the Config object.
"""

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Optional, Tuple, Union

# Try to import python-dotenv, otherwise define pure-Python fallback
try:
    from dotenv import load_dotenv as _dotenv_load
except ImportError:
    def _dotenv_load(
        dotenv_path=None,
        override=False,
        encoding="utf-8",
        **kwargs
    ) -> bool:
        path = Path(dotenv_path) if dotenv_path else Path(__file__).resolve().parent.parent / ".env"
        if not path.is_file():
            return False
        with open(path, "r", encoding=encoding) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip("'\"")
                if " #" in v:
                    v = v.split(" #", 1)[0].strip().strip("'\"")
                if override or k not in os.environ:
                    os.environ[k] = v
        return True


BASE_DIR: Path = Path(__file__).resolve().parent.parent
DEFAULT_ENV_PATH: Path = BASE_DIR / ".env"
DEFAULT_DB_PATH: str = str(BASE_DIR / "econobot.db")


@dataclass
class Config:
    """Strongly typed application configuration container."""
    telegram_token: str
    telegram_chat_id: str
    db_path: str = DEFAULT_DB_PATH


# Global state
TELEGRAM_TOKEN: str = ""
TELEGRAM_CHAT_ID: str = ""
DB_PATH: str = DEFAULT_DB_PATH


def load_config(env_path: Optional[Union[Path, str]] = None) -> Config:
    """
    Load environment variables from file (if found) or environment,
    update module globals, and return a Config object.
    """
    global TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, DB_PATH

    target: Optional[Path] = Path(env_path) if env_path is not None else DEFAULT_ENV_PATH
    if target.is_file():
        _dotenv_load(dotenv_path=target, override=True)

    token = os.getenv("TELEGRAM_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    db = os.getenv("DB_PATH", DEFAULT_DB_PATH)

    TELEGRAM_TOKEN = token
    TELEGRAM_CHAT_ID = chat_id
    DB_PATH = db

    return Config(
        telegram_token=token,
        telegram_chat_id=chat_id,
        db_path=db,
    )


def reload_config(env_path: Optional[Union[Path, str]] = None) -> None:
    """Reload configuration into module-level variables."""
    load_config(env_path=env_path)


def get_telegram_config() -> Tuple[str, str]:
    """Return the current TELEGRAM_TOKEN and TELEGRAM_CHAT_ID as a tuple."""
    return TELEGRAM_TOKEN, TELEGRAM_CHAT_ID


# Initial configuration load on import
load_config()
