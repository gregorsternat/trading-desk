# User trading profile

- Venue: Hyperliquid crypto perpetuals.
- Preferred duration: roughly 15 minutes to several hours, ideally closed the same day; maximum modeled hold 24 hours.
- Style: discretionary intraday trading supported by current activity, price structure, trend, momentum and actual order-flow data where available.
- High risk tolerance, large leverage and potentially almost all available margin on one trade. Avoid artificially tiny positions on strong, liquid setups; choose size from structural invalidation and the explicit risk budget.
- Explicit clarification on 2026-09-10 Asia/Shanghai: **maximum modeled loss of 20% of verified trading equity per trade**. Costs count toward this ceiling. No default target risk percentage was chosen.
- The account's current equity, available collateral, exposures and fills must be read afresh. Prior conversations do not establish any current holdings or balance.
- User execution is manual; the requested automation covers research, journal updates and learning.
- Watchlist: identify what is moving now; no directional advice or entry plan.
- Analysis: few useful, specific decisions, or no trade. Include exact contract, entry, size, margin, leverage, SL, TP, costs, expiry, horizon, invalidation and modeled risk/return when supported.
- News: only sourced events with a plausible impact within the session; no generic headline padding.

Implementation defaults, not additional user choices: 2% liquidity reserve, 20% aggregate committed stop risk, isolated-margin calculator and minimum 1.5 net reward/risk. Configuration is centralized in `config/profile.json`.

At a 20% realized loss repeated five times, 32.768% of initial equity remains (before other effects). This arithmetic is why the cap must not become a target or a reason to increase risk after losses. Stops can slip, fail to fill or be overtaken by liquidation; the numeric ceiling is a planning constraint, not a guaranteed worst case.
