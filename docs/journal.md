# Journal inputs and accounting

`journal/ledger.json` is the atomic source ledger. `journal/episodes.json` and `journal/daily/*` are derived output. `journal/account/*` stores timestamped observations; `state/account.json` is the latest observation. `journal/reviews/*` holds human reasoning and must not be overwritten by regeneration.

## Import contract

Create a JSON bundle following `templates/journal-import.json` from actual observations. Required envelope: `account_label`, `source`, `observed_at` (offset-aware ISO timestamp), and explicit `coverage`. The account label is a local nickname such as `main`, never a wallet address. Use a different repo/journal scope for another account; do not mix identities.

`fills` accepts Hyperliquid field names:

- Required: `coin`, `tid` (or a stable source `fill_id`), `time` in Unix **milliseconds**, `side` (`B` buy, `A` sell), `px`, `sz`, `closedPnl`, `fee`, `feeToken`.
- Useful: `startPosition`, `dir`, `oid`. Missing leverage, original SL/TP and trade thesis cannot be reconstructed from fills. Keep them unknown until sourced.
- Decimal strings preserve the venue values. `fee` already includes any builder fee; never add `builderFee` again. Negative maker rebates remain negative fees.
- Native perp PnL is USDC. For HIP-3 fills, supply `pnl_token` only after verifying contract collateral; otherwise the currency remains unknown and aggregate USDC net is withheld. Spot executions remain in the ledger but outside perp episode/day totals.
- Do not silently convert a grouped UI row into a single exchange execution. Inspect exported headers and aggregation. A timestamp/price/size fingerprint can collapse genuinely identical fills; obtain stable IDs or retain the observation in a review as incomplete until reconciled.
- Deduplication uses `coin:tid`; an identical reimport adds no execution. Conflicting data with the same ID is rejected, not overwritten.

`funding` accepts API `{time, hash, delta: {coin, usdc}}` or normalized `{id, time, coin, usdc}`. Positive `usdc` is received; negative is paid. Funding belongs to the account timeline first. Allocate it to a trade only if the position/exposure interval is clear.

`cashflows` accepts `{id, time, type, amount_usdc, scope, note}`. Use signed amounts only after confirming whether the record is an external deposit/withdrawal, an internal spot/perp transfer or another ledger event. The optional API history helper leaves unclassified transfer amounts null; inspect the actual portfolio/export to classify them. No counterparty address is retained. A transfer can affect a native-perp balance while leaving total account equity unchanged.

`coverage` must state earliest/latest observed execution, requested period, source timezone, pagination/export scope and missing ranges. Hyperliquid time APIs return limited pages and only the latest 10,000 fills are retained. The helper pages with an inclusive boundary overlap and fails on a saturated timestamp that could hide fills. A response smaller than a page does not prove complete all-time history; compare the first recorded fill and the export. Never label a day complete just because the last API call succeeded.

## Account snapshot

Use `templates/account.json`. `status` can be `unverified`, `partial`, or `verified`. Observe and distinguish:

- Equity/PnL scope: native perps versus unified portfolio; collateral and liabilities.
- Available to Trade, not just total balance or withdrawable.
- Balances, Positions, Open orders and their separate observation times.
- Actual positions, leverage/mode, size, mark value, unrealized PnL, margin and estimated liquidation.
- Orders with side, price/trigger, size, order type and reduce-only status, including attached/conditional children where visible.
- Available collateral after order reservations and the total risk if all pending entries that can coexist fill.

Explicit empty lists are valid only after verifying the corresponding tabs. `null` means unknown. Never set `available_includes_order_reservations` or `committed_risk_verified` true from a guess. A stale verified snapshot is still historical evidence; the sizing calculator rejects it after 120 seconds. Subaccounts, unified accounts and portfolio margin can make API balances non-interchangeable. Read the UI when the optional account helper returns partial.

## Daily report and episodes

Daily boundaries are 00:00–24:00 Asia/Shanghai (half-open); raw timestamps remain UTC milliseconds. The generated daily net trading cashflow is `sum(closedPnl) - sum(all fill fees in USDC) + sum(funding)`. It includes opening fees from positions still open and excludes deposits/withdrawals. Non-USDC fees make the net incomplete until converted with verified valuation. It is **not** a daily equity return, nor necessarily a completed-trade PnL.

Episode reconstruction follows `startPosition` and signed fills from flat to flat. Partial fills remain separate evidence. A reversal closes one episode and opens another, allocating its fee in proportion to size and all reported closed PnL to the closing leg. A missing opening or position discontinuity flags incomplete history. Holding duration is unknown when the opening is unknown. Equal-millisecond fills need a source-defined sequence; review any ambiguous order instead of asserting reconstructed episodes are exact. Funding is not automatically allocated to episodes.

To reconcile balance, use observed opening and closing snapshots with the same equity perimeter. Account for realized PnL, all fees, funding, deposits/withdrawals, change in unrealized PnL, collateral valuation and relevant other ledger movements. The system deliberately records `not_established` until this comparison has evidence. Write the reconciliation in the human review; do not invent a starting balance or force an arithmetic match.

For user-supplied qualitative outcomes, record them as user-reported until matched to executions. Risk multiple `R` needs the initial planned all-in loss amount; never derive it from the maximum allowed 20%. Do not classify a process as profitable based only on win rate or one large leveraged gain.
