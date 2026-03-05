# Equity Dilution Calculator – Internal User Guide

> **Live app:** [nm-equitycalc.streamlit.app](https://nm-equitycalc.streamlit.app)
> For strategic decision support only. Not legal or accounting advice.

---

## What it does

Models how a funding round dilutes the founding team's equity. Enter your current shareholders, define one or more fundraising scenarios, and instantly see how ownership percentages change.

---

## Quick Start

### 1. Set up your cap table
The **sidebar** (left panel) holds the cap table. It comes preloaded with example data — edit it to match your actual shareholders:

- Click any cell to edit a value
- Click **＋** at the bottom to add a new row
- Click the **🗑** icon on a row to delete it
- Only enter **Shares** (raw share count) — percentages calculate automatically

### 2. Model a funding round
Go to the **🎯 Scenario Builder** tab:

| Field | What to enter |
|-------|--------------|
| Name | A label, e.g. "Seed Round" |
| Pre-Money Valuation | Company value before investment |
| Investment | Amount being raised |
| Option Pool (%) | Additional pool to create before the round (enter 0 if none) |

Preview metrics (post-money, investor %, dilution) appear instantly below each scenario.

### 3. Compare scenarios
The **📊 Scenario Comparison** tab shows all scenarios side by side:

- A table with each shareholder's % across all scenarios
- A grouped bar chart for visual comparison
- Individual pie charts per scenario
- A **Download CSV** button to export the comparison

### 4. Model multiple sequential rounds
The **🔄 Multi-Round Dilution** tab chains rounds together (Seed → Series A → Series B). Each round starts from the previous round's cap table. You'll see:

- A line chart of combined founder ownership declining over rounds
- A stacked bar showing the full cap table composition at each stage
- A metrics table with post-money valuation and price per share per round

---

## Key concepts

**Option pool shuffle** – When you add a new option pool %, it is created *before* the investor comes in. This means founders bear the dilution from the pool, not the new investors. This is standard VC practice.

**Scenarios vs. Multi-Round** – Scenarios are *alternatives* (e.g. "what if we raise $1M vs $2M?"). Multi-Round is *cumulative* (what happens if we do all three rounds in sequence).

**Price per share** – Calculated as Pre-Money ÷ Total Shares. Used to determine how many shares the investor receives.

---

## Exporting data

Every tab has a **⬇ Download CSV** button. Use these to paste data into a spreadsheet or share with advisors.

---

## Editing scenarios
You can have up to **5 scenarios** in the Scenario Builder and up to **5 rounds** in Multi-Round. Use the **➕ Add / ➖ Remove Last** buttons to manage them.

---

## Limitations
- Does not model SAFEs, convertible notes, or anti-dilution provisions
- All scenarios reset when the browser tab is closed (no save/load yet)
- For legal or accounting decisions, always verify with a qualified professional
