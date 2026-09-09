# Setup verification — 2026-09-10 Asia/Shanghai

## Implemented

- Three repository-scoped Codex skills: activity watchlist, named-pair OpenMarket analysis, and journal/account/learning updates. All three passed the skill creator's frontmatter validator.
- Dependency-free Python CLI for public universe scans, live instrument metadata/books, proposed isolated-trade sizing, idempotent history import, daily accounting, and optional public-address account/history collection.
- User-selected 20% maximum modeled loss per trade, with costs included; configurable implementation defaults documented separately.
- Original toolkit attachments preserved byte-for-byte. Indicator interpretation includes delayed pivot confirmation, shared inputs, unavailable order flow and rounded display limits.
- Timestamped account/session state, an appendable evidence-based lesson register and a human review location kept separate from generated daily reports.

## Verified

`python3 -m unittest discover -s tests -v`: **30 tests passed**. Tests cover price/size precision, long/short arithmetic, maintenance-tier liquidation, risk and collateral budgets, stale/missing/mismatched data, order-book capacity, instrument classification collisions, partial fills and reversals, ambiguous equal-time fills, deduplication/conflicts, funding and local-day accounting, non-USDC ambiguity, unified-account balance handling and weighted request costs. Synthetic fixtures do not represent the user's account or historical trades.

A separate temporary CLI integration run imported two synthetic executions, reimported with zero additions, generated one completed episode, and preserved a human review on regeneration. These fixtures were never written to the real journal. Running `size` against the unverified account returned `BLOCKED`, without an order action.

The public API scan at **2026-09-09 19:06:02 UTC / 2026-09-10 03:06:02 Asia/Shanghai** inventoried **517 contracts across 11 DEXs**, inspected closed candles for **73 liquid crypto candidates**, and completed without DEX retrieval failures. Its dated artifacts are:

- `reports/watchlists/20260909T190602Z.json`
- `reports/watchlists/20260909T190602Z.md`

This was a collector verification, not a complete session brief: current-news and discretionary activity review remain pending. The saved watchlist expires and is not a standing list to trade. The scan had 33 unclassified active HIP-3 symbols; subsequent official specification review classified 20 of these in `config/asset-overrides.json`. The remaining 13 are explicitly unresolved (`xyz:SKHX`, `xyz:CL`, `xyz:SMSN`, `para:ANSEM`, four `mkts` markets, and five `io` markets). They remain inventoried and must not be silently labeled crypto. Classification changes do not change the original scan's observation time or claim full coverage retroactively.

Fresh per-instrument API collection was also checked for INJ and BTC. Leverage and margin tables come from live metadata, not stored assumptions. The final client revision paces by documented endpoint and returned-item weight, with 900-weight/minute headroom under the shared IP limit.

The exact OpenMarket shared chart opened through native Chrome. PUMP on `HYPERLIQUID.F` at 1h and all three toolkit names/panels were visually verified. The INJ selector returned the correct Hyperliquid perp venue and was selected; the last observed state was loading candles. The Mac then locked, so a completed INJ chart refresh was not verified. No current trade analysis is being claimed.

## Account initialization pending

The portfolio opened but showed **Connect**. It did not provide authenticated balances, positions, orders or history. Browser-tab calls had earlier timed out; native Chrome navigation recovered public-page access. The Mac subsequently locked and needs manual unlocking for further browser work.

No user balance, fill, PnL, leverage or historical trade was invented or imported. `state/account.json` remains unverified, with unknown values represented as null. `journal/initialization.json` records the concrete blocker. A public account address has been requested for the optional read-only API fallback; no address was supplied during setup.

To finish initialization: read the intended connected portfolio after the Mac is unlocked, or use the user-supplied public address for API collection; import the observed bundle and reconcile the daily journal. No private key is needed.

No recurring clock schedule was chosen or enabled, and no exchange action was signed or submitted. The skills are on demand. Changes are delivered on `gregorsternat/hyperliquid-workflows`; remote publication is separate from these local checks.
