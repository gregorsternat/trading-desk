# Hyperliquid trading desk

Personal research workflows for crypto perpetuals held for **15 minutes to several hours**, with a **24-hour maximum horizon**. Python 3.9+ and the standard library are sufficient. The three Codex skills live in `.agents/skills/` and travel with this repository.

## Use in Codex

Open this repository, then invoke:

| Skill | Example | Result |
|---|---|---|
| `$hyperliquid-watchlist` | `Use $hyperliquid-watchlist for my next 3-hour session.` | Current active crypto watchlist, coverage and only relevant verified news. No trade recommendations. |
| `$hyperliquid-analyze` | `Use $hyperliquid-analyze on INJ and BTC for the next few hours.` | Actual OpenMarket chart review and, where justified, priced scenarios with size, leverage, SL, TP and expiry. An empty decision list is valid. |
| `$hyperliquid-journal` | `Use $hyperliquid-journal to update today's trades and account balance.` | New executions, fees, funding, daily journal and evidence-based lessons. |

If a newly created skill is not yet in the picker, open a new task in this repository or ask Codex to read its `.agents/skills/<name>/SKILL.md`. No external AI API subscription or exchange API key is required. These are reusable on-demand workflows; no clock schedule is enabled. A future scheduler can invoke the same skills at user-selected times.

## Trading profile

The user explicitly selected a **20% maximum modeled loss per trade**, including fees, estimated slippage and funding. There is no default target loss percentage: the analyst must choose and justify one at or below the cap. Large leverage and margin allocations are allowed when the setup and liquidation buffer support them. The limit does not make a stop a guaranteed loss cap.

Implementation defaults in [config/profile.json](config/profile.json): isolated margin, a 2% cash reserve, at most 20% aggregate committed stop risk across positions and orders that could fill together, and at least 1.5 net reward/risk. These are transparent design choices, distinct from the user-selected per-trade cap. They can be reviewed as real results accumulate. No fixed maximum leverage is hardcoded; instrument metadata and margin tiers are refreshed.

## Commands

Run from the repository root:

```bash
python3 scripts/desk.py watchlist
python3 scripts/desk.py market INJ --output .local/inj-market.json
python3 scripts/desk.py journal-import .local/observed-history.json
python3 scripts/desk.py journal-day 2026-09-10
python3 scripts/desk.py size --plan .local/plan.json --market .local/inj-market.json
python3 -m unittest discover -s tests -v
```

The collector inventories all available perpetual DEXs, filters delisted/non-crypto instruments, checks closed 5m candles across the liquid crypto universe, then inspects books for the strongest activity candidates. Every exclusion and retrieval failure is retained. HIP-3 underlyings not yet verified remain `unclassified`; a native symbol match is only a candidate classification and requires contract verification before analysis. The approximate 1h notional volume and relative volume are not trading signals. News and actual indicator interpretation are performed by the skill, not invented by the collector.

The journal accepts actual API fills or normalized observations using [the import contract](docs/journal.md). It deduplicates by stable execution ID, refuses conflicting records, reconstructs partial fills and reversals, and separates deposits and withdrawals from trading PnL. Human reviews live in `journal/reviews/` so regenerating daily accounting does not overwrite them.

The optional `fetch-history` and `fetch-account` commands read a **public account address from `HL_ACCOUNT_ADDRESS` in the process environment**. Supply it temporarily; do not commit it. They query only Hyperliquid `/info`. Account availability remains unknown when account mode, collateral, open-order reservations or ongoing exposure cannot be reconciled. The portfolio browser is the preferred cross-check; credentials and signed endpoints are never needed.

## Files that matter

- [AGENTS.md](AGENTS.md): shared workflow and source rules.
- [PROFILE.md](PROFILE.md) and [config/profile.json](config/profile.json): trading intent and numerical limits.
- [docs/analysis.md](docs/analysis.md): analysis and financial mechanics.
- [docs/indicators.md](docs/indicators.md): interpretation of the three supplied scripts; originals preserved in `docs/indicators/`.
- [state/account.json](state/account.json): latest observed account state, with verification and timestamps.
- `reports/watchlists/`, `reports/analysis/`: dated research artifacts.
- `journal/ledger.json`, `journal/account/`, `journal/daily/`, `journal/reviews/`: account facts and trading history.
- [memory/lessons.md](memory/lessons.md): short, evidence-linked learning register.

The repository contains personal financial records when initialized. `.local/` holds temporary inputs and raw browser exports and is ignored. No credentials, account addresses, wallet bindings, or browser storage belong in version control. Repository creation does not publish these records automatically.

## Verification boundaries

The implementation does not place, cancel or modify orders, change leverage on an account, or move funds. It prepares decision support for manual execution. Unit tests cover data and financial arithmetic; they do not validate a profitable trading strategy. Current setup verification and concrete access blockers are recorded in [docs/setup-status.md](docs/setup-status.md).
