import streamlit as st
import pandas as pd
import plotly.graph_objects as go

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
  @import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;600&family=IBM+Plex+Sans:wght@300;400;500;600&display=swap');
  html, body, [class*="css"] { font-family: 'IBM Plex Sans', sans-serif; }
  h1, h2, h3 { font-family: 'Playfair Display', serif; }
  .stApp { background-color: #0c0e14; color: #ddd8cc; }

  /* ── Sidebar: high-contrast text ── */
  [data-testid="stSidebar"] {
    background-color: #111318;
    border-right: 1px solid #2e3240;
  }
  [data-testid="stSidebar"] label,
  [data-testid="stSidebar"] .stMarkdown p,
  [data-testid="stSidebar"] .stMarkdown li,
  [data-testid="stSidebar"] .stMarkdown strong,
  [data-testid="stSidebar"] span,
  [data-testid="stSidebar"] div {
    color: #c8cdd8 !important;
  }
  [data-testid="stSidebar"] h2,
  [data-testid="stSidebar"] h3 {
    color: #e8e4da !important;
  }
  [data-testid="stSidebar"] .stSlider [data-testid="stMarkdownContainer"] p {
    color: #c8cdd8 !important;
  }
  [data-testid="stSidebar"] hr { border-color: #2e3240; }

  /* ── Scenario cards ── */
  .scenario-card {
    background: #161921; border: 1px solid #252830; border-radius: 10px;
    padding: 18px 20px; height: 100%;
  }
  .sc-title    { font-size: 11px; letter-spacing: 0.15em; text-transform: uppercase; color: #7a8090; margin-bottom: 10px; }
  .sc-main     { font-family: 'Playfair Display', serif; font-size: 24px; color: #ddd8cc; margin-bottom: 4px; }
  .sc-sub      { font-size: 12px; color: #7a8090; margin-bottom: 8px; }
  .sc-saved    { font-size: 14px; font-weight: 600; margin-bottom: 6px; }
  .sc-net      { font-size: 12px; color: #7a8090; margin-bottom: 10px; }
  .sc-hr       { border: none; border-top: 1px solid #252830; margin: 10px 0; }
  .sc-analysis { font-size: 12px; color: #9aa0ad; line-height: 1.65; }
  .green { color: #4ade80 !important; }
  .red   { color: #f87171 !important; }
  .gold  { color: #d4a843 !important; }

  /* ── Section headers ── */
  .section-header { border-left: 3px solid #d4a843; padding-left: 12px; margin: 32px 0 16px; }
  .section-header h2 { color: #ddd8cc; font-size: 19px; margin: 0; }
  .section-header p  { color: #7a8090; font-size: 13px; margin: 4px 0 0; }

  /* ── Info / warn boxes ── */
  .info-box {
    background: #161921; border: 1px solid #d4a84344;
    border-left: 3px solid #d4a843; border-radius: 8px;
    padding: 14px 18px; font-size: 13px; color: #b8a870; margin: 12px 0;
  }
  .warn-box {
    background: #161921; border: 1px solid #f8717144;
    border-left: 3px solid #f87171; border-radius: 8px;
    padding: 14px 18px; font-size: 13px; color: #c08888; margin: 12px 0;
  }

  [data-testid="stMetricValue"] { color: #ddd8cc !important; font-family: 'Playfair Display', serif; }
  [data-testid="stMetricLabel"] { color: #7a8090 !important; font-size: 12px; }
</style>
""", unsafe_allow_html=True)

# ─── Tax helpers ──────────────────────────────────────────────────────────────
# IRPEF 2026: 23% / 33% / 43% + ~3.3% regional/municipal (Rome estimate)
IRPEF_BRACKETS = [(28_000, 0.23), (50_000, 0.33), (float("inf"), 0.43)]
SURCHARGE       = 0.033
CGT_RATE        = 0.26    # standard 26% substitute tax for UCITS / other capital gains
SPY_DIV_YIELD   = 0.0125  # SPY trailing dividend yield ~1.25%
FLAT_TAX_LUMP   = 300_000 # €300k from 1 Jan 2026 (2026 Budget Law), treated at USD parity

def compute_irpef(gain, other_income=0):
    """Progressive IRPEF on gain stacked on top of other_income."""
    tax, prev = 0, 0
    for ceiling, rate in IRPEF_BRACKETS:
        ceil_val = ceiling if ceiling != float("inf") else other_income + gain + 1
        in_band  = max(0, min(other_income + gain, ceil_val) - max(other_income, prev))
        tax     += in_band * rate
        prev     = ceiling
        if ceil_val > other_income + gain:
            break
    tax += gain * SURCHARGE
    eff  = tax / gain if gain > 0 else 0
    return tax, eff

def fmt(v):
    return f"${v:,.0f}"

# ─── SIDEBAR ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## Portfolio Parameters")
    st.markdown("---")

    st.markdown("### SPY Position (USD)")
    spy_value = st.slider(
        "Current Market Value ($)",
        min_value=500_000, max_value=10_000_000,
        value=1_800_000, step=50_000, format="$%d"
    )
    spy_cost = st.slider(
        "Cost Basis ($)",
        min_value=100_000, max_value=int(spy_value),
        value=min(600_000, int(spy_value)), step=25_000, format="$%d"
    )

    st.markdown("---")
    st.markdown("### Income & Other Gains")
    other_income = st.slider(
        "Other annual taxable income ($)",
        min_value=0, max_value=500_000,
        value=80_000, step=5_000, format="$%d",
        help="Pre-existing income — determines which IRPEF bracket SPY gain is stacked into"
    )
    other_capital_gains = st.slider(
        "Other latent capital gains ($)",
        min_value=0, max_value=2_000_000,
        value=400_000, step=25_000, format="$%d",
        help="Other gains (UCITS funds, equities, etc.) taxed at standard 26% — added to all scenarios"
    )

    st.markdown("---")
    st.markdown("### Holding Period")
    holding_years = st.slider(
        "Holding period before disposal (years)",
        min_value=1, max_value=15,
        value=5,
        help="Models future SPY value assuming historical ~10% CAGR, cumulative dividends taxed at IRPEF, and IVAFE each year"
    )

    st.markdown("---")
    st.markdown("### Flat Tax — Multi-Year")
    flat_other_yrs = st.slider(
        "Years of flat tax regime to crystalise other gains",
        min_value=0, max_value=5, value=2,
        help="Number of additional regime years used to shelter other latent gains beyond the SPY year"
    )

    st.markdown("---")
    st.markdown("### Relocation Option")
    reloc_rate = st.selectbox(
        "Jurisdiction CGT Rate",
        options=[0.00, 0.05, 0.10],
        format_func=lambda x: f"{int(x*100)}% — {'Dubai / Monaco' if x==0 else 'Malta / Cyprus' if x==0.05 else 'Portugal'}"
    )
    reloc_years    = st.slider("Years of relocation", 1, 5, 1)
    reloc_cost_pct = st.slider("Annual running costs (% of portfolio)", 0.5, 3.0, 1.5, 0.1,
                                help="Advisors, dual domicile, travel, admin")

    st.markdown("""
    <div class='info-box' style='font-size:11px; margin-top:16px'>
    ⚠️ Illustrative only. Not tax advice.<br>Consult a <em>commercialista</em>.
    </div>""", unsafe_allow_html=True)

# ─── Core computations ────────────────────────────────────────────────────────
spy_gain  = max(0, spy_value - spy_cost)
gain_pct  = spy_gain / spy_cost * 100 if spy_cost > 0 else 0

# SPY dividend income: cumulative over holding period, taxed at IRPEF each year
annual_div        = spy_value * SPY_DIV_YIELD
cumul_divs        = annual_div * holding_years
div_irpef_tax, _  = compute_irpef(annual_div, other_income)
cumul_div_tax     = div_irpef_tax * holding_years  # annual tax on dividends × years

# Future SPY value at end of holding period (10% CAGR assumption, pre-tax)
SPY_CAGR          = 0.10
future_spy_value  = spy_value * ((1 + SPY_CAGR) ** holding_years)
future_gain       = future_spy_value - spy_cost
future_irpef, future_irpef_eff = compute_irpef(future_gain, other_income)

# IVAFE cost over holding period (0.2%/yr on average value, simplified)
ivafe_annual      = spy_value * 0.002
ivafe_total       = ivafe_annual * holding_years

# Other capital gains tax (standard 26% — not IRPEF, not SPY)
other_cgt_tax     = other_capital_gains * CGT_RATE

# ── Scenario: Sell at End of Holding Period (IRPEF on future gain) ────────────
s_sell_tax_total  = future_irpef + cumul_div_tax + ivafe_total + other_cgt_tax
s_sell_net        = future_spy_value - future_irpef  # SPY net only
s_sell_saved      = 0  # this is the baseline

# ── Scenario: Flat Tax — 1 Year (SPY only, sell now) ─────────────────────────
# Lump sum covers SPY gain. Dividends still arise in future but under flat tax regime
# they'd also be covered. Here we model: elect regime, sell SPY this year.
s2_tax            = float(FLAT_TAX_LUMP)
s2_net            = spy_value - s2_tax
# Saving vs selling at end of holding at IRPEF
s2_saved          = s_sell_tax_total - (s2_tax + other_cgt_tax)

# ── Scenario: Flat Tax — Multi-Year (SPY year 1 + other gains over N years) ──
multi_yrs         = 1 + flat_other_yrs   # 1 year for SPY + optional extra years
s3_lump           = FLAT_TAX_LUMP * multi_yrs
# Other latent gains (non-SPY, non-UCITS foreign) also covered by lump sum if foreign-source
# Standard other gains (26% CGT) are NOT covered — they remain at 26%
s3_saved          = s_sell_tax_total - (s3_lump + other_cgt_tax)
s3_net            = spy_value - FLAT_TAX_LUMP  # SPY sold in year 1

# ── Scenario: Relocation ─────────────────────────────────────────────────────
reloc_cgt         = spy_gain * reloc_rate
reloc_running     = spy_value * (reloc_cost_pct / 100) * reloc_years
s4_total_cost     = reloc_cgt + reloc_running
s4_net            = spy_value - s4_total_cost
s4_saved          = s_sell_tax_total - (s4_total_cost + other_cgt_tax)

# ─── HEADER ──────────────────────────────────────────────────────────────────
st.markdown("""
<div style='padding:24px 0 4px'>
  <h1 style='color:#ddd8cc;font-size:30px;margin:0'>SPY Disposal Options Modeller</h1>
  <p style='color:#7a8090;font-size:14px;margin:6px 0 0'>
    Italian Fiscal Resident · Non-UCITS Security · IRPEF Progressive Tax Analysis
  </p>
</div>""", unsafe_allow_html=True)

# ── KPI Strip ────────────────────────────────────────────────────────────────
k1, k2, k3, k4, k5, k6 = st.columns(6)
k1.metric("SPY Value (Now)",         fmt(spy_value))
k2.metric("Cost Basis",              fmt(spy_cost))
k3.metric("Current Gain",            fmt(spy_gain),          delta=f"+{gain_pct:.1f}%")
k4.metric(f"Est. Value in {holding_years}yr", fmt(int(future_spy_value)))
k5.metric("IRPEF on Future Gain",    fmt(int(future_irpef)))
k6.metric("Cumul. Dividend Tax",     fmt(int(cumul_div_tax)), delta=f"{holding_years}yr @ IRPEF", delta_color="inverse")

# ── Non-UCITS / Dividend Warning ─────────────────────────────────────────────
st.markdown(f"""
<div class='warn-box'>
⚠️ <b>SPY is non-UCITS — two tax problems, not one.</b><br><br>
<b>1. Capital gains:</b> The 26% <em>imposta sostitutiva</em> does not apply. Gains are subject to full progressive
IRPEF (up to 43% + ~3.3% surcharge). At your income level, effective rate on the current gain is <b>{compute_irpef(spy_gain, other_income)[1]*100:.1f}%</b>
vs 26% for a UCITS equivalent — a material difference on a {fmt(spy_value)} position.<br><br>
<b>2. Dividends:</b> SPY distributes quarterly dividends (~1.25% yield, ~{fmt(int(annual_div))}/yr at current value).
As a non-UCITS fund, these are classified as <em>redditi di capitale</em> under Art. 44 TUIR and taxed at full
IRPEF progressive rates — <em>not</em> the 26% substitute tax available on UCITS dividends.
Over your {holding_years}-year holding period this cumulative dividend tax is estimated at <b>{fmt(int(cumul_div_tax))}</b>,
which is included in the "Sell at End of Period" baseline.
All scenarios are measured against this baseline total cost.
</div>""", unsafe_allow_html=True)

with st.expander("📐 IRPEF & Baseline Calculation Detail"):
    rows = []
    prev = 0
    for ceiling, rate in IRPEF_BRACKETS:
        ceil_val = ceiling if ceiling != float("inf") else other_income + future_gain + 1
        in_band  = max(0, min(other_income + future_gain, ceil_val) - max(other_income, prev))
        if in_band > 0:
            rows.append({"Band": f"{int(rate*100)}% national",
                         "Gain in Band ($)": int(in_band),
                         "Tax ($)": int(in_band * rate)})
        prev = ceiling
        if ceil_val > other_income + future_gain:
            break
    rows.append({"Band": "~3.3% surcharge", "Gain in Band ($)": int(future_gain), "Tax ($)": int(future_gain * SURCHARGE)})
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    st.markdown(f"""
    | Component | Amount |
    |-----------|--------|
    | Future SPY value (in {holding_years}yr at 10% CAGR) | {fmt(int(future_spy_value))} |
    | Future gain (vs cost basis {fmt(spy_cost)}) | {fmt(int(future_gain))} |
    | IRPEF on future SPY gain | {fmt(int(future_irpef))} |
    | Cumulative dividends over {holding_years}yr (~1.25%/yr) | {fmt(int(cumul_divs))} |
    | IRPEF on dividends (per year × {holding_years}) | {fmt(int(cumul_div_tax))} |
    | IVAFE (0.2%/yr × {holding_years}yr) | {fmt(int(ivafe_total))} |
    | Standard CGT on other gains ({fmt(other_capital_gains)} × 26%) | {fmt(int(other_cgt_tax))} |
    | **Total baseline cost** | **{fmt(int(s_sell_tax_total))}** |
    """)

# ─── Scenario Cards ──────────────────────────────────────────────────────────
st.markdown("""
<div class='section-header'>
  <h2>Scenario Analysis</h2>
  <p>Key figure: dollars saved vs. selling SPY at end of holding period and paying full IRPEF + dividend tax.</p>
</div>""", unsafe_allow_html=True)

def saved_html(saved):
    if saved is None: return ""
    colour = "green" if saved > 0 else "red"
    label  = "Saved vs baseline" if saved >= 0 else "Extra cost vs baseline"
    return f"<div class='sc-saved {colour}'>{label}: {fmt(int(abs(saved)))}</div>"

def card(col, num, title, tax_val, tax_label, net, saved, analysis_html):
    with col:
        st.markdown(f"""
        <div class='scenario-card'>
          <div class='sc-title'>{num} · {title}</div>
          <div class='sc-main'>{fmt(int(tax_val))}</div>
          <div class='sc-sub'>{tax_label}</div>
          {saved_html(saved)}
          <div class='sc-net'>Net SPY proceeds: <b style='color:#ddd8cc'>{fmt(int(net))}</b></div>
          <hr class='sc-hr'/>
          <div class='sc-analysis'>{analysis_html}</div>
        </div>""", unsafe_allow_html=True)

c1, c2, c3, c4 = st.columns(4)

card(c1, "①", f"Sell in {holding_years} Years (IRPEF)",
     s_sell_tax_total,
     f"IRPEF on gain + divs + IVAFE + 26% other gains",
     int(s_sell_net), 0,
     f"The baseline. SPY is held for {holding_years} years (assumed 10% CAGR → {fmt(int(future_spy_value))}). "
     f"IRPEF on future gain: {fmt(int(future_irpef))}. "
     f"Dividend IRPEF over {holding_years}yr: {fmt(int(cumul_div_tax))}. "
     f"IVAFE: {fmt(int(ivafe_total))}. Other gains CGT (26%): {fmt(int(other_cgt_tax))}. "
     f"Total tax cost: <b style='color:#f87171'>{fmt(int(s_sell_tax_total))}</b>. All alternatives are measured against this."
)

card(c2, "②", "Flat Tax — 1 Year (SPY now)",
     FLAT_TAX_LUMP + other_cgt_tax,
     "€300k lump sum + 26% on other gains",
     int(s2_net), int(s2_saved),
     f"Elect Art. 24-bis regime and sell SPY this year. The {fmt(FLAT_TAX_LUMP)} lump sum replaces all IRPEF on the "
     f"SPY gain and future dividend exposure. Other gains ({fmt(other_capital_gains)}) still taxed at standard 26% "
     f"({fmt(int(other_cgt_tax))}). Total cost: {fmt(int(FLAT_TAX_LUMP + other_cgt_tax))}. "
     f"Saves {fmt(int(s2_saved))} vs the {holding_years}-year baseline. "
     f"Condition: not Italian resident for 9 of prior 10 years."
)

card(c3, f"③", f"Flat Tax — {multi_yrs} Years",
     s3_lump + other_cgt_tax,
     f"€300k × {multi_yrs} yrs + 26% on other gains",
     int(s3_net), int(s3_saved),
     f"Year 1: sell SPY under lump sum. Years 1–{flat_other_yrs+1}: lump sum also shelters "
     f"any foreign-source latent gains. Other standard gains ({fmt(other_capital_gains)}) remain at 26% CGT. "
     f"Total flat tax: {fmt(int(s3_lump))}. Total cost incl. other gains: {fmt(int(s3_lump + other_cgt_tax))}. "
     f"Saving vs baseline: {fmt(int(s3_saved))}. Most powerful when other foreign income is large relative to {fmt(FLAT_TAX_LUMP)}/yr."
)

card(c4, f"④", f"Relocate ({int(reloc_rate*100)}% CGT)",
     s4_total_cost + other_cgt_tax,
     f"{reloc_years}yr relocation + running costs + 26% other",
     int(s4_net), int(s4_saved),
     f"Move to {int(reloc_rate*100)}% CGT jurisdiction, sell SPY, repatriate. CGT: {fmt(int(reloc_cgt))}. "
     f"Running costs ({reloc_cost_pct}%/yr × {reloc_years}yr): {fmt(int(reloc_running))}. "
     f"Other gains still 26%: {fmt(int(other_cgt_tax))}. Saving vs baseline: {fmt(int(s4_saved))}. "
     f"Key risk: Italian exit tax (Art. 166-bis TUIR) may crystallise IRPEF immediately on deemed disposal at departure. "
     f"Genuine residency is mandatory and rigorously tested."
)

# ─── Charts ──────────────────────────────────────────────────────────────────
st.markdown("""<div class='section-header'>
  <h2>Visual Comparison</h2>
</div>""", unsafe_allow_html=True)

DARK_BG = "#111318"
GRID    = "#252830"
FONT_C  = "#9aa0ad"
LABEL_C = "#7a8090"

sc_labels  = [f"① Sell in {holding_years}yr\n(IRPEF)", "② Flat Tax\n1 Year",
              f"③ Flat Tax\n{multi_yrs} Years", f"④ Relocate\n{int(reloc_rate*100)}%"]
total_costs = [s_sell_tax_total, FLAT_TAX_LUMP + other_cgt_tax, s3_lump + other_cgt_tax, s4_total_cost + other_cgt_tax]
saved_vals  = [0, s2_saved, s3_saved, s4_saved]
net_spy     = [int(s_sell_net), int(s2_net), int(s3_net), int(s4_net)]
colours     = ["#f87171", "#60a5fa", "#4ade80", "#fbbf24"]

def base_layout(title):
    return dict(
        title=dict(text=title, font=dict(color="#ddd8cc", size=14), x=0),
        paper_bgcolor=DARK_BG, plot_bgcolor=DARK_BG,
        font=dict(color=FONT_C, family="IBM Plex Sans"),
        yaxis=dict(tickprefix="$", tickformat=",.0f", gridcolor=GRID, color=LABEL_C),
        xaxis=dict(color=LABEL_C),
        height=370, margin=dict(t=50, b=10, l=10, r=10),
        showlegend=False,
    )

ch1, ch2 = st.columns(2)

with ch1:
    fig = go.Figure()
    fig.add_bar(x=sc_labels, y=total_costs, marker_color=colours,
                text=[fmt(int(v)) for v in total_costs],
                textposition="outside", textfont=dict(color="#ddd8cc", size=10))
    fig.update_layout(**base_layout("Total Tax + Cost by Scenario"))
    st.plotly_chart(fig, use_container_width=True)

with ch2:
    sv_colours = ["#5a6070"] + ["#4ade80" if v > 0 else "#f87171" for v in saved_vals[1:]]
    fig2 = go.Figure()
    fig2.add_bar(x=sc_labels, y=saved_vals, marker_color=sv_colours,
                 text=["Baseline"] + [fmt(int(v)) for v in saved_vals[1:]],
                 textposition="outside", textfont=dict(color="#ddd8cc", size=10))
    fig2.add_hline(y=0, line_dash="dash", line_color="#5a6070", line_width=1)
    layout2 = base_layout("$ Saved vs. Baseline (Sell in Holding Period at IRPEF)")
    layout2["showlegend"] = False
    fig2.update_layout(**layout2)
    st.plotly_chart(fig2, use_container_width=True)

ch3, ch4 = st.columns(2)

with ch3:
    # Stacked: net proceeds vs tax
    fig3 = go.Figure()
    fig3.add_bar(name="Net SPY Proceeds", x=sc_labels, y=net_spy,
                 marker_color="rgba(74,222,128,0.4)",
                 text=[fmt(v) for v in net_spy],
                 textposition="inside", textfont=dict(color="#ddd8cc", size=10))
    fig3.add_bar(name="Tax / Cost", x=sc_labels, y=total_costs,
                 marker_color="rgba(248,113,113,0.4)",
                 text=[fmt(int(v)) for v in total_costs],
                 textposition="inside", textfont=dict(color="#ddd8cc", size=10))
    layout3 = base_layout("Net SPY Proceeds vs. Total Tax Cost")
    layout3["barmode"]    = "stack"
    layout3["showlegend"] = True
    layout3["legend"]     = dict(font=dict(color="#9ca3af"), bgcolor=DARK_BG)
    fig3.update_layout(**layout3)
    st.plotly_chart(fig3, use_container_width=True)

with ch4:
    # IRPEF band breakdown on FUTURE gain (baseline scenario)
    band_labels, band_gains, band_taxes = [], [], []
    prev = 0
    for ceiling, rate in IRPEF_BRACKETS:
        ceil_val = ceiling if ceiling != float("inf") else other_income + future_gain + 1
        in_band  = max(0, min(other_income + future_gain, ceil_val) - max(other_income, prev))
        if in_band > 0:
            band_labels.append(f"{int(rate*100)}% band")
            band_gains.append(in_band)
            band_taxes.append(in_band * rate)
        prev = ceiling
        if ceil_val > other_income + future_gain:
            break
    fig4 = go.Figure()
    fig4.add_bar(name="Gain in band", x=band_labels, y=band_gains,
                 marker_color="rgba(96,165,250,0.55)",
                 text=[fmt(int(v)) for v in band_gains],
                 textposition="outside", textfont=dict(color="#ddd8cc", size=10))
    fig4.add_bar(name="Tax in band", x=band_labels, y=band_taxes,
                 marker_color="rgba(248,113,113,0.55)",
                 text=[fmt(int(v)) for v in band_taxes],
                 textposition="outside", textfont=dict(color="#ddd8cc", size=10))
    layout4 = base_layout(f"IRPEF Band Breakdown on Future Gain (Year {holding_years})")
    layout4["barmode"]    = "group"
    layout4["showlegend"] = True
    layout4["legend"]     = dict(font=dict(color="#9ca3af"), bgcolor=DARK_BG)
    fig4.update_layout(**layout4)
    st.plotly_chart(fig4, use_container_width=True)

# ── Holding period cost breakdown ────────────────────────────────────────────
st.markdown("""<div class='section-header'>
  <h2>Baseline Cost Waterfall — Sell at End of Holding Period</h2>
  <p>Breakdown of each tax component in the "sell at end of holding period" scenario.</p>
</div>""", unsafe_allow_html=True)

wf_x = ["IRPEF on\nSPY gain", "Dividend\nIRPEF", "IVAFE", "Other gains\n26% CGT", "TOTAL\ncost"]
wf_y = [future_irpef, cumul_div_tax, ivafe_total, other_cgt_tax, s_sell_tax_total]
wf_m = ["absolute", "absolute", "absolute", "absolute", "total"]

fig_wf = go.Figure(go.Waterfall(
    orientation="v", measure=wf_m, x=wf_x, y=wf_y,
    connector=dict(line=dict(color="#252830", width=1)),
    increasing=dict(marker=dict(color="#f87171")),
    totals=dict(marker=dict(color="#d4a843")),
    text=[fmt(int(v)) for v in wf_y],
    textposition="outside", textfont=dict(color="#ddd8cc", size=11),
))
fig_wf.update_layout(
    paper_bgcolor=DARK_BG, plot_bgcolor=DARK_BG,
    font=dict(color=FONT_C, family="IBM Plex Sans"),
    yaxis=dict(tickprefix="$", tickformat=",.0f", gridcolor=GRID, color=LABEL_C),
    xaxis=dict(color=LABEL_C),
    height=380, margin=dict(t=30, b=10, l=10, r=10),
)
st.plotly_chart(fig_wf, use_container_width=True)

# ─── Summary Table ────────────────────────────────────────────────────────────
st.markdown("""<div class='section-header'><h2>Summary Table</h2></div>""", unsafe_allow_html=True)

df = pd.DataFrame([
    {"Scenario": f"① Sell in {holding_years}yr (IRPEF)",
     "SPY Tax ($)": int(future_irpef), "Dividend Tax ($)": int(cumul_div_tax),
     "IVAFE ($)": int(ivafe_total), "Other Gains Tax ($)": int(other_cgt_tax),
     "Total Cost ($)": int(s_sell_tax_total), "Net SPY Proceeds ($)": int(s_sell_net),
     "Saved vs Baseline": "Baseline", "Key Risk": "IRPEF ~46% on gain + dividend drag"},
    {"Scenario": "② Flat Tax 1yr (€300k)",
     "SPY Tax ($)": FLAT_TAX_LUMP, "Dividend Tax ($)": 0,
     "IVAFE ($)": 0, "Other Gains Tax ($)": int(other_cgt_tax),
     "Total Cost ($)": int(FLAT_TAX_LUMP + other_cgt_tax), "Net SPY Proceeds ($)": int(s2_net),
     "Saved vs Baseline": f"+{fmt(int(s2_saved))}", "Key Risk": "9/10yr non-residency required"},
    {"Scenario": f"③ Flat Tax {multi_yrs}yr",
     "SPY Tax ($)": FLAT_TAX_LUMP, "Dividend Tax ($)": 0,
     "IVAFE ($)": 0, "Other Gains Tax ($)": int(other_cgt_tax),
     "Total Cost ($)": int(s3_lump + other_cgt_tax), "Net SPY Proceeds ($)": int(s3_net),
     "Saved vs Baseline": f"+{fmt(int(s3_saved))}", "Key Risk": "Regime eligibility; other gains must be foreign"},
    {"Scenario": f"④ Relocate {int(reloc_rate*100)}%",
     "SPY Tax ($)": int(reloc_cgt), "Dividend Tax ($)": 0,
     "IVAFE ($)": int(reloc_running), "Other Gains Tax ($)": int(other_cgt_tax),
     "Total Cost ($)": int(s4_total_cost + other_cgt_tax), "Net SPY Proceeds ($)": int(s4_net),
     "Saved vs Baseline": f"+{fmt(int(s4_saved))}" if s4_saved > 0 else fmt(int(s4_saved)),
     "Key Risk": "Exit tax; genuine residency required"},
])
st.dataframe(df.set_index("Scenario"), use_container_width=True, height=215)

# ─── Detailed text analysis ───────────────────────────────────────────────────
st.markdown("""<div class='section-header'>
  <h2>Detailed Scenario Analysis</h2>
</div>""", unsafe_allow_html=True)

with st.expander(f"① Sell at End of {holding_years}-Year Holding Period — full analysis"):
    st.markdown(f"""
**The baseline scenario.** SPY is held for {holding_years} years and disposed of at the end.
Assumes 10% annual CAGR — a reasonable long-run approximation of SPY's historical performance.
Future value: **{fmt(int(future_spy_value))}**. Future gain: **{fmt(int(future_gain))}**.

**Capital gains — IRPEF:** SPY is non-UCITS, so the 26% *imposta sostitutiva* does not apply.
The gain is stacked on top of your {fmt(other_income)} other income and assessed to progressive IRPEF.
At the {holding_years}-year horizon the gain has grown substantially, pushing even more into the 43% band.
IRPEF on future gain: **{fmt(int(future_irpef))}** (effective rate: **{future_irpef_eff*100:.1f}%**).

**Dividends — also IRPEF, not 26%:** SPY distributes quarterly dividends (estimated ~1.25% yield,
~{fmt(int(annual_div))}/yr at current value). As income from a non-UCITS fund, these are
*redditi di capitale* under Art. 44 TUIR and taxed at full IRPEF progressive rates, not the 26%
substitute tax available on UCITS fund distributions. Annual dividend IRPEF: ~{fmt(int(div_irpef_tax))}.
Over {holding_years} years: **{fmt(int(cumul_div_tax))}**. This is a real, recurring annual cash cost —
not a deferrable amount.

**IVAFE:** 0.2% wealth tax on foreign-held financial assets per year. Estimated at
{fmt(int(ivafe_annual))}/yr → **{fmt(int(ivafe_total))}** over {holding_years} years.

**Other gains:** Your {fmt(other_capital_gains)} in other latent gains (UCITS, equities etc.)
are taxed at the standard 26% CGT → **{fmt(int(other_cgt_tax))}**.

**Total cost of this path: {fmt(int(s_sell_tax_total))}**. This is the number every other scenario aims to beat.
    """)

with st.expander("② Flat Tax — 1 Year — full analysis"):
    st.markdown(f"""
**The regime:** Art. 24-bis TUIR (*regime dei neo-residenti*) allows qualifying individuals to pay
a flat **€300,000 annual lump sum** in place of IRPEF on all foreign-source income and capital gains.
From 1 January 2026 per the 2026 Budget Law — grandfathered rates apply for earlier entrants
(€100k pre-2025, €200k from 2025).

**What the lump sum covers:**
- The entire SPY capital gain — foreign-source, fully sheltered ✓
- SPY dividends received during the regime year — also foreign-source ✓
- Any other foreign-source income in the same year ✓

**What it does NOT cover:**
- Italian-source income (taxed normally at IRPEF)
- Other capital gains on assets outside the regime scope
- The {fmt(other_capital_gains)} of other gains at 26% CGT — these remain payable

**Cost:** {fmt(FLAT_TAX_LUMP)} lump sum + {fmt(int(other_cgt_tax))} other CGT = **{fmt(int(FLAT_TAX_LUMP + other_cgt_tax))}**

**Saved vs {holding_years}-year baseline: {fmt(int(s2_saved))}**

**Eligibility (all conditions must be met):**
1. Must not have been Italian fiscal resident for **9 of the prior 10 fiscal years**
2. Must transfer residency to Italy and elect the regime in the first return (*Modello Redditi PF*)
3. Not automatic — requires active election
4. Available for up to **15 years**

**If already a long-term Italian resident:** This regime is not available on a new election.
It requires a qualifying period of non-residency prior to (re-)establishing Italian residency.
    """)

with st.expander(f"③ Flat Tax — {multi_yrs} Years — full analysis"):
    st.markdown(f"""
**The strategy:** Use the flat tax regime for {multi_yrs} year(s). Year 1 covers SPY disposal.
{f"Years 2–{flat_other_yrs+1} are used to crystalise additional foreign-source latent gains under the lump sum." if flat_other_yrs > 0 else "No additional years selected — same as scenario ②."}

**Year-by-year:**
- **Year 1:** Sell SPY. Lump sum: {fmt(FLAT_TAX_LUMP)}. IRPEF avoided: {fmt(int(compute_irpef(spy_gain, other_income)[0]))}
{f"- **Years 2–{flat_other_yrs+1}:** Crystalise other foreign gains. Lump sum: {fmt(FLAT_TAX_LUMP)} × {flat_other_yrs} = {fmt(int(FLAT_TAX_LUMP * flat_other_yrs))}" if flat_other_yrs > 0 else ""}
- **Total flat tax:** {fmt(int(s3_lump))}
- **Other 26% CGT gains:** {fmt(int(other_cgt_tax))} (not covered — standard rate applies)
- **Total cost:** {fmt(int(s3_lump + other_cgt_tax))}
- **Saved vs baseline:** {fmt(int(s3_saved))}

**The compounding advantage:** The €300k lump sum covers *all* foreign-source income in a given year.
If you have foreign dividends, bond interest, or other foreign gains beyond SPY, they are sheltered
simultaneously at no extra cost. The effective per-gain cost of the regime falls the more foreign
income is sheltered.

**Key constraint:** Only foreign-source gains qualify. Italian-source assets (Italian property,
Italian securities) are taxed normally. The other {fmt(other_capital_gains)} in gains in this model
are assumed to be UCITS/standard CGT assets at 26% — not covered by the regime.
    """)

with st.expander(f"④ Relocation to {int(reloc_rate*100)}% Jurisdiction — full analysis"):
    st.markdown(f"""
**The approach:** Establish genuine fiscal residency in a jurisdiction applying {int(reloc_rate*100)}% CGT,
sell SPY there, and repatriate (or continue to reside there).

**Cost breakdown:**
| Component | Amount |
|-----------|--------|
| CGT at {int(reloc_rate*100)}% on gain {fmt(int(spy_gain))} | {fmt(int(reloc_cgt))} |
| Running costs ({reloc_cost_pct}%/yr × {reloc_years}yr) | {fmt(int(reloc_running))} |
| Other gains at 26% CGT | {fmt(int(other_cgt_tax))} |
| **Total cost** | **{fmt(int(s4_total_cost + other_cgt_tax))}** |
| **Saved vs {holding_years}-year baseline** | **{fmt(int(s4_saved))}** |
| **Net SPY proceeds** | **{fmt(int(s4_net))}** |

**Dividend treatment during relocation:** Dividends received while resident abroad would be
taxed according to the new jurisdiction's rules. In Dubai/Monaco (0% CGT) dividends may also
be tax-free, potentially adding a further saving not modelled here.

**Critical legal risks:**

**1. Italian exit tax (Art. 166-bis TUIR):** Italy can impose a deemed disposal of all assets
at fair market value upon fiscal emigration if the transfer is considered motivated by tax avoidance.
This crystallises the full IRPEF liability immediately — precisely the outcome the relocation
was designed to avoid. The risk is highest for large, concentrated positions like this.

**2. Genuine residency test:** Italian law determines residency by *anagrafe* registration,
habitual abode, and centre of vital interests. A move that does not genuinely transfer the
centre of life — family, business, social relationships — is unlikely to survive a challenge
from the *Guardia di Finanza*. Residency must be real, documented, and sustained.

**3. The 183-day rule:** Fewer than 183 days per calendar year in Italy. Travel records,
utility bills, and other evidence must be maintained rigorously.

**Conclusion:** Viable where the saving ({fmt(int(s4_saved))}) justifies genuine life
disruption, and particularly compelling if the relocation aligns with other personal plans.
As a pure tax play on a {fmt(spy_value)} position, the legal risk relative to the flat tax
regime is significant — especially given the exit tax exposure.
    """)

# ─── Disclaimer ──────────────────────────────────────────────────────────────
st.markdown("""
<div class='info-box' style='margin-top:32px;font-size:11px;color:#6a7080'>
<b>Disclaimer:</b> Illustrative only. Not tax, legal, or investment advice. IRPEF calculations
approximate; surcharges vary by region/municipality (Rome estimate used). Flat tax lump sums:
€100k (pre-2025 entrants), €200k (2025 entrants), €300k (2026+ entrants). SPY CAGR 10% is
a historical approximation, not a forecast. Dividend yield ~1.25% is approximate.
USD/EUR at parity. Consult a qualified <em>commercialista</em> or international tax counsel.
</div>""", unsafe_allow_html=True)
