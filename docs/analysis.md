# Analysis and sizing contract

Start with a market hypothesis and a falsifiable invalidation. Set the stop where the thesis fails, with room for typical local volatility and an actual structural reason. Choose an entry and a reachable target in the 15-minute to several-hour horizon. Only then compute risk, quantity, margin and leverage. A smaller stop chosen solely to inflate the position is not evidence of a better opportunity.

## Evidence and horizons

Use 1h/4h for trend, compression/range, nearby liquidity and context; 15m for the setup; 5m for trigger/retest and execution timing. A 1m fluctuation should not reverse a 15m thesis unless the original invalidation says so. Separate a closed-bar break from a wick excursion. Note whether the move has already traveled most of its expected local range and whether entry would chase late participants.

Distinguish a trend continuation, range fade and failed-breakout/sweep setup. A range oscillator extreme is not automatically a reversal during a strong trend. Do not force a countertrend trade because it offers a tighter-looking stop. Price-action boxes are historical price-derived zones, not proof of resting orders. Real footprint/taker data only adds evidence when it is actually present for the exact venue.

Before a new idea, inspect prior plans: classify pending, triggered, missed, invalidated or expired. Do not move a past target/stop to make the historical call look correct. A setup not taken belongs in the review only when there was a recorded contemporaneous plan.

## Costs, size and liquidation

`risk.py` models a **new isolated linear USDC perpetual**. It does not model cross collateral, portfolio margin, non-USDC collateral or adding to an existing same-coin exposure. These cases need current combined-position arithmetic and must remain non-actionable while it is absent. Existing other positions/orders require verified total committed risk. Do not count potentially simultaneous pending entries as independent uses of the same balance.

The helper accepts `entry_order_type: limit` or `post_only` and `stop_order_type: stop_market`. It blocks a post-only entry that currently crosses the book. A stop-limit requires a separate nonfill scenario and is not accepted by this helper. State a concrete `invalidation` in every plan.

For side `s = +1` long or `-1` short, entry `E`, stop `S`, quantity `q` and leverage `L`:

```text
notional = q × E
initial margin = notional / L
modeled stop fill = S × (1 - s × (adverse slippage + absolute current mark/book basis))
loss = q × [s × (E - stop fill) + E × (entry fee + funding reserve) + stop fill × exit fee]
quantity <= risk budget / loss per unit
quantity <= affordable collateral after reserve and costs
quantity <= configured participation in currently visible exit depth
```

All rates use their stated units. Plan cost inputs are **basis points**, where 1 bp = 0.01%. Funding budget is the total adverse rate allowance for the proposed holding horizon, not an annualized rate or a claim that the current hourly rate will persist. Negative expected funding is not treated as guaranteed income. Fee assumptions must identify the source and reflect maker/taker treatment, discounts and builder fees where applicable. The calculator does not assume that every limit order is a maker; a crossing limit can be taker. Its TP projection uses the stated exit fee and assumes execution at the target, so do not present it as a guarantee.

The user selected a maximum **20% loss per trade**, inclusive of these modeled costs. Keep a 2% equity reserve and at most 20% total committed stop risk as implementation defaults. Reserve constraints can make exactly 100% margin allocation infeasible. The output explicitly shows any reduction from the requested risk size; do not compensate by fabricating a closer stop.

Prices obey the venue's five-significant-figure and decimal rules (integer prices are allowed), sizes round down to `szDecimals`. Long entries/targets/stops round down and shorts round up; rerun structural checks after rounding. Fetch the margin table and check entry-tier maximum leverage. Maintenance margin is tier-dependent with a deduction that makes tier boundaries continuous. The liquidation solver selects the tier applicable **at the computed liquidation price**, rather than assuming the entry tier persists. It deducts modeled costs from isolated collateral conservatively.

Use the highest useful leverage only if margin efficiency is needed and the estimated liquidation remains beyond the modeled stop fill by at least half the entry-to-stop distance. This half-distance buffer is a configurable implementation default, not a venue guarantee. Cross liquidation cannot be obtained from `1 / leverage`; other positions, funding and mark valuation change the account risk. Verify the exchange's own liquidation preview before placement.

Current order-book depth is a snapshot of at most 20 levels per side. The calculator limits quantity to 25% of the visible exit-side quantity within the specified slippage window. This can be conservative when the visible levels do not span the full window. It cannot guarantee depth will remain during a stop run. The output includes a larger adverse-slippage stress loss and whether it crosses modeled liquidation. Neither a stress scenario nor a stop defines an absolute maximum loss.

## Entry and exit semantics

State whether a limit is post-only, a normal resting limit, or would immediately cross the market. A passive order has fill uncertainty and adverse-selection risk; an unfilled good idea is not a trade. Every candidate needs a short validity window (at most 15 minutes without a refresh), an exact conditional trigger, a cancel-on-invalidation condition and a maximum holding time. A time stop can be useful when the expected impulse has not materialized.

On Hyperliquid, TP/SL triggers use **mark price**. A stop-market prioritizes an attempted exit but still has a slippage limit; a stop-limit can remain unfilled after a gap. A high-leverage position can liquidate before an inadequate stop executes. Verify actual protective orders in Open orders, quantity and reduce-only status after any manual fill. Parent-attached protection has partial-fill behavior: canceling a partially filled parent can cancel its child protection; do not assume the filled portion is protected.

Prefer one structural stop and one target unless separate liquidity/structure levels support scaling out. If there are multiple targets, allocations must total exactly 100%. Weighted net reward/risk assumes all targets; separately describe TP1 then remaining stop and the remaining net payout. Moving a stop to entry after TP1 can still lose money after costs and is not automatically correct. Never widen a stop to avoid realizing a loss without a new explicit user decision and recalculated aggregate risk.

## Output quality

Use `NO_TRADE` when no setup has attractive evidence and feasible economics. Use `WAIT_EVENT` for a specific untriggered condition and `DATA_BLOCKED` for unavailable evidence. These are different states. Do not fill an empty decision list with weak trades. No fixed win-rate, confidence percentage or expected value is justified without relevant recorded samples. Net target payout is conditional arithmetic, not a prediction of gain.

For multiple candidates, consider shared BTC/ETH beta and simultaneous stop-outs. Reductions in size due to existing risk, cash reserves or liquidity are informative, not reasons to bypass the controls. A missed trade does not justify increasing the next risk budget.

The API and exchange mechanics above were checked against [Hyperliquid's source documentation](sources.md). Recheck them when schemas or behavior change.
