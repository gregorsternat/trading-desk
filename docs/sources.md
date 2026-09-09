# Primary sources and verification

Checked on 2026-09-10 Asia/Shanghai. Refresh official documentation when a response schema or exchange behavior changes. Example values in documentation are not current instrument limits; always use live metadata.

- [Info endpoint](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint): books, candles, fills, fees, account abstraction. Latest 5,000 candles; time-based fill history limited to the latest 10,000 fills and 2,000 per response. Book snapshots expose up to 20 levels per side.
- [Perpetual info endpoints](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint/perpetuals): DEX inventory, metadata, context, leverage/margin tables, account and funding/ledger observations.
- [Spot info endpoints](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint/spot): balances needed for unified-account context.
- [Rate limits](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/rate-limits-and-user-limits): weighted public requests; the client deliberately serializes and throttles requests and bounds retries.
- [Price and size precision](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/tick-and-lot-size): significant figures, decimal limits and size precision.
- [Margin tiers](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/margin-tiers): tier maximum leverage and continuous maintenance deductions.
- [Liquidation mechanics](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/liquidations): mark price, cross versus isolated and position-level liquidation estimation.
- [TP/SL behavior](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/take-profit-and-stop-loss-orders-tp-sl): mark triggers, slippage, limit-fill uncertainty and parent/partial-fill protection.
- [Fees](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/fees): actual fee treatment depends on tier, maker/taker, discounts, venue and collateral. Use observed user fee rates where available.
- [Requested portfolio](https://app.hyperliquid.xyz/portfolio): actual account tabs and history; requires working browser access or public-address read-only fallback.
- [Requested OpenMarket chart](https://openmarket.xyz/chart/FjCa6FS3): actual indicator observations. Supplied script sources live in `docs/indicators/`.
- [tradeXYZ specifications](https://docs.trade.xyz/consolidated-resources/specification-index) and [Paragon products](https://paragon.trade/products/): distinguish crypto underlyings from equities, FX, commodities and indexes. Check an exact contract, not just its ticker.

Do not add a news event to a report unless its current source supports the timing and claimed session impact. Source availability and current observation are different from validity of a trading thesis.
