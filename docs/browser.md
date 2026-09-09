# Browser observations and recovery

Verified on 2026-09-10 Asia/Shanghai during setup. Use current tool documentation and fresh accessibility state; do not copy old element indexes.

The browser-tab backend repeatedly timed out. Native Chrome accessibility through the available CUA tool succeeded as a fallback. Use this recovery path when browser automation is unavailable; do not inspect cookies, local storage, wallet extensions or filesystem credentials.

## Hyperliquid portfolio

The requested URL opens. In the tested Chrome session it displayed `Connect`, so its empty balance/positions are unauthenticated placeholders. They do not prove a zero balance. Wait for the user to connect the intended account or provide a public address for read-only API retrieval. Opening account menus does not authorize signing, orders, transfers or new API wallets.

## OpenMarket

The exact shared chart opens in Guest Mode, with a banner that changes are not saved. The chart displayed `HYPERLIQUID.F`, a PERP selector and all three supplied toolkit names. A browser-access failure therefore does not mean the workspace or indicators were deleted.

- Dismiss ordinary sign-up banners and the `Best on Desktop` presentation prompt when they obstruct viewing. Use a screenshot if the accessibility tree still exposes a hidden prompt.
- Click the contract selector, search by ticker in `Search by symbol or name`, and choose the row explicitly labeled `HYPERLIQUID.F PERP`. Other venues/spot pairs can appear in the same search. INJ returned 30 venues during verification.
- A ticker can change **before** the old candle/price values are replaced. Wait for `Loading candles...` to disappear and verify that price, instrument and timeframe correspond to the fresh Hyperliquid API before interpreting indicators.
- The PUMP legend rendered `Adaptive Trail: 0.00` at a sub-cent price, and some flow legend fields displayed dashes. These are precision/availability limits, not literal zero support or zero money flow. Use the chart axis/data view with sufficient precision, or record unknown. Do not choose a numeric entry/SL from a rounded-to-zero label.
- Inspect actual closed bars and any crosshair selection. Animated digit text in accessibility can concatenate into misleading numbers; confirm exact financial values through a stable display or API rather than parsing transient animated strings.

This document records navigation verification, not a current trade recommendation. Refresh market and account observations in every actual analysis.
