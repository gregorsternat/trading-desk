# Trading lessons

Initial API import on 2026-09-10 contains two completed positions (INJ short and PUMP long), six fills and one funding event. See `journal/reviews/2026-09-09.md` and `journal/reviews/2026-09-10.md`. Neither a strategy edge nor a trade-quality judgment is established by this sample. Initial planned risk, SL/TP and leverage remain unknown; future entry plans must retain these to support comparable net-R reviews. Browser account cross-check remains pending.

## Process rules in use

- Inspect the full available universe before a session; activity over the last hour matters more than yesterday's headline move.
- Use the requested chart's actual values and confirmed bars. Backdrawn pivots and shared primitives must not inflate confidence.
- Choose structural invalidation before leverage or size. Apply the user-selected 20% maximum modeled loss including costs; do not target the ceiling automatically.
- Preserve raw executions, contemporaneous plans and unknowns so future reviews can test a hypothesis instead of rewriting history.

These are implementation principles, not conclusions learned from profitable trades.

## Evidence register

Add an entry only when it changes a future decision:

`ID | status (hypothesis / repeated observation / retired) | concrete claim | supporting review + fill IDs | contrary evidence | comparable sample count | next test | date`

Avoid win-rate claims on incomplete episodes. Evaluate net R only with known initial risk, costs, regime and exposure. A valid losing trade can support a sound process; a profitable rule violation cannot validate the violation. Keep this file short and link detailed reviews.

`PREPLAN-001 | repeated observation | Profitable or losing fills cannot be evaluated in net R when invalidation, intended risk and exit logic are not recorded before entry. | journal/reviews/2026-09-09.md and journal/reviews/2026-09-11.md; four completed INJ, PUMP, TAO and XMR episodes | XMR had leverage and TP/SL captured shortly after entry, but not verified pre-fill protection or all-in initial risk | 4 completed episodes | Before the next manual order, save a timestamped plan with invalidation, all-in risk and intended exit reason; compare the resulting episode without retrofitting. | 2026-09-11`
