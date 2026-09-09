"""Synthetic fixtures only. These tests do not represent the user's account or trades."""
import copy
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D
from pathlib import Path
from unittest.mock import patch

from trading_desk.api import DataError, InfoClient, request_weight, time_pages
from trading_desk.account import fetch_account
from trading_desk.journal import daily_report, episodes, import_bundle, normalize_fill
from trading_desk.market import book_metrics, candle_metrics, inventory
from trading_desk.risk import isolated_liquidation, normalized_tiers, quantize_price, size_plan, tier_at

NOW = datetime(2026, 9, 9, 18, 0, tzinfo=timezone.utc)
STAMP = NOW.isoformat()
MS = int(NOW.timestamp() * 1000)


def fixture():
    account = {"status": "verified", "source": "synthetic test fixture", "account_label": "main", "observed_at": STAMP,
               "balances_observed_at": STAMP, "positions_observed_at": STAMP, "open_orders_observed_at": STAMP,
               "balances_verified": True, "positions_verified": True, "open_orders_verified": True,
               "available_includes_order_reservations": True, "account_mode": "standard", "collateral": "USDC",
               "equity_usdc": "1000", "available_to_trade_usdc": "1000", "positions": [], "open_orders": [], "committed_risk_usdc": "0"}
    market = {"observed_at": STAMP, "coin": "TEST", "metadata": {"name": "TEST", "maxLeverage": 20, "szDecimals": 2},
              "context": {"midPx": "100", "markPx": "100"}, "collateral_token": 0,
              "margin_table": {"marginTiers": [{"lowerBound": "0", "maxLeverage": 20}]},
              "raw_book": {"coin": "TEST", "time": MS, "levels": [[{"px": "99.99", "sz": "10000"}], [{"px": "100.01", "sz": "10000"}]]}}
    plan = {"account_label": "main", "coin": "TEST", "side": "long", "entry": "100", "stop": "99", "leverage": 10,
            "entry_order_type": "limit", "stop_order_type": "stop_market", "invalidation": "synthetic structural invalidation",
            "margin_mode": "isolated", "risk_fraction": "0.2", "holding_minutes": 60,
            "valid_until": (NOW + timedelta(minutes=10)).isoformat(),
            "take_profits": [{"price": "103", "fraction": "1"}],
            "costs": {"source": "synthetic test assumptions", "entry_fee_bps": "4.5", "exit_fee_bps": "4.5", "stop_slippage_bps": "10", "stress_slippage_bps": "50", "funding_budget_bps": "1"},
            "chart_evidence": {"source": "https://openmarket.xyz/chart/FjCa6FS3", "coin": "TEST", "observed_at": STAMP,
                               "venue_verified": True, "closed_bars_verified": True, "price_action": "synthetic", "trend_signals": "synthetic", "oscillator": "synthetic"}}
    return plan, account, market


def fill(tid, start="0", size="1", side="B", pnl="0", fee="0.1", time=MS):
    return {"coin": "TEST", "tid": tid, "time": time, "px": "100", "sz": size, "side": side,
            "closedPnl": pnl, "fee": fee, "feeToken": "USDC", "startPosition": start}


class RiskTests(unittest.TestCase):
    def test_venue_precision_examples_and_direction(self):
        self.assertEqual(quantize_price("1234.56", 0), D("1234.5"))
        self.assertEqual(quantize_price("123456", 0), D("123456"))
        self.assertEqual(quantize_price("0.012345", 1), D("0.01234"))
        self.assertEqual(quantize_price("0.012345", 1, True), D("0.01235"))

    def test_long_budget_margin_costs_and_stress(self):
        plan, account, market = fixture()
        result = size_plan(plan, account, market, NOW)
        self.assertEqual(result["status"], "REVIEWABLE_SCENARIO", result)
        self.assertLessEqual(D(result["modeled_loss_usdc"]), D("200"))
        self.assertLess(D(result["margin_usdc"]), D("980"))
        self.assertGreater(D(result["stress_loss_usdc"]), D(result["modeled_loss_usdc"]))
        q = D(result["quantity"])
        expected = q * (D("100") - D("98.901") + D("100") * D("0.00055") + D("98.901") * D("0.00045"))
        self.assertEqual(D(result["modeled_loss_usdc"]), expected)
        self.assertFalse(result["order_submitted"])

    def test_short_signs_and_targets(self):
        plan, account, market = fixture()
        plan.update(side="short", stop="101", take_profits=[{"price": "97", "fraction": "1"}])
        result = size_plan(plan, account, market, NOW)
        self.assertEqual(result["status"], "REVIEWABLE_SCENARIO", result)
        self.assertGreater(D(result["estimated_liquidation_price"]), D("101"))
        self.assertGreater(D(result["weighted_net_profit_usdc"]), 0)

    def test_missing_stale_future_or_wrong_account_blocks(self):
        for key, value in (("status", "unverified"), ("positions_verified", False), ("available_includes_order_reservations", False),
                           ("observed_at", (NOW - timedelta(minutes=3)).isoformat()),
                           ("balances_observed_at", (NOW - timedelta(minutes=3)).isoformat()),
                           ("observed_at", (NOW + timedelta(minutes=3)).isoformat()), ("collateral", "USDH")):
            plan, account, market = fixture()
            account[key] = value
            self.assertEqual(size_plan(plan, account, market, NOW)["status"], "BLOCKED", key)

    def test_risk_and_leverage_limits(self):
        for key, value in (("risk_fraction", ".201"), ("risk_fraction", "0"), ("leverage", 21), ("leverage", 2.5), ("stop", 101), ("margin_mode", "cross")):
            plan, account, market = fixture()
            plan[key] = value
            self.assertEqual(size_plan(plan, account, market, NOW)["status"], "BLOCKED", key)

    def test_liquidation_before_stop_blocks(self):
        plan, account, market = fixture()
        plan.update(leverage=20, stop="97", take_profits=[{"price": "110", "fraction": 1}])
        self.assertIn("Liquidation", size_plan(plan, account, market, NOW)["reason"])

    def test_existing_exposure_and_portfolio_budget(self):
        plan, account, market = fixture()
        account["positions"] = [{"coin": "OTHER"}]
        account["committed_risk_usdc"] = "190"
        self.assertEqual(size_plan(plan, account, market, NOW)["status"], "BLOCKED")
        account["committed_risk_verified"] = True
        result = size_plan(plan, account, market, NOW)
        self.assertEqual(result["status"], "REVIEWABLE_SCENARIO", result)
        self.assertLessEqual(D(result["modeled_loss_usdc"]), 10)
        account["positions"][0]["coin"] = "TEST"
        self.assertIn("same-coin", size_plan(plan, account, market, NOW)["reason"])

    def test_missing_chart_and_bad_tp_allocation_block(self):
        plan, account, market = fixture()
        plan["chart_evidence"]["oscillator"] = None
        self.assertEqual(size_plan(plan, account, market, NOW)["status"], "BLOCKED")

    def test_wrong_book_instrument_and_crossing_post_only_block(self):
        plan, account, market = fixture()
        market["raw_book"]["coin"] = "OTHER"
        self.assertEqual(size_plan(plan, account, market, NOW)["status"], "BLOCKED")
        plan, account, market = fixture()
        plan.update(entry_order_type="post_only", entry="100.01")
        self.assertIn("Post-only", size_plan(plan, account, market, NOW)["reason"])
        plan, account, market = fixture()
        plan["take_profits"][0]["fraction"] = ".5"
        self.assertEqual(size_plan(plan, account, market, NOW)["status"], "BLOCKED")

    def test_illiquid_exit_or_stale_book_blocks(self):
        plan, account, market = fixture()
        market["raw_book"]["levels"][0][0]["sz"] = "0.00001"
        self.assertEqual(size_plan(plan, account, market, NOW)["status"], "BLOCKED")
        plan, account, market = fixture()
        market["raw_book"]["time"] -= 61000
        self.assertEqual(size_plan(plan, account, market, NOW)["status"], "BLOCKED")

    def test_liquidation_tier_equation_and_boundary_continuity(self):
        tiers = normalized_tiers({"marginTiers": [{"lowerBound": "0", "maxLeverage": 20}, {"lowerBound": "100000", "maxLeverage": 10}]})
        self.assertEqual(tiers[0]["rate"] * 100000, tiers[1]["rate"] * 100000 - tiers[1]["deduction"])
        for side in (D(1), D(-1)):
            price = isolated_liquidation(D(110), D(1000), D(11000), side, D(0), tiers)
            tier = tier_at(tiers, price * 1000)
            equity = 11000 + side * 1000 * (price - 110)
            maintenance = price * 1000 * tier["rate"] - tier["deduction"]
            self.assertLess(abs(equity - maintenance), D("0.00000000000000001"))


class JournalTests(unittest.TestCase):
    def bundle(self, fills):
        return {"account_label": "main", "source": "synthetic fixture", "observed_at": (NOW + timedelta(days=1)).isoformat(), "fills": fills,
                "coverage": {"status": "synthetic"}}

    def test_reimport_is_idempotent_and_conflicts_do_not_mutate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle = self.bundle([fill(1)])
            self.assertEqual(import_bundle(bundle, root)["new_records"]["fills"], 1)
            self.assertEqual(import_bundle(bundle, root)["new_records"]["fills"], 0)
            before = (root / "journal/ledger.json").read_bytes()
            bundle["fills"][0]["sz"] = "2"
            with self.assertRaises(ValueError):
                import_bundle(bundle, root)
            self.assertEqual(before, (root / "journal/ledger.json").read_bytes())

    def test_missing_identity_or_nonfinite_amount_rejected(self):
        row = fill(1)
        del row["tid"]
        with self.assertRaises(ValueError):
            normalize_fill(row)
        row["tid"], row["fee"] = 1, "NaN"
        with self.assertRaises(ValueError):
            normalize_fill(row)

    def test_partial_fills_and_flip_conserve_pnl_and_fees(self):
        fills = [fill(1, size="2", fee=".2", time=MS - 600000),
                 fill(2, start="2", size="1", side="A", pnl="2", fee=".1", time=MS),
                 fill(3, start="1", size="3", side="A", pnl="3", fee=".3", time=MS + 1),
                 fill(4, start="-2", size="2", side="B", pnl="4", fee=".2", time=MS + 2)]
        result = episodes([normalize_fill(f) for f in fills])
        self.assertEqual(len(result), 2)
        self.assertTrue(all(e["status"] == "closed" for e in result))
        self.assertEqual(sum(D(e["fees_usdc"]) for e in result), D(".8"))
        self.assertEqual(sum(D(e["closed_pnl"]) for e in result), D("9"))

    def test_missing_opening_not_a_complete_trade(self):
        result = episodes([normalize_fill(fill(1, start="1", size="1", side="A"))])
        self.assertEqual(result[0]["status"], "missing_opening")
        self.assertIsNone(result[0]["holding_minutes"])

    def test_same_millisecond_execution_sequence_uses_positions(self):
        result = episodes([normalize_fill(fill(2, start="1", side="A", pnl="2")), normalize_fill(fill(10))])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["status"], "closed")
        self.assertEqual(result[0]["fill_ids"], ["TEST:10", "TEST:2"])

    def test_ambiguous_sequence_does_not_create_completed_trades(self):
        result = episodes([normalize_fill(fill(1)), normalize_fill(fill(2))])
        self.assertFalse(any(e["status"] == "closed" for e in result))
        self.assertTrue(all(e["status"] == "ambiguous_execution_order" for e in result))

    def test_unknown_hip3_pnl_currency_not_claimed_usdc(self):
        with tempfile.TemporaryDirectory() as tmp:
            row = fill(1, pnl="20")
            row["coin"] = "other:TEST"
            import_bundle(self.bundle([row]), Path(tmp))
            result = daily_report("2026-09-10", Path(tmp))
            self.assertIsNone(result["observed_net_trading_cashflow_usdc"])

    def test_local_midnight_funding_and_cashflows_separate(self):
        midnight = int(datetime(2026, 9, 9, 16, tzinfo=timezone.utc).timestamp() * 1000)
        with tempfile.TemporaryDirectory() as tmp:
            bundle = self.bundle([fill(1, time=midnight - 1), fill(2, start="1", side="A", pnl="5", time=midnight)])
            bundle["funding"] = [{"id": "fund1", "time": midnight, "coin": "TEST", "usdc": "-.2"}]
            bundle["cashflows"] = [{"id": "deposit1", "time": midnight, "type": "deposit", "amount_usdc": "100", "scope": "external"}]
            import_bundle(bundle, Path(tmp))
            result = daily_report("2026-09-10", Path(tmp))
            self.assertEqual(result["fills"], 1)
            self.assertEqual(result["observed_net_trading_cashflow_usdc"], "4.7")


class DataTests(unittest.TestCase):
    def test_weighted_rate_budget_accounts_for_payload_size(self):
        self.assertEqual(request_weight("l2Book"), 2)
        self.assertEqual(request_weight("metaAndAssetCtxs"), 20)
        self.assertEqual(request_weight("candleSnapshot", [None] * 361), 27)
        self.assertEqual(request_weight("userFillsByTime", [None] * 2000), 120)

    def test_unified_account_never_uses_native_zero_as_total_balance(self):
        class Client:
            def post(self, kind, **kwargs):
                return {"userAbstraction": "unifiedAccount", "perpDexs": [None],
                        "clearinghouseState": {"marginSummary": {"accountValue": "0"}, "withdrawable": "0", "assetPositions": []},
                        "frontendOpenOrders": [], "spotClearinghouseState": {"balances": [{"coin": "USDC", "total": "1000"}]},
                        "userFees": {}}[kind]
        with patch("trading_desk.account.InfoClient", return_value=Client()), patch.dict("os.environ", {"HL_ACCOUNT_ADDRESS": "0x" + "0" * 40}):
            result = fetch_account()
        self.assertEqual(result["status"], "partial")
        self.assertIsNone(result["equity_usdc"])
        self.assertIsNone(result["available_to_trade_usdc"])
        self.assertEqual(result["spot_balances"][0]["total"], "1000")

    def test_flat_legacy_account_uses_conservative_available_amount(self):
        class Client:
            def post(self, kind, **kwargs):
                return {"userAbstraction": "disabled", "perpDexs": [None],
                        "clearinghouseState": {"marginSummary": {"accountValue": "1000"}, "withdrawable": "990", "assetPositions": []},
                        "frontendOpenOrders": [], "spotClearinghouseState": {"balances": []}, "userFees": {}}[kind]
        with patch("trading_desk.account.InfoClient", return_value=Client()), patch.dict("os.environ", {"HL_ACCOUNT_ADDRESS": "0x" + "0" * 40}):
            result = fetch_account()
        self.assertEqual(result["available_to_trade_usdc"], "990")
        self.assertEqual(result["equity_usdc"], "1000")

    def test_exact_namespace_override_prevents_crypto_equity_collision(self):
        class Client:
            def post(self, kind, **kwargs):
                if kind == "perpDexs":
                    return [None, {"name": "para"}]
                name = "STX" if kwargs["dex"] == "" else "para:STX"
                return [{"universe": [{"name": name, "maxLeverage": 10}]}, [{"dayNtlVlm": "10"}]]
        rows, _, _ = inventory(Client(), {"para:STX": {"asset_class": "non_crypto", "reason": "Seagate stock"}})
        self.assertEqual([r["asset_class"] for r in rows], ["crypto", "non_crypto"])

    def test_signed_or_unknown_api_calls_refused(self):
        with self.assertRaises(ValueError):
            InfoClient().post("order")

    def test_pagination_inclusive_overlap_and_dedup(self):
        page = [{"time": 100 + i // 2, "tid": i} for i in range(2000)]
        calls = []
        class Client:
            def post(self, kind, **kwargs):
                calls.append(kwargs["startTime"])
                return page if len(calls) == 1 else [page[-1], {"time": 1100, "tid": 2000}]
        result = time_pages(Client(), "userFillsByTime", 0, 1200, lambda r: r["tid"])
        self.assertEqual(len(result), 2001)
        self.assertEqual(calls, [0, 1099])

    def test_saturated_timestamp_is_not_complete(self):
        class Client:
            def post(self, kind, **kwargs):
                return [{"time": 10, "tid": i} for i in range(2000)]
        with self.assertRaises(DataError):
            time_pages(Client(), "userFillsByTime", 10, 20, lambda r: r["tid"])

    def candles(self):
        return [{"t": MS - (300 - i) * 300000, "T": MS - (299 - i) * 300000 - 1,
                 "o": "100", "h": "101", "l": "99", "c": "100", "v": "100"} for i in range(300)]

    def test_open_candle_does_not_inflate_activity(self):
        candles = self.candles()
        expected = candle_metrics(candles, MS)
        candles.append({"t": MS, "T": MS + 299999, "o": "100", "h": "9999", "l": "1", "c": "500", "v": "999999"})
        self.assertEqual(expected, candle_metrics(candles, MS))
        self.assertAlmostEqual(expected["relative_volume_1h"], 1)

    def test_gaps_and_stale_candles_rejected(self):
        candles = self.candles()
        del candles[-15]
        with self.assertRaises(DataError):
            candle_metrics(candles, MS)
        with self.assertRaises(DataError):
            candle_metrics(self.candles(), MS + 600001)

    def test_book_spread_depth_and_freshness(self):
        book = {"time": MS, "levels": [[{"px": "99.99", "sz": "10"}], [{"px": "100.01", "sz": "10"}]]}
        self.assertAlmostEqual(book_metrics(book, MS)["spread_bps"], 2)
        self.assertTrue(book_metrics(book, MS)["depth_is_lower_bound"])
        with self.assertRaises(DataError):
            book_metrics(book, MS + 61000)

    def test_every_dex_inventoried_and_unknown_underlying_retained(self):
        class Client:
            def post(self, kind, **kwargs):
                if kind == "perpDexs":
                    return [None, {"name": "xyz"}]
                names = ["BTC", "PAXG"] if kwargs["dex"] == "" else ["xyz:BTC", "xyz:TSLA"]
                return [{"universe": [{"name": n, "maxLeverage": 10} for n in names]}, [{"dayNtlVlm": "10"} for _ in names]]
        rows, errors, names = inventory(Client(), {"PAXG": {"asset_class": "non_crypto", "reason": "gold"}})
        self.assertEqual(names, ["", "xyz"])
        self.assertEqual(len(rows), 4)
        self.assertEqual([r["asset_class"] for r in rows], ["crypto", "non_crypto", "crypto", "unclassified"])
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
