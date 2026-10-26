# Crypto Trading System: Full Build Plan

Real-time, multi-coin, paper-first, live-ready. Prepared 27 Oct 2026.

## 0. Purpose, scope and ground rules

**Goal:** a system that runs on your computer 24/7, streams live prices for several coins, generates signals with rule-based and ML strategies, trades virtual money on live prices (paper mode), switches to real money only through guarded config, and ends every day with a summary report.

**Out of scope for now:** high-frequency trading, leverage and shorting, automatic withdrawals, NSE stocks (the same engine gets reused for them in the next phase).

**Ground rules**

1. No plan can guarantee profit. Success means the system is correct and safe, and strategies are validated after fees, slippage and tax. A strategy that fails validation is not shipped.
2. One code path. Strategy, risk and execution code is identical in backtest, paper and live. Only the exchange adapter differs.
3. When in doubt: stop opening trades, protect existing positions, alert you.
4. The LLM never places orders and never changes risk limits. It only explains and summarizes.
5. Every decision is logged and replayable. Money math uses Decimal. Time is UTC.

## 1. Requirements checklist (re-verified in section 17)

- R1 Real-time live data for multiple coins (sec 4)
- R2 Paper trading with virtual money on live prices (sec 6)
- R3 Easy, guarded switch from paper to real money (sec 3, 14)
- R4 Kill switch: manual and automatic, multi-level, survives restart (sec 7.4)
- R5 Loss handling (sec 7.2)
- R6 Profit handling (sec 7.3)
- R7 Daily summary report of everything done (sec 10)
- R8 Multiple strategies and coins running concurrently (sec 5)
- R9 AI automation: ML signals, sentiment, LLM journal, Telegram control (sec 5, 9)
- R10 Backtesting and validation (sec 8)
- R11 Crash recovery and reliability (sec 12)
- R12 Dashboard (sec 11)
- R13 Testing including fault injection (sec 13)
- R14 Security and secrets (sec 12)
- R15 Tax and record keeping (sec 7.3, 10, 14)
- R16 Timeline (sec 15)
- R17 Stress test of the plan itself (sec 16)
- R18 Final recheck (sec 17)

## 2. Architecture

```
Exchange WebSocket / REST
        |
  [Market Data Service] --> candles + order book store (Parquet + DuckDB)
        | events
  [Strategy Workers] (symbol x strategy) --> Signals
        |
  [Allocator / Sizer] --> order intents
        |
  [Risk Engine] --approve/veto--> [Order Manager] --> [Adapter: Paper | Testnet | Live]
        ^                               | fills
        |                         [Position + PnL Ledger] -- SQLite (state + event log)
  [Kill Switch Controller] <-- [Watchdog process] <-- heartbeats
        |
  [Telegram alerts]  [Reports + LLM journal]  [Streamlit dashboard]
```

**Processes:** (1) bot: one asyncio process with data, strategies, risk, execution, scheduler; (2) watchdog: separate process with its own exchange client; (3) dashboard: separate read-only Streamlit process.

**Stack**

- Python 3.11+, asyncio; ccxt for exchange access behind your own thin adapter interface
- pandas, numpy, pandas-ta or TA-Lib
- SQLite (WAL mode) for state and event log; Parquet + DuckDB for market data and analytics
- pydantic (config validation), structlog (JSON logs), APScheduler (jobs)
- XGBoost or LightGBM, scikit-learn, transformers (FinBERT)
- python-telegram-bot, Streamlit + Plotly, an LLM API for the journal
- pytest, hypothesis, ruff, mypy, Docker Compose, GitHub Actions

**Repo layout**

```
tradebot/
  config/        settings.yaml, risk.yaml, strategies.yaml, symbols.yaml
  src/tradebot/
    core/        events, models (Order, Fill, Position, Signal), clock, money
    data/        stream, candles, backfill, quality, store
    strategies/  base, ema_trend, meanrev, breakout, ml_signal, regime
    portfolio/   allocator, sizing, ledger
    risk/        engine, limits, killswitch
    execution/   order_manager, rate_limit, reconcile, adapters/(base, paper, ccxt_live)
    backtest/    engine, costs, metrics, walkforward, montecarlo
    ai/          features, sentiment, journal, models/
    reporting/   daily, templates/, tax_ledger
    alerts/      telegram_bot, notifier
    watchdog/    watchdog
    main.py
  dashboard/app.py
  tests/         unit, integration, replay, chaos
  data/ reports/ logs/   (git-ignored)
  Dockerfile, docker-compose.yml, .env.example, pyproject.toml
  .github/workflows/ci.yml
```

## 3. Modes and the paper-to-real switch

Three modes: **paper**, **testnet** (if the exchange offers one), **live**.

Every adapter implements the same interface: place\_order, cancel\_order, cancel\_all, get\_order, get\_open\_orders, get\_balances, get\_market\_rules (tick size, lot size, min notional, fees), subscribe streams. The paper adapter matches it exactly, so strategies and risk code never know which mode they run in.

**Live-mode guards (all must pass or the bot refuses to start live)**

1. Two independent switches: mode: live in config AND environment variable LIVE\_TRADING\_ENABLED=true.
2. Typed confirmation at startup: you type the capital amount and the word LIVE.
3. A go/no-go record in the database (section 14) with every gate passed, dated within the last 14 days.
4. API key check at startup: trading permission yes, withdrawal permission NO (bot aborts if withdrawals are enabled), IP whitelist set.
5. Hard capital cap (max\_capital\_usdt). The bot never uses more, even if the account holds more. Use a dedicated sub-account or a small deposit.
6. Preflight: time sync OK, balances match expectations, no unknown open orders or positions, kill switch at L0, feeds fresh, database writable, test Telegram message delivered.
7. Enforced ramp: size multiplier 10% then 25% then 50% then 100%. Each stage needs a minimum number of days and zero critical incidents.

Switching back to paper is one setting and needs no confirmation. Paper and live use separate database files and state folders so they never mix. Testnet and live use separate API keys.

## 4. Data layer

**Symbols:** BTC/USDT, ETH/USDT, SOL/USDT, BNB/USDT, XRP/USDT to start (config list). Base timeframe 1m, derived 5m, 15m, 1h.

**Live feeds per symbol:** trades, 1m klines, order book top 20 levels (for slippage and spread).

**Candle builder:** builds bars from trades, closes a bar when the next interval starts, and reconciles with exchange klines every 5 minutes via REST, repairing differences.

**Storage:** raw ticks kept 7 days; candles and 1-second order book snapshots (top 10 levels) in Parquet partitioned by symbol and date; DuckDB for queries.

**Historical backfill:** 3 years of 1m candles via REST, resumable and validated.

**Data quality guards**

- Duplicate and out-of-order ticks dropped.
- Gap detector with automatic REST gap fill.
- Spike filter: a move above 5% in one tick without volume support is quarantined.
- Stale feed: no update for 15 s pauses that symbol; all symbols stale for 60 s triggers kill switch L1.

**Reconnect:** exponential backoff with jitter, resubscribe, backfill the gap, resume trading only after candles are consistent.

**Time:** UTC everywhere, NTP drift check every 5 minutes, abort above 1 s drift. Dashboard and reports show IST.

## 5. Strategy layer

**Interface:** on\_candle(context) returns zero or more Signals (symbol, side, entry type, stop, target, confidence, reason text). Strategies are pure functions of data and parameters, so they are testable and replayable. They never touch the exchange or balances.

**Initial strategies**

- S1 Trend: EMA 20/50 crossover, ADX above 20, ATR-based stop (1.5 to 2 ATR).
- S2 Mean reversion: Bollinger Bands plus RSI extremes, only in low-trend regimes.
- S3 Breakout: Donchian 20-bar breakout with above-average volume.
- S4 ML signal: XGBoost or LightGBM classifier; trades only when probability exceeds a threshold calibrated on validation data.
- S5 Sentiment overlay: FinBERT score on crypto headlines (RSS or news API), used as a filter or size modifier, never a standalone trigger.

**Regime detector:** trend, range or high-volatility using ADX and realized volatility (HMM later). Each strategy declares the regimes it may trade in.

**Allocator:** capital split per strategy; per-symbol caps; correlation bucket (BTC, ETH, SOL count as one correlated bucket); one position per symbol-strategy pair; conflicting signals on one symbol resolved by priority.

**ML pipeline**

- Features: multi-horizon returns, ATR and volatility ratios, RSI, MACD, EMA distances, VWAP distance, volume z-score, order book imbalance, spread, hour of day, BTC trend as market context, sentiment score.
- Label: triple barrier (target, stop, time limit) in ATR units.
- Validation: purged and embargoed walk-forward CV; features use only data available at bar close.
- Model registry: versioned files with data hash, metrics and date. Weekly retrain or on drift; a new model is promoted only if it beats the incumbent on validation; every promotion is logged.
- Drift monitor: PSI on key features plus rolling hit rate; on drift fall back to rule-based strategies and alert.
- Decay detector: if live expectancy over the last 50 trades falls below the backtest lower confidence bound, the strategy is auto-disabled and you are alerted.

## 6. Execution layer and paper exchange

**Order lifecycle:** NEW, SUBMITTED, PARTIALLY\_FILLED, FILLED, or CANCELED, REJECTED, EXPIRED. Every order gets an idempotent client order ID so retries cannot duplicate.

**Rules**

- On timeout or unknown response never resend blindly: query status by client ID first.
- Retry only safe errors (network, 429, 5xx) with backoff. Never retry rejects such as insufficient funds or invalid size.
- Token-bucket rate limiter stays under 50% of the published limit.
- Entry then protection: after an entry fills, a protective stop is placed immediately (exchange-side in live where supported, simulated in paper). If the stop cannot be placed within 3 s, the position is flattened.
- Order types: limit entries with timeout then cancel (default); market orders only for exits and emergencies, with a slippage cap; stop-loss and take-profit as stop-limit or OCO where supported.
- Prices and sizes are rounded to tick size, lot size and min notional from exchange rules. Orders below min notional are rejected by the risk engine, not the exchange.
- The ledger uses Decimal and tracks average entry, fees, realized and unrealized PnL, and asserts after every fill that cash plus position value equals equity.

**Reconciliation:** every 30 s compare internal state with exchange balances, open orders and positions. Any mismatch, including a trade you placed manually in the exchange app, raises an alert and moves the bot to L1 until resolved.

**Paper exchange realism (so paper results are not flattering)**

- Market orders walk the real live order book, so size moves the price.
- Fees: 0.1% taker and 0.1% maker by default, configurable per exchange tier.
- Latency: random 100 to 500 ms between decision and fill, filled at the delayed price.
- Limit orders fill only when price trades through the level, not merely touches it.
- Simulated rejects and errors (min notional, lot size, rate limits, random 0.1% API failures) so error handling gets exercised.
- Virtual wallet starts at 1,000 USDT (config), spot long-only.

## 7. Risk, kill switch, loss and profit handling

Defaults below are starting values. Tune them with backtest evidence and never loosen them just to make a strategy look better.

### 7.1 Pre-trade checks (every order must pass all, in this order)

1. Kill switch at L0
2. Mode permissions and ramp multiplier
3. Data fresh for the symbol
4. Symbol enabled
5. Spread under 0.15%
6. Price within 1% of mid (fat-finger check)
7. Notional within min and max
8. Risk per trade at most 0.5% of equity (size = risk amount / stop distance)
9. Per-symbol exposure at most 20% of equity
10. Total exposure at most 60%
11. Correlated bucket at most 40%
12. At most 5 open positions
13. Order size at most 10% of top-10 book depth
14. Daily and weekly loss limits not hit
15. 15-minute cooldown per symbol after a stop-out
16. Orders-per-minute and per-day caps

Every rejection is logged with its reason.

### 7.2 Loss handling

- **Per trade:** stop at 1.5 to 2 ATR set at entry; time stop closes trades that go nowhere after N bars; a stop is never moved further away.
- **Consecutive losses:** 4 in a row halves size; 6 pauses that strategy for 24 hours.
- **Daily loss limit:** -2% of day-start equity stops new entries (existing positions keep their stops); -3% triggers kill switch L2 (flatten).
- **Weekly loss limit:** -5% pauses everything until you review and reset.
- **Max drawdown from peak:** -10% triggers L3 lockdown.
- **Bad fills:** if a stop fills worse than 2x expected slippage, alert and update cost assumptions.
- After any L2 or L3 event the AI layer writes an incident summary and the bot stays down until you reset it.

### 7.3 Profit handling

- **Exits:** take 50% at 1.5R, move the stop to break-even, trail the rest with a 3-ATR chandelier stop.
- **Daily profit lock:** at +3% day gain size drops to 50%; at +5% no new entries. Both configurable; backtest whether they help.
- **Compounding cap:** sizing uses current equity but is capped at 1.5x starting capital so a hot streak does not inflate risk.
- **Tax reserve ledger:** 30% of net realized gains is set aside virtually each day. India taxes crypto gains at a flat 30% with no loss set-off, plus 1% TDS on sales; verify current rules before real use. In live mode the report reminds you to move that amount aside. The bot never moves money.
- Partial exits, trailing stops, locks and reserve accrual all appear in the daily report.

### 7.4 Kill switch

**Levels**

- **L0** normal
- **L1 PAUSE:** no new entries; existing positions managed by their stops
- **L2 FLATTEN:** cancel all orders, close all positions at market, stop trading
- **L3 LOCKDOWN:** L2 plus no restart until you reset with a written reason and a 1-hour cooldown

**Automatic triggers:** daily loss limit; drawdown limit; all feeds stale over 60 s; exchange error rate above 20% over 5 min; reconciliation mismatch; clock drift above 1 s; unknown position or order; unexplained balance drop; 5 rejects in 5 min; strategy exception loop; watchdog heartbeat lost; disk or memory critical.

**Manual triggers:** Telegram /pause /flatten /kill (with confirmation), dashboard button, CLI command, and a KILL file in the project folder checked every loop.

**Design rules**

- Kill state is stored in SQLite, so a restart never clears it.
- The watchdog is a separate process with its own exchange client, so it can flatten even if the main bot hangs. Heartbeat every 2 s.
- In live mode exchange-side stops protect positions even if both processes and your internet die.
- Time-to-flat is measured in drills and must be under 10 s in paper.

## 8. Backtesting and validation of the strategies

**Engine:** event-driven. It replays historical candles (and recorded order books when available) through the same strategy, risk and execution code using the paper adapter, so backtest and paper behave identically.

**Data and splits:** 3 years of 1m data. Train 60%, validation 20%, final holdout 20% touched exactly once at the very end. Include different regimes (2022 bear, 2023 sideways, 2024-25 bull).

**Costs:** fees 0.1% per side, order-book slippage model, latency, plus a post-tax view (30% on net gains, no loss offset, 1% TDS on sells).

**Walk-forward:** rolling 6-month train and 1-month test windows. ML uses purged and embargoed CV.

**Metrics:** total and annualized return, Sharpe, Sortino, Calmar, max drawdown and its duration, win rate, profit factor, expectancy in R, average win and loss, trade count, exposure, turnover, fees paid, and results split by symbol, regime, hour and weekday.

**Robustness tests**

- Parameter sensitivity heatmaps. Good strategies show broad plateaus, not isolated peaks.
- Monte Carlo: shuffle and bootstrap trade order for confidence bands on drawdown and return.
- Cost stress: double fees and slippage; the strategy must still be profitable.
- Period stress: results must not depend on a single bull run.
- Multiple-testing log: record every variant tried and apply a deflated Sharpe check so luck is not mistaken for edge.
- Benchmarks: buy-and-hold BTC and an equal-weight basket.

**Acceptance gates (defaults) before a strategy enters paper-live:** out-of-sample profit factor above 1.3 after costs; Sharpe above 1.0; max drawdown below 15%; at least 200 trades; still profitable at 2x costs; Monte Carlo 95th percentile drawdown below 20%. A strategy that fails is dropped or reworked, never forced through.

**Parity test:** record one live day of data, run it through the backtester and through the live loop in replay mode. Decisions and fills must match exactly.

## 9. AI automation layer

- **LLM daily journal agent:** input is a structured JSON of the day (trades, PnL, risk events, anomalies). It may use only the supplied numbers, makes no predictions and gives no instruction to change risk. Output is 5 to 8 commentary bullets. Every number in the text is cross-checked against the JSON; any mismatch falls back to the template-only report.
- **Safety:** web text such as news headlines is only ever processed by FinBERT or by an LLM with no tool access and no ability to affect trading. This blocks prompt-injection through headlines.
- **Incident explainer:** on any kill switch event, a plain-English note on the cause, what the bot did, and what you should check.
- **Weekly review agent:** strategy decay, parameter drift and cost drift. Suggestions only; you approve, nothing is applied automatically.
- **Telegram command bot:** /status /pnl /positions /report /pause /resume /flatten /kill. Only your whitelisted chat ID is accepted, destructive commands need a confirm step, every command is logged.
- **Cost control:** one LLM call per day plus one per incident. If the LLM is unavailable the template report still goes out.

## 10. Reporting

**Day boundary:** 00:00 UTC (05:30 IST), configurable. The report is sent within 5 minutes after the boundary, and /report gives it on demand.

**Contents**

1. Header: date, mode, kill switch level, start and end equity, net PnL (amount and %)
2. PnL split: realized, unrealized, fees, tax reserve accrued
3. Trade stats: count, wins and losses, win rate, profit factor, average R, best and worst trade
4. Breakdown by strategy and by symbol
5. Risk: max intraday drawdown, peak exposure, limits approached or hit, cooldowns, size reductions
6. Loss and profit handling log: stops hit, partial exits, trailing stops, daily locks
7. System health: uptime, reconnects, data gaps, API errors, rejects, reconciliation result, latency
8. Kill switch events and incident notes
9. Open positions with their stops and targets
10. AI commentary (5 to 8 bullets)
11. Next-day state: active, paused or disabled strategies, anything needing your attention

**Outputs:** Telegram summary (about 20 lines), full HTML report and CSV in reports/YYYY-MM-DD/, a dashboard page, weekly and monthly rollups, and a tax ledger CSV (date, asset, quantity, cost, sale value, fees, gain) to help with Schedule VDA filing.

**Example Telegram summary (illustrative numbers)**

```
DAILY REPORT | 2026-10-28 UTC | PAPER | Kill switch L0
Equity 1,012.40 (start 1,000.00) | Net +12.40 (+1.24%)
Realized +10.10 | Unrealized +2.30 | Fees -3.20 | Tax reserve +3.03
Trades 9 (W6 / L3) | Win 67% | PF 2.1 | Avg R +0.42
Best: SOL long +4.10 (S1) | Worst: ETH long -2.20 (S2 stop)
By strategy: S1 +8.2 | S2 -1.1 | S3 +3.0 | S4 +2.3
Risk: max intraday DD -0.9% | peak exposure 38% | limits hit: none
Events: 1 WS reconnect (4 s) | 0 gaps | 0 rejects | recon OK
Open: BTC long (stop 66,200) | SOL long (trailing)
AI notes: 3 bullets
Tomorrow: all strategies active | S2 on watch (4 losses in 7 days)
```

## 11. Dashboard (Streamlit, localhost only)

- **Live:** equity curve, positions, open orders, latest signals with reasons
- **Risk:** limits used versus allowed, exposure, kill switch state and history
- **Performance:** metrics by strategy, symbol and regime; paper versus backtest comparison
- **Trades:** full ledger with filters and export
- **Health:** feed latency, reconnects, API errors, resource use
- **Controls:** pause, resume, flatten, kill with confirmation (can be set read-only)
- **Reports:** archive of daily, weekly and monthly reports

## 12. Reliability, operations and security

- **Hosting:** a home PC is fine for paper trading. For live, prefer a small VPS (static IP for API whitelisting, no sleep, no power cuts). On a PC: disable sleep, use wired internet, auto-start on boot.
- **Supervision:** Docker Compose with restart: unless-stopped for bot, watchdog and dashboard.
- **Crash recovery:** on start load state from SQLite, reconcile with the exchange, warm up indicators from stored candles, and resume only if reconciliation is clean. Otherwise stay at L1 and alert. In live, open positions are always rediscovered from the exchange, never trusted from local state alone.
- **Logging:** structured JSON, rotated. Every decision has an audit chain: signal ID, risk verdict, order ID, fills, PnL. The events table is append-only.
- **Backups:** daily database and config backup, 30-day retention, restore tested monthly.
- **Monitoring:** CPU, memory, disk, WebSocket latency, event-loop lag, with thresholds. Disk above 80% warns; above 95% triggers L1.
- **Alerts:** INFO, WARN, CRIT levels, deduplicated and rate-limited. A daily heartbeat message means silence signals a problem.
- **Secrets:** .env only (git-ignored), never logged. Trade-only API keys, withdrawals disabled, IP whitelist, separate keys per mode, 2FA on the exchange account, rotate keys quarterly.
- **Network:** no inbound ports, dashboard bound to localhost, Telegram chat ID whitelist, pinned dependencies with pip-audit in CI.
- **Config safety:** pydantic validation with hard bounds (for example risk per trade cannot exceed 2% even if you type more). Every config change is logged, and risk-limit increases only take effect after a 24-hour delay, so you cannot loosen limits in a bad moment after a loss.

## 13. Testing strategy

- **Unit tests:** indicators against reference values, fee and PnL math, every risk check, order state machine, rounding to tick and lot size, Decimal handling.
- **Property tests (hypothesis):** cash plus position value always equals equity; balances never go negative; position size never exceeds caps for random inputs.
- **Integration tests:** paper exchange against scripted order books; full signal-to-fill flow.
- **Replay tests:** same recorded data must produce identical trades every run.
- **Chaos and fault injection:** drop and delay the WebSocket, duplicate ticks, exchange 5xx and 429, partial fills, order timeouts, kill -9 mid-order, clock skew, disk full. Assert the right kill switch level or recovery each time.
- **Kill switch drills:** every trigger tested, time-to-flat measured.
- **CI:** ruff, mypy, pytest on every push; coverage above 80% overall and above 95% for risk and execution modules.
- **Paper soak:** 30 days continuous before any go/no-go decision.

## 14. Paper-to-live go/no-go checklist

All boxes must be ticked, and the result is stored in the database (live mode refuses to start without it).

- [ ] Paper soak of at least 30 days and at least 100 trades per strategy going live
- [ ] Paper metrics within tolerance of backtest on the same period (profit factor within 25%)
- [ ] All acceptance gates passed on the untouched holdout
- [ ] No unresolved critical incident in the last 14 days
- [ ] Kill switch drills passed for every trigger, time-to-flat under 10 s
- [ ] Chaos tests passed; crash recovery tested with open positions
- [ ] Reconciliation clean for 14 days
- [ ] Daily report delivered every day for 30 days
- [ ] API keys: no withdrawal permission, IP whitelist, separate live keys
- [ ] Exchange access from India and its terms verified by you; tax treatment understood; reserve ledger working
- [ ] Capital chosen is money you can afford to lose entirely; max\_capital cap set
- [ ] Order lifecycle tested with tiny real orders: place, partial fill, cancel, stop
- [ ] Ramp plan accepted: 10% size for 7 days, 25% for 14, 50% for 14, then 100%
- [ ] Rollback rule accepted: any critical incident, or 2 consecutive daily-loss-limit days, sends the bot back to paper

A ramp stage also does not advance if live costs (fees plus slippage) exceed the paper assumptions by more than 50%.

## 15. Timeline (about 10 weeks at 10 to 15 hours per week)

- **Week 1:** repo, config, models, logging, CI
- **Week 2:** data layer: streaming, candles, storage, backfill, quality guards
- **Week 3:** paper adapter, order manager, ledger, reconciliation
- **Week 4:** risk engine, kill switch, watchdog
- **Week 5:** backtester, metrics, strategies S1 to S3
- **Week 6:** validation: walk-forward, Monte Carlo, stress tests, parity test
- **Week 7:** ML signal and sentiment overlay
- **Week 8:** reporting, Telegram bot, LLM journal, dashboard
- **Week 9:** chaos tests, kill drills, start the 30-day paper soak
- **Week 10 onward:** soak, fixes, go/no-go review, optional live ramp; NSE stocks afterwards on the same engine

Each week ends with passing tests and a short demo.

## 16. Stress test of the plan (failure scenario walk-through)

For each scenario: how the plan detects it and what happens.

1. **Internet drops with positions open:** feeds go stale, L1. Exchange-side stops protect live positions. On return, reconcile, then resume.
2. **PC sleeps, crashes or loses power:** heartbeat lost; stops on the exchange protect live positions; startup recovery reconciles before trading.
3. **Flash crash of 15% in minutes:** stops fire, spread and price checks block new entries, daily loss limit escalates to L2 if reached, slippage is logged.
4. **Exchange outage or maintenance:** error rate trigger gives L1; backoff prevents retry storms.
5. **Order timeout with unknown state:** status queried by client ID, no duplicate order.
6. **Strategy bug sends a huge order:** fat-finger check, max notional and exposure caps veto it.
7. **Crash mid-order:** startup reconciliation finds the stray order or position and cancels or adopts it.
8. **Protective stop cannot be placed:** position flattened within 3 s.
9. **You trade manually in the exchange app:** reconciliation mismatch, L1, alert.
10. **API key leak:** no withdrawal permission, IP whitelist, quick rotation.
11. **Clock drift:** detected by the NTP check, trading aborted.
12. **LLM invents numbers in the report:** numbers cross-checked, fallback to template report.
13. **Model drift or strategy decay:** drift monitor falls back to rules; decay detector disables the strategy.
14. **Overfitting:** holdout, deflated Sharpe, cost stress and the paper gate.
15. **Coin delisted or trading halted:** stale feed or changed market rules pause the symbol and flag positions for manual action.
16. **Report or Telegram fails:** report always saved to disk, retries sent, missing daily heartbeat alerts you.
17. **Disk full:** warning at 80%, L1 at 95%.
18. **Tax or record errors:** automatic trade ledger CSV and reserve ledger.
19. **Live fills worse than paper:** paper-versus-live cost tracking blocks ramp advancement.
20. **You raise limits after a loss:** hard config bounds, logged changes, 24-hour delay on loosening.

## 17. Final recheck

### 17.1 Requirement verification

- R1 Real-time multi-coin data: covered, sec 4 (5 coins, WebSocket, backfill, stale-feed guards)
- R2 Paper trading on live prices: covered, sec 6 (order book fills, fees, latency, rejects)
- R3 Easy paper-to-real switch: covered, sec 3 and 14 (one mode setting plus 7 guards and ramp)
- R4 Kill switch: covered, sec 7.4 (4 levels, 12 automatic triggers, 4 manual routes, persistent, independent watchdog)
- R5 Loss handling: covered, sec 7.2 (per trade, streak, daily, weekly, drawdown)
- R6 Profit handling: covered, sec 7.3 (partials, trailing, locks, compounding cap, tax reserve)
- R7 Daily summary report: covered, sec 10 (11 sections, Telegram plus HTML and CSV, example)
- R8 Multi-strategy and multi-coin: covered, sec 5
- R9 AI automation: covered, sec 5 and 9
- R10 Backtesting: covered, sec 8
- R11 Reliability: covered, sec 12
- R12 Dashboard: covered, sec 11
- R13 Testing: covered, sec 13
- R14 Security: covered, sec 12
- R15 Tax and records: covered, sec 7.3, 10, 14
- R16 Timeline: covered, sec 15
- R17 Stress test: covered, sec 16

### 17.2 Consistency and sanity checks on the numbers

- **Loss limits vs position limits:** 5 open positions at 0.5% risk each means about 2.5% loss if all stop out together. That is above the 2% daily limit (new entries stop) and below the 3% flatten level, so the escalation order makes sense. Crypto coins are highly correlated, which is why the correlated bucket cap exists.
- **Caps will often bind:** with a tight stop, risk-based sizing can exceed the 20% per-symbol cap. Size is the smaller of the two, so actual risk per trade is often below 0.5%. That is intended.
- **Costs vs timeframe:** round-trip fees are about 0.2% plus slippage. Signals on 1m bars would be eaten by costs. Default signal timeframes should be 15m and 1h; 1m is for data, stop monitoring and execution. The backtest must confirm any shorter timeframe survives 2x costs.
- **Small capital:** at 1,000 USDT, minimum order sizes on the exchange are far below your position sizes, so they should not block trades. The risk engine still checks them from live market rules.
- **Tax drag:** the 30% tax with no loss set-off means post-tax returns are reported next to pre-tax everywhere, and gates are judged on after-cost numbers.

### 17.3 What this recheck can and cannot show

A plan cannot be backtested the way a strategy can. What was done here is a requirement cross-check, a numeric consistency check and a 20-scenario failure walk-through. The real backtests happen in section 8 once the data pipeline exists. Nothing in this plan guarantees profit, and the most likely outcome of honest validation is that some strategies are rejected. The system, the validation process and the engineering are the deliverable.

### 17.4 Decisions needed from you before coding

1. Which exchange's public data to use (and confirm it is accessible and permitted for you in India)
2. Starting virtual capital (default 1,000 USDT)
3. Final coin list (default BTC, ETH, SOL, BNB, XRP)
4. Hosting: your PC for now, or a VPS before going live
5. LLM provider and API key for the journal, and a Telegram bot token

**Next step:** Weeks 1 and 2 of the timeline (repo skeleton, config, models, data streaming and storage).

## 18. Additions after review: gaps closed

Nine gaps found after the first full pass. They extend the requirements list:

- R19 Order book recording (18.1)
- R20 Counterparty and stablecoin risk (18.2)
- R21 Recruiter-facing deliverables (18.3)
- R22 Emergency runbook (18.4)
- R23 Safe deployment and rollback (18.5)
- R24 Experiment tracking (18.6)
- R25 Running costs (18.7)
- R26 NSE-ready design (18.8)
- R27 Bear-market behavior (18.9)

### 18.1 Order book recording (start in Week 2)

**Why:** exchanges do not give historical order books for free, so backtest slippage would otherwise rest on a guess. Recording your own live books from day 1 gives you real data to calibrate and validate the slippage model.

**What to record**

- Top 20 levels per side for every traded symbol, snapshot every 1 second, plus best bid/ask and spread.
- Stored as Parquet (zstd compression), partitioned by symbol and date. Expect roughly 10 to 30 MB per day for 5 coins; measure it in the first week and set retention from the real number.
- Retention: raw snapshots 90 days, then downsample to 5-second snapshots and keep.

**How it is used**

1. Calibrate an empirical slippage curve: expected slippage as a function of order size, volatility and spread.
2. Compare the paper exchange fills against what the curve predicts, and flag drift.
3. Replay recorded books in the backtester for periods that have them.

**Until 90 days exist:** use a conservative model (fixed 0.05% plus a volatility-scaled term) and label every result computed with it as slippage-unvalidated.

### 18.2 Counterparty and stablecoin risk

**Risks:** exchange hack or insolvency, withdrawal freeze, account or KYC freeze, regulatory block in India, stablecoin losing its peg, API key compromise.

**Rules**

1. Keep only trading capital on the exchange. The bot has a hard max\_capital cap, and you sweep profits off the exchange manually on a schedule (suggested weekly in live).
2. Never deposit more than you can afford to lose entirely.
3. Prefer an exchange that publishes proof of reserves, has a clear compliance record for Indian users, and has a public status page. Verify this yourself before choosing.
4. **Depeg monitor:** track a stablecoin cross price (for example USDC/USDT) every 10 seconds. A deviation above 0.5% raises a WARN and above 1% triggers L1. Reports show the quote currency used.
5. **Exchange status monitor:** poll the status page or announcements feed; pause entries before announced maintenance windows.
6. Store 2FA backup codes and recovery details offline, in a place that is not on the trading PC.
7. Decide the quote currency deliberately (USDT, USDC or INR pairs on an Indian exchange). Each has different fee, tax-record and depeg implications, so record the decision and reason in the repo.

### 18.3 Recruiter-facing deliverables (dedicated Week 11)

**Public repository**

- README with a one-paragraph problem statement, architecture diagram, feature list, and a one-command demo (docker compose up in paper mode with sample data).
- No secrets ever: gitleaks in CI, .env.example only, sample dataset included.
- Clear docs: setup, config reference, risk model, how to run backtests, how to read reports.

**Results write-up (blog post or PDF)**

- Methodology, data splits, cost model, validation tests, post-tax results, and a section called What did not work. Include honest limitations.
- Every number comes from real runs. Do not invent or round up results.

**Demo video (about 2 minutes)**

1. 0:00 problem and goal (15 s)
2. 0:15 architecture in one diagram (20 s)
3. 0:35 live dashboard with paper trades (30 s)
4. 1:05 a risk event: kill switch drill (25 s)
5. 1:30 daily report and AI journal (20 s)
6. 1:50 validation results and what you learned (10 s)

**Portfolio presence**

- Read-only public dashboard on your portfolio, with delayed data, no controls and no account details.
- Disclaimer: educational project, not investment advice, no signals offered. Do not sell or share signals publicly without checking SEBI registration rules.

**Resume and interview material**

- Resume bullets built from your real measured results (placeholders until you have them): system scope, validation rigor, reliability, AI components.
- Prepared talking points: one code path for backtest, paper and live; the risk engine and kill switch design; why strategies were rejected; deflated Sharpe and cost stress; what you would improve next.

### 18.4 Emergency runbook (one page; keep a copy on your phone)

**If something looks wrong, in this order**

1. Stop adding risk. Do not open trades manually.
2. Check state: Telegram /status, then the dashboard Risk page, then the last 50 log lines.
3. If the bot responds: send /flatten.
4. If it does not respond: create the KILL file or run the CLI kill command. Note that stopping the container does not cancel orders or close positions.
5. Open the exchange app or website: cancel all open orders, check balances and positions, close positions manually if needed.
6. If key compromise is suspected: revoke the API key immediately, then change the exchange password and 2FA.
7. Write the incident log entry (template below).
8. Do not restart until the cause is understood and reconciliation is clean.

**Quick diagnosis checklist:** exchange status page; your internet (ping and speed); system clock sync; disk space; CPU and memory; last deployment time; last config change.

**Incident log template:** time (UTC and IST), mode, what you saw, trigger, bot actions, your actions, PnL impact, root cause, fix, test added to prevent recurrence.

**Keep in the runbook:** exchange support link, status page link, where 2FA backup codes are stored, the exact CLI commands, and the Telegram commands.

**Fire drill:** rehearse this runbook once a month in paper mode, and once before going live. A runbook never practiced is not reliable.

### 18.5 Safe deployment and rollback

**Release discipline**

- Protected main branch; CI (lint, types, tests, replay and chaos subsets) must pass.
- Version tags and a changelog; Docker images tagged by version; config files versioned with the code.

**Deploying while positions are open (live)**

1. Announce on Telegram.
2. Send /pause (L1). Cancel pending entry orders; leave protective exchange-side stops in place.
3. Back up the database.
4. Deploy the new container.
5. On startup: reconcile with the exchange, run preflight checks.
6. Smoke test: replay the last hour of recorded data and confirm sensible decisions.
7. Send /resume (back to L0).
8. Watch closely for 30 minutes with alerts at WARN level or above.

**Rollback:** keep the previous image tag. Database migrations follow expand-then-contract, so the old version can still read the new schema. If reconciliation mismatches or the smoke test fails, roll back and stay at L1.

**Canary rule:** any strategy or risk change runs in shadow (paper) mode alongside live for at least 3 days before promotion.

**Timing:** avoid deploying during high-volatility events or major scheduled news. In paper mode, deploy any time.

### 18.6 Experiment tracking

- Every backtest run is auto-logged and cannot execute without logging. Use MLflow with a local file backend, or an experiments table in SQLite.
- Fields: run ID, git commit, data version hash, strategy and parameters, cost model version, split, seed, metrics, artifacts (equity curve, trades CSV), timestamp, notes.
- The count of variants tried per strategy feeds the deflated Sharpe calculation, so skipping logs would weaken the validation.
- **Holdout lock:** the final holdout can be run once per strategy. The run is flagged, and a second access requires an explicit override that is recorded and noted in the write-up.
- Fixed random seeds, a lockfile for dependencies, and data versioning (hash manifest or DVC) so any result can be reproduced.
- Dashboard Experiments page to compare runs side by side.

### 18.7 Running costs (estimates; verify before committing)

- **Exchange public data:** free.
- **VPS (live only):** roughly 5 to 10 USD per month for a small instance.
- **LLM API:** one call per day plus incidents. Likely cents per day, but set a monthly budget cap in code and a template fallback.
- **News data:** free tiers or RSS to start; paid feeds only if clearly useful.
- **Telegram, GitHub Actions on a public repo, Vercel hobby tier:** free.
- **Backups:** small storage cost.
- **Rough total:** about 0 to 5 USD per month for paper on your own PC; about 10 to 25 USD per month for live on a VPS.
- **Trading costs (separate):** exchange fees (0.1% default assumption), 18% GST on exchange platform fees, 1% TDS on sales, and the 30% tax on gains with no loss set-off. Verify current rules with a tax professional before real money.

### 18.8 NSE-ready design (build the seams now)

Build these abstractions in the first weeks so adding stocks later is an adapter job, not a rewrite.

**Abstractions to add now**

- `MarketCalendar`: crypto implements always-open; NSE will implement sessions (09:15 to 15:30 IST), holidays and pre-open.
- `CostModel` per venue: crypto uses percentage fees; NSE needs brokerage, STT, exchange charges, GST, stamp duty and SEBI fees.
- `Instrument` model with tick size, lot or quantity step, min quantity, price bands and product type.
- `SessionManager`: handles authentication, daily session expiry and re-login.
- Risk engine hook for market-hours gating and a mandatory square-off scheduler.

**NSE and SEBI items to design for (verify against your broker docs and current SEBI circulars)**

- Intraday positions must be squared off before close, at a time set by the broker.
- API access needs OAuth plus 2FA, sessions close at end of day, and brokers require a whitelisted static IP, so the daily login flow cannot be fully unattended.
- Order-rate limit for personal API strategies (10 orders per second under a generic algo ID) and possible strategy ID tagging.
- Price bands and circuit limits, tick and lot sizes, T+1 settlement, and short-selling restrictions in delivery.
- Different product types (intraday versus delivery) with different margin and tax treatment.

### 18.9 Bear markets and long-only behavior

- A long-only spot system will mostly sit in cash during sustained downtrends. That is acceptable and by design, but it means returns come only from uptrends and ranges.
- Reports include time in market and compare performance to buy-and-hold, because in bear periods being in cash is itself an edge.
- The backtest must include the 2022 bear market, and results must be shown separately for it.
- **Later extension (separate module, separate go/no-go):** shorting via futures. This adds leverage and liquidation risk, funding rates and margin. It would need new risk rules (leverage cap of 1x to 2x, liquidation distance checks, funding cost model) and availability for Indian users must be verified first.
- Recommendation: ship long-only first, and consider shorting only after at least 3 months of stable operation.

### 18.10 Plan changes caused by these additions

**Timeline updates**

- Week 2: add order book recording to the data layer
- Week 4: add depeg and exchange status monitors to the risk and kill switch work
- Week 5: add experiment tracking before any backtest runs
- Week 7 to 8: build the NSE-ready abstractions (calendar, cost model, instrument, session manager) while writing the adapters
- Week 9: write the emergency runbook and deployment procedure, and run the first fire drill
- Week 11: recruiter-facing deliverables

**Go/no-go checklist additions (section 14)**

- [ ] Runbook fire drill completed in the last 30 days
- [ ] Deployment and rollback procedure rehearsed once in paper mode
- [ ] Depeg and exchange status monitors active
- [ ] Counterparty rules accepted: capital cap set, sweep schedule decided, quote currency decided
- [ ] Slippage model calibrated against recorded books, or live results explicitly marked as unvalidated

## 19. Advanced signal engine (hidden-logic layer)

This extends the ML layer (section 5) and the validation process (section 8). It adds requirement R28: a research-grade signal engine that is validated, explainable and fully controlled by the risk engine.

### 19.1 Signal library

**Interface:** every signal implements compute(features) and returns a score in \[-1, 1\] (long-only trading uses \[0, 1\]) with timestamp. Signals use only data available at bar close. Each one is registered with metadata: name, family, inputs, lookback, version.

**Families (start with 30 to 60 signals total)**

- **Trend:** EMA slope, Donchian position, ADX-weighted direction
- **Mean reversion:** RSI, Bollinger z-score, VWAP distance
- **Volatility:** ATR percentile, volatility of volatility, compression and expansion
- **Volume and flow:** volume z-score, OBV slope, taker buy ratio
- **Order book:** imbalance over top 5 and 10 levels, spread, depth ratio, microprice offset
- **Derivatives (if public data is available to you):** funding rate z-score, open interest change
- **Cross-asset:** ETH/BTC ratio, correlation shifts, BTC trend as context
- **Time:** hour of day, weekend flag
- **Sentiment:** FinBERT score, headline volume

**Per-signal evaluation (before a signal may enter any model)**

- Information coefficient (rank correlation with forward returns at 1, 4 and 24 bars)
- Hit rate, turnover, decay curve across horizons
- Stability across periods and regimes
- Cost-adjusted standalone PnL
- Keep a signal only if its IC is stable, positive and survives costs. Drop signals with IC near zero, and drop one of any pair with correlation above 0.8.

**Hygiene rules:** rolling normalization only (never full-history statistics), explicit NaN handling, versioned definitions, no future data.

### 19.2 Ensemble and stacking

**Complexity ladder (each level must earn promotion over the one below)**

1. **Baseline:** equal-weight or IC-weighted average of the top signals
2. **Regularized linear stack:** ridge or logistic regression
3. **Gradient boosting:** LightGBM or XGBoost with shallow trees, strong regularization, early stopping, and monotonic constraints where the sign is known
4. **Neural or sequence models:** only if they beat level 3 net of costs (unlikely to be needed)

**Promotion rule:** a higher level is adopted only if it beats the lower one by a clear margin (for example 10% higher net expectancy) out-of-sample across at least 3 walk-forward windows.

**Training**

- Purged and embargoed walk-forward; weekly retrain on a rolling window.
- Hyperparameter search with a capped number of trials, all logged.
- Probabilities calibrated (isotonic or Platt scaling).
- The decision threshold is chosen to maximize post-cost expectancy on validation data, not accuracy.
- Average a few seeds or models for stability.

### 19.3 Meta-labeling

**Idea:** the rule-based strategies (S1 to S3) propose candidate trades with a side. A second model predicts whether each candidate will hit its target before its stop, and the trade is taken or skipped accordingly.

**Pipeline**

1. Generate candidate trades from the primary strategies on historical data.
2. Label each with the triple barrier outcome (target, stop, time limit in ATR units).
3. Features: signal values at entry, regime, spread, volatility, recent performance of the primary strategy, time features.
4. Train the meta-model with purged CV, using sample weights based on label uniqueness (overlapping trades would otherwise leak information).
5. In use: take the trade if probability exceeds the threshold; size may scale with probability, capped by the risk engine and never above base sizing.

**Needs:** at least about 500 candidate trades; pool across coins if one coin has too few.

**Acceptance:** compare against the primary strategy alone on net expectancy, Sharpe, drawdown and trade count. It must improve out-of-sample, and the report shows the precision versus trades-skipped trade-off.

### 19.4 Alternative data

- **Funding rates and open interest:** from public endpoints, as features only; check availability and legality for you first.
- **Own order book data:** from the recorder in 18.1.
- **News sentiment:** RSS or news API, deduplicated, scored by FinBERT; rolling sentiment and headline counts. Store publish time and retrieval time separately so tests never use news before it was actually available.
- **On-chain (optional):** exchange net flows and active addresses from free sources, treated as slow daily signals.
- **Governance for every source:** quality checks, an availability monitor, a defined behavior when stale (the signal goes missing and the model must handle that), and a terms-of-use check.
- Web text is processed only by FinBERT or by an LLM with no tools and no influence over trading.

### 19.5 Automated research loop

- A scheduled job (weekly, or nightly) runs on recorded data only and never touches the live system.
- It generates candidate experiments from a configured search space (feature subsets, windows, thresholds, hyperparameters), runs walk-forward tests, logs everything to the experiment tracker (18.6), applies deflated Sharpe using the true trial count, applies the acceptance gates, and sends you a ranked report.
- **Trial budget:** a weekly cap per strategy family (for example 200), because every trial raises the odds of a lucky result.
- **No auto-promotion:** a candidate goes to shadow mode only after you approve it.
- **Pre-registration:** each hypothesis is written to the log before testing with its mechanism and expected sign. An LLM may help brainstorm hypotheses, but the test rules do not change.
- The final holdout stays locked.

### 19.6 Shadow mode (champion and challenger)

- The shadow runner consumes live data and produces signals and simulated trades in a separate paper ledger, passing through the same risk engine. It sends nothing to a live exchange.
- **Minimum:** 21 days and 50 trades (more for slow strategies).
- **Compare with** backtest expectations and with the incumbent: expectancy, hit rate, slippage, trade overlap and correlation. A divergence alarm fires if live shadow results drift far from expectation.
- **Promotion:** only through the go/no-go checklist and the capital ramp (10%, 25%, 50%, 100%). Demotion is automatic through the decay detector (section 5).

### 19.7 Explainability and leakage checks

- **SHAP:** global importance and its stability over time, plus a local explanation per trade (top 5 contributions) stored with the signal. The dashboard Trades page and the daily report show why each trade was taken.
- **Plausibility checks:** the sign and size of key effects must make sense. Flag models that lean on suspicious features such as time index, symbol ID or anything that could carry future information.
- **Leakage detectors:** shuffled-label test (performance must collapse), time-shift test, and a flag if a single feature carries over 40% of importance.
- **Model card per version:** data range, features, metrics, known weaknesses, approval record.

### 19.8 Non-negotiable guardrails

- Models output signals and probabilities only. They never call the exchange and never change risk limits or config.
- The risk engine and kill switch live in their own package that does not import anything from the AI code.
- **Fail-safe:** a model error, NaN, stale feature or drift alarm results in no trade, with fallback to rule-based strategies or flat.
- Position size comes from the risk engine only. Model confidence may scale size only within a cap.
- Every model passes the same acceptance gates, holdout lock, paper soak and go/no-go checklist as the rule-based strategies.
- **Complexity budget:** each added layer must beat the simpler version net of costs, or it is removed.

### 19.9 What stays private

- **Public repo:** architecture, infrastructure, risk engine, backtester, paper exchange, reporting, dashboards, a simple demonstration strategy set, and the results write-up with methodology.
- **Private repo:** the proprietary feature set, trained model weights, tuned parameters and research search spaces.
- Label any model in the public repo as demonstration only, and state in the README that live parameters are private. Do not publish weights trained on licensed data.
- Using hidden logic on your own account is fine. Selling or sharing signals publicly brings in SEBI rules, so avoid that unless you have checked them.

### 19.10 Plan changes caused by this section

**Timeline**

- Week 5: signal interface, registry and per-signal evaluation alongside S1 to S3
- Week 7: ensemble, meta-labeling and SHAP (this expands the ML signal work)
- Week 8: research loop job and an Experiments page
- Week 9: shadow runner; extend chaos tests to model failure, NaN output and stale features

**Extra stress scenarios (extending section 16)**

- **Scenario 21, model outputs NaN or crashes:** no trade, fallback strategy or flat, alert.
- **Scenario 22, look-ahead leakage:** shuffled-label and time-shift tests catch it before any capital is used.
- **Scenario 23, research loop finds a lucky result:** trial budget, deflated Sharpe and shadow mode filter it.
- **Scenario 24, regime change breaks the ensemble:** drift monitor and decay detector disable it and fall back.

**Go/no-go checklist additions (section 14)**

- [ ] Model card complete for every model going live
- [ ] Leakage tests passed
- [ ] Shadow mode of at least 21 days and 50 trades
- [ ] Fail-safe behavior tested (NaN, stale features, model crash)
- [ ] Added complexity justified against the simpler baseline

## 20. Self-healing system

Sections 4, 6, 7 and 12 already contain pieces of recovery (reconnects, reconciliation, restart, kill switch). This section turns them into one designed system and adds requirement R29: the system detects its own faults, repairs what is safe to repair, verifies the repair, and escalates to you when it cannot.

### 20.1 Principles

1. **Heal infrastructure automatically, heal trading decisions conservatively.** Reconnecting a feed is automatic. Changing risk limits or strategy logic is never automatic.
2. **Healing never adds risk.** While healing, the only trading actions allowed are cancelling orders, reducing or closing positions, and placing protective stops.
3. **Exchange state is the source of truth.** After any fault, rebuild local state from the exchange and the event log, never the other way around.
4. **Verify before resuming.** A repair counts only after health checks pass.
5. **Bounded and logged.** Every heal attempt is rate-limited, recorded, and escalates after repeated failure.

### 20.2 Health model

Each component reports three states: HEALTHY, DEGRADED, FAILED. Checks cover liveness (is it running), readiness (can it do its job) and correctness (is its output sane).

- **Data feed:** tick age, gaps, duplicate rate
- **Candle builder:** difference versus exchange klines
- **Strategy workers:** heartbeat, last signal time, exception count
- **Order manager:** orders stuck in SUBMITTED or PARTIAL beyond a time limit
- **Exchange adapter:** error rate, latency, rate-limit hits
- **Database:** write latency, disk space, WAL size
- **AI models:** NaN rate, feature drift, prediction latency
- **Alerting and reporting:** delivery success

A health score per component and overall is shown on the dashboard Health page and in the daily report.

### 20.3 Heal playbook (failure, automatic action, verification, escalation)

- **WebSocket drop or stale feed:** reconnect with backoff, resubscribe, fill the gap through REST. Verify candle continuity. After 5 failures in 10 minutes: fall back to REST polling (DEGRADED), then L1.
- **API errors or 429:** back off, lower request rate, open a circuit breaker for 60 s. Verify successful calls. Escalate to L1 if errors persist.
- **Stuck order:** query status by client ID, cancel if needed, reconcile. Unknown outcome: L1.
- **Strategy worker exception or hang:** restart only that worker, re-warm its indicators from stored candles. After 3 restarts in an hour, disable that strategy and alert. Open positions stay protected by their stops.
- **Candle mismatch:** repair from REST data and mark the repaired window.
- **Process crash:** container restarts, startup recovery runs, trading resumes only after reconciliation is clean.
- **Hung process (heartbeat lost, still running):** the watchdog kills and restarts it. In live mode, if any position lacks a protective stop, the watchdog attempts to flatten first.
- **Database lock or corruption:** retry and checkpoint on lock. On corruption: restore the latest backup, replay the event log, then reconcile with the exchange.
- **Disk filling up:** purge and compress old raw ticks and logs per retention rules. If still above 95%: L1.
- **Memory growth:** controlled restart at a safe moment (no orders in flight).
- **Clock drift:** force an NTP resync. If drift remains above 1 s: L1.
- **Model failure or drift:** roll back to the previous model version in the registry, then to rule-based strategies, then to flat. Start a retrain in the research environment; the new model goes to shadow mode and is never hot-swapped into live.
- **Feature pipeline anomaly (NaN spike):** quarantine that signal; the ensemble continues with the remaining signals only if it was trained to handle missing inputs, otherwise the strategy goes flat.
- **Strategy decay:** auto-disable and send a candidate for review.
- **Alert or report delivery failure:** retry queue, then an alternate channel, with the report always saved to disk.
- **Invalid config on reload:** reject it and keep the last known good config.
- **Failed deployment:** automatic rollback to the previous image if health checks fail within 5 minutes.
- **Exchange outage:** pause, poll the status page with backoff, resume only after health checks and reconciliation pass.

### 20.4 Escalation ladder and guardrails

**Ladder:** retry, restart the component, fallback mode, degraded operation, L1 pause, L2 flatten, L3 human.

- **Restart limits:** at most 3 restarts per component per hour.
- **Flapping detector:** more than 5 state changes in 10 minutes holds the system in L1.
- **Post-heal checklist before returning to L0:** reconciliation clean, feeds fresh, candles continuous, indicators warmed up, clock in sync, no unprotected positions.
- **Auto-resume:** only from L1 caused by transient infrastructure issues (feed, API, network), after at least 10 minutes of sustained health. L2 and L3 never auto-resume.
- **Audit:** every heal action is logged with what happened, why, outcome and time taken, and appears in the daily report under System health and healing.

### 20.5 Supervision architecture (layers)

1. **In-process supervisor tree:** each component is an asyncio task with its own restart policy. A failure restarts only that component.
2. **External watchdog process:** monitors heartbeats and can restart or flatten independently.
3. **Container restart policy:** Docker restarts crashed containers, and health checks gate traffic.
4. **Dead man's switch (live):** the bot pings an external uptime service every minute. If pings stop, you are alerted on a channel independent of Telegram, such as email or SMS.
5. **Independent alert channel:** a second path to reach you if Telegram itself is down.

### 20.6 Testing and measuring self-healing

- **One test per playbook row:** inject the fault, assert the heal action, verify end state.
- **MTTR targets (mean time to recovery):** feed reconnect under 10 s, worker restart under 5 s, full process restart plus reconciliation under 60 s.
- **Monthly game day in paper mode:** inject random faults. Pass criteria: no unprotected position, no duplicate orders, state consistent after recovery, correct escalation when healing fails.
- **Reported metrics:** uptime, MTTR per component, heal counts, escalations, flapping events.

### 20.7 What self-healing cannot fix

- A strategy whose edge has gone: it can be disabled automatically, but fixing or replacing it needs your research.
- Deterministic bugs: restart loops stop after 3 attempts and the component is disabled for review.
- Exchange insolvency, regulatory blocks or key compromise: these need the runbook (18.4).
- Wrong assumptions in the design itself: caught only by validation, shadow mode and your review.

### 20.8 Plan changes caused by this section

**Timeline**

- Week 4: supervisor tree, circuit breakers, flapping detector, watchdog restart logic
- Week 8: health model, dashboard Health page, report section
- Week 9: playbook tests, MTTR measurement, first game day, dead man's switch and independent alert channel

**Extra stress scenarios (extending section 16)**

- **Scenario 25, worker restart loop:** capped at 3 restarts, strategy disabled, alert sent.
- **Scenario 26, database corruption:** restore backup, replay event log, reconcile with the exchange.
- **Scenario 27, Telegram outage:** alternate channel and the dead man's switch still reach you.
- **Scenario 28, bad deployment:** health checks fail, automatic rollback within 5 minutes.

**Go/no-go checklist additions (section 14)**

- [ ] Every heal playbook test passes
- [ ] MTTR within targets
- [ ] One successful game day in the last 30 days
- [ ] Flapping detector and restart limits tested
- [ ] Dead man's switch and independent alert channel verified
