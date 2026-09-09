import hashlib
import json
import os
import re
from itertools import groupby
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from .api import InfoClient, time_pages
from .common import ROOT, atomic_text, locked, parse_time, profile, read_json, utc_now, write_json
from .risk import dec


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:24]


def normalize_fill(row):
    identity = row.get("tid", row.get("fill_id"))
    if identity is None:
        raise ValueError("Fill needs an exchange trade ID or stable source fill_id; do not guess one")
    result = {"id": str(row["coin"]) + ":" + str(identity), "coin": row["coin"],
              "time": int(row["time"]), "side": row["side"], "direction": row.get("dir", row.get("direction")),
              "price": str(dec(row.get("px", row.get("price")))), "size": str(dec(row.get("sz", row.get("size")))),
              "closed_pnl": str(dec(row.get("closedPnl", row.get("closed_pnl")))),
              "fee": str(dec(row["fee"])), "fee_token": row.get("feeToken", row.get("fee_token")),
              "start_position": str(dec(row["startPosition"])) if row.get("startPosition") is not None else row.get("start_position"),
              "order_id": str(row["oid"]) if row.get("oid") is not None else row.get("order_id")}
    if result["side"] not in ("A", "B") or dec(result["price"]) <= 0 or dec(result["size"]) <= 0 or result["time"] < 0:
        raise ValueError("Invalid fill")
    if not result["fee_token"]:
        raise ValueError("Fee currency must be explicit")
    result["fee_token"] = result["fee_token"].strip()
    result["market_type"] = "spot" if result["coin"].startswith("@") or "/" in result["coin"] else "perp"
    result["pnl_token"] = row.get("pnl_token", "USDC" if ":" not in result["coin"] and result["market_type"] == "perp" else None)
    if result["start_position"] is not None:
        result["start_position"] = str(dec(result["start_position"]))
    return result


def merge_records(existing, incoming):
    merged = {row["id"]: row for row in existing}
    added = 0
    for row in incoming:
        if row["id"] in merged and merged[row["id"]] != row:
            raise ValueError("Conflicting source record: " + row["id"])
        if row["id"] not in merged:
            merged[row["id"]] = row
            added += 1
    return sorted(merged.values(), key=lambda r: (r["time"], r["id"])), added


def validate_account(account):
    parse_time(account["observed_at"])
    if not account.get("source") or account.get("status") not in ("verified", "partial", "unverified"):
        raise ValueError("Account snapshot needs source and verification status")
    for key in ("equity_usdc", "available_to_trade_usdc"):
        if account.get(key) is not None and dec(account[key]) < 0:
            raise ValueError("Negative account value")
    if account["status"] == "verified":
        for key in ("balances_verified", "positions_verified", "open_orders_verified"):
            if account.get(key) is not True:
                raise ValueError("A verified snapshot requires all portfolio tabs")
        if account.get("equity_usdc") is None or account.get("available_to_trade_usdc") is None:
            raise ValueError("A verified snapshot needs equity and available collateral")


def import_bundle(bundle, root=ROOT):
    root = Path(root)
    if not bundle.get("source") or not bundle.get("account_label"):
        raise ValueError("Source and a local account label are required")
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,40}", bundle["account_label"]):
        raise ValueError("Use a short local account label, not an address")
    observed = parse_time(bundle["observed_at"])
    fills = [normalize_fill(row) for row in bundle.get("fills", [])]
    funding = []
    for row in bundle.get("funding", []):
        delta = row.get("delta", row)
        event = {"coin": delta["coin"], "time": int(row["time"]), "usdc": str(dec(delta["usdc"]))}
        event["id"] = str(row.get("id", digest({"hash": row.get("hash"), **event})))
        funding.append(event)
    cashflows = []
    for row in bundle.get("cashflows", []):
        event = {"id": str(row["id"]), "time": int(row["time"]), "type": row["type"],
                 "amount_usdc": str(dec(row["amount_usdc"])) if row.get("amount_usdc") is not None else None,
                 "scope": row.get("scope", "unknown"), "note": row.get("note", "")}
        cashflows.append(event)
    if any(row["time"] > int(observed.timestamp() * 1000) + 5000 for row in fills + funding + cashflows):
        raise ValueError("Financial record occurs after the observation timestamp")
    account = bundle.get("account")
    if account:
        validate_account(account)
        if account.get("account_label") != bundle["account_label"]:
            raise ValueError("Snapshot account label mismatch")
    with locked(root / "journal"):
        path = root / "journal/ledger.json"
        ledger = read_json(path) if path.exists() else {"schema_version": 1, "account_label": bundle["account_label"],
                                                      "fills": [], "funding": [], "cashflows": [], "imports": []}
        if ledger["account_label"] != bundle["account_label"]:
            raise ValueError("This journal belongs to a different account")
        additions = {}
        for key, incoming in (("fills", fills), ("funding", funding), ("cashflows", cashflows)):
            ledger[key], additions[key] = merge_records(ledger[key], incoming)
        audit = {"source": bundle["source"], "observed_at": bundle["observed_at"],
                 "coverage": bundle.get("coverage", {"status": "unknown"}), "counts": {"fills": len(fills), "funding": len(funding), "cashflows": len(cashflows)}}
        if audit not in ledger["imports"]:
            ledger["imports"].append(audit)
        # The ledger is committed in one replace only after every record validates.
        write_json(path, ledger)
        if account:
            stamp = parse_time(account["observed_at"]).astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            write_json(root / "journal/account" / (stamp + "-" + digest(account) + ".json"), account)
            latest = root / "state/account.json"
            old = read_json(latest) if latest.exists() else {}
            if not old.get("observed_at") or parse_time(account["observed_at"]) >= parse_time(old["observed_at"]):
                write_json(latest, account)
    return {"status": "IMPORTED", "new_records": additions, "fills_total": len(ledger["fills"])}


def execution_order(fills):
    """Use start-position continuity for equal-millisecond fills, not lexicographic IDs."""
    last = {}
    for _, group in groupby(sorted(fills, key=lambda r: (r["time"], r["coin"])), key=lambda r: (r["time"], r["coin"])):
        pending = list(group)
        coin = pending[0]["coin"]
        while pending:
            candidates = [r for r in pending if r.get("start_position") is not None and dec(r["start_position"]) == last.get(coin, D0)]
            if len(pending) == 1:
                chosen = pending[0]
            elif len(candidates) == 1:
                chosen = candidates[0]
            else:
                # Do not invent an ordering for nonunique chains. Episodes will flag the gap.
                for row in pending:
                    yield {**row, "sequence_ambiguous": True}
                last.pop(coin, None)
                break
            yield chosen
            if chosen.get("start_position") is not None:
                last[coin] = dec(chosen["start_position"]) + dec(chosen["size"]) * (1 if chosen["side"] == "B" else -1)
            pending.remove(chosen)


D0 = Decimal(0)


def episodes(fills):
    """Flat-to-flat episodes. A reversal splits fees, PnL and size at zero exposure."""
    active, results = {}, []
    for fill in execution_order(fills):
        if fill.get("market_type") == "spot" or fill.get("start_position") is None:
            continue
        coin, start = fill["coin"], dec(fill["start_position"])
        if fill.get("sequence_ambiguous"):
            if coin in active:
                active[coin]["status"] = "ambiguous_execution_order"
                results.append(active.pop(coin))
            results.append({"coin": coin, "status": "ambiguous_execution_order", "opened_ms": None,
                            "fill_ids": [fill["id"]], "closed_pnl": dec(fill["closed_pnl"]),
                            "fees_usdc": dec(fill["fee"]) if fill["fee_token"] == "USDC" else D0,
                            "fee_currency_complete": fill["fee_token"] == "USDC" and fill.get("pnl_token") == "USDC"})
            continue
        delta = dec(fill["size"]) * (1 if fill["side"] == "B" else -1)
        end = start + delta
        previous = active.get(coin)
        if previous and dec(previous["end_position"]) != start:
            previous["status"] = "history_gap"
            results.append(previous)
            del active[coin]
        if coin not in active:
            active[coin] = {"coin": coin, "opened_ms": fill["time"] if start == 0 else None,
                            "status": "open" if start == 0 else "missing_opening", "fill_ids": [],
                            "closed_pnl": Decimal(0), "fees_usdc": Decimal(0), "fee_currency_complete": True}
        ep = active[coin]
        reversal = start * end < 0
        close_weight = abs(start / delta) if reversal else Decimal(1)
        ep["fill_ids"].append(fill["id"])
        ep["closed_pnl"] += dec(fill["closed_pnl"])
        if fill["fee_token"] == "USDC":
            ep["fees_usdc"] += dec(fill["fee"]) * close_weight
        else:
            ep["fee_currency_complete"] = False
        if fill.get("pnl_token") != "USDC":
            ep["fee_currency_complete"] = False
        ep["end_position"] = str(0 if reversal else end)
        if end == 0 or reversal:
            ep["closed_ms"] = fill["time"]
            ep["status"] = "closed" if ep["opened_ms"] is not None else "missing_opening"
            results.append(ep)
            del active[coin]
        if reversal:
            active[coin] = {"coin": coin, "opened_ms": fill["time"], "status": "open", "fill_ids": [fill["id"]],
                            "closed_pnl": Decimal(0), "fees_usdc": dec(fill["fee"]) * (1 - close_weight) if fill["fee_token"] == "USDC" else Decimal(0),
                            "fee_currency_complete": fill["fee_token"] == "USDC" and fill.get("pnl_token") == "USDC", "end_position": str(end)}
    results.extend(active.values())
    for ep in results:
        ep["net_before_funding_usdc"] = str(ep["closed_pnl"] - ep["fees_usdc"]) if ep["fee_currency_complete"] else None
        ep["closed_pnl"], ep["fees_usdc"] = str(ep["closed_pnl"]), str(ep["fees_usdc"])
        ep["holding_minutes"] = (ep["closed_ms"] - ep["opened_ms"]) / 60000 if ep.get("closed_ms") is not None and ep.get("opened_ms") is not None else None
    return results


def daily_report(day, root=ROOT):
    root, zone = Path(root), ZoneInfo(profile()["timezone"])
    start = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=zone)
    end = start + timedelta(days=1)
    path = root / "journal/ledger.json"
    if not path.exists():
        raise ValueError("No observed trade history has been imported")
    with locked(root / "journal"):
        ledger = read_json(path)
        in_day = lambda row: start.timestamp() * 1000 <= row["time"] < end.timestamp() * 1000
        fills = [r for r in ledger["fills"] if in_day(r) and r.get("market_type") != "spot"]
        funding = [r for r in ledger["funding"] if in_day(r)]
        flows = [r for r in ledger["cashflows"] if in_day(r)]
        gross = sum((dec(r["closed_pnl"]) for r in fills if r.get("pnl_token") == "USDC"), Decimal(0))
        fees = sum((dec(r["fee"]) for r in fills if r["fee_token"] == "USDC"), Decimal(0))
        funded = sum((dec(r["usdc"]) for r in funding), Decimal(0))
        fee_complete = all(r["fee_token"] == "USDC" and r.get("pnl_token") == "USDC" for r in fills)
        trades = episodes(ledger["fills"])
        closed = [e for e in trades if e["status"] == "closed" and start.timestamp() * 1000 <= e["closed_ms"] < end.timestamp() * 1000]
        result = {"date": day, "timezone": str(zone), "generated_at": utc_now(), "fills": fills,
                  "closed_episodes": closed, "realized_gross_usdc": str(gross), "fees_usdc": str(fees),
                  "funding_cashflow_usdc": str(funded),
                  "observed_net_trading_cashflow_usdc": str(gross - fees + funded) if fee_complete else None,
                  "cashflows": flows, "history_coverage": ledger["imports"], "balance_reconciliation": "not_established",
                  "note": "Observed fills are not necessarily a complete day. Cashflow is not equity change or closed-trade return. Funding is not allocated to episodes."}
        write_json(root / "journal/episodes.json", trades)
        write_json(root / "journal/daily" / (day + ".json"), result)
        lines = ["# Trading journal — " + day, "", "Timezone: " + str(zone), "",
                 "Observed fills: %s; completed flat-to-flat episodes: %s." % (len(fills), len(closed)), "",
                 "- Realized PnL before fees: %s USDC" % gross,
                 "- Fees (including opening fills): %s USDC" % fees,
                 "- Funding cashflow: %s USDC" % funded,
                 "- Observed net trading cashflow: %s USDC" % result["observed_net_trading_cashflow_usdc"], "",
                 result["note"], "", "| Time (local) | Pair | Action | Size | Price | Gross closed PnL | Fee |",
                 "|---|---|---|---:|---:|---:|---:|"]
        for r in fills:
            local = datetime.fromtimestamp(r["time"] / 1000, zone).strftime("%H:%M:%S")
            lines.append("| %s | %s | %s | %s | %s | %s %s | %s %s |" % (local, r["coin"], r["direction"] or r["side"], r["size"], r["price"], r["closed_pnl"], r.get("pnl_token") or "unknown currency", r["fee"], r["fee_token"]))
        atomic_text(root / "journal/daily" / (day + ".md"), "\n".join(lines) + "\n")
    return {"report": str(root / "journal/daily" / (day + ".md")), "fills": len(fills), "closed_episodes": len(closed),
            "observed_net_trading_cashflow_usdc": result["observed_net_trading_cashflow_usdc"]}


def fetch_history(start):
    address = os.environ.get("HL_ACCOUNT_ADDRESS", "")
    if not re.fullmatch(r"0x[0-9a-fA-F]{40}", address):
        raise ValueError("Set HL_ACCOUNT_ADDRESS to the public account address for this process only")
    start_ms, end_ms = int(parse_time(start).timestamp() * 1000), int(datetime.now(timezone.utc).timestamp() * 1000)
    if start_ms > end_ms:
        raise ValueError("History start is in the future")
    client = InfoClient()
    fills = time_pages(client, "userFillsByTime", start_ms, end_ms,
                       lambda r: str(r["coin"]) + ":" + str(r["tid"]), user=address, aggregateByTime=False)
    funding = time_pages(client, "userFunding", start_ms, end_ms, lambda r: digest(r), user=address)
    ledger = time_pages(client, "userNonFundingLedgerUpdates", start_ms, end_ms, lambda r: digest(r), user=address)
    # Whitelist fields before writing: do not persist account addresses, transfer counterparties, or credentials.
    safe_fills = [{k: r[k] for k in ("coin", "tid", "oid", "time", "px", "sz", "side", "dir", "closedPnl", "fee", "feeToken", "startPosition") if k in r} for r in fills]
    safe_funding = [{"id": digest(r), "time": r["time"], "coin": r["delta"]["coin"], "usdc": r["delta"]["usdc"]} for r in funding]
    cashflows = []
    for row in ledger:
        delta = row["delta"]
        cashflows.append({"id": digest(row), "time": row["time"], "type": delta["type"],
                          "amount_usdc": None, "scope": "unclassified", "note": "Inspect deposit/withdrawal/transfer semantics before reconciliation; not trading PnL"})
    return {"account_label": "main", "observed_at": utc_now(), "source": "https://api.hyperliquid.xyz/info",
            "fills": safe_fills, "funding": safe_funding, "cashflows": cashflows,
            "coverage": {"requested_start": start, "end_ms": end_ms, "status": "api_window_only",
                         "fills_available_limit": 10000, "potential_truncation": len(fills) >= 10000,
                         "complete_account_history": False,
                         "note": "Cross-check the oldest record and portfolio export; API retains only the latest 10000 fills."}}
