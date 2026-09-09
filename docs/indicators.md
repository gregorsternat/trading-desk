# Supplied OpenMarket toolkits

The three original user-supplied scripts are preserved verbatim under `docs/indicators/`. They use OpenMarket's `define`, `ohlcv`, series and drawing APIs. The `//@version=3` header does **not** make them interchangeable with TradingView Pine v3. No port or source modification is needed for the requested workflow.

Source text describes the rules; it does not establish which settings or signals are active on the current chart. Read the actual displayed instrument, timeframe, legend/data values and settings when a setting changes the interpretation. A source comment claiming a test harness exists is not evidence of trading profitability or an independently verified local test.

| Toolkit | Decision-relevant interpretation | Limits |
|---|---|---|
| Price Action Toolkit | Internal/swing structure breaks, CHoCH, sweeps, historical order-block/FVG zones and local invalidation. | Several objects share one swing detector and are correlated. An order block is not an exchange order-book observation. |
| Trend Signals Toolkit | Regime/trend filter, volatility-band flips, adaptive trail, stepper/keel/cloud and potential momentum exhaustion. | A plotted TP/SL ladder is a rule-derived overlay, not a personalized risk plan or placed order. Signals can lag or whipsaw. |
| Oscillator Toolkit | Momentum behavior, actual confirmed divergences, range money flow, and optional genuine taker flow/CVD. | The classic money-flow line is range/direction-derived, not actual signed capital flow. A confluence score is not a calibrated probability. |

## Price Action Toolkit

The shared leg-state detector confirms internal pivots after the configured lookback (default 5 bars) and swing pivots after the swing lookback (default 50). Letters/zones can therefore be drawn at a historical pivot only after later confirmation. At 5m, the default internal pivot delay is 25 minutes; a default 15m swing pivot takes 12.5 hours. Do not treat these as real-time discoveries at the plotted pivot timestamp.

Equal levels use different two-sided fractals (3/15 bars), trend lines use two-sided 2-bar wick pivots, and patterns use symmetric body pivots. ATR(200) supplies tolerances and zone widths. Defaults show internal structure while swing structure is off; chart settings can differ. Footprint grades annotate classic objects and stand down when their source is absent. Verify whether an order-flow layer is enabled and has real sided data before attributing a sweep or break to aggressor flow.

## Trend Signals Toolkit

The signal trigger uses ratcheting bands around OHLC4 with ATR(7); grades also use the SMA50 trend basis, RSI-like momentum and a 72-bar strength measure. The default trigger width is 12 and presets can override several display/logic settings. Adaptive Trail, Trail Buffer Edge, Trend Stepper, Trend Keel and Trail Cloud are different stateful overlays; use the relevant one for the current regime rather than counting them as separate confirmations.

TP/SL spacing uses ATR(200) frozen at an anchor. An old anchor may not match the intended entry or today's account risk. Fade signals mean a countertrend model is active; do not label them trend continuation. Signal evaluation is intended at bar close, so record the last completed signal and distinguish an intrabar developing change.

## Oscillator Toolkit

The momentum wave is a double-EMA normalized momentum measure; it is not standard RSI. Wave divergences use strict 1/1 fractal pivots confirmed one bar later and compare extreme **closes** in six-bar windows. A divergence is known on the confirmation bar, even when a connector extends backward.

Range Money Flow is based on directional closes and smoothed ranges. Its adaptive ceiling/floor has long memory and may need roughly 300 bars to settle. Taker Money Flow is a separate optional series computed from actual sided USD trades. CVD is session-anchored; its divergences stay within one session and the stronger grade uses a higher-frame cumulative delta check, finalized on a closed bar. A missing CVD/taker lane means unavailable or disabled, not neutral flow or zero delta.

The confluence strip/score reuses wave, wave/signal, classic flow, surge and divergence components. These are related transforms, not five independent statistical tests. Describe useful agreement, disagreement and which observation would invalidate the thesis. Extreme readings can persist during an impulse; divergence without structural confirmation is insufficient by itself.

The three scripts should inform judgment with the actual chart; there is no automated buy/sell ensemble in this repo.
