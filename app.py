import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import requests
from datetime import datetime

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

  [data-testid="stSidebar"] { background-color: #111318; border-right: 1px solid #2e3240; }
  [data-testid="stSidebar"] label,
  [data-testid="stSidebar"] .stMarkdown p,
  [data-testid="stSidebar"] .stMarkdown li,
  [data-testid="stSidebar"] .stMarkdown strong,
  [data-testid="stSidebar"] span,
  [data-testid="stSidebar"] div { color: #c8cdd8 !important; }
  [data-testid="stSidebar"] h2,
  [data-testid="stSidebar"] h3 { color: #e8e4da !important; }
  [data-testid="stSidebar"] hr { border-color: #2e3240; }

  .scenario-card {
    background: #161921; border: 1px solid #252830; border-radius: 10px;
    padding: 18px 20px; height: 100%;
  }
  .sc-title    { font-size: 11px; letter-spacing: 0.15em; text-transform: uppercase; color: #7a8090; margin-bottom: 10px; }
  .sc-main     { font-family: 'Playfair Display', serif; font-size: 26px; color: #ddd8cc; margin-bottom: 2px; }
  .sc-main-sub { font-size: 12px; color: #7a8090; margin-bottom: 8px; }
  .sc-sub      { font-size: 12px; color: #7a8090; margin-bottom: 8px; }
  .sc-saved    { font-size: 14px; font-weight: 600; margin-bottom: 6px; }
  .sc-net      { font-size: 12px; color: #7a8090; margin-bottom: 10px; }
  .sc-hr       { border: none; border-top: 1px solid #252830; margin: 10px 0; }
  .sc-analysis { font-size: 12px; color: #9aa0ad; line-height: 1.65; }
  .green { color: #4ade80 !important; }
  .red   { color: #f87171 !important; }
  .gold  { color: #d4a843 !important; }

  .section-header { border-left: 3px solid #d4a843; padding-left: 12px; margin: 32px 0 16px; }
  .section-header h2 { color: #ddd8cc; font-size: 19px; margin: 0; }
  .section-header p  { color: #7a8090; font-size: 13px; margin: 4px 0 0; }

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
  .fx-badge {
    display: inline-block; background: #1e2130; border: 1px solid #2e3240;
    border-radius: 6px; padding: 4px 10px; font-size: 12px; color: #9aa0ad;
    margin-left: 12px; vertical-align: middle;
  }

  [data-testid="stMetricValue"] { color: #ddd8cc !important; font-family: 'Playfair Display', serif; }
  [data-testid="stMetricLabel"] { color: #7a8090 !important; font-size: 12px; }
  [data-testid="stMetricDelta"] { font-size: 11px !important; }
</style>
""", unsafe_allow_html=True)

# ─── Live FX Rate ─────────────────────────────────────────────────────────────
@st.cache_data(ttl=3600)  # refresh every hour
def get_usd_eur_rate():
    """Fetch live USD/EUR rate from ECB public API. Falls back to 0.92 if unavailable."""
    try:
        r = requests.get(
            "https://api.frankfurter.app/latest?from=USD&to=EUR",
            timeout=5
        )
        data = r.json()
        rate = data["rates"]["EUR"]
        as_of = data["date"]
        return rate, as_of
    except Exception:
        return 0.92, "fallback"

fx_rate, fx_date = get_usd_eur_rate()

def usd_to_eur(usd):
    return usd * fx_rate

def fmte(usd_val):
    """Format a USD value as EUR string."""
    return f"€{usd_to_eur(usd_val):,.0f}"

def fmtu(usd_val):
    """Format as USD string."""
    return f"${usd_val:,.0f}"

def fmt_both(usd_val):
    """USD primary, EUR secondary."""
    return fmtu(usd_val), fmte(usd_val)

# ─── Tax constants ────────────────────────────────────────────────────────────
IRPEF_BRACKETS = [(28_000, 0.23), (50_000, 0.33), (float("inf"), 0.43)]
SURCHARGE      = 0.033   # regional + municipal, Rome estimate
CGT_RATE       = 0.26    # standard substitute tax for UCITS / qualifying gains
SPY_DIV_YIELD  = 0.0125  # ~1.25% trailing yield
FLAT_TAX_LUMP  = 300_000 # €300k/yr from 1 Jan 2026; model uses EUR, input in USD at FX

# IRPEF brackets are defined in EUR — convert inputs to EUR for IRPEF, report in EUR
def compute_irpef_eur(gain_eur, other_income_eur=0):
    """Progressive IRPEF on gain (EUR) stacked on other_income (EUR). Returns (tax_eur, eff_rate)."""
    tax, prev = 0, 0
    for ceiling, rate in IRPEF_BRACKETS:
        ceil_val = ceiling if ceiling != float("inf") else other_income_eur + gain_eur + 1
        in_band  = max(0, min(other_income_eur + gain_eur, ceil_val) - max(other_income_eur, prev))
        tax     += in_band * rate
        prev     = ceiling
        if ceil_val > other_income_eur + gain_eur:
            break
    tax += gain_eur * SURCHARGE
    eff  = tax / gain_eur if gain_eur > 0 else 0
    return tax, eff

# ─── SIDEBAR ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## Portfolio Parameters")
    st.markdown("---")

    st.markdown("### SPY Position (USD)")
    spy_value_usd = st.slider(
        "Current Market Value ($)",
        min_value=500_000, max_value=10_000_000,
        value=1_800_000, step=50_000, format="$%d"
    )
    spy_cost_usd = st.slider(
        "Cost Basis ($)",
        min_value=100_000, max_value=int(spy_value_usd),
        value=min(600_000, int(spy_value_usd)), step=25_000, format="$%d"
    )

    st.markdown("---")
    st.markdown("### Income & Other Gains")
    other_income_usd = st.slider(
        "Other annual taxable income ($)",
        min_value=0, max_value=500_000,
        value=80_000, step=5_000, format="$%d",
        help="Pre-existing income — determines which IRPEF bracket SPY gain is stacked into"
    )
    other_capital_gains_usd = st.slider(
        "Other latent capital gains ($)",
        min_value=0, max_value=2_000_000,
        value=400_000, step=25_000, format="$%d",
        help="UCITS funds, equities etc. taxed at standard 26% CGT — added to all scenarios"
    )

    st.markdown("---")
    st.markdown("### Holding Period & Growth")
    holding_years = st.slider(
        "Holding period before disposal (years)",
        min_value=0, max_value=15, value=5,
        help="0 = sell immediately. Otherwise models future value at the selected growth rate."
    )
    portfolio_growth_rate = st.slider(
        "Portfolio growth rate (% p.a.)",
        min_value=0, max_value=20, value=10, step=1, format="%d%%",
        help="Annual CAGR assumption for SPY over the holding period. 10% approximates SPY's historical long-run average."
    )

    st.markdown("---")
    st.markdown("### Flat Tax — Multi-Year")
    flat_other_yrs = st.slider(
        "Extra regime years to crystalise other foreign gains",
        min_value=0, max_value=5, value=2,
        help="Years beyond year 1 (SPY year) during which the lump sum also shelters other foreign-source gains"
    )

    st.markdown("---")
    st.markdown("### Relocation Option")
    reloc_rate = st.selectbox(
        "Jurisdiction CGT Rate",
        options=[0.00, 0.05, 0.10],
        format_func=lambda x: f"{int(x*100)}% — {'Dubai / Monaco' if x==0 else 'Malta / Cyprus' if x==0.05 else 'Portugal'}"
    )
    reloc_years = st.slider("Years of relocation", 1, 5, 1)
    reloc_cost_annual = st.slider(
        "Annual running costs (€)",
        min_value=50_000, max_value=500_000,
        value=75_000, step=5_000, format="€%d",
        help="Advisors, dual domicile, travel, admin — nominal annual amount in EUR"
    )

    st.markdown("""
    <div class='info-box' style='font-size:11px; margin-top:16px'>
    ⚠️ Illustrative only. Not tax advice.<br>Consult a <em>commercialista</em>.
    </div>""", unsafe_allow_html=True)

# ─── Convert all USD inputs to EUR for tax calculations ──────────────────────
spy_value_eur         = usd_to_eur(spy_value_usd)
spy_cost_eur          = usd_to_eur(spy_cost_usd)
other_income_eur      = usd_to_eur(other_income_usd)
other_cap_gains_eur   = usd_to_eur(other_capital_gains_usd)

spy_gain_eur          = max(0, spy_value_eur - spy_cost_eur)
spy_gain_usd          = max(0, spy_value_usd - spy_cost_usd)
gain_pct              = spy_gain_usd / spy_cost_usd * 100 if spy_cost_usd > 0 else 0

# ─── Future value projections ─────────────────────────────────────────────────
cagr = portfolio_growth_rate / 100
if holding_years == 0:
    future_spy_eur    = spy_value_eur
    future_spy_usd    = spy_value_usd
else:
    future_spy_usd    = spy_value_usd * ((1 + cagr) ** holding_years)
    future_spy_eur    = usd_to_eur(future_spy_usd)

future_gain_eur       = max(0, future_spy_eur - spy_cost_eur)
future_irpef_eur, future_irpef_eff = compute_irpef_eur(future_gain_eur, other_income_eur)

# SPY dividends — annual, taxed at IRPEF as non-UCITS redditi di capitale
annual_div_eur        = spy_value_eur * SPY_DIV_YIELD
annual_div_irpef_eur, _ = compute_irpef_eur(annual_div_eur, other_income_eur)
cumul_div_tax_eur     = annual_div_irpef_eur * holding_years

# IVAFE 0.2%/yr
ivafe_annual_eur      = spy_value_eur * 0.002
ivafe_total_eur       = ivafe_annual_eur * holding_years

# Other gains at 26% CGT
other_cgt_eur         = other_cap_gains_eur * CGT_RATE

# ─── Scenario: Baseline (sell at end of holding period) ──────────────────────
s_sell_tax_eur        = future_irpef_eur + cumul_div_tax_eur + ivafe_total_eur + other_cgt_eur
s_sell_net_eur        = future_spy_eur - future_irpef_eur

# ─── Scenario: Flat Tax 1 Year ────────────────────────────────────────────────
# FLAT_TAX_LUMP is already in EUR
s2_tax_eur            = float(FLAT_TAX_LUMP)
s2_net_eur            = spy_value_eur - s2_tax_eur
s2_total_eur          = s2_tax_eur + other_cgt_eur
s2_saved_eur          = s_sell_tax_eur - s2_total_eur

# ─── Scenario: Flat Tax Multi-Year ────────────────────────────────────────────
multi_yrs             = 1 + flat_other_yrs
s3_lump_eur           = FLAT_TAX_LUMP * multi_yrs
s3_total_eur          = s3_lump_eur + other_cgt_eur
s3_saved_eur          = s_sell_tax_eur - s3_total_eur
s3_net_eur            = spy_value_eur - FLAT_TAX_LUMP

# ─── Scenario: Relocation ────────────────────────────────────────────────────
reloc_cgt_eur         = spy_gain_eur * reloc_rate
reloc_running_eur     = reloc_cost_annual * reloc_years   # already in EUR
s4_cost_eur           = reloc_cgt_eur + reloc_running_eur
s4_total_eur          = s4_cost_eur + other_cgt_eur
s4_net_eur            = spy_value_eur - s4_cost_eur
s4_saved_eur          = s_sell_tax_eur - s4_total_eur

# ─── HEADER ──────────────────────────────────────────────────────────────────
holding_label = "Now" if holding_years == 0 else f"in {holding_years}yr"
fx_source     = f"ECB · {fx_date}" if fx_date != "fallback" else "fallback rate"

st.markdown(f"""
<div style='padding:24px 0 4px'>
  <h1 style='color:#ddd8cc;font-size:30px;margin:0'>
    SPY Disposal Options Modeller
    <span class='fx-badge'>1 USD = €{fx_rate:.4f} · {fx_source}</span>
  </h1>
  <p style='color:#7a8090;font-size:14px;margin:6px 0 0'>
    Italian Fiscal Resident · Non-UCITS Security · IRPEF Progressive Tax Analysis ·
    Header in USD · Analysis in EUR at live FX
  </p>
</div>""", unsafe_allow_html=True)

# ── KPI Strip — header stays in USD with EUR sub-value ───────────────────────
k1, k2, k3, k4, k5, k6 = st.columns(6)
k1.metric("SPY Value (USD)",  fmtu(spy_value_usd),  delta=fmte(spy_value_usd))
k2.metric("Cost Basis (USD)", fmtu(spy_cost_usd),   delta=fmte(spy_cost_usd))
k3.metric("Current Gain",     fmtu(spy_gain_usd),   delta=f"+{gain_pct:.1f}%")
k4.metric(f"Est. Value {holding_label} (USD)",
          fmtu(int(future_spy_usd)), delta=fmte(int(future_spy_eur)))
k5.metric("IRPEF on Future Gain",
          fmte(int(future_irpef_eur)))
k6.metric("Cumul. Dividend Tax",
          fmte(int(cumul_div_tax_eur)),
          delta=f"{holding_years}yr @ IRPEF" if holding_years > 0 else "No holding",
          delta_color="inverse")

# ── Non-UCITS Warning ─────────────────────────────────────────────────────────
div_note = (
    f"Over your {holding_years}-year holding period cumulative dividend IRPEF is estimated at "
    f"<b>€{cumul_div_tax_eur:,.0f}</b>, included in the baseline."
    if holding_years > 0
    else "With a 0-year holding period no dividend tax accrues — you are selling immediately."
)
st.markdown(f"""
<div class='warn-box'>
⚠️ <b>SPY is non-UCITS — two distinct tax problems.</b><br><br>
<b>1. Capital gains:</b> The 26% <em>imposta sostitutiva</em> does not apply to non-UCITS funds.
Gains fall under full progressive IRPEF (up to 43% national + ~3.3% surcharge). At your income
level the effective rate on the current gain is <b>{compute_irpef_eur(spy_gain_eur, other_income_eur)[1]*100:.1f}%</b>
vs 26% for a UCITS equivalent — a material difference on a position of this size.<br><br>
<b>2. Dividends:</b> SPY distributes quarterly (~1.25% yield, ~€{annual_div_eur:,.0f}/yr).
As a non-UCITS fund these are <em>redditi di capitale</em> under Art. 44 TUIR, taxed at full
IRPEF rates, not the 26% substitute available on UCITS distributions. {div_note}<br><br>
All figures below are in <b>EUR at the live FX rate</b> (1 USD = €{fx_rate:.4f}).
All scenarios are measured against the baseline total cost.
</div>""", unsafe_allow_html=True)

with st.expander("📐 IRPEF & Baseline Calculation Detail (EUR)"):
    rows = []
    prev = 0
    for ceiling, rate in IRPEF_BRACKETS:
        ceil_val = ceiling if ceiling != float("inf") else other_income_eur + future_gain_eur + 1
        in_band  = max(0, min(other_income_eur + future_gain_eur, ceil_val) - max(other_income_eur, prev))
        if in_band > 0:
            rows.append({"Band": f"{int(rate*100)}% national",
                         "Gain in Band (€)": f"€{in_band:,.0f}",
                         "Tax (€)": f"€{in_band*rate:,.0f}"})
        prev = ceiling
        if ceil_val > other_income_eur + future_gain_eur:
            break
    rows.append({"Band": "~3.3% surcharge (regional/municipal)",
                 "Gain in Band (€)": f"€{future_gain_eur:,.0f}",
                 "Tax (€)": f"€{future_gain_eur*SURCHARGE:,.0f}"})
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    st.markdown(f"""
    | Component | EUR |
    |-----------|-----|
    | Future SPY value ({holding_label} at {portfolio_growth_rate}% CAGR) | €{future_spy_eur:,.0f} |
    | Future gain vs cost basis €{spy_cost_eur:,.0f} | €{future_gain_eur:,.0f} |
    | IRPEF on future SPY gain | €{future_irpef_eur:,.0f} |
    | Cumulative dividends (~1.25%/yr × {holding_years}yr) | €{annual_div_eur*holding_years:,.0f} |
    | IRPEF on dividends (per year × {holding_years}) | €{cumul_div_tax_eur:,.0f} |
    | IVAFE (0.2%/yr × {holding_years}yr) | €{ivafe_total_eur:,.0f} |
    | Other gains CGT (€{other_cap_gains_eur:,.0f} × 26%) | €{other_cgt_eur:,.0f} |
    | **Total baseline cost** | **€{s_sell_tax_eur:,.0f}** |
    """)

# ─── Scenario Cards ──────────────────────────────────────────────────────────
st.markdown("""
<div class='section-header'>
  <h2>Scenario Analysis (EUR)</h2>
  <p>Key figure: euros saved vs. the baseline (sell at end of holding period, full IRPEF).</p>
</div>""", unsafe_allow_html=True)

def saved_html(saved_eur):
    if saved_eur is None: return ""
    colour = "green" if saved_eur > 0 else "red"
    label  = "Saved vs baseline" if saved_eur >= 0 else "Extra cost vs baseline"
    return f"<div class='sc-saved {colour}'>{label}: €{abs(saved_eur):,.0f}</div>"

def card(col, num, title, tax_eur, tax_label, net_eur, saved_eur, analysis_html):
    with col:
        st.markdown(f"""
        <div class='scenario-card'>
          <div class='sc-title'>{num} · {title}</div>
          <div class='sc-main'>€{int(tax_eur):,}</div>
          <div class='sc-main-sub'>total tax / cost</div>
          <div class='sc-sub'>{tax_label}</div>
          {saved_html(saved_eur)}
          <div class='sc-net'>Net SPY proceeds: <b style='color:#ddd8cc'>€{int(net_eur):,}</b></div>
          <hr class='sc-hr'/>
          <div class='sc-analysis'>{analysis_html}</div>
        </div>""", unsafe_allow_html=True)

c1, c2, c3, c4 = st.columns(4)

card(c1, "①", f"Sell {holding_label} — IRPEF",
     s_sell_tax_eur,
     "IRPEF on gain + divs + IVAFE + 26% other",
     s_sell_net_eur, 0,
     f"Baseline. {'Sell immediately.' if holding_years==0 else f'Hold {holding_years}yr at {portfolio_growth_rate}% CAGR → €{future_spy_eur:,.0f}.'} "
     f"IRPEF on gain: €{future_irpef_eur:,.0f}. "
     f"Dividend IRPEF ({holding_years}yr): €{cumul_div_tax_eur:,.0f}. "
     f"IVAFE: €{ivafe_total_eur:,.0f}. Other gains (26%): €{other_cgt_eur:,.0f}. "
     f"Total: <b style='color:#f87171'>€{s_sell_tax_eur:,.0f}</b>."
)

card(c2, "②", "Flat Tax — 1 Year",
     s2_total_eur,
     "€300k lump sum + 26% on other gains",
     s2_net_eur, s2_saved_eur,
     f"Elect Art. 24-bis, sell SPY this year. €300k lump sum replaces all IRPEF on SPY gain and dividends. "
     f"Other gains still 26%: €{other_cgt_eur:,.0f}. "
     f"Total: €{s2_total_eur:,.0f}. "
     f"Saving vs baseline: <b style='color:#4ade80'>€{s2_saved_eur:,.0f}</b>. "
     f"Condition: not resident for 9 of prior 10 years."
)

card(c3, f"③", f"Flat Tax — {multi_yrs} Years",
     s3_total_eur,
     f"€300k × {multi_yrs}yr + 26% other gains",
     s3_net_eur, s3_saved_eur,
     f"Year 1: sell SPY. {f'Years 2–{multi_yrs}: crystalise other foreign gains.' if flat_other_yrs > 0 else 'No additional years.'} "
     f"Total lump sum: €{s3_lump_eur:,.0f}. Other gains 26%: €{other_cgt_eur:,.0f}. "
     f"Total cost: €{s3_total_eur:,.0f}. "
     f"Saving: <b style='color:#4ade80'>€{s3_saved_eur:,.0f}</b>. "
     f"Covers all foreign-source income in each regime year."
)

card(c4, f"④", f"Relocate ({int(reloc_rate*100)}% CGT)",
     s4_total_eur,
     f"{reloc_years}yr relocation + €{reloc_cost_annual:,}/yr costs",
     s4_net_eur, s4_saved_eur,
     f"CGT at {int(reloc_rate*100)}%: €{reloc_cgt_eur:,.0f}. "
     f"Running costs (€{reloc_cost_annual:,}/yr × {reloc_years}yr): €{reloc_running_eur:,.0f}. "
     f"Other gains 26%: €{other_cgt_eur:,.0f}. "
     f"Total: €{s4_total_eur:,.0f}. Saving: "
     f"<b style='color:{'#4ade80' if s4_saved_eur>0 else '#f87171'}'>€{s4_saved_eur:,.0f}</b>. "
     f"Key risk: Italian exit tax (Art. 166-bis TUIR) may crystallise IRPEF at departure."
)

# ─── Charts ──────────────────────────────────────────────────────────────────
st.markdown("""<div class='section-header'>
  <h2>Visual Comparison (EUR)</h2>
</div>""", unsafe_allow_html=True)

DARK_BG = "#111318"
GRID    = "#252830"
FONT_C  = "#9aa0ad"
LABEL_C = "#7a8090"

sc_labels   = [f"① Sell {holding_label}\n(IRPEF)", "② Flat Tax\n1 Year",
               f"③ Flat Tax\n{multi_yrs} Years", f"④ Relocate\n{int(reloc_rate*100)}%"]
total_costs = [s_sell_tax_eur, s2_total_eur, s3_total_eur, s4_total_eur]
saved_vals  = [0, s2_saved_eur, s3_saved_eur, s4_saved_eur]
net_vals    = [s_sell_net_eur, s2_net_eur, s3_net_eur, s4_net_eur]
colours     = ["#f87171", "#60a5fa", "#4ade80", "#fbbf24"]

def base_layout(title):
    return dict(
        title=dict(text=title, font=dict(color="#ddd8cc", size=14), x=0),
        paper_bgcolor=DARK_BG, plot_bgcolor=DARK_BG,
        font=dict(color=FONT_C, family="IBM Plex Sans"),
        yaxis=dict(tickprefix="€", tickformat=",.0f", gridcolor=GRID, color=LABEL_C),
        xaxis=dict(color=LABEL_C),
        height=370, margin=dict(t=50, b=10, l=10, r=10),
        showlegend=False,
    )

ch1, ch2 = st.columns(2)

with ch1:
    fig = go.Figure()
    fig.add_bar(x=sc_labels, y=total_costs, marker_color=colours,
                text=[f"€{int(v):,}" for v in total_costs],
                textposition="outside", textfont=dict(color="#ddd8cc", size=10))
    fig.update_layout(**base_layout("Total Tax + Cost by Scenario (€)"))
    st.plotly_chart(fig, use_container_width=True)

with ch2:
    sv_colours = ["#5a6070"] + ["#4ade80" if v > 0 else "#f87171" for v in saved_vals[1:]]
    fig2 = go.Figure()
    fig2.add_bar(x=sc_labels, y=saved_vals, marker_color=sv_colours,
                 text=["Baseline"] + [f"€{int(v):,}" for v in saved_vals[1:]],
                 textposition="outside", textfont=dict(color="#ddd8cc", size=10))
    fig2.add_hline(y=0, line_dash="dash", line_color="#5a6070", line_width=1)
    fig2.update_layout(**base_layout("€ Saved vs. Baseline (IRPEF at End of Holding Period)"))
    st.plotly_chart(fig2, use_container_width=True)

ch3, ch4 = st.columns(2)

with ch3:
    fig3 = go.Figure()
    fig3.add_bar(name="Net SPY Proceeds", x=sc_labels, y=net_vals,
                 marker_color="rgba(74,222,128,0.4)",
                 text=[f"€{int(v):,}" for v in net_vals],
                 textposition="inside", textfont=dict(color="#ddd8cc", size=10))
    fig3.add_bar(name="Tax / Cost", x=sc_labels, y=total_costs,
                 marker_color="rgba(248,113,113,0.4)",
                 text=[f"€{int(v):,}" for v in total_costs],
                 textposition="inside", textfont=dict(color="#ddd8cc", size=10))
    layout3 = base_layout("Net SPY Proceeds vs. Total Tax Cost (€)")
    layout3["barmode"]    = "stack"
    layout3["showlegend"] = True
    layout3["legend"]     = dict(font=dict(color="#9ca3af"), bgcolor=DARK_BG)
    fig3.update_layout(**layout3)
    st.plotly_chart(fig3, use_container_width=True)

with ch4:
    # Baseline waterfall breakdown
    wf_x = ["IRPEF:\nSPY gain", "Dividend\nIRPEF", "IVAFE", "Other gains\n26% CGT", "TOTAL\ncost"]
    wf_y = [future_irpef_eur, cumul_div_tax_eur, ivafe_total_eur, other_cgt_eur, s_sell_tax_eur]
    wf_m = ["absolute", "absolute", "absolute", "absolute", "total"]
    fig4 = go.Figure(go.Waterfall(
        orientation="v", measure=wf_m, x=wf_x, y=wf_y,
        connector=dict(line=dict(color="#252830", width=1)),
        increasing=dict(marker=dict(color="#f87171")),
        totals=dict(marker=dict(color="#d4a843")),
        text=[f"€{int(v):,}" for v in wf_y],
        textposition="outside", textfont=dict(color="#ddd8cc", size=10),
    ))
    layout4 = base_layout(f"Baseline Cost Waterfall — Sell {holding_label} (€)")
    layout4["showlegend"] = False
    fig4.update_layout(**layout4)
    st.plotly_chart(fig4, use_container_width=True)

# ─── IRPEF band chart ────────────────────────────────────────────────────────
st.markdown("""<div class='section-header'>
  <h2>IRPEF Band Breakdown on Future SPY Gain (€)</h2>
  <p>How the gain is distributed across progressive brackets at end of holding period.</p>
</div>""", unsafe_allow_html=True)

band_labels, band_gains, band_taxes = [], [], []
prev = 0
for ceiling, rate in IRPEF_BRACKETS:
    ceil_val = ceiling if ceiling != float("inf") else other_income_eur + future_gain_eur + 1
    in_band  = max(0, min(other_income_eur + future_gain_eur, ceil_val) - max(other_income_eur, prev))
    if in_band > 0:
        band_labels.append(f"{int(rate*100)}% band")
        band_gains.append(in_band)
        band_taxes.append(in_band * rate)
    prev = ceiling
    if ceil_val > other_income_eur + future_gain_eur:
        break

fig5 = go.Figure()
fig5.add_bar(name="Gain in band", x=band_labels, y=band_gains,
             marker_color="rgba(96,165,250,0.55)",
             text=[f"€{int(v):,}" for v in band_gains],
             textposition="outside", textfont=dict(color="#ddd8cc", size=10))
fig5.add_bar(name="Tax in band", x=band_labels, y=band_taxes,
             marker_color="rgba(248,113,113,0.55)",
             text=[f"€{int(v):,}" for v in band_taxes],
             textposition="outside", textfont=dict(color="#ddd8cc", size=10))
layout5 = base_layout(f"IRPEF Bands on SPY Gain — {holding_label} Horizon (€)")
layout5["barmode"]    = "group"
layout5["showlegend"] = True
layout5["legend"]     = dict(font=dict(color="#9ca3af"), bgcolor=DARK_BG)
fig5.update_layout(**layout5)
st.plotly_chart(fig5, use_container_width=True)

# ─── Summary Table ────────────────────────────────────────────────────────────
st.markdown("""<div class='section-header'><h2>Summary Table (EUR)</h2></div>""", unsafe_allow_html=True)

df = pd.DataFrame([
    {"Scenario": f"① Sell {holding_label} (IRPEF)",
     "SPY Tax (€)": f"€{future_irpef_eur:,.0f}", "Div Tax (€)": f"€{cumul_div_tax_eur:,.0f}",
     "IVAFE (€)": f"€{ivafe_total_eur:,.0f}", "Other CGT (€)": f"€{other_cgt_eur:,.0f}",
     "Total Cost (€)": f"€{s_sell_tax_eur:,.0f}", "Net SPY (€)": f"€{s_sell_net_eur:,.0f}",
     "Saved vs Baseline": "Baseline", "Key Risk": "IRPEF ~46% on gain + dividend drag"},
    {"Scenario": "② Flat Tax 1yr (€300k)",
     "SPY Tax (€)": f"€{FLAT_TAX_LUMP:,}", "Div Tax (€)": "€0",
     "IVAFE (€)": "€0", "Other CGT (€)": f"€{other_cgt_eur:,.0f}",
     "Total Cost (€)": f"€{s2_total_eur:,.0f}", "Net SPY (€)": f"€{s2_net_eur:,.0f}",
     "Saved vs Baseline": f"+€{s2_saved_eur:,.0f}", "Key Risk": "9/10yr non-residency required"},
    {"Scenario": f"③ Flat Tax {multi_yrs}yr",
     "SPY Tax (€)": f"€{FLAT_TAX_LUMP:,}", "Div Tax (€)": "€0",
     "IVAFE (€)": "€0", "Other CGT (€)": f"€{other_cgt_eur:,.0f}",
     "Total Cost (€)": f"€{s3_total_eur:,.0f}", "Net SPY (€)": f"€{s3_net_eur:,.0f}",
     "Saved vs Baseline": f"+€{s3_saved_eur:,.0f}", "Key Risk": "Regime eligibility; foreign gains only"},
    {"Scenario": f"④ Relocate {int(reloc_rate*100)}%",
     "SPY Tax (€)": f"€{reloc_cgt_eur:,.0f}", "Div Tax (€)": "€0",
     "IVAFE (€)": f"€{reloc_running_eur:,.0f}", "Other CGT (€)": f"€{other_cgt_eur:,.0f}",
     "Total Cost (€)": f"€{s4_total_eur:,.0f}", "Net SPY (€)": f"€{s4_net_eur:,.0f}",
     "Saved vs Baseline": f"+€{s4_saved_eur:,.0f}" if s4_saved_eur > 0 else f"€{s4_saved_eur:,.0f}",
     "Key Risk": "Exit tax; genuine residency required"},
])
st.dataframe(df.set_index("Scenario"), use_container_width=True, height=215)

# ─── Detailed text analysis ───────────────────────────────────────────────────
st.markdown("""<div class='section-header'>
  <h2>Detailed Scenario Analysis</h2>
</div>""", unsafe_allow_html=True)

hold_desc = "immediately" if holding_years == 0 else f"at the end of a {holding_years}-year holding period"
with st.expander(f"① Sell {holding_label} at IRPEF — full analysis"):
    st.markdown(f"""
**The baseline.** SPY is sold {hold_desc}.
{"No growth is assumed — the current gain of **€{:,.0f}** is the taxable amount.".format(spy_gain_eur)
 if holding_years == 0
 else f"At **{portfolio_growth_rate}% CAGR** over {holding_years} years, SPY grows to **€{future_spy_eur:,.0f}** (from €{spy_value_eur:,.0f} today). Future gain: **€{future_gain_eur:,.0f}**."}

**Capital gains — IRPEF:** SPY is non-UCITS so the 26% *imposta sostitutiva* does not apply.
The gain is stacked on top of your €{other_income_eur:,.0f} other income and assessed to progressive IRPEF.
{"The larger future gain pushes even more into the 43% band. " if holding_years > 0 else ""}
IRPEF on gain: **€{future_irpef_eur:,.0f}** (effective rate: **{future_irpef_eff*100:.1f}%**).

**Dividends — also IRPEF, not 26%:** SPY's quarterly distributions (~1.25% yield, ~€{annual_div_eur:,.0f}/yr)
are *redditi di capitale* under Art. 44 TUIR — full IRPEF applies, not the 26% substitute tax.
{"Annual dividend IRPEF: ~€{:,.0f}. Over {:d} years: **€{:,.0f}**.".format(annual_div_irpef_eur, holding_years, cumul_div_tax_eur)
 if holding_years > 0 else "No dividend tax as holding period is zero."}

**IVAFE:** 0.2%/yr on foreign-held assets → **€{ivafe_total_eur:,.0f}** over {holding_years} year(s).

**Other gains:** €{other_cap_gains_eur:,.0f} at 26% CGT → **€{other_cgt_eur:,.0f}**.

**Total baseline cost: €{s_sell_tax_eur:,.0f}**. This is what every other scenario aims to beat.
(Equivalent to ~{fmtu(int(s_sell_tax_eur / fx_rate))} at current FX.)
    """)

with st.expander("② Flat Tax — 1 Year — full analysis"):
    st.markdown(f"""
**The regime:** Art. 24-bis TUIR (*regime dei neo-residenti*) — a flat **€300,000 annual lump sum**
replaces IRPEF on all foreign-source income and capital gains (2026 Budget Law rate for new entrants).

**Coverage:**
- SPY capital gain (foreign-source) ✓ — full IRPEF of **€{future_irpef_eur:,.0f}** replaced by €300,000
- SPY dividends in the regime year (foreign-source) ✓
- Any other foreign-source income in the same year ✓
- Italian-source income ✗ — taxed normally
- Other gains at 26% CGT ✗ — remain at standard rate: **€{other_cgt_eur:,.0f}**

**Total cost:** €300,000 + €{other_cgt_eur:,.0f} = **€{s2_total_eur:,.0f}**
**Saved vs baseline: €{s2_saved_eur:,.0f}**
(Equivalent to ~{fmtu(int(s2_saved_eur / fx_rate))} at current FX.)

**Grandfathered rates:** €100k (opted in pre-2025) · €200k (from 2025) · €300k (from 2026).
This model uses €300,000 — adjust if you qualify at a lower grandfathered rate.

**Eligibility:** Not resident for 9 of the prior 10 fiscal years · Must be elected in first Italian
tax return (*Modello Redditi PF*) · Valid for up to 15 years · €25k/yr per additional family member.
    """)

with st.expander(f"③ Flat Tax — {multi_yrs} Years — full analysis"):
    st.markdown(f"""
**Strategy:** Use the flat tax regime for {multi_yrs} year(s) to shelter SPY and other foreign gains.

**Structure:**
- **Year 1:** Sell SPY. Lump sum cost: **€300,000**. IRPEF avoided: **€{future_irpef_eur:,.0f}**
{"- **Years 2–{:d}:** Crystalise other foreign-source latent gains. Additional lump sums: **€{:,}**".format(multi_yrs, int(FLAT_TAX_LUMP * flat_other_yrs)) if flat_other_yrs > 0 else "- No additional years selected."}
- **Total flat tax:** €{s3_lump_eur:,.0f}
- **Other gains (26% CGT, not covered):** €{other_cgt_eur:,.0f}
- **Total cost:** €{s3_total_eur:,.0f}
- **Saved vs baseline: €{s3_saved_eur:,.0f}** (~{fmtu(int(s3_saved_eur/fx_rate))})

**Key advantage:** The €300k lump sum shelters *all* foreign-source income in a given year —
dividends, bond interest, other foreign gains — simultaneously at no extra cost. The more foreign
income you have, the lower the effective per-euro cost of the regime.

**Constraint:** Only foreign-source gains qualify. The other {fmte(other_cap_gains_eur)} of gains
in this model are treated as standard CGT assets (UCITS, Italian-listed) at 26% and remain payable.
    """)

with st.expander(f"④ Relocation to {int(reloc_rate*100)}% Jurisdiction — full analysis"):
    st.markdown(f"""
**Approach:** Establish genuine fiscal residency in a {int(reloc_rate*100)}% CGT jurisdiction, sell SPY, repatriate.

| Component | EUR | USD equiv. |
|-----------|-----|------------|
| CGT at {int(reloc_rate*100)}% on gain €{spy_gain_eur:,.0f} | €{reloc_cgt_eur:,.0f} | ~{fmtu(int(reloc_cgt_eur/fx_rate))} |
| Running costs (€{reloc_cost_annual:,}/yr × {reloc_years}yr) | €{reloc_running_eur:,.0f} | ~{fmtu(int(reloc_running_eur/fx_rate))} |
| Other gains 26% CGT | €{other_cgt_eur:,.0f} | ~{fmtu(int(other_cgt_eur/fx_rate))} |
| **Total cost** | **€{s4_total_eur:,.0f}** | **~{fmtu(int(s4_total_eur/fx_rate))}** |
| **Saved vs baseline** | **€{s4_saved_eur:,.0f}** | **~{fmtu(int(s4_saved_eur/fx_rate))}** |
| **Net SPY proceeds** | **€{s4_net_eur:,.0f}** | **~{fmtu(int(s4_net_eur/fx_rate))}** |

**Critical risks:**
1. **Exit tax (Art. 166-bis TUIR):** Fiscal emigration can trigger deemed disposal at fair market value,
crystallising full IRPEF immediately. Highest risk for large, concentrated positions.
2. **Genuine residency:** *Anagrafe* registration, habitual abode, and centre of vital interests must
genuinely transfer. Contested by *Guardia di Finanza* where family, home, and business remain in Italy.
3. **183-day rule:** Fewer than 183 days/yr in Italy. Rigorously document travel and presence.
4. **Re-entry:** Returning to Italy after disposal is clean — no Italian CGT on the already-realised gain.
The period of non-residency must simply be demonstrated as genuine.

**Conclusion:** Most compelling where relocation aligns with genuine life plans. As a pure tax play the
legal risk is significant relative to the flat tax alternative, particularly on a position of this size.
    """)

# ─── Disclaimer ──────────────────────────────────────────────────────────────
st.markdown(f"""
<div class='info-box' style='margin-top:32px;font-size:11px;color:#6a7080'>
<b>Disclaimer:</b> Illustrative only. Not tax, legal, or investment advice. IRPEF rates: 23%/33%/43% national
+ ~3.3% surcharge (Rome estimate). Flat tax lump sums: €100k (pre-2025), €200k (2025), €300k (2026+).
SPY dividend yield ~1.25% approximate. FX rate: 1 USD = €{fx_rate:.4f} ({fx_source}, refreshed hourly).
Consult a qualified <em>commercialista</em> or international tax counsel before acting.
</div>""", unsafe_allow_html=True)
