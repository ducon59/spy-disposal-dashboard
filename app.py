import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots

# ─── Page Config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="SPY Disposal Modeller | Italian Fiscal Resident",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Custom CSS ───────────────────────────────────────────────────────────────
st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=DM+Sans:wght@300;400;500;600&display=swap');

  html, body, [class*="css"] {
    font-family: 'DM Sans', sans-serif;
  }
  h1, h2, h3 {
    font-family: 'DM Serif Display', serif;
  }

  /* Dark background */
  .stApp {
    background-color: #0d0f14;
    color: #e8e4da;
  }
  
  /* Sidebar */
  [data-testid="stSidebar"] {
    background-color: #13161e;
    border-right: 1px solid #2a2d38;
  }
  
  /* Metric cards */
  .metric-card {
    background: linear-gradient(135deg, #1a1d27 0%, #13161e 100%);
    border: 1px solid #2a2d38;
    border-radius: 12px;
    padding: 20px 24px;
    margin-bottom: 16px;
  }
  .metric-card h4 {
    font-size: 11px;
    letter-spacing: 0.15em;
    text-transform: uppercase;
    color: #6b7080;
    margin-bottom: 6px;
    font-family: 'DM Sans', sans-serif;
  }
  .metric-card .value {
    font-size: 28px;
    font-family: 'DM Serif Display', serif;
    color: #e8e4da;
  }
  .metric-card .sub {
    font-size: 12px;
    color: #6b7080;
    margin-top: 4px;
  }
  .positive { color: #4ade80 !important; }
  .negative { color: #f87171 !important; }
  .neutral  { color: #60a5fa !important; }
  
  /* Section header */
  .section-header {
    border-left: 3px solid #c9a84c;
    padding-left: 12px;
    margin: 32px 0 16px;
  }
  .section-header h2 {
    color: #e8e4da;
    font-size: 20px;
    margin: 0;
  }
  .section-header p {
    color: #6b7080;
    font-size: 13px;
    margin: 4px 0 0;
  }
  
  /* Warning / note box */
  .info-box {
    background: #1a1d27;
    border: 1px solid #c9a84c44;
    border-left: 3px solid #c9a84c;
    border-radius: 8px;
    padding: 14px 18px;
    font-size: 13px;
    color: #a89060;
    margin: 12px 0;
  }

  /* Stremlit default overrides */
  .stSlider label { color: #9ca3af; }
  div[data-baseweb="slider"] div { background: #c9a84c44; }
  div[data-baseweb="slider"] div[role="slider"] { background: #c9a84c; }

  .stNumberInput label { color: #9ca3af; }
  [data-testid="stMetricValue"] { color: #e8e4da; font-family: 'DM Serif Display', serif; }
  [data-testid="stMetricLabel"] { color: #6b7080; font-size: 12px; }
</style>
""", unsafe_allow_html=True)

# ─── Constants ────────────────────────────────────────────────────────────────
STANDARD_CGT_RATE   = 0.26   # Italy standard capital gains tax (regime dichiarativo)
FLAT_TAX_RATE       = 0.07   # Flat tax regime for new residents (regime forfettario/res impatriati)
FLAT_TAX_YEARS_MAX  = 15     # Max years flat tax available (res impatriati)
LOW_TAX_RATE        = 0.00   # Dubai / no-CGT jurisdiction (illustrative)
MOVING_COST_PCT     = 0.015  # Estimated relocation / admin cost as % of portfolio
FLAT_TAX_LUMP_SUM   = 100_000  # Annual lump-sum for flat tax regime (€100k/year)

# ─── Helper functions ─────────────────────────────────────────────────────────

def fmt_eur(v):
    return f"€{v:,.0f}"

def compute_do_nothing(spy_current_value, spy_cost_basis):
    """Tax deferred indefinitely; unrealised gain grows."""
    gain = spy_current_value - spy_cost_basis
    tax_if_sold_now = gain * STANDARD_CGT_RATE
    return {
        "label": "Do Nothing",
        "tax_on_spy": 0,
        "tax_total": 0,
        "net_proceeds": spy_current_value,  # no sale
        "notes": "No tax event. Non-UCITS 'rapport dei redditi di capitale' risk if deemed distributed.",
        "gain": gain,
        "latent_tax": tax_if_sold_now,
    }

def compute_standard_sale(spy_current_value, spy_cost_basis):
    gain = spy_current_value - spy_cost_basis
    tax = max(0, gain) * STANDARD_CGT_RATE
    net = spy_current_value - tax
    return {
        "label": "Sell Now (Standard 26%)",
        "tax_on_spy": tax,
        "tax_total": tax,
        "net_proceeds": net,
        "gain": gain,
        "effective_rate": tax / spy_current_value,
    }

def compute_flat_tax_1yr(spy_current_value, spy_cost_basis):
    """
    Regime dei 'neo-residenti' (Art. 24-bis TUIR).
    €100k annual lump-sum covers all foreign income including capital gains.
    Gain on SPY (US-listed, non-UCITS) = foreign-source income → covered by lump sum.
    """
    gain = spy_current_value - spy_cost_basis
    tax_on_spy = FLAT_TAX_LUMP_SUM  # lump sum covers the foreign gain
    tax_standard = max(0, gain) * STANDARD_CGT_RATE
    saved = tax_standard - tax_on_spy
    net = spy_current_value - tax_on_spy
    return {
        "label": "Flat Tax — 1 Year",
        "tax_on_spy": tax_on_spy,
        "tax_total": tax_on_spy,
        "net_proceeds": net,
        "tax_saved_vs_standard": saved,
        "gain": gain,
        "effective_rate": tax_on_spy / spy_current_value,
    }

def compute_flat_tax_multi(spy_current_value, spy_cost_basis, spy_years, other_latent_gain, other_years):
    """
    Multi-year flat tax: lump sum x years covers SPY sale AND crystallises other gains.
    """
    total_lump = FLAT_TAX_LUMP_SUM * max(spy_years, other_years)

    spy_gain = spy_current_value - spy_cost_basis
    tax_standard_spy   = max(0, spy_gain) * STANDARD_CGT_RATE
    tax_standard_other = max(0, other_latent_gain) * STANDARD_CGT_RATE
    tax_standard_total = tax_standard_spy + tax_standard_other

    saved = tax_standard_total - total_lump
    net   = spy_current_value - total_lump  # only spy proceeds shown

    return {
        "label": f"Flat Tax — {max(spy_years, other_years)} Years",
        "tax_on_spy": FLAT_TAX_LUMP_SUM * spy_years,
        "tax_other": FLAT_TAX_LUMP_SUM * max(0, other_years - spy_years),
        "tax_total": total_lump,
        "net_proceeds": net,
        "tax_saved_vs_standard": saved,
        "gain_spy": spy_gain,
        "gain_other": other_latent_gain,
        "tax_standard_total": tax_standard_total,
        "effective_rate": total_lump / (spy_current_value + other_latent_gain),
    }

def compute_relocation(spy_current_value, spy_cost_basis, jurisdiction_rate, years_away):
    """
    Move to low/no tax jurisdiction, sell, repatriate.
    Costs: relocation, lost Italian social ties, possible exit tax on unrealised gains.
    Italy imposes exit tax (26%) on unrealised gains > €2m or deemed emigration.
    """
    gain = spy_current_value - spy_cost_basis
    annual_cost = spy_current_value * MOVING_COST_PCT
    total_running_cost = annual_cost * years_away
    tax_on_sale = max(0, gain) * jurisdiction_rate
    total_cost = tax_on_sale + total_running_cost

    tax_standard = max(0, gain) * STANDARD_CGT_RATE
    saved = tax_standard - total_cost

    net = spy_current_value - total_cost

    return {
        "label": f"Relocate ({int(jurisdiction_rate*100)}% CGT, {years_away}yr)",
        "tax_on_spy": tax_on_sale,
        "running_costs": total_running_cost,
        "tax_total": total_cost,
        "net_proceeds": net,
        "tax_saved_vs_standard": saved,
        "gain": gain,
        "effective_rate": total_cost / spy_current_value,
        "annual_cost": annual_cost,
    }

# ─── SIDEBAR ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 📊 Portfolio Parameters")
    st.markdown("---")

    st.markdown("**SPY Position**")
    spy_value = st.number_input(
        "Current Market Value (€)", min_value=100_000, max_value=50_000_000,
        value=1_800_000, step=50_000, format="%d"
    )
    spy_cost = st.number_input(
        "Cost Basis (€)", min_value=0, max_value=int(spy_value),
        value=600_000, step=50_000, format="%d"
    )

    st.markdown("---")
    st.markdown("**Flat Tax — Multi-Year Options**")
    flat_tax_spy_years = st.slider("Years to crystalise SPY gain", 1, 5, 1)
    other_latent_gain = st.slider(
        "Other latent gains to crystalise (€)", 0, 2_000_000, 400_000, 50_000,
        format="€%d"
    )
    flat_tax_other_years = st.slider("Years to crystalise other gains", 0, 5, 2)

    st.markdown("---")
    st.markdown("**Relocation Option**")
    reloc_jurisdiction_rate = st.selectbox(
        "Jurisdiction CGT Rate",
        options=[0.00, 0.05, 0.10],
        format_func=lambda x: f"{int(x*100)}% — {'Dubai / Monaco' if x==0 else 'Malta / Cyprus' if x==0.05 else 'Portugal NHR'}",
    )
    reloc_years = st.slider("Years of relocation", 1, 5, 1)

    st.markdown("---")
    st.markdown("""
    <div class='info-box'>
    ⚠️ <b>Disclaimer</b><br>
    This model is for illustrative purposes only and does not constitute professional tax advice.
    Consult a <em>commercialista</em> or tax counsel for your specific situation.
    </div>
    """, unsafe_allow_html=True)

# ─── Compute all scenarios ────────────────────────────────────────────────────
spy_gain = spy_value - spy_cost
gain_pct = spy_gain / spy_cost * 100 if spy_cost > 0 else 0

s0 = compute_do_nothing(spy_value, spy_cost)
s1 = compute_standard_sale(spy_value, spy_cost)
s2 = compute_flat_tax_1yr(spy_value, spy_cost)
s3 = compute_flat_tax_multi(spy_value, spy_cost, flat_tax_spy_years, other_latent_gain, flat_tax_other_years)
s4 = compute_relocation(spy_value, spy_cost, reloc_jurisdiction_rate, reloc_years)

# ─── MAIN CONTENT ─────────────────────────────────────────────────────────────
st.markdown("""
<div style='padding: 24px 0 8px'>
  <h1 style='color:#e8e4da; font-size:32px; margin:0'>SPY Disposal Options Modeller</h1>
  <p style='color:#6b7080; font-size:15px; margin:6px 0 0'>Italian Fiscal Resident · Non-UCITS Security · Capital Gains Analysis</p>
</div>
""", unsafe_allow_html=True)

# ── KPI Strip ────────────────────────────────────────────────────────────────
c1, c2, c3, c4 = st.columns(4)
with c1:
    st.metric("SPY Market Value", fmt_eur(spy_value))
with c2:
    st.metric("Cost Basis", fmt_eur(spy_cost))
with c3:
    st.metric("Unrealised Gain", fmt_eur(spy_gain), delta=f"+{gain_pct:.1f}%")
with c4:
    std_tax = max(0, spy_gain) * STANDARD_CGT_RATE
    st.metric("Tax at Standard 26%", fmt_eur(std_tax))

st.markdown("<hr style='border-color:#2a2d38; margin:24px 0'>", unsafe_allow_html=True)

# ── Scenario Cards ────────────────────────────────────────────────────────────
st.markdown("""
<div class='section-header'>
  <h2>Scenario Comparison</h2>
  <p>All figures in EUR. Tax saved is relative to selling at standard 26% today.</p>
</div>
""", unsafe_allow_html=True)

col_a, col_b, col_c, col_d, col_e = st.columns(5)

def scenario_card(col, label, tax, net, saved=None, colour="neutral", note=""):
    with col:
        cls = "positive" if saved and saved > 0 else "negative" if saved and saved < 0 else "neutral"
        saved_html = f"<div class='sub {cls}'>{'Saved' if saved and saved>0 else 'Extra cost'}: {fmt_eur(abs(saved)) if saved else '—'}</div>" if saved is not None else ""
        st.markdown(f"""
        <div class='metric-card'>
          <h4>{label}</h4>
          <div class='value'>{fmt_eur(tax)}</div>
          <div class='sub' style='color:#9ca3af'>Tax liability</div>
          {saved_html}
          <div class='sub' style='margin-top:10px;color:#6b7080'>{note}</div>
        </div>
        """, unsafe_allow_html=True)

scenario_card(col_a, "① Do Nothing", 0, spy_value, None, note="Latent tax: " + fmt_eur(s0["latent_tax"]))
scenario_card(col_b, "② Sell Now (26%)", int(s1["tax_on_spy"]), int(s1["net_proceeds"]), 0, note=f"Eff. rate: {s1['effective_rate']*100:.1f}%")
scenario_card(col_c, "③ Flat Tax 1yr (€100k)", int(s2["tax_on_spy"]), int(s2["net_proceeds"]), int(s2["tax_saved_vs_standard"]), note="SPY gain covered by lump sum")
scenario_card(col_d, f"④ Flat Tax {max(flat_tax_spy_years, flat_tax_other_years)}yr", int(s3["tax_total"]), int(s3["net_proceeds"]), int(s3["tax_saved_vs_standard"]), note=f"SPY + €{other_latent_gain/1e3:.0f}k other gains")
scenario_card(col_e, f"⑤ Relocate {int(reloc_jurisdiction_rate*100)}%", int(s4["tax_total"]), int(s4["net_proceeds"]), int(s4["tax_saved_vs_standard"]), note=f"Incl. ~€{s4['annual_cost']/1e3:.0f}k/yr costs")

# ── Charts Row 1 ─────────────────────────────────────────────────────────────
st.markdown("""
<div class='section-header'>
  <h2>Visual Analysis</h2>
</div>
""", unsafe_allow_html=True)

chart_col1, chart_col2 = st.columns(2)

scenarios_labels = ["Do Nothing\n(sell later)", "Sell Now\n26%", f"Flat Tax\n1 Year", f"Flat Tax\n{max(flat_tax_spy_years, flat_tax_other_years)} Years", f"Relocate\n{int(reloc_jurisdiction_rate*100)}%"]
tax_values  = [s0["latent_tax"], s1["tax_on_spy"], s2["tax_on_spy"], s3["tax_total"], s4["tax_total"]]
net_values  = [spy_value, s1["net_proceeds"], s2["net_proceeds"], s3["net_proceeds"], s4["net_proceeds"]]
saved_values = [0, 0, s2["tax_saved_vs_standard"], s3["tax_saved_vs_standard"], s4["tax_saved_vs_standard"]]

colours = ["#6b7080", "#f87171", "#60a5fa", "#4ade80", "#fbbf24"]

with chart_col1:
    fig = go.Figure()
    fig.add_bar(
        x=scenarios_labels,
        y=tax_values,
        marker_color=colours,
        text=[fmt_eur(v) for v in tax_values],
        textposition="outside",
        textfont=dict(color="#e8e4da", size=11),
    )
    fig.update_layout(
        title=dict(text="Total Tax Liability by Scenario", font=dict(color="#e8e4da", size=15), x=0),
        paper_bgcolor="#13161e", plot_bgcolor="#13161e",
        font=dict(color="#9ca3af", family="DM Sans"),
        yaxis=dict(tickformat="€,.0f", gridcolor="#2a2d38", color="#6b7080"),
        xaxis=dict(color="#6b7080"),
        height=360, margin=dict(t=50, b=10, l=10, r=10),
        showlegend=False,
    )
    st.plotly_chart(fig, use_container_width=True)

with chart_col2:
    saved_bar_colours = ["#6b7080" if v <= 0 else "#4ade80" for v in saved_values]
    fig2 = go.Figure()
    fig2.add_bar(
        x=scenarios_labels,
        y=saved_values,
        marker_color=saved_bar_colours,
        text=[fmt_eur(v) for v in saved_values],
        textposition="outside",
        textfont=dict(color="#e8e4da", size=11),
    )
    fig2.add_hline(y=0, line_dash="dash", line_color="#6b7080", line_width=1)
    fig2.update_layout(
        title=dict(text="Tax Saved vs. Selling Now at 26%", font=dict(color="#e8e4da", size=15), x=0),
        paper_bgcolor="#13161e", plot_bgcolor="#13161e",
        font=dict(color="#9ca3af", family="DM Sans"),
        yaxis=dict(tickformat="€,.0f", gridcolor="#2a2d38", color="#6b7080"),
        xaxis=dict(color="#6b7080"),
        height=360, margin=dict(t=50, b=10, l=10, r=10),
        showlegend=False,
    )
    st.plotly_chart(fig2, use_container_width=True)

# ── Charts Row 2 ─────────────────────────────────────────────────────────────
chart_col3, chart_col4 = st.columns(2)

with chart_col3:
    # Waterfall for flat tax multi-year
    waterfall_labels = ["SPY Standard Tax", "Flat Tax Lump Sum(s)", "Net Saving", "Other Gains Std", "Other Gains via Flat"]
    spy_std = max(0, spy_gain) * STANDARD_CGT_RATE
    other_std = max(0, other_latent_gain) * STANDARD_CGT_RATE
    flat_lumps_spy = FLAT_TAX_LUMP_SUM * flat_tax_spy_years
    flat_lumps_other = FLAT_TAX_LUMP_SUM * flat_tax_other_years

    fig3 = go.Figure(go.Waterfall(
        orientation="v",
        measure=["absolute","absolute","relative","absolute","absolute"],
        x=["SPY Tax\n(standard)", f"Flat Lump\n{flat_tax_spy_years}yr (SPY)", "Saving\non SPY", f"Other Gains\nStd 26%", f"Other Gains\nFlat Tax"],
        y=[spy_std, -flat_lumps_spy, spy_std - flat_lumps_spy, other_std, -flat_lumps_other],
        connector=dict(line=dict(color="#2a2d38")),
        increasing=dict(marker=dict(color="#f87171")),
        decreasing=dict(marker=dict(color="#4ade80")),
        totals=dict(marker=dict(color="#60a5fa")),
        text=[fmt_eur(spy_std), fmt_eur(flat_lumps_spy), fmt_eur(spy_std-flat_lumps_spy), fmt_eur(other_std), fmt_eur(flat_lumps_other)],
        textposition="outside",
        textfont=dict(color="#e8e4da", size=10),
    ))
    fig3.update_layout(
        title=dict(text="Flat Tax Multi-Year: Gain Crystallisation Waterfall", font=dict(color="#e8e4da", size=14), x=0),
        paper_bgcolor="#13161e", plot_bgcolor="#13161e",
        font=dict(color="#9ca3af", family="DM Sans"),
        yaxis=dict(tickformat="€,.0f", gridcolor="#2a2d38", color="#6b7080"),
        xaxis=dict(color="#6b7080"),
        height=380, margin=dict(t=50, b=10, l=10, r=10),
    )
    st.plotly_chart(fig3, use_container_width=True)

with chart_col4:
    # Net proceeds comparison pie/donut
    fig4 = make_subplots(rows=1, cols=3, specs=[[{"type":"pie"},{"type":"pie"},{"type":"pie"}]],
                          subplot_titles=["Sell Now 26%", "Flat Tax 1yr", "Relocate"])

    for i, (scenario, col) in enumerate([(s1, 1), (s2, 2), (s4, 3)]):
        tax_v = scenario["tax_on_spy"] if "tax_on_spy" in scenario else scenario["tax_total"]
        run_v = scenario.get("running_costs", 0)
        net_v = spy_value - tax_v - run_v
        vals = [net_v, tax_v, run_v] if run_v > 0 else [net_v, tax_v]
        labs = ["Net Proceeds", "Tax", "Running Costs"] if run_v > 0 else ["Net Proceeds", "Tax"]
        fig4.add_trace(go.Pie(
            labels=labs, values=vals,
            hole=0.55,
            marker=dict(colors=["#4ade80", "#f87171", "#fbbf24"]),
            textinfo="percent",
            textfont=dict(size=10),
            showlegend=i==0,
        ), row=1, col=col)

    fig4.update_layout(
        title=dict(text="Net Proceeds vs. Tax Cost (SPY only)", font=dict(color="#e8e4da", size=14), x=0),
        paper_bgcolor="#13161e", plot_bgcolor="#13161e",
        font=dict(color="#9ca3af", family="DM Sans"),
        legend=dict(font=dict(color="#9ca3af"), bgcolor="#13161e"),
        height=380, margin=dict(t=50, b=10, l=10, r=10),
    )
    st.plotly_chart(fig4, use_container_width=True)

# ── Detailed Breakdown Table ──────────────────────────────────────────────────
st.markdown("""
<div class='section-header'>
  <h2>Detailed Breakdown</h2>
</div>
""", unsafe_allow_html=True)

total_years_flat = max(flat_tax_spy_years, flat_tax_other_years)
total_gain_flat  = spy_gain + other_latent_gain

df = pd.DataFrame([
    {
        "Scenario": "① Do Nothing",
        "Tax on SPY (€)": 0,
        "Tax on Other Gains (€)": 0,
        "Running Costs (€)": 0,
        "Total Cost (€)": 0,
        "Net SPY Proceeds (€)": spy_value,
        "Effective Rate": "—",
        "Tax Saved vs 26% (€)": "—",
        "Key Condition": "Non-UCITS phantom income risk",
    },
    {
        "Scenario": "② Sell Now at 26%",
        "Tax on SPY (€)": int(s1["tax_on_spy"]),
        "Tax on Other Gains (€)": 0,
        "Running Costs (€)": 0,
        "Total Cost (€)": int(s1["tax_total"]),
        "Net SPY Proceeds (€)": int(s1["net_proceeds"]),
        "Effective Rate": f"{s1['effective_rate']*100:.1f}%",
        "Tax Saved vs 26% (€)": "—",
        "Key Condition": "No conditions",
    },
    {
        "Scenario": "③ Flat Tax — 1 Year",
        "Tax on SPY (€)": FLAT_TAX_LUMP_SUM,
        "Tax on Other Gains (€)": 0,
        "Running Costs (€)": 0,
        "Total Cost (€)": FLAT_TAX_LUMP_SUM,
        "Net SPY Proceeds (€)": int(s2["net_proceeds"]),
        "Effective Rate": f"{s2['effective_rate']*100:.1f}%",
        "Tax Saved vs 26% (€)": f"+{fmt_eur(s2['tax_saved_vs_standard'])}",
        "Key Condition": "Art. 24-bis TUIR; prior non-residency",
    },
    {
        "Scenario": f"④ Flat Tax — {total_years_flat} Years",
        "Tax on SPY (€)": int(FLAT_TAX_LUMP_SUM * flat_tax_spy_years),
        "Tax on Other Gains (€)": int(FLAT_TAX_LUMP_SUM * flat_tax_other_years),
        "Running Costs (€)": 0,
        "Total Cost (€)": int(s3["tax_total"]),
        "Net SPY Proceeds (€)": int(s3["net_proceeds"]),
        "Effective Rate": f"{s3['effective_rate']*100:.1f}%",
        "Tax Saved vs 26% (€)": f"+{fmt_eur(s3['tax_saved_vs_standard'])}",
        "Key Condition": f"Crystalise €{(spy_gain+other_latent_gain)/1e3:.0f}k total gains",
    },
    {
        "Scenario": f"⑤ Relocate ({int(reloc_jurisdiction_rate*100)}% CGT, {reloc_years}yr)",
        "Tax on SPY (€)": int(s4["tax_on_spy"]),
        "Tax on Other Gains (€)": 0,
        "Running Costs (€)": int(s4["running_costs"]),
        "Total Cost (€)": int(s4["tax_total"]),
        "Net SPY Proceeds (€)": int(s4["net_proceeds"]),
        "Effective Rate": f"{s4['effective_rate']*100:.1f}%",
        "Tax Saved vs 26% (€)": f"+{fmt_eur(s4['tax_saved_vs_standard'])}" if s4['tax_saved_vs_standard'] > 0 else fmt_eur(s4['tax_saved_vs_standard']),
        "Key Condition": "Genuine residency; Italian exit tax check",
    },
])
df_display = df.set_index("Scenario")

st.dataframe(df_display, use_container_width=True, height=230)

# ── Non-UCITS Risk Note ───────────────────────────────────────────────────────
st.markdown("""
<div class='section-header'>
  <h2>Non-UCITS Specific Risk: SPY ETF</h2>
</div>
""", unsafe_allow_html=True)

nc1, nc2 = st.columns(2)
with nc1:
    st.markdown("""
    <div class='info-box'>
    <b>🇮🇹 Italian Treatment of Non-UCITS ETFs</b><br><br>
    SPY (SPDR S&P 500 ETF) is a US-domiciled ETF and therefore <b>not UCITS-compliant</b>.
    Under Italian tax law (Art. 26-quinquies and 44 TUIR), non-UCITS funds may be subject to
    <b>phantom income taxation</b> — the Italian revenue agency (<em>Agenzia delle Entrate</em>)
    can deem annual accruals of income even without disposal.<br><br>
    <b>Key risks:</b>
    <ul>
      <li>Annual deemed income based on NAV increase (regime dichiarativo)</li>
      <li>No tax deferral benefit unlike UCITS accumulating ETFs</li>
      <li>IVAFE at 0.2% p.a. on value applies regardless</li>
      <li>"Do nothing" is <em>not</em> truly tax-neutral</li>
    </ul>
    </div>
    """, unsafe_allow_html=True)

with nc2:
    st.markdown("""
    <div class='info-box'>
    <b>⚖️ Flat Tax Regime (Art. 24-bis TUIR) Summary</b><br><br>
    The <em>regime dei neo-residenti</em> provides a €100,000 annual lump-sum substitutive tax
    covering all foreign-source income and capital gains. Key conditions:<br><br>
    <ul>
      <li>Must not have been Italian tax resident for 9 of last 10 fiscal years</li>
      <li>Application made in tax return for year of first residency</li>
      <li>Covers up to 15 years; renewable annually at €100k</li>
      <li>Family members can be added at €25k/person per year</li>
      <li>SPY capital gain = foreign-source income → <b>fully covered by lump sum</b></li>
      <li>Italian-source income taxed normally</li>
    </ul>
    </div>
    """, unsafe_allow_html=True)

st.markdown("""
<div class='info-box' style='margin-top:20px; font-size:12px; color:#6b7080'>
⚠️ <b>Disclaimer:</b> This model is for illustrative purposes only and does not constitute tax, legal, or investment advice. 
Italian tax law is complex and subject to change; figures are approximate. Please consult a qualified <em>commercialista</em> or 
international tax advisor before taking any action. Tax saved figures assume the flat tax regime is properly elected and maintained.
</div>
""", unsafe_allow_html=True)
