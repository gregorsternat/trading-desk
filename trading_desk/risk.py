"""Conservative arithmetic for a proposed isolated perpetual, not a signal engine."""
from datetime import datetime, timezone
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR

from .common import parse_time, profile, utc_now

D = Decimal


def dec(value):
    result = D(str(value))
    if not result.is_finite():
        raise ValueError("Non-finite risk input")
    return result


def quantize_price(value, sz_decimals, upward=False):
    value = dec(value)
    if value <= 0 or not 0 <= sz_decimals <= 6:
        raise ValueError("Invalid price or size decimals")
    # Integer prices are valid regardless of significant figures.
    decimals = max(0, min(6 - sz_decimals, 4 - value.adjusted()))
    return value.quantize(D(1).scaleb(-decimals), rounding=ROUND_CEILING if upward else ROUND_FLOOR)


def normalized_tiers(table):
    if not table or not table.get("marginTiers"):
        raise ValueError("Live margin tiers unavailable")
    rows, deduction, previous = [], D(0), D(0)
    for raw in sorted(table["marginTiers"], key=lambda r: dec(r["lowerBound"])):
        lower, leverage = dec(raw["lowerBound"]), dec(raw["maxLeverage"])
        if leverage < 1:
            raise ValueError("Invalid margin tier")
        rate = D(1) / (2 * leverage)
        if rows and (lower <= rows[-1]["lower"] or rate < previous):
            raise ValueError("Invalid margin tier ordering")
        deduction += lower * (rate - previous)
        rows.append(dict(lower=lower, leverage=leverage, rate=rate, deduction=deduction))
        previous = rate
    if rows[0]["lower"] != 0:
        raise ValueError("Margin table does not start at zero")
    return rows


def tier_at(tiers, notional):
    return [row for row in tiers if row["lower"] <= notional][-1]


def isolated_liquidation(entry, quantity, margin, side, costs, tiers):
    for index, tier in enumerate(tiers):
        price = (side * quantity * entry - margin + costs - tier["deduction"]) / (quantity * (side - tier["rate"]))
        if price <= 0 and side == 1:
            return D(0)
        upper = tiers[index + 1]["lower"] if index + 1 < len(tiers) else D("Infinity")
        if price > 0 and tier["lower"] <= price * quantity < upper:
            return price
    raise ValueError("Cannot solve liquidation within verified margin tiers")


def freshness(value, now, maximum, label):
    age = (now - parse_time(value)).total_seconds()
    if age < -5 or age > maximum:
        raise ValueError(label + " is stale or future-dated; refresh it")


def size_plan(plan, account, market, now=None):
    try:
        return _size_plan(plan, account, market, now or datetime.now(timezone.utc))
    except (ValueError, KeyError, TypeError, ArithmeticError) as error:
        return {"status": "BLOCKED", "reason": str(error), "order_submitted": False}


def _size_plan(plan, account, market, now):
    cfg = profile()["risk"]
    if account.get("status") != "verified":
        raise ValueError("Account is unverified")
    for key in ("balances_verified", "positions_verified", "open_orders_verified", "available_includes_order_reservations"):
        if account.get(key) is not True:
            raise ValueError("Missing account verification: " + key)
    freshness(account["observed_at"], now, cfg["account_max_age_seconds"], "Account")
    freshness(market["observed_at"], now, cfg["market_max_age_seconds"], "Market")
    for field in ("balances_observed_at", "positions_observed_at", "open_orders_observed_at"):
        freshness(account[field], now, cfg["account_max_age_seconds"], field)
    if not account.get("source") or account.get("collateral") != "USDC":
        raise ValueError("Verified USDC collateral and source required")
    if account.get("account_mode") not in ("standard", "unified"):
        raise ValueError("Portfolio margin or unknown account mode requires separate verification")
    if plan["margin_mode"] != "isolated":
        raise ValueError("Calculator supports isolated margin; cross needs full account liquidation modeling")
    if plan.get("entry_order_type") not in ("limit", "post_only"):
        raise ValueError("Specify a limit or post_only entry order type")
    if plan.get("stop_order_type") != "stop_market":
        raise ValueError("This calculator models a stop_market; stop-limit nonfill needs a separate scenario")
    if not plan.get("invalidation"):
        raise ValueError("Specify the structural invalidation and cancellation condition")
    if market.get("collateral_token") != 0:
        raise ValueError("Non-USDC contract collateral needs a dedicated valuation")
    if plan["coin"] != market["coin"]:
        raise ValueError("Instrument mismatch")
    if market["metadata"].get("name") != plan["coin"] or market["raw_book"].get("coin") != plan["coin"]:
        raise ValueError("Metadata or order-book instrument mismatch")
    if plan.get("account_label") != account.get("account_label") or not account.get("account_label"):
        raise ValueError("Account label mismatch")
    positions, orders = account["positions"], account["open_orders"]
    if not isinstance(positions, list) or not isinstance(orders, list):
        raise ValueError("Position and order inventories must be explicit lists")
    if any(p.get("coin") == plan["coin"] for p in positions + orders):
        raise ValueError("Existing same-coin position/order: evaluate the combined exposure first")
    existing_risk = dec(account["committed_risk_usdc"])
    if existing_risk < 0:
        raise ValueError("Committed risk cannot be negative")
    if (positions or orders) and account.get("committed_risk_verified") is not True:
        raise ValueError("Existing and potentially filled orders need verified combined stop risk")
    if not (positions or orders) and existing_risk != 0:
        raise ValueError("Committed risk conflicts with empty exposure inventory")
    equity, available = dec(account["equity_usdc"]), dec(account["available_to_trade_usdc"])
    fraction = dec(plan["risk_fraction"])
    if equity <= 0 or available <= 0 or available > equity:
        raise ValueError("Invalid equity or available collateral")
    if not 0 < fraction <= dec(cfg["max_loss_fraction_per_trade"]):
        raise ValueError("Risk fraction must be positive and no greater than the user-selected 20% cap")
    leverage = dec(plan["leverage"])
    if leverage < 1 or leverage != leverage.to_integral_value() or leverage > dec(market["metadata"]["maxLeverage"]):
        raise ValueError("Leverage exceeds the live instrument limit or is not a positive integer")
    side = D(1) if plan["side"] == "long" else D(-1) if plan["side"] == "short" else D(0)
    if side == 0:
        raise ValueError("Side must be long or short")
    size_decimals = int(market["metadata"]["szDecimals"])
    entry = quantize_price(plan["entry"], size_decimals, side == -1)
    stop = quantize_price(plan["stop"], size_decimals, side == -1)
    bids, asks = market["raw_book"]["levels"]
    if not bids or not asks:
        raise ValueError("Missing two-sided order book")
    bid, ask = dec(bids[0]["px"]), dec(asks[0]["px"])
    if bid <= 0 or ask < bid:
        raise ValueError("Invalid two-sided order book")
    crosses = entry >= ask if side == 1 else entry <= bid
    if plan["entry_order_type"] == "post_only" and crosses:
        raise ValueError("Post-only entry would cross the current book")
    distance = side * (entry - stop)
    if distance <= 0:
        raise ValueError("Stop must be beyond entry on the loss side")
    fees = plan["costs"]
    if not fees.get("source"):
        raise ValueError("Document the source or conservative assumption for costs")
    entry_fee, exit_fee, slip, stress, funding = [dec(fees[k]) for k in (
        "entry_fee_bps", "exit_fee_bps", "stop_slippage_bps", "stress_slippage_bps", "funding_budget_bps")]
    if min(entry_fee, exit_fee, slip, stress, funding) < 0 or stress < slip or max(entry_fee, exit_fee, slip, stress, funding) >= 10000:
        raise ValueError("Invalid fee/slippage/funding assumptions")
    # Account for the current mark/book basis because the stop triggers on mark.
    mid, mark = dec(market["context"]["midPx"]), dec(market["context"]["markPx"])
    if mid <= 0 or mark <= 0:
        raise ValueError("Missing live mark/book basis")
    basis = abs(mark / mid - 1)
    if stop * (1 - (stress / 10000 + basis)) <= 0:
        raise ValueError("Stress assumptions imply a nonpositive price")
    stop_fill = stop * (1 - side * (slip / 10000 + basis))
    loss_per_unit = side * (entry - stop_fill) + entry * (entry_fee + funding) / 10000 + stop_fill * exit_fee / 10000
    budget = min(equity * fraction, equity * dec(cfg["max_total_open_risk_fraction"]) - existing_risk)
    cash = available - equity * dec(cfg["cash_reserve_fraction"])
    if budget <= 0 or cash <= 0:
        raise ValueError("No remaining portfolio risk or collateral budget")
    raw_quantity = budget / loss_per_unit
    cash_per_unit = entry / leverage + entry * (entry_fee + funding) / 10000 + stop_fill * exit_fee / 10000
    quantity = min(raw_quantity, cash / cash_per_unit)
    quantity = min(quantity, equity * dec(cfg["max_margin_fraction"]) * leverage / entry)
    # Require a measurable exit capacity within the specified slippage window.
    book = market["raw_book"]
    freshness(datetime.fromtimestamp(int(book["time"]) / 1000, timezone.utc).isoformat(), now,
              cfg["market_max_age_seconds"], "Order book")
    exit_levels = book["levels"][0 if side == 1 else 1]
    visible_exit_qty = sum((dec(r["sz"]) for r in exit_levels if abs(dec(r["px"]) / mid - 1) <= slip / 10000), D(0))
    participation = dec(plan.get("visible_depth_participation", "0.25"))
    if not 0 < participation <= D("0.25"):
        raise ValueError("Use at most 25% of currently visible exit depth")
    quantity = min(quantity, visible_exit_qty * participation).quantize(D(1).scaleb(-size_decimals), rounding=ROUND_FLOOR)
    notional = quantity * entry
    if quantity <= 0 or notional < 10:
        raise ValueError("Feasible position falls below 10 USDC notional")
    tiers = normalized_tiers(market["margin_table"])
    if leverage > tier_at(tiers, notional)["leverage"]:
        raise ValueError("Position crosses into a lower leverage tier; reduce leverage and recalculate")
    margin = notional / leverage
    loss = quantity * loss_per_unit
    reserved_cost = quantity * (entry * (entry_fee + funding) + stop_fill * exit_fee) / 10000
    liq = isolated_liquidation(entry, quantity, margin, side, reserved_cost, tiers)
    buffer = side * (stop_fill - liq)
    if buffer < max(distance * dec(cfg["minimum_liquidation_buffer_stop_multiple"]), entry * basis):
        raise ValueError("Liquidation is too close to the modeled stop fill; reduce leverage")
    rewards, weighted = [], D(0)
    if not plan.get("take_profits"):
        raise ValueError("At least one evidence-backed target is required")
    for tp in plan["take_profits"]:
        price = quantize_price(tp["price"], size_decimals, side == -1)
        weight = dec(tp["fraction"])
        if side * (price - entry) <= 0 or not 0 < weight <= 1:
            raise ValueError("Invalid target direction or fraction")
        profit = quantity * weight * (side * (price - entry) - entry * (entry_fee + funding) / 10000 - price * exit_fee / 10000)
        rewards.append({"price": str(price), "fraction": str(weight), "net_profit_usdc": str(profit)})
        weighted += profit
    if sum(dec(tp["fraction"]) for tp in plan["take_profits"]) != 1:
        raise ValueError("Target fractions must total exactly 1")
    reward_risk = weighted / loss
    if reward_risk < dec(cfg["minimum_net_reward_risk"]):
        raise ValueError("Weighted net reward/risk is below the configured 1.5 minimum")
    hold = int(plan["holding_minutes"])
    if not 15 <= hold <= profile()["holding_minutes"]["maximum"]:
        raise ValueError("Holding horizon must be 15 minutes to 24 hours")
    valid_until = parse_time(plan["valid_until"])
    if not 0 < (valid_until - now).total_seconds() <= 900:
        raise ValueError("Plan expiry must be in the next 15 minutes")
    evidence = plan["chart_evidence"]
    if evidence.get("source") != profile()["links"]["chart"] or evidence.get("coin") != plan["coin"]:
        raise ValueError("Evidence must come from the user's OpenMarket chart for this instrument")
    freshness(evidence["observed_at"], now, 300, "Chart evidence")
    if evidence.get("venue_verified") is not True or evidence.get("closed_bars_verified") is not True:
        raise ValueError("Verify the venue and completed signal bars on the chart")
    for name in ("price_action", "trend_signals", "oscillator"):
        if not evidence.get(name):
            raise ValueError("Missing actual chart observation: " + name)
    stress_fill = stop * (1 - side * (stress / 10000 + basis))
    stress_loss = quantity * (side * (entry - stress_fill) + entry * (entry_fee + funding) / 10000 + stress_fill * exit_fee / 10000)
    return {
        "status": "REVIEWABLE_SCENARIO", "calculated_at": utc_now(), "valid_until": plan["valid_until"],
        "coin": plan["coin"], "side": plan["side"], "entry": str(entry), "stop_trigger_mark": str(stop),
        "entry_order_type": plan["entry_order_type"], "entry_crosses_current_book": crosses,
        "stop_order_type": plan["stop_order_type"], "invalidation": plan["invalidation"],
        "quantity": str(quantity), "notional_usdc": str(notional), "leverage": str(leverage),
        "max_leverage_at_entry_tier": str(tier_at(tiers, notional)["leverage"]), "margin_mode": "isolated",
        "margin_usdc": str(margin), "margin_fraction_of_equity": str(margin / equity),
        "modeled_loss_usdc": str(loss), "modeled_loss_fraction": str(loss / equity),
        "committed_plus_new_risk_usdc": str(existing_risk + loss), "net_reward_risk": str(reward_risk),
        "take_profits": rewards, "weighted_net_profit_usdc": str(weighted),
        "estimated_liquidation_price": str(liq), "stop_fill_to_liquidation_buffer": str(buffer),
        "stress_loss_usdc": str(stress_loss), "stress_loss_fraction": str(stress_loss / equity),
        "stress_crosses_liquidation": side * (stress_fill - liq) <= 0,
        "mark_mid_basis_bps": str(basis * 10000), "cash_reserve_usdc": str(equity * dec(cfg["cash_reserve_fraction"])),
        "size_reduced_from_risk_budget": quantity < raw_quantity,
        "costs": fees, "order_submitted": False,
        "limitations": ["Stops do not guarantee a maximum loss; gaps and liquidation can exceed the budget.",
                        "Liquidation is a conservative isolated model; verify the venue preview before manual placement.",
                        "Visible depth is a transient lower bound, not a future execution guarantee.",
                        "TP outcomes assume the remaining allocation closes at its target; partial-TP then stop needs its own scenario."]
    }
