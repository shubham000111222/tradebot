# Implementation status

Verified checkpoints are pushed to GitHub with tags.

## Implemented

- Core UTC/Decimal domain models and guarded paper configuration
- Tick quality checks, candle building, order-book models, and optional Parquet/DuckDB storage
- Paper execution, idempotent orders, SQLite WAL ledger, reconciliation
- Persistent L0-L3 kill switch and ordered risk vetoes
- EMA trend, mean reversion, Donchian breakout, and candle backtesting
- Metrics, walk-forward windows, Monte Carlo stress, acceptance gates, experiment holdout lock
- Fail-safe demonstration ML model, feature vector, sentiment overlay, PSI drift monitor
- Daily text/HTML/CSV reports, FIFO tax ledger, venue/NSE-ready abstractions
- Watchdog health, restart limits, flapping detector, KILL-file controller
- Deterministic paper demo and read-only local dashboard

## Pending before any real-money consideration

- Exchange WebSocket/REST adapter and historical backfill
- Realistic latency/order-book paper fills beyond the deterministic demo
- Full live preflight gates, API permission verification, and ramp controls
- Telegram control/alerts and optional LLM journal
- 30-day paper soak, chaos drills, kill-switch timing drills, and measured validation on real data
- Exchange, India access, tax, stablecoin, and counterparty review by the operator

No live trading is enabled by this repository state.
