# Equity Dilution Calculator

A strategic tool for founders to model cap table dilution across fundraising scenarios.

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

Or with a virtual environment (recommended):

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### 2. Run the app

```bash
streamlit run app.py
```

The app opens automatically at `http://localhost:8501`.

---

## Features

| Tab | What it does |
|-----|--------------|
| **📋 Current Cap Table** | View and edit shareholders + pie chart of current ownership |
| **🎯 Scenario Builder** | Define up to 5 independent fundraising scenarios |
| **📊 Scenario Comparison** | Side-by-side table + grouped bar + pie charts |
| **🔄 Multi-Round Dilution** | Sequential Seed → A → B waterfall with founder line chart |

### Sidebar
- Edit the cap table inline (add/remove rows dynamically)
- Shares are recalculated automatically – you only enter raw share counts

---

## Equity Maths

Standard startup dilution logic used throughout:

```
post_money      = pre_money + investment
investor_pct    = investment / post_money
investor_shares = existing_shares × investor_pct / (1 − investor_pct)
```

**Option pool shuffle** (when a new pool is requested):
The option pool is expanded *before* the investor comes in, so founders –
not the new investors – bear the cost of the pool increase.

```
new_pool_shares / (old_total + new_pool_shares) = target_pool_pct
```

---

## Project Structure

```
EQUITYCALC/
├── app.py            # Streamlit UI (all tabs, charts, session state)
├── equity_calc.py    # Pure calculation functions (no UI)
├── requirements.txt
└── README.md
```

### Extending the tool

- **Add a new calculation** → edit `equity_calc.py` only
- **Add a new chart / section** → edit `app.py` only
- **SAFEs / convertible notes / pro-rata** → add functions to `equity_calc.py`
  and a new tab in `app.py`

---

## Example Data (preloaded)

| Shareholder | Shares      | % |
|-------------|-------------|---|
| Founder 1   | 4,000,000   | 40% |
| Founder 2   | 3,000,000   | 30% |
| Yannick     | 1,000,000   | 10% |
| Louisa      | 500,000     | 5%  |
| Option Pool | 1,500,000   | 15% |

Preloaded scenarios:

- **Angel Round** – $1M at $5M pre-money
- **Seed Round** – $2M at $10M pre-money
- **Seed + Pool Expand** – $3M at $10M pre-money + 10% additional option pool

---

## Disclaimer

This tool is for **strategic decision support** only. It is not accounting
software, not legal advice, and does not model all real-world cap table
complexities (SAFEs, convertible notes, anti-dilution provisions, etc.).
Always verify with a qualified lawyer and accountant before making decisions.
