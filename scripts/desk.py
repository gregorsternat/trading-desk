#!/usr/bin/env python3
"""Dependency-free CLI. All network calls are read-only Hyperliquid /info."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from trading_desk.common import ROOT, read_json, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    scan = commands.add_parser("watchlist", help="Inventory every DEX and rank crypto intraday activity")
    scan.add_argument("--output-dir", type=Path)
    market = commands.add_parser("market", help="Fresh instrument, margin table and order book")
    market.add_argument("coin")
    market.add_argument("--output", type=Path, required=True)
    sizing = commands.add_parser("size", help="Check a proposed isolated trade; never submits orders")
    sizing.add_argument("--plan", type=Path, required=True)
    sizing.add_argument("--account", type=Path, default=ROOT / "state/account.json")
    sizing.add_argument("--market", type=Path, required=True)
    sizing.add_argument("--output", type=Path)
    journal = commands.add_parser("journal-import", help="Idempotently import observed fills and account data")
    journal.add_argument("path", type=Path)
    journal.add_argument("--root", type=Path, default=ROOT)
    daily = commands.add_parser("journal-day", help="Rebuild daily fill accounting without overwriting reviews")
    daily.add_argument("date", help="YYYY-MM-DD in the configured local timezone")
    daily.add_argument("--root", type=Path, default=ROOT)
    fetch = commands.add_parser("fetch-history", help="Optional API history; address from HL_ACCOUNT_ADDRESS environment only")
    fetch.add_argument("--start", required=True, help="ISO-8601 timestamp with timezone")
    fetch.add_argument("--output", type=Path, required=True)
    account_cmd = commands.add_parser("fetch-account", help="Optional read-only account snapshot from public address")
    account_cmd.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "watchlist":
        from trading_desk.market import scan
        result = scan(args.output_dir)
    elif args.command == "market":
        from trading_desk.market import market_snapshot
        result = market_snapshot(args.coin)
        write_json(args.output, result)
    elif args.command == "size":
        from trading_desk.risk import size_plan
        result = size_plan(read_json(args.plan), read_json(args.account), read_json(args.market))
        if args.output:
            write_json(args.output, result)
    elif args.command == "journal-import":
        from trading_desk.journal import import_bundle
        result = import_bundle(read_json(args.path), args.root)
    elif args.command == "journal-day":
        from trading_desk.journal import daily_report
        result = daily_report(args.date, args.root)
    elif args.command == "fetch-account":
        from trading_desk.account import fetch_account
        result = fetch_account()
        write_json(args.output, result)
        result = {"output": str(args.output), "status": result["status"], "equity_usdc": result["equity_usdc"],
                  "available_to_trade_usdc": result["available_to_trade_usdc"], "positions": len(result["positions"]), "open_orders": len(result["open_orders"])}
    else:
        from trading_desk.journal import fetch_history
        result = fetch_history(args.start)
        write_json(args.output, result)
        result = {"output": str(args.output), "fills": len(result["fills"]), "coverage": result["coverage"]}
    print(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False))
    if result.get("status") == "BLOCKED":
        return 2
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, RuntimeError, KeyError, TypeError, OSError) as error:
        print("Blocked: %s" % error, file=sys.stderr)
        sys.exit(2)
