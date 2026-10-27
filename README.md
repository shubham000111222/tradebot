# Tradebot

Paper-first, long-only crypto trading system built around one strategy, risk and execution code path.

The project is being implemented incrementally from the [full build plan](Crypto%20Trading%20System%20Full%20Build%20Plan%20%283%29.md). The current milestone is Week 1: configuration, core domain models, money handling, logging, and CI scaffolding.

## Quick start

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
python -m pip install -e ".[dev]"
tradebot --config config/settings.yaml
tradebot --config config/settings.yaml --demo
pytest
```

The default configuration is paper mode with 1,000 USDT and the five initial symbols from the plan. Live mode is deliberately guarded and cannot be enabled by changing the YAML file alone.

Install the optional Parquet/DuckDB storage dependencies when your Python platform provides them:

```bash
python -m pip install -e ".[dev,storage]"
```

## Repository layout

```text
config/                 runtime configuration
src/tradebot/core/      shared domain models and money/time primitives
tests/                   automated checks
data/ logs/ reports/     runtime output (ignored by git)
```

No exchange credentials are required for the Week 1 demo.

The read-only dashboard is optional:

```bash
python -m pip install -e ".[dashboard]"
streamlit run dashboard/app.py
```
