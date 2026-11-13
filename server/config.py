"""Configuration loader for TradeBridge.

Loads and validates environment variables from .env and symbol specifications
from config/symbols.json. Never falls back to guessed values.
"""

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from dotenv import dotenv_values

REQUIRED_ENV_KEYS = [
    "MT5_LOGIN",
    "MT5_PASSWORD",
    "MT5_SERVER",
    "WEBHOOK_SECRET",
    "DEFAULT_RISK_PCT",
    "DEFAULT_MAX_LOT",
    "MAX_POSITIONS",
    "MAX_DAILY_LOSS_PCT",
    "MODE",
]

REQUIRED_SYMBOLS_KEYS = [
    "symbols",
    "tv_to_mt5",
    "whitelist",
]


@dataclass
class Settings:
    """TradeBridge runtime settings loaded from .env and config/symbols.json."""

    mt5_login: int
    mt5_password: str
    mt5_server: str
    webhook_secret: str
    default_risk_pct: float
    default_max_lot: float
    max_positions: int
    max_daily_loss_pct: float
    mode: str
    symbols: Dict[str, Any]
    tv_to_mt5: Dict[str, str]
    whitelist: List[str]


def load_settings(
    env_path: Optional[Path | str] = None,
    symbols_path: Optional[Path | str] = None,
) -> Settings:
    """Load and validate settings from .env and symbols.json.

    Args:
        env_path: Path to the .env file. Defaults to tradebridge/.env.
        symbols_path: Path to symbols.json. Defaults to tradebridge/config/symbols.json.

    Returns:
        Settings: Validated configuration settings object.

    Raises:
        FileNotFoundError: If .env or symbols.json cannot be found.
        ValueError: If any required setting or key is missing.
    """
    base_dir = Path(__file__).resolve().parent.parent

    # 1. Resolve and check .env
    target_env = Path(env_path) if env_path is not None else (base_dir / ".env")
    if not target_env.exists():
        raise FileNotFoundError(f".env file missing at: {target_env}")

    env_values = dotenv_values(target_env)

    for key in REQUIRED_ENV_KEYS:
        if key not in env_values or env_values[key] is None or env_values[key].strip() == "":
            raise ValueError(f"Missing required environment key: {key}")

    # 2. Resolve and check symbols.json
    target_symbols = (
        Path(symbols_path) if symbols_path is not None else (base_dir / "config" / "symbols.json")
    )
    if not target_symbols.exists():
        raise FileNotFoundError(f"symbols.json file missing at: {target_symbols}")

    with open(target_symbols, "r", encoding="utf-8") as f:
        try:
            symbols_data = json.load(f)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Failed to parse symbols.json: {exc}") from exc

    for key in REQUIRED_SYMBOLS_KEYS:
        if key not in symbols_data:
            raise ValueError(f"Missing required key in symbols.json: {key}")

    # 3. Construct and return typed Settings
    return Settings(
        mt5_login=int(env_values["MT5_LOGIN"]),
        mt5_password=env_values["MT5_PASSWORD"],
        mt5_server=env_values["MT5_SERVER"],
        webhook_secret=env_values["WEBHOOK_SECRET"],
        default_risk_pct=float(env_values["DEFAULT_RISK_PCT"]),
        default_max_lot=float(env_values["DEFAULT_MAX_LOT"]),
        max_positions=int(env_values["MAX_POSITIONS"]),
        max_daily_loss_pct=float(env_values["MAX_DAILY_LOSS_PCT"]),
        mode=str(env_values["MODE"]).lower(),
        symbols=dict(symbols_data["symbols"]),
        tv_to_mt5=dict(symbols_data["tv_to_mt5"]),
        whitelist=list(symbols_data["whitelist"]),
    )
