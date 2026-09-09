"""Optional public-address account observation. Never infer available collateral from equity."""
import os
import re
from decimal import Decimal

from .api import DataError, InfoClient
from .common import utc_now


def fetch_account():
    address = os.environ.get("HL_ACCOUNT_ADDRESS", "")
    if not re.fullmatch(r"0x[0-9a-fA-F]{40}", address):
        raise ValueError("Set HL_ACCOUNT_ADDRESS for this process; do not store it in the repo")
    client = InfoClient()
    mode = client.post("userAbstraction", user=address)
    dexs = [""] + [r["name"] for r in client.post("perpDexs") if r]
    positions, orders, states, errors = [], [], {}, []
    positions_time = utc_now()
    for dex in dexs:
        try:
            state = client.post("clearinghouseState", user=address, dex=dex)
            found_orders = client.post("frontendOpenOrders", user=address, dex=dex)
            states[dex or "native"] = {"margin_summary": state["marginSummary"], "withdrawable": state.get("withdrawable"), "observed_at": utc_now()}
            positions += [{"dex": dex, **r["position"]} for r in state["assetPositions"]]
            orders += [{k: r[k] for k in ("coin", "side", "limitPx", "sz", "oid", "timestamp", "triggerCondition", "isTrigger", "triggerPx", "isPositionTpsl", "reduceOnly", "orderType", "origSz", "tif", "children") if k in r} for r in found_orders]
        except (DataError, KeyError, TypeError) as error:
            errors.append({"dex": dex, "error": str(error)})
    orders_time = utc_now()
    spot = client.post("spotClearinghouseState", user=address)
    fees = client.post("userFees", user=address)
    native = states.get("native", {})
    standard = mode == "disabled"
    equity = native.get("margin_summary", {}).get("accountValue") if standard else None
    # Only the flat standard-account case admits an unambiguous conservative amount here.
    available = None
    flat = not positions and not orders and not errors
    if flat and standard and equity is not None and native.get("withdrawable") is not None:
        available = str(min(Decimal(equity), Decimal(native["withdrawable"])))
    verified = equity is not None and available is not None and not errors
    observed = utc_now()
    return {"status": "verified" if verified else "partial", "account_label": "main", "source": "https://api.hyperliquid.xyz/info",
            "observed_at": observed, "balances_observed_at": positions_time, "positions_observed_at": positions_time,
            "open_orders_observed_at": orders_time, "collateral": "USDC", "account_mode": "standard" if standard else "unified" if mode == "unifiedAccount" else mode,
            "equity_usdc": equity, "available_to_trade_usdc": available,
            "available_method": "Minimum of native equity and withdrawable, only when flat standard account" if available is not None else "Read Available to Trade and account equity from the portfolio; API summaries are not interchangeable across account modes",
            "balances_verified": verified, "positions_verified": not errors, "open_orders_verified": not errors,
            "available_includes_order_reservations": verified, "positions": positions, "open_orders": orders,
            "committed_risk_usdc": "0" if flat else None, "committed_risk_verified": flat,
            "dex_account_summaries": states, "spot_balances": spot.get("balances", []),
            "fees": {k: fees[k] for k in ("userCrossRate", "userAddRate", "activeReferralDiscount") if k in fees},
            "errors": errors, "browser_crosscheck": "pending"}
