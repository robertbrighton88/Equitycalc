"""equity_calc.py
────────────────────────────────────────────────────────────────
Pure calculation functions for startup equity dilution modelling.
No UI code – only business logic.

Public API
──────────
    with_ownership_pct   – adds 'Ownership %' column to a cap table DataFrame
    price_per_share      – implied PPS from pre-money valuation
    model_round          – models a single funding round
    build_comparison_df  – compares multiple independent scenarios side-by-side
    model_multi_round    – models sequential cumulative rounds (Seed → A → B)
    fmt_currency         – format dollar value
    fmt_pct              – format percentage value
"""

import pandas as pd
from typing import Union


# ─────────────────────────────────────────────────────────────────────────────
# CAP TABLE HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def with_ownership_pct(cap_table: pd.DataFrame) -> pd.DataFrame:
    """
    Return a copy of cap_table with an 'Ownership %' column added/recalculated.

    Expects columns: ['Shareholder', 'Shares']
    Safe when total shares == 0 (returns 0.0 for all rows).
    """
    df = cap_table[["Shareholder", "Shares"]].copy()
    total = df["Shares"].sum()
    df["Ownership %"] = (df["Shares"] / total * 100).round(2) if total > 0 else 0.0
    return df


def price_per_share(cap_table: pd.DataFrame, pre_money_valuation: float) -> float:
    """
    Implied price per share = pre_money_valuation / total_shares.

    This is the theoretical share price used to compute investor share count.
    """
    total = cap_table["Shares"].sum()
    return pre_money_valuation / total if total > 0 else 0.0


# ─────────────────────────────────────────────────────────────────────────────
# CORE ROUND MODEL
# ─────────────────────────────────────────────────────────────────────────────

def model_round(
    cap_table: pd.DataFrame,
    pre_money: float,
    investment: float,
    new_option_pool_pct: float = 0.0,
    investor_label: str = "New Investors",
) -> tuple:
    """
    Model a single funding round using standard startup dilution logic.

    Dilution mechanics (in order)
    ─────────────────────────────
    1.  Option pool shuffle (if new_option_pool_pct > 0)
        Expand the pool BEFORE the investor comes in.  This means founders
        (not new investors) bear the cost of the expanded pool.

            new_pool_shares / (old_total + new_pool_shares) = new_option_pool_pct

    2.  Post-money valuation  = pre_money + investment

    3.  Investor ownership fraction  = investment / post_money

    4.  New investor shares issued so investor gets exactly that fraction:
            investor_shares / (post_pool_total + investor_shares) = fraction
            ⟹  investor_shares = post_pool_total × fraction / (1 − fraction)

    5.  Recalculate all ownership percentages.

    Parameters
    ──────────
    cap_table            DataFrame with columns ['Shareholder', 'Shares']
    pre_money            Pre-money valuation in dollars
    investment           Capital raised in dollars
    new_option_pool_pct  Additional option pool as a FRACTION (0.10 = 10 %).
                         This is the TARGET fraction of (old_total + new_pool).
    investor_label       Row label for the incoming investor(s)

    Returns
    ───────
    (updated_cap_table, metrics)

    updated_cap_table  – DataFrame with columns ['Shareholder', 'Shares', 'Ownership %']
    metrics            – dict with key round figures
    """
    df = cap_table[["Shareholder", "Shares"]].copy()
    pre_total_shares = int(df["Shares"].sum())

    # ── 1. Option pool shuffle ────────────────────────────────────────────────
    new_pool_shares_added = 0
    if new_option_pool_pct > 0:
        # Solve: new_pool / (pre_total + new_pool) = new_option_pool_pct
        new_pool_shares_added = round(
            pre_total_shares * new_option_pool_pct / (1.0 - new_option_pool_pct)
        )
        # Find an existing option pool / ESOP row and expand it; otherwise add one.
        pool_mask = df["Shareholder"].str.lower().str.contains(
            r"option|pool|esop|unallocated", na=False, regex=True
        )
        if pool_mask.any():
            df.loc[pool_mask, "Shares"] += new_pool_shares_added
        else:
            new_row = pd.DataFrame([{
                "Shareholder": "Option Pool",
                "Shares": new_pool_shares_added,
            }])
            df = pd.concat([df, new_row], ignore_index=True)

    post_pool_total = int(df["Shares"].sum())   # after pool, before investors

    # ── 2-4. Investor ownership and share issuance ────────────────────────────
    post_money = pre_money + investment
    investor_fraction = investment / post_money

    # Solve for investor_shares such that:
    #   investor_shares / (post_pool_total + investor_shares) == investor_fraction
    investor_shares = round(
        post_pool_total * investor_fraction / (1.0 - investor_fraction)
    )

    investor_row = pd.DataFrame([{
        "Shareholder": investor_label,
        "Shares": investor_shares,
    }])
    df = pd.concat([df, investor_row], ignore_index=True)

    # ── 5. Recalculate ownership % ────────────────────────────────────────────
    new_total = int(df["Shares"].sum())
    df["Ownership %"] = (df["Shares"] / new_total * 100).round(2)

    # ── Metrics dict ──────────────────────────────────────────────────────────
    pps = pre_money / pre_total_shares if pre_total_shares > 0 else 0.0
    # dilution_pct: how much each pre-round holder was diluted (fractional loss)
    dilution_pct = (1.0 - pre_total_shares / new_total) * 100

    metrics = {
        "pre_money":             pre_money,
        "investment":            investment,
        "post_money":            post_money,
        "investor_pct":          round(investor_fraction * 100, 2),
        "investor_shares":       investor_shares,
        "pre_total_shares":      pre_total_shares,
        "post_total_shares":     new_total,
        "price_per_share":       round(pps, 4),
        "new_pool_shares_added": new_pool_shares_added,
        "dilution_pct":          round(dilution_pct, 2),
    }

    return df, metrics


# ─────────────────────────────────────────────────────────────────────────────
# SCENARIO COMPARISON  (independent alternatives, same base table)
# ─────────────────────────────────────────────────────────────────────────────

def build_comparison_df(
    base_cap_table: pd.DataFrame,
    scenarios: list,
) -> pd.DataFrame:
    """
    Build a wide DataFrame comparing ownership % across multiple scenarios.

    Each scenario is run independently from the same base cap table
    (i.e., scenarios are ALTERNATIVES, not cumulative rounds).

    Columns:  Shareholder | Current | <scenario 1 name> | <scenario 2 name> | …

    Parameters
    ──────────
    base_cap_table  Current cap table DataFrame
    scenarios       List of dicts with keys:
                      name, pre_money, investment, new_option_pool_pct (fraction)
    """
    base_pct = with_ownership_pct(base_cap_table).set_index("Shareholder")["Ownership %"]

    # Seed data dict: shareholder → {column: ownership %}
    data: dict = {
        sh: {"Current": float(base_pct.get(sh, 0.0))}
        for sh in base_cap_table["Shareholder"]
    }

    for sc in scenarios:
        updated_ct, _ = model_round(
            base_cap_table,
            sc["pre_money"],
            sc["investment"],
            sc["new_option_pool_pct"],   # already a fraction
            investor_label="Investors",
        )
        sc_pct = updated_ct.set_index("Shareholder")["Ownership %"].to_dict()

        # Update rows for shareholders that were already in the base table
        for sh in list(data.keys()):
            data[sh][sc["name"]] = sc_pct.get(sh, 0.0)

        # Add new rows for shareholders that only appear in this scenario
        # (new investors, expanded pool row if option pool didn't exist before)
        for sh, pct in sc_pct.items():
            if sh not in data:
                data[sh] = {"Current": 0.0}
                data[sh][sc["name"]] = pct

    # Build final DataFrame, ensuring all scenario columns exist for every row
    sc_names = [sc["name"] for sc in scenarios]
    rows = []
    for sh, cols in data.items():
        row = {"Shareholder": sh, "Current": cols.get("Current", 0.0)}
        for sc_name in sc_names:
            row[sc_name] = cols.get(sc_name, 0.0)
        rows.append(row)

    return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────────────────────
# MULTI-ROUND (SEQUENTIAL / CUMULATIVE) MODEL
# ─────────────────────────────────────────────────────────────────────────────

def model_multi_round(
    cap_table: pd.DataFrame,
    rounds: list,
) -> list:
    """
    Model sequential funding rounds (Seed → Series A → Series B …).

    Each round uses the cap table produced by the PRIOR round as its input,
    so dilution compounds realistically over time.

    Parameters
    ──────────
    cap_table  Initial (pre-seed) cap table DataFrame
    rounds     List of dicts with keys:
                 name, pre_money, investment, new_option_pool_pct (fraction)

    Returns
    ───────
    List of (round_name, cap_table_snapshot, metrics) tuples.
    First element is always ("Current", initial_cap_table_with_pct, {}).
    """
    results = [("Current", with_ownership_pct(cap_table), {})]
    current_ct = cap_table[["Shareholder", "Shares"]].copy()

    for rd in rounds:
        updated_ct, metrics = model_round(
            current_ct,
            rd["pre_money"],
            rd["investment"],
            rd.get("new_option_pool_pct", 0.0),
            investor_label=rd["name"],
        )
        results.append((rd["name"], updated_ct, metrics))
        # Feed the updated Shares into the next round (drop the % column)
        current_ct = updated_ct[["Shareholder", "Shares"]].copy()

    return results


# ─────────────────────────────────────────────────────────────────────────────
# FORMATTING HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def fmt_currency(value: float, compact: bool = False) -> str:
    """Format a dollar amount, optionally in compact form (1.5M, 500K)."""
    if compact:
        if abs(value) >= 1_000_000_000:
            return f"${value / 1_000_000_000:.1f}B"
        if abs(value) >= 1_000_000:
            return f"${value / 1_000_000:.1f}M"
        if abs(value) >= 1_000:
            return f"${value / 1_000:.0f}K"
    return f"${value:,.0f}"


def fmt_pct(value: float, decimals: int = 2) -> str:
    """Format a percentage value."""
    return f"{value:.{decimals}f}%"
