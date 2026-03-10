"""app.py
────────────────────────────────────────────────────────────────
Equity Dilution Scenario Calculator
A strategic tool for founders to model cap table dilution.

Run with:  streamlit run app.py
"""

import io
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from equity_calc import (
    with_ownership_pct,
    model_round,
    build_comparison_df,
    model_multi_round,
    build_vesting_schedule,
    token_metrics,
    fmt_currency,
    fmt_pct,
)

# ─────────────────────────────────────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Equity Dilution Calculator",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    /* Tighten up metric cards */
    [data-testid="metric-container"] {
        background: #f8f9fa;
        border: 1px solid #e9ecef;
        border-radius: 8px;
        padding: 12px 16px;
    }
    /* Accent colour on metric values */
    [data-testid="stMetricValue"] { color: #1a1a2e; }

    /* Make tab text slightly bolder */
    .stTabs [data-baseweb="tab"] { font-weight: 500; }

    /* Highlight founder rows in tables (applied via JS-free approach via st.dataframe styling) */
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# SESSION STATE – initialised once per session
# ─────────────────────────────────────────────────────────────────────────────

def _init_state() -> None:
    """Populate session_state with default data on first load."""

    if "cap_table" not in st.session_state:
        st.session_state.cap_table = pd.DataFrame([
            {"Shareholder": "Founder 1",   "Shares": 4_000_000},
            {"Shareholder": "Founder 2",   "Shares": 3_000_000},
            {"Shareholder": "Yannick",     "Shares": 1_000_000},
            {"Shareholder": "Louisa",      "Shares":   500_000},
            {"Shareholder": "Option Pool", "Shares": 1_500_000},
        ])

    # Scenarios are INDEPENDENT alternatives run against the same base table.
    # Option pool stored as integer % (0-25); converted to fraction (/100) for maths.
    if "scenarios" not in st.session_state:
        st.session_state.scenarios = [
            {
                "name":         "Angel Round",
                "pre_money":    5_000_000,
                "investment":   1_000_000,
                "pool_pct":     0,          # integer %
            },
            {
                "name":         "Seed Round",
                "pre_money":    10_000_000,
                "investment":   2_000_000,
                "pool_pct":     0,
            },
            {
                "name":         "Seed + Pool Expand",
                "pre_money":    10_000_000,
                "investment":   3_000_000,
                "pool_pct":     10,         # 10 % additional option pool
            },
        ]

    # Multi-round: CUMULATIVE sequential rounds.
    if "multi_rounds" not in st.session_state:
        st.session_state.multi_rounds = [
            {
                "name":       "Seed",
                "pre_money":  8_000_000,
                "investment": 2_000_000,
                "pool_pct":   0,
            },
            {
                "name":       "Series A",
                "pre_money":  25_000_000,
                "investment": 5_000_000,
                "pool_pct":   5,
            },
            {
                "name":       "Series B",
                "pre_money":  80_000_000,
                "investment": 15_000_000,
                "pool_pct":   3,
            },
        ]

    # Tokenomics defaults – standard Web3 allocation structure
    if "token_name" not in st.session_state:
        st.session_state.token_name    = "MyToken"
        st.session_state.token_ticker  = "MYT"
        st.session_state.token_supply  = 1_000_000_000
        st.session_state.token_price   = 0.05   # price at TGE in USD

    if "token_allocations" not in st.session_state:
        st.session_state.token_allocations = pd.DataFrame([
            {"Stakeholder": "Team",         "Allocation %": 20, "TGE Unlock %":   0, "Cliff (months)": 12, "Vest (months)": 36},
            {"Stakeholder": "Investors",    "Allocation %": 15, "TGE Unlock %":   0, "Cliff (months)":  6, "Vest (months)": 24},
            {"Stakeholder": "Ecosystem",    "Allocation %": 30, "TGE Unlock %":   5, "Cliff (months)":  0, "Vest (months)": 48},
            {"Stakeholder": "Treasury",     "Allocation %": 20, "TGE Unlock %":   0, "Cliff (months)":  0, "Vest (months)":  0},
            {"Stakeholder": "Public Sale",  "Allocation %": 10, "TGE Unlock %": 100, "Cliff (months)":  0, "Vest (months)":  0},
            {"Stakeholder": "Advisors",     "Allocation %":  5, "TGE Unlock %":   0, "Cliff (months)":  6, "Vest (months)": 24},
        ])


_init_state()

# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

COLOUR_SEQ = px.colors.qualitative.Set2  # consistent palette throughout


def founder_mask(df: pd.DataFrame) -> pd.Series:
    """Boolean mask for rows whose Shareholder name contains 'founder'."""
    return df["Shareholder"].str.lower().str.contains("founder", na=False)


def _fmt_pct_cell(v: float) -> str:
    """Format a percentage for display in comparison tables."""
    return f"{v:.2f}%" if v > 0 else "—"


def _round_inputs(sc: dict, idx: int, key_prefix: str) -> None:
    """
    Render the 4 input widgets for a single scenario/round dict (in-place update).
    key_prefix + idx ensures unique widget keys across tabs.
    """
    c1, c2, c3, c4 = st.columns([2, 2, 2, 1])
    with c1:
        sc["name"] = st.text_input(
            "Name", value=sc["name"], key=f"{key_prefix}_name_{idx}"
        )
    with c2:
        sc["pre_money"] = st.number_input(
            "Pre-Money Valuation ($)",
            min_value=100_000,
            max_value=5_000_000_000,
            value=int(sc["pre_money"]),
            step=500_000,
            format="%d",
            key=f"{key_prefix}_pre_{idx}",
        )
    with c3:
        sc["investment"] = st.number_input(
            "Investment ($)",
            min_value=10_000,
            max_value=1_000_000_000,
            value=int(sc["investment"]),
            step=250_000,
            format="%d",
            key=f"{key_prefix}_inv_{idx}",
        )
    with c4:
        sc["pool_pct"] = st.number_input(
            "Option Pool (%)",
            min_value=0,
            max_value=25,
            value=int(sc.get("pool_pct", 0)),
            step=1,
            help="Additional option pool to create BEFORE investor comes in (option pool shuffle). Enter as integer, e.g. 10 = 10%.",
            key=f"{key_prefix}_pool_{idx}",
        )


# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR – CAP TABLE EDITOR
# ─────────────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.title("📋 Cap Table")
    st.caption("Edit rows inline. Add or remove shareholders with the ＋ / 🗑 controls.")

    edited = st.data_editor(
        st.session_state.cap_table,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "Shareholder": st.column_config.TextColumn("Shareholder", width="medium"),
            "Shares": st.column_config.NumberColumn(
                "Shares", min_value=0, format="%d", width="small"
            ),
        },
        key="cap_table_editor",
    )
    # Persist edits (drop blank rows)
    st.session_state.cap_table = (
        edited.dropna(subset=["Shareholder"])
              .query("Shareholder != ''")
              .reset_index(drop=True)
    )

    ct_live = with_ownership_pct(st.session_state.cap_table)
    total_sh = int(ct_live["Shares"].sum())
    f_mask = founder_mask(ct_live)
    founder_total_pct = ct_live.loc[f_mask, "Ownership %"].sum() if f_mask.any() else 0.0

    st.divider()
    col_a, col_b = st.columns(2)
    col_a.metric("Total Shares", f"{total_sh:,}")
    col_b.metric("Founder %", fmt_pct(founder_total_pct))
    st.divider()
    st.caption("EquityCalc v1.0 · For strategic decisions only.\nNot legal or accounting advice.")


# ─────────────────────────────────────────────────────────────────────────────
# HEADER
# ─────────────────────────────────────────────────────────────────────────────

st.title("📈 Equity Dilution Calculator")
st.caption(
    "Model funding rounds, compare scenarios side-by-side, "
    "and visualise how founder ownership evolves over time."
)

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📋 Current Cap Table",
    "🎯 Scenario Builder",
    "📊 Scenario Comparison",
    "🔄 Multi-Round Dilution",
    "🪙 Tokenomics",
    "📖 Manual",
])


# ─────────────────────────────────────────────────────────────────────────────
# TAB 1 – CURRENT CAP TABLE
# ─────────────────────────────────────────────────────────────────────────────

with tab1:
    ct = with_ownership_pct(st.session_state.cap_table)

    # ── Key metrics row ───────────────────────────────────────────────────────
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Shares",   f"{int(ct['Shares'].sum()):,}")
    m2.metric("Shareholders",   len(ct))

    if founder_mask(ct).any():
        f_pct = ct.loc[founder_mask(ct), "Ownership %"].sum()
        m3.metric("Founder Ownership", fmt_pct(f_pct))
    else:
        m3.metric("Founder Ownership", "—")

    pool_mask = ct["Shareholder"].str.lower().str.contains(
        r"option|pool|esop", na=False, regex=True
    )
    pool_pct = ct.loc[pool_mask, "Ownership %"].sum() if pool_mask.any() else 0.0
    m4.metric("Option Pool", fmt_pct(pool_pct))

    st.divider()

    # ── Table + Pie chart side by side ────────────────────────────────────────
    col_left, col_right = st.columns([1, 1], gap="large")

    with col_left:
        st.subheader("Shareholders")
        st.dataframe(
            ct.style.format({"Shares": "{:,.0f}", "Ownership %": "{:.2f}%"}),
            use_container_width=True,
            hide_index=True,
        )
        csv_bytes = ct.to_csv(index=False).encode()
        st.download_button(
            "⬇ Download CSV",
            data=csv_bytes,
            file_name="cap_table_current.csv",
            mime="text/csv",
        )

    with col_right:
        fig_pie = px.pie(
            ct,
            values="Ownership %",
            names="Shareholder",
            title="Current Ownership Distribution",
            color_discrete_sequence=COLOUR_SEQ,
            hole=0.35,
        )
        fig_pie.update_traces(textposition="inside", textinfo="percent+label")
        fig_pie.update_layout(
            showlegend=False,
            margin=dict(t=50, b=10, l=10, r=10),
        )
        st.plotly_chart(fig_pie, use_container_width=True)


# ─────────────────────────────────────────────────────────────────────────────
# TAB 2 – SCENARIO BUILDER
# ─────────────────────────────────────────────────────────────────────────────

with tab2:
    st.subheader("Define Fundraising Scenarios")
    st.caption(
        "Each scenario is modelled independently against the same base cap table. "
        "For cumulative (sequential) rounds see the **Multi-Round Dilution** tab."
    )

    btn_add, btn_rem, _ = st.columns([1, 1, 5])
    with btn_add:
        if st.button("➕ Add Scenario", disabled=len(st.session_state.scenarios) >= 5):
            st.session_state.scenarios.append({
                "name":       f"Scenario {len(st.session_state.scenarios) + 1}",
                "pre_money":  10_000_000,
                "investment": 2_000_000,
                "pool_pct":   0,
            })
            st.rerun()
    with btn_rem:
        if st.button("➖ Remove Last", disabled=len(st.session_state.scenarios) <= 1):
            st.session_state.scenarios.pop()
            st.rerun()

    st.divider()

    for i, sc in enumerate(st.session_state.scenarios):
        with st.expander(f"**{sc['name']}**", expanded=True):
            _round_inputs(sc, i, key_prefix="sc")

            # ── Quick preview metrics for this scenario ───────────────────────
            try:
                _, metrics = model_round(
                    st.session_state.cap_table,
                    pre_money=sc["pre_money"],
                    investment=sc["investment"],
                    new_option_pool_pct=sc["pool_pct"] / 100,
                )
                p1, p2, p3, p4 = st.columns(4)
                p1.metric("Post-Money",         fmt_currency(metrics["post_money"], compact=True))
                p2.metric("Investor Ownership", fmt_pct(metrics["investor_pct"]))
                p3.metric("Price / Share",      f"${metrics['price_per_share']:.4f}")
                p4.metric("Dilution (existing)", fmt_pct(metrics["dilution_pct"]))
            except Exception as e:
                st.warning(f"Could not compute preview: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# TAB 3 – SCENARIO COMPARISON
# ─────────────────────────────────────────────────────────────────────────────

with tab3:
    st.subheader("Scenario Comparison")

    if not st.session_state.scenarios:
        st.info("Add at least one scenario in the **Scenario Builder** tab.")
    else:
        try:
            comp_df = build_comparison_df(
                st.session_state.cap_table,
                [
                    {**sc, "new_option_pool_pct": sc["pool_pct"] / 100}
                    for sc in st.session_state.scenarios
                ],
            )
        except Exception as e:
            st.error(f"Error building comparison: {e}")
            st.stop()

        # ── Formatted comparison table ────────────────────────────────────────
        pct_cols = [c for c in comp_df.columns if c != "Shareholder"]
        display_df = comp_df.copy()
        for col in pct_cols:
            display_df[col] = display_df[col].apply(_fmt_pct_cell)

        st.dataframe(display_df, use_container_width=True, hide_index=True)

        csv_comp = comp_df.to_csv(index=False).encode()
        st.download_button(
            "⬇ Download Comparison CSV",
            data=csv_comp,
            file_name="scenario_comparison.csv",
            mime="text/csv",
        )

        st.divider()

        # ── Grouped bar chart: all shareholders × all scenarios ───────────────
        st.subheader("Ownership by Shareholder Across Scenarios")

        melted = comp_df.melt(
            id_vars="Shareholder",
            var_name="Scenario",
            value_name="Ownership %",
        )
        fig_bar = px.bar(
            melted,
            x="Shareholder",
            y="Ownership %",
            color="Scenario",
            barmode="group",
            text_auto=".1f",
            color_discrete_sequence=COLOUR_SEQ,
        )
        fig_bar.update_traces(texttemplate="%{text}%", textposition="outside")
        fig_bar.update_layout(
            xaxis_tickangle=-30,
            yaxis_title="Ownership %",
            yaxis_ticksuffix="%",
            legend_title_text="Scenario",
            uniformtext_minsize=8,
        )
        st.plotly_chart(fig_bar, use_container_width=True)

        st.divider()

        # ── Pie charts: one per scenario ──────────────────────────────────────
        st.subheader("Post-Round Cap Table by Scenario")

        n_sc = len(st.session_state.scenarios)
        n_cols = min(n_sc, 3)
        pie_cols = st.columns(n_cols)

        for i, sc in enumerate(st.session_state.scenarios):
            try:
                updated_ct, metrics = model_round(
                    st.session_state.cap_table,
                    pre_money=sc["pre_money"],
                    investment=sc["investment"],
                    new_option_pool_pct=sc["pool_pct"] / 100,
                    investor_label="New Investors",
                )
            except Exception:
                continue

            with pie_cols[i % n_cols]:
                fig_sc_pie = px.pie(
                    updated_ct,
                    values="Ownership %",
                    names="Shareholder",
                    title=f"{sc['name']}<br><sup>Post-money: {fmt_currency(metrics['post_money'], compact=True)}</sup>",
                    color_discrete_sequence=COLOUR_SEQ,
                    hole=0.35,
                )
                fig_sc_pie.update_traces(textposition="inside", textinfo="percent")
                fig_sc_pie.update_layout(
                    showlegend=True,
                    margin=dict(t=60, b=10, l=10, r=10),
                    height=320,
                    legend=dict(font=dict(size=10)),
                )
                st.plotly_chart(fig_sc_pie, use_container_width=True)

                # Quick stats under each pie
                a1, a2 = st.columns(2)
                a1.metric("Investor %", fmt_pct(metrics["investor_pct"]))
                a2.metric("Dilution", fmt_pct(metrics["dilution_pct"]))


# ─────────────────────────────────────────────────────────────────────────────
# TAB 4 – MULTI-ROUND DILUTION
# ─────────────────────────────────────────────────────────────────────────────

with tab4:
    st.subheader("Multi-Round Dilution Waterfall")
    st.caption(
        "Rounds are CUMULATIVE – each round starts from the prior round's cap table. "
        "Use this to model a Seed → Series A → Series B fundraising journey."
    )

    # ── Round input cards ─────────────────────────────────────────────────────
    for i, rd in enumerate(st.session_state.multi_rounds):
        with st.expander(f"**Round {i + 1}: {rd['name']}**", expanded=(i == 0)):
            _round_inputs(rd, i, key_prefix="mr")

    btn_add_r, btn_rem_r, _ = st.columns([1, 1, 5])
    with btn_add_r:
        if st.button("➕ Add Round", key="mr_add"):
            n = len(st.session_state.multi_rounds)
            st.session_state.multi_rounds.append({
                "name":       f"Round {n + 1}",
                "pre_money":  50_000_000 * (n + 1),
                "investment": 10_000_000 * (n + 1),
                "pool_pct":   0,
            })
            st.rerun()
    with btn_rem_r:
        if st.button("➖ Remove Last Round", key="mr_rem",
                     disabled=len(st.session_state.multi_rounds) <= 1):
            st.session_state.multi_rounds.pop()
            st.rerun()

    st.divider()

    # ── Run the sequential model ──────────────────────────────────────────────
    try:
        mr_results = model_multi_round(
            st.session_state.cap_table,
            [
                {**rd, "new_option_pool_pct": rd["pool_pct"] / 100}
                for rd in st.session_state.multi_rounds
            ],
        )
    except Exception as e:
        st.error(f"Error computing multi-round model: {e}")
        st.stop()

    # ── Identify founders (anyone with 'founder' in name) ────────────────────
    base_shareholders = list(st.session_state.cap_table["Shareholder"])
    founder_names = [
        sh for sh in base_shareholders
        if "founder" in sh.lower()
    ]

    # ── Line chart: combined founder ownership across rounds ──────────────────
    founder_timeline = []
    for round_name, ct_snap, _ in mr_results:
        ct_pct = ct_snap.set_index("Shareholder")["Ownership %"].to_dict()
        f_total = sum(ct_pct.get(f, 0.0) for f in founder_names)
        founder_timeline.append({"Round": round_name, "Founder Ownership %": round(f_total, 2)})

    if founder_names and founder_timeline:
        f_df = pd.DataFrame(founder_timeline)
        fig_line = px.line(
            f_df,
            x="Round",
            y="Founder Ownership %",
            title="Combined Founder Ownership Over Rounds",
            markers=True,
            color_discrete_sequence=["#2ecc71"],
        )
        fig_line.update_traces(
            line=dict(width=3),
            marker=dict(size=10),
            text=f_df["Founder Ownership %"].apply(lambda v: f"{v:.1f}%"),
            textposition="top center",
            mode="lines+markers+text",
        )
        fig_line.update_layout(
            yaxis_title="Ownership %",
            yaxis_ticksuffix="%",
            yaxis_range=[0, 100],
        )
        st.plotly_chart(fig_line, use_container_width=True)
    else:
        st.info("Name founders with 'Founder' in their name to see the founder dilution line chart.")

    # ── Stacked bar: full cap table composition per round ─────────────────────
    stacked_rows = []
    for round_name, ct_snap, _ in mr_results:
        for _, row in ct_snap.iterrows():
            stacked_rows.append({
                "Round":       round_name,
                "Shareholder": row["Shareholder"],
                "Ownership %": row["Ownership %"],
            })

    stacked_df = pd.DataFrame(stacked_rows)

    fig_stack = px.bar(
        stacked_df,
        x="Round",
        y="Ownership %",
        color="Shareholder",
        title="Cap Table Composition Over All Rounds",
        color_discrete_sequence=COLOUR_SEQ,
        text_auto=".1f",
    )
    fig_stack.update_traces(texttemplate="%{text}%", textposition="inside")
    fig_stack.update_layout(
        barmode="stack",
        yaxis_title="Ownership %",
        yaxis_ticksuffix="%",
        yaxis_range=[0, 100],
        legend_title_text="Shareholder",
    )
    st.plotly_chart(fig_stack, use_container_width=True)

    st.divider()

    # ── Round metrics table ───────────────────────────────────────────────────
    st.subheader("Round Metrics")

    metrics_rows = []
    for round_name, _, metrics in mr_results[1:]:   # skip "Current"
        metrics_rows.append({
            "Round":            round_name,
            "Pre-Money":        fmt_currency(metrics["pre_money"], compact=True),
            "Investment":       fmt_currency(metrics["investment"], compact=True),
            "Post-Money":       fmt_currency(metrics["post_money"], compact=True),
            "New Investor %":   fmt_pct(metrics["investor_pct"]),
            "Price / Share":    f"${metrics['price_per_share']:.4f}",
            "Dilution (round)": fmt_pct(metrics["dilution_pct"]),
        })

    if metrics_rows:
        st.dataframe(pd.DataFrame(metrics_rows), use_container_width=True, hide_index=True)

    # ── Export ────────────────────────────────────────────────────────────────
    mr_comp_rows = []
    for round_name, ct_snap, _ in mr_results:
        row = {"Round": round_name}
        for _, sh_row in ct_snap.iterrows():
            row[sh_row["Shareholder"]] = round(sh_row["Ownership %"], 2)
        mr_comp_rows.append(row)

    mr_comp_df = pd.DataFrame(mr_comp_rows).fillna(0.0)
    st.download_button(
        "⬇ Download Multi-Round CSV",
        data=mr_comp_df.to_csv(index=False).encode(),
        file_name="multi_round_dilution.csv",
        mime="text/csv",
    )

# ─────────────────────────────────────────────────────────────────────────────
# TAB 5 – TOKENOMICS
# ─────────────────────────────────────────────────────────────────────────────

with tab5:
    st.subheader("🪙 Token Distribution & Vesting")
    st.caption(
        "Model your token supply, allocation across stakeholders, "
        "and how tokens unlock over time after the Token Generation Event (TGE)."
    )

    # ── Token basics ──────────────────────────────────────────────────────────
    st.markdown("#### Token Basics")
    tb1, tb2, tb3, tb4 = st.columns(4)
    with tb1:
        st.session_state.token_name = st.text_input(
            "Token Name", value=st.session_state.token_name, key="tok_name"
        )
    with tb2:
        st.session_state.token_ticker = st.text_input(
            "Ticker", value=st.session_state.token_ticker, key="tok_ticker"
        )
    with tb3:
        st.session_state.token_supply = st.number_input(
            "Total Supply",
            min_value=1_000,
            max_value=1_000_000_000_000,
            value=int(st.session_state.token_supply),
            step=100_000_000,
            format="%d",
            key="tok_supply",
        )
    with tb4:
        st.session_state.token_price = st.number_input(
            "TGE Token Price (USD)",
            min_value=0.000001,
            max_value=100_000.0,
            value=float(st.session_state.token_price),
            step=0.01,
            format="%.4f",
            key="tok_price",
        )

    st.divider()

    # ── Allocation table ──────────────────────────────────────────────────────
    st.markdown("#### Allocation Table")
    st.caption(
        "Each row is a stakeholder group. "
        "**Allocation %** must sum to 100. "
        "**TGE Unlock %** = how much of that group's tokens unlock immediately at TGE. "
        "Remaining tokens vest linearly after the cliff."
    )

    edited_alloc = st.data_editor(
        st.session_state.token_allocations,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "Stakeholder":     st.column_config.TextColumn("Stakeholder", width="medium"),
            "Allocation %":    st.column_config.NumberColumn("Allocation %",   min_value=0, max_value=100, format="%d %%"),
            "TGE Unlock %":    st.column_config.NumberColumn("TGE Unlock %",   min_value=0, max_value=100, format="%d %%"),
            "Cliff (months)":  st.column_config.NumberColumn("Cliff (months)", min_value=0, max_value=60,  format="%d"),
            "Vest (months)":   st.column_config.NumberColumn("Vest (months)",  min_value=0, max_value=120, format="%d"),
        },
        key="tok_alloc_editor",
    )
    st.session_state.token_allocations = edited_alloc.dropna(subset=["Stakeholder"]).reset_index(drop=True)

    # Validate total %
    total_alloc_pct = st.session_state.token_allocations["Allocation %"].sum()
    if abs(total_alloc_pct - 100) > 0.01:
        st.warning(f"Allocation % sums to **{total_alloc_pct:.1f}%** — should be 100%.")
    else:
        st.success("Allocation % sums to 100% ✓")

    st.divider()

    # ── Build allocations list for calc functions ─────────────────────────────
    alloc_df = st.session_state.token_allocations
    allocations = [
        {
            "name":    row["Stakeholder"],
            "pct":     row["Allocation %"],
            "tge_pct": row["TGE Unlock %"],
            "cliff":   int(row["Cliff (months)"]),
            "vest":    int(row["Vest (months)"]),
        }
        for _, row in alloc_df.iterrows()
    ]

    tok_supply = int(st.session_state.token_supply)
    tok_price  = float(st.session_state.token_price)
    tok_ticker = st.session_state.token_ticker

    try:
        tm = token_metrics(allocations, tok_supply, tok_price)

        # ── Key metrics row ───────────────────────────────────────────────────
        st.markdown("#### Key Metrics at TGE")
        km1, km2, km3, km4 = st.columns(4)
        km1.metric("Fully Diluted Valuation",    fmt_currency(tm["fdv"], compact=True))
        km2.metric("Initial Market Cap",         fmt_currency(tm["initial_market_cap"], compact=True))
        km3.metric("Initial Circulating Supply", f"{tm['initial_circ_supply']:,} {tok_ticker}")
        km4.metric("Circ. Supply at TGE",        fmt_pct(tm["initial_circ_pct"]))

        st.divider()

        # ── Charts ────────────────────────────────────────────────────────────
        col_pie, col_vest = st.columns([1, 2], gap="large")

        with col_pie:
            st.markdown("#### Token Distribution")
            fig_tok_pie = px.pie(
                alloc_df,
                values="Allocation %",
                names="Stakeholder",
                color_discrete_sequence=COLOUR_SEQ,
                hole=0.4,
            )
            fig_tok_pie.update_traces(textposition="inside", textinfo="percent+label")
            fig_tok_pie.update_layout(
                showlegend=False,
                margin=dict(t=10, b=10, l=10, r=10),
            )
            st.plotly_chart(fig_tok_pie, use_container_width=True)

        with col_vest:
            st.markdown("#### Cumulative Token Unlock Schedule")
            n_months = st.slider(
                "Months to model", min_value=12, max_value=120,
                value=60, step=6, key="tok_months"
            )
            vest_df = build_vesting_schedule(allocations, tok_supply, n_months)

            # Melt for stacked area chart
            vest_melted = vest_df.melt(
                id_vars="Month", var_name="Stakeholder", value_name="Tokens Unlocked"
            )
            fig_vest = px.area(
                vest_melted,
                x="Month",
                y="Tokens Unlocked",
                color="Stakeholder",
                color_discrete_sequence=COLOUR_SEQ,
                groupnorm="",   # absolute values, not normalised
            )
            fig_vest.update_layout(
                xaxis_title="Months after TGE",
                yaxis_title="Cumulative Tokens Unlocked",
                legend_title_text="Stakeholder",
                hovermode="x unified",
            )
            fig_vest.update_yaxes(tickformat=".2s")
            st.plotly_chart(fig_vest, use_container_width=True)

        # ── Unlock schedule table (collapsed by default) ──────────────────────
        with st.expander("View full unlock schedule table"):
            display_vest = vest_df.copy()
            # Format large numbers with commas
            for col in display_vest.columns[1:]:
                display_vest[col] = display_vest[col].apply(lambda v: f"{int(v):,}")
            st.dataframe(display_vest, use_container_width=True, hide_index=True)

        # ── Export ────────────────────────────────────────────────────────────
        st.download_button(
            "⬇ Download Vesting Schedule CSV",
            data=vest_df.to_csv(index=False).encode(),
            file_name=f"{tok_ticker.lower()}_vesting_schedule.csv",
            mime="text/csv",
        )

    except Exception as e:
        st.error(f"Error computing token metrics: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# TAB 6 – MANUAL
# ─────────────────────────────────────────────────────────────────────────────

with tab6:
    st.markdown("""
## 📖 User Manual

> **For strategic decision support only.** Not legal or accounting advice.

---

### What it does

Models how a funding round dilutes the founding team's equity. Enter your current
shareholders, define one or more fundraising scenarios, and instantly see how
ownership percentages change.

---

### 1 · Set up your cap table

The **sidebar** (left panel) holds the cap table. It comes preloaded with example
data — edit it to match your actual shareholders:

- Click any cell to edit a value
- Click **＋** at the bottom to add a new row
- Click the **🗑** icon on a row to delete it
- Only enter **Shares** (raw share count) — percentages calculate automatically

---

### 2 · Model a funding round

Go to the **🎯 Scenario Builder** tab:

| Field | What to enter |
|-------|--------------|
| Name | A label, e.g. "Seed Round" |
| Pre-Money Valuation | Company value before investment |
| Investment | Amount being raised |
| Option Pool (%) | Additional pool to create before the round — enter 0 if none |

Preview metrics (post-money, investor %, dilution) appear instantly below each scenario.

---

### 3 · Compare scenarios

The **📊 Scenario Comparison** tab shows all scenarios side by side:

- A table with each shareholder's % across all scenarios
- A grouped bar chart for visual comparison
- Individual pie charts per scenario
- A **⬇ Download CSV** button to export the comparison

---

### 4 · Model multiple sequential rounds

The **🔄 Multi-Round Dilution** tab chains rounds together (Seed → Series A → Series B).
Each round starts from the previous round's cap table. You'll see:

- A line chart of combined founder ownership declining over rounds
- A stacked bar showing the full cap table composition at each stage
- A metrics table with post-money valuation and price per share per round

---

### Key concepts

**Option pool shuffle** — When you add a new option pool %, it is created *before* the
investor comes in. This means founders bear the dilution from the pool, not the new
investors. This is standard VC practice.

**Scenarios vs. Multi-Round** — Scenarios are *alternatives* (e.g. "what if we raise
\\$1M vs \\$2M?"). Multi-Round is *cumulative* (what happens if we do all three rounds
in sequence).

**Price per share** — Calculated as Pre-Money ÷ Total Shares. Used to determine how
many shares the investor receives.

---

### Exporting data

Every tab has a **⬇ Download CSV** button. Use these to paste data into a spreadsheet
or share with advisors.

---

### Editing scenarios

You can have up to **5 scenarios** in the Scenario Builder and up to **5 rounds** in
Multi-Round. Use the **➕ Add / ➖ Remove Last** buttons to manage them.

---

### Limitations

- Does not model SAFEs, convertible notes, or anti-dilution provisions
- All data resets when the browser tab is closed (no save/load yet)
- For legal or accounting decisions, always verify with a qualified professional
""")
