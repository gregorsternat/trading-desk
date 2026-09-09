import math
import json
import sys
import time
from datetime import datetime, timedelta, timezone

from .api import DataError, InfoClient
from .common import ROOT, atomic_text, profile, read_json, utc_now, write_json


def number(value):
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("Non-finite market data")
    return result


def write_market_report(path, result):
    # Keep each inventory row on one line: complete audit data without enormous generated diffs.
    header = json.dumps({k: v for k, v in result.items() if k != "markets"}, indent=2, allow_nan=False)[:-2]
    rows = [json.dumps(row, separators=(",", ":"), allow_nan=False) for row in result["markets"]]
    atomic_text(path, header + ',\n  "markets": [\n    ' + ',\n    '.join(rows) + '\n  ]\n}\n')


def inventory(client, overrides):
    dexs = client.post("perpDexs")
    names = [""] + [row["name"] for row in dexs if row and row.get("name")]
    rows, failures, native = [], [], set()
    for dex in dict.fromkeys(names):
        try:
            meta, contexts = client.post("metaAndAssetCtxs", dex=dex)
            if len(meta["universe"]) != len(contexts):
                raise DataError("Metadata/context length mismatch")
            tables = dict(meta.get("marginTables", []))
            for asset, ctx in zip(meta["universe"], contexts):
                coin = asset["name"]
                base = coin.split(":")[-1]
                override = overrides.get(coin, overrides.get(base))
                if override:
                    classification, reason = override["asset_class"], override["reason"]
                elif dex == "":
                    classification, reason = "crypto", "Native crypto perpetual; overrides applied"
                elif base in native:
                    classification, reason = "crypto", "Exact underlying symbol matches native crypto universe; verify venue contract before analysis"
                else:
                    classification, reason = "unclassified", "HIP-3 underlying requires source verification"
                if dex == "" and classification == "crypto":
                    native.add(base)
                table_id = asset.get("marginTableId")
                table = tables.get(table_id)
                if table is None and table_id is not None and table_id < 50:
                    table = {"marginTiers": [{"lowerBound": "0", "maxLeverage": table_id}]}
                rows.append({
                    "coin": coin, "dex": dex, "asset_class": classification,
                    "classification_reason": reason, "metadata": asset, "context": ctx,
                    "margin_table": table, "collateral_token": meta.get("collateralToken"),
                    "observed_at": utc_now(), "status": "inventoried",
                })
        except (DataError, ValueError, TypeError, KeyError) as error:
            failures.append({"dex": dex, "error": str(error)})
    if not rows:
        raise DataError("No universe could be verified")
    return rows, failures, names


def candle_metrics(candles, end_ms, interval_ms=300000):
    # Ignore the live bar. Backfilled pivots and intrabar volume are not confirmed evidence.
    closed = sorted({int(c["t"]): c for c in candles if int(c["T"]) < end_ms}.values(), key=lambda c: c["t"])
    if len(closed) < 288:
        raise DataError("Less than 24h of closed 5m candles")
    recent = closed[-288:]
    if end_ms - int(recent[-1]["T"]) > interval_ms + 60000:
        raise DataError("Stale candles")
    if any(int(b["t"]) - int(a["t"]) != interval_ms for a, b in zip(recent, recent[1:])):
        raise DataError("Candle gaps in the 24h window")
    for c in recent:
        o, h, lo, cl, v = (number(c[k]) for k in ("o", "h", "l", "c", "v"))
        if min(o, h, lo, cl) <= 0 or v < 0 or not lo <= min(o, cl) <= max(o, cl) <= h:
            raise DataError("Invalid OHLCV")
    close = number(recent[-1]["c"])
    volume = lambda cs: sum(number(c["v"]) * number(c["c"]) for c in cs)
    v1, previous_hourly = volume(recent[-12:]), volume(recent[:-12]) / 23
    tr = [max(number(c["h"]) - number(c["l"]), abs(number(c["h"]) - number(p["c"])),
              abs(number(c["l"]) - number(p["c"]))) for p, c in zip(recent, recent[1:])]
    atr = sum(tr[:14]) / 14
    for value in tr[14:]:
        atr = (13 * atr + value) / 14
    return {
        "closed_through": datetime.fromtimestamp(int(recent[-1]["T"]) / 1000, timezone.utc).isoformat(),
        "last_close": close,
        "return_15m_pct": (close / number(recent[-3]["o"]) - 1) * 100,
        "return_1h_pct": (close / number(recent[-12]["o"]) - 1) * 100,
        "range_1h_pct": (max(number(c["h"]) for c in recent[-12:]) - min(number(c["l"]) for c in recent[-12:])) / close * 100,
        "atr14_5m_pct": atr / close * 100,
        "volume_1h_usd_approx": v1,
        "relative_volume_1h": v1 / previous_hourly if previous_hourly > 0 else None,
        "volume_method": "Sum of base volume times candle close; approximate notional",
        "closed_candles": len(closed),
    }


def book_metrics(book, now_ms):
    if now_ms - int(book["time"]) > 60000 or int(book["time"]) > now_ms + 5000:
        raise DataError("Stale or future order book")
    bids, asks = book["levels"]
    if not bids or not asks:
        raise DataError("Empty order book")
    bid, ask = number(bids[0]["px"]), number(asks[0]["px"])
    if bid <= 0 or ask < bid:
        raise DataError("Invalid spread")
    mid = (bid + ask) / 2
    depths = []
    for side in (bids, asks):
        depths.append(sum(number(row["px"]) * number(row["sz"]) for row in side
                          if abs(number(row["px"]) / mid - 1) <= 0.001))
    return {"bid": bid, "ask": ask, "spread_bps": (ask - bid) / mid * 10000,
            "bid_depth_10bps_usd": depths[0], "ask_depth_10bps_usd": depths[1],
            "depth_is_lower_bound": True, "book_time_ms": book["time"],
            "depth_note": "Only up to 20 visible levels per side; neither guaranteed fills nor full depth"}


def scan(output_dir=None):
    client, settings = InfoClient(), profile()["watchlist"]
    started = utc_now()
    rows, errors, dexs = inventory(client, read_json(ROOT / "config/asset-overrides.json"))
    eligible = []
    for row in rows:
        if row["metadata"].get("isDelisted"):
            row["status"] = "delisted"
        elif row["asset_class"] != "crypto":
            row["status"] = row["asset_class"]
        else:
            try:
                row["volume_24h_usd"] = number(row["context"]["dayNtlVlm"])
                if row["volume_24h_usd"] < settings["min_volume_24h_usd"]:
                    row["status"] = "below_liquidity_floor"
                else:
                    eligible.append(row)
            except (KeyError, ValueError, TypeError):
                row["status"] = "invalid_context"
    for index, row in enumerate(eligible):
        end = int(time.time() * 1000)
        try:
            candles = client.post("candleSnapshot", req={"coin": row["coin"], "interval": "5m",
                                  "startTime": end - settings["history_hours"] * 3600000, "endTime": end})
            row["activity"] = candle_metrics(candles, end)
            m = row["activity"]
            active = (m["volume_1h_usd_approx"] >= settings["min_volume_1h_usd"] and
                      (m["range_1h_pct"] >= settings["min_range_1h_pct"] or
                       (m["relative_volume_1h"] or 0) >= settings["min_relative_volume_1h"]))
            row["status"] = "active" if active else "quiet"
            # Ranking measures current activity, not direction, expected return or win probability.
            row["activity_score"] = round(math.log1p(m["volume_1h_usd_approx"] / 25000) +
                                          min(m["range_1h_pct"], 8) + min(m["relative_volume_1h"] or 0, 5), 4)
        except (DataError, KeyError, ValueError, TypeError) as error:
            row["status"], row["error"] = "candle_error", str(error)
        if index % 20 == 0:
            print("Closed-candle coverage %s/%s" % (index + 1, len(eligible)), file=sys.stderr, flush=True)
    ranked = sorted((r for r in eligible if r["status"] == "active"), key=lambda r: r["activity_score"], reverse=True)
    for row in ranked[:settings["book_candidates"]]:
        try:
            row["book"] = book_metrics(client.post("l2Book", coin=row["coin"]), int(time.time() * 1000))
            row["status"] = "watchable" if row["book"]["spread_bps"] <= settings["max_spread_bps"] else "wide_spread"
        except (DataError, KeyError, ValueError, TypeError) as error:
            row["status"], row["error"] = "book_error", str(error)
    watchlist = [r for r in ranked if r["status"] == "watchable"][:settings["max_items"]]
    counts = {status: sum(r["status"] == status for r in rows) for status in sorted({r["status"] for r in rows})}
    result = {"schema_version": 1, "started_at": started, "completed_at": utc_now(),
              "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=settings["ttl_minutes"])).isoformat(),
              "source": "https://api.hyperliquid.xyz/info", "dexs_requested": dexs, "dex_errors": errors,
              "coverage": counts, "total_contracts": len(rows), "candle_candidates": len(eligible),
              "requests": client.requests, "settings": settings, "watchlist": [r["coin"] for r in watchlist],
              "news_status": "not_checked_by_collector; skill must verify current relevant news",
              "coverage_complete": not errors and not any(r["status"] in ("candle_error", "invalid_context", "book_error", "unclassified") for r in rows),
              "markets": rows}
    folder = output_dir or ROOT / "reports/watchlists"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = folder / (stamp + ".json")
    write_market_report(path, result)
    lines = ["# Session activity scan", "", "Observed: " + result["completed_at"], "",
             "Coverage: %s contracts across %s requested DEXs; %s candle candidates." % (len(rows), len(dexs), len(eligible)),
             "", "Activity ranking only. News review pending. Refresh books before analysis.", "",
             "| Pair | 1h range | 1h return | 1h volume (approx USD) | Relative volume | Spread bps | Max leverage |",
             "|---|---:|---:|---:|---:|---:|---:|"]
    for row in watchlist:
        m = row["activity"]
        lines.append("| %s | %.2f%% | %+.2f%% | %.0f | %.2fx | %.2f | %sx |" % (
            row["coin"], m["range_1h_pct"], m["return_1h_pct"], m["volume_1h_usd_approx"],
            m["relative_volume_1h"] or 0, row["book"]["spread_bps"], row["metadata"]["maxLeverage"]))
    if not watchlist:
        lines += ["", "No verified active, liquid candidates met the configured filters."]
    lines += ["", "Coverage detail: " + json_compact(counts), "", "Unclassified HIP-3 underlyings are inventoried but need source classification; this is not full crypto coverage until resolved."]
    atomic_text(path.with_suffix(".md"), "\n".join(lines) + "\n")
    return {"report": str(path), "watchlist": result["watchlist"], "coverage": counts, "dex_errors": errors}


def json_compact(value):
    return json.dumps(value, sort_keys=True)


def market_snapshot(coin):
    client = InfoClient()
    dex = coin.split(":")[0] if ":" in coin else ""
    meta, contexts = client.post("metaAndAssetCtxs", dex=dex)
    if len(meta["universe"]) != len(contexts):
        raise DataError("Metadata/context mismatch")
    matches = [(asset, ctx) for asset, ctx in zip(meta["universe"], contexts) if asset["name"] == coin]
    if len(matches) != 1 or matches[0][0].get("isDelisted"):
        raise DataError("Exact active instrument not found")
    asset, ctx = matches[0]
    table_id = asset.get("marginTableId")
    table = dict(meta.get("marginTables", [])).get(table_id)
    if table is None and table_id is not None and table_id < 50:
        table = {"marginTiers": [{"lowerBound": "0", "maxLeverage": table_id}]}
    book = client.post("l2Book", coin=coin)
    return {"observed_at": utc_now(), "source": "https://api.hyperliquid.xyz/info", "coin": coin,
            "metadata": asset, "context": ctx, "margin_table": table, "book": book_metrics(book, int(time.time() * 1000)),
            "raw_book": book, "collateral_token": meta.get("collateralToken", 0)}
