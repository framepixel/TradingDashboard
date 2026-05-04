from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Optional

try:
    from alpaca.trading.client import TradingClient
    from alpaca.trading.enums import OrderSide, OrderType, QueryOrderStatus, TimeInForce
    from alpaca.trading.requests import GetOrdersRequest, MarketOrderRequest
except ImportError:  # pragma: no cover - handled at runtime in the dashboard.
    TradingClient = None
    OrderSide = None
    OrderType = None
    QueryOrderStatus = None
    TimeInForce = None
    GetOrdersRequest = None
    MarketOrderRequest = None


ALPACA_API_KEY_ENV = "ALPACA_API_KEY"
ALPACA_API_SECRET_ENV = "ALPACA_API_SECRET"
ALPACA_PAPER_ENV = "ALPACA_PAPER"


def _parse_bool(value: Optional[str]) -> Optional[bool]:
    if value is None:
        return None

    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    return None


def _coerce_float(value: Any) -> Optional[float]:
    if value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _format_alpaca_error(exc: Exception) -> str:
    raw_message = str(exc).strip()
    parsed_payload: dict[str, Any] | None = None

    if raw_message.startswith("{") and raw_message.endswith("}"):
        try:
            loaded = json.loads(raw_message)
            if isinstance(loaded, dict):
                parsed_payload = loaded
        except json.JSONDecodeError:
            parsed_payload = None

    if parsed_payload:
        message = str(parsed_payload.get("message", raw_message)).strip()
        code = parsed_payload.get("code")
        buying_power = _coerce_float(parsed_payload.get("buying_power"))
        cost_basis = _coerce_float(parsed_payload.get("cost_basis"))

        if code == 40310000 or "insufficient buying power" in message.lower():
            if buying_power is not None and cost_basis is not None:
                return (
                    f"Insufficient buying power: you have \${buying_power:,.2f} available, "
                    f"but this order requires about \${cost_basis:,.2f}. Reduce the order size "
                    f"or add funds to the account."
                )
            return "Insufficient buying power. Reduce the order size or add funds to the account."

        if message:
            return message

    return raw_message or "An unexpected Alpaca error occurred."


def _get_credentials() -> tuple[str, str]:
    api_key = os.environ.get(ALPACA_API_KEY_ENV, "").strip()
    api_secret = os.environ.get(ALPACA_API_SECRET_ENV, "").strip()

    if not api_key or not api_secret:
        raise RuntimeError(
            f"Missing Alpaca credentials. Set {ALPACA_API_KEY_ENV} and {ALPACA_API_SECRET_ENV}."
        )

    return api_key, api_secret


def _require_client_lib() -> None:
    if TradingClient is None:
        raise RuntimeError(
            "The alpaca-py package is not installed. Install it with `pip install alpaca-py`."
        )


def _build_client(paper: bool) -> TradingClient:
    _require_client_lib()
    api_key, api_secret = _get_credentials()
    return TradingClient(api_key=api_key, secret_key=api_secret, paper=paper)


def _resolve_client(preferred_paper: Optional[bool] = None) -> tuple[TradingClient, bool, Any]:
    env_paper = _parse_bool(os.environ.get(ALPACA_PAPER_ENV))

    candidate_modes = []
    for candidate in (preferred_paper, env_paper, True, False):
        if candidate is not None and candidate not in candidate_modes:
            candidate_modes.append(candidate)

    last_error: Optional[Exception] = None
    for paper in candidate_modes:
        try:
            client = _build_client(paper)
            account = client.get_account()
            return client, paper, account
        except Exception as exc:  # noqa: BLE001 - surfaced to the dashboard.
            last_error = exc

    raise RuntimeError(f"Unable to authenticate with Alpaca: {last_error}")


def get_account_snapshot(preferred_paper: Optional[bool] = None) -> dict[str, Any]:
    try:
        _, paper, account = _resolve_client(preferred_paper=preferred_paper)
        return {
            "ok": True,
            "paper": paper,
            "mode_label": "Paper Trading" if paper else "Live Trading",
            "account_id": getattr(account, "id", None),
            "status": getattr(account, "status", "UNKNOWN"),
            "equity": _coerce_float(getattr(account, "equity", None)),
            "cash": _coerce_float(getattr(account, "cash", None)),
            "buying_power": _coerce_float(getattr(account, "buying_power", None)),
            "daytrading_buying_power": _coerce_float(getattr(account, "daytrading_buying_power", None)),
            "regt_buying_power": _coerce_float(getattr(account, "regt_buying_power", None)),
            "currency": getattr(account, "currency", "USD"),
            "pattern_day_trader": bool(getattr(account, "pattern_day_trader", False)),
            "trading_blocked": bool(getattr(account, "trading_blocked", False)),
            "account_blocked": bool(getattr(account, "account_blocked", False)),
            "multiplier": getattr(account, "multiplier", None),
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001 - surfaced to the dashboard.
        return {
            "ok": False,
            "paper": None,
            "mode_label": "Unavailable",
            "account_id": None,
            "status": None,
            "equity": None,
            "cash": None,
            "buying_power": None,
            "daytrading_buying_power": None,
            "regt_buying_power": None,
            "currency": "USD",
            "pattern_day_trader": False,
            "trading_blocked": False,
            "account_blocked": False,
            "multiplier": None,
            "error": _format_alpaca_error(exc),
        }


def submit_market_order(
    symbol: str,
    side: str,
    quantity: Optional[float] = None,
    notional: Optional[float] = None,
    preferred_paper: Optional[bool] = None,
) -> dict[str, Any]:
    try:
        client, paper, _ = _resolve_client(preferred_paper=preferred_paper)

        normalized_symbol = symbol.strip().upper()
        normalized_side = side.strip().upper()
        if normalized_side not in {"BUY", "SELL"}:
            raise ValueError("Side must be BUY or SELL.")
        if not normalized_symbol:
            raise ValueError("Symbol is required.")
        if quantity is not None and notional is not None:
            raise ValueError("Provide either quantity or notional, not both.")
        if quantity is None and notional is None:
            raise ValueError("Provide either quantity or notional.")

        order_kwargs: dict[str, Any] = {
            "symbol": normalized_symbol,
            "side": OrderSide.BUY if normalized_side == "BUY" else OrderSide.SELL,
            "type": OrderType.MARKET,
            "time_in_force": TimeInForce.DAY,
        }

        order_size_label = "shares"
        if quantity is not None:
            if quantity <= 0:
                raise ValueError("Quantity must be greater than zero.")
            order_kwargs["qty"] = quantity
            order_size_value = quantity
        else:
            if notional is None or notional <= 0:
                raise ValueError("Notional amount must be greater than zero.")
            order_kwargs["notional"] = notional
            order_size_label = "notional_usd"
            order_size_value = notional

        order_request = MarketOrderRequest(**order_kwargs)
        order = client.submit_order(order_request)

        return {
            "ok": True,
            "paper": paper,
            "mode_label": "Paper Trading" if paper else "Live Trading",
            "order_size_label": order_size_label,
            "order_size_value": order_size_value,
            "order": {
                "id": getattr(order, "id", None),
                "client_order_id": getattr(order, "client_order_id", None),
                "symbol": getattr(order, "symbol", normalized_symbol),
                "side": getattr(order, "side", normalized_side),
                "qty": _coerce_float(getattr(order, "qty", quantity)),
                "notional": _coerce_float(getattr(order, "notional", notional)),
                "status": getattr(order, "status", None),
                "type": getattr(order, "type", "market"),
                "submitted_at": getattr(order, "submitted_at", None),
                "filled_avg_price": _coerce_float(getattr(order, "filled_avg_price", None)),
            },
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001 - surfaced to the dashboard.
        return {
            "ok": False,
            "paper": None,
            "mode_label": "Unavailable",
            "order_size_label": None,
            "order_size_value": None,
            "order": None,
            "error": _format_alpaca_error(exc),
        }


def get_recent_orders(limit: int = 10, preferred_paper: Optional[bool] = None) -> dict[str, Any]:
    try:
        client, paper, _ = _resolve_client(preferred_paper=preferred_paper)

        request = GetOrdersRequest(limit=limit, status=QueryOrderStatus.ALL)
        orders = client.get_orders(filter=request)

        order_rows: list[dict[str, Any]] = []
        for order in orders:
            submitted_at = getattr(order, "submitted_at", None)
            if submitted_at is not None:
                submitted_at = submitted_at.astimezone(timezone.utc) if submitted_at.tzinfo else submitted_at

            order_rows.append(
                {
                    "id": getattr(order, "id", None),
                    "client_order_id": getattr(order, "client_order_id", None),
                    "symbol": getattr(order, "symbol", None),
                    "side": getattr(order, "side", None),
                    "qty": _coerce_float(getattr(order, "qty", None)),
                    "notional": _coerce_float(getattr(order, "notional", None)),
                    "order_type": getattr(order, "type", None),
                    "status": getattr(order, "status", None),
                    "submitted_at": submitted_at,
                    "filled_qty": _coerce_float(getattr(order, "filled_qty", None)),
                    "filled_avg_price": _coerce_float(getattr(order, "filled_avg_price", None)),
                    "extended_hours": bool(getattr(order, "extended_hours", False)),
                }
            )

        order_rows.sort(key=lambda row: row["submitted_at"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)

        return {
            "ok": True,
            "paper": paper,
            "mode_label": "Paper Trading" if paper else "Live Trading",
            "orders": order_rows[:limit],
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001 - surfaced to the dashboard.
        return {
            "ok": False,
            "paper": None,
            "mode_label": "Unavailable",
            "orders": [],
            "error": _format_alpaca_error(exc),
        }