import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import requests
from datetime import datetime, timezone

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
  .price-badge {
    display: inline-block; background: #1e2130; border: 1px solid #2e3240;
    border-radius: 6px; padding: 4px 10px; font-size: 12px; color: #9aa0ad;
    margin-left: 10px; vertical-align: middle;
  }
  .price-badge b { color: #d4a843; }

  [data-testid="stMetricValue"] { color: #ddd8cc !important; font-family: 'Playfair Display', serif; }
  [data-testid="stMetricLabel"] { color: #7a8090 !important; font-size: 12px; }
  [data-testid="stMetricDelta"] { font-size: 11px !important; }
</style>
""", unsafe_allow_html=True)

# ─── Live Data Fetches ────────────────────────────────────────────────────────
SPY_SHARES = 2707

@st.cache_data(ttl=300)   # SPY price: refresh every 5 minutes
def get_spy_price():
    """Live SPY price from Yahoo Finance. Falls back to 560.0."""
    try:
        r = requests.get(
            "https://query1.finance.yahoo.com/v8/finance/chart/SPY?interval=1m&range=1d",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=6,
        )
        meta  = r.json()["chart"]["result"][0]["meta"]
        price = float(meta["regularMarketPrice"])
        ts    = meta.get("regularMarketTime", 0)
        ts_str = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC") if ts else "live"
        return price, ts_str
    except Exception:
        return 560.0, "fallback"

@st.cache_data(ttl=3600)  # FX rate: refresh every hour
def get_fx_rate():
    """Live USD/EUR from ECB Frankfurter API. Falls back to 0.92."""
    try:
        r    = requests.get("https://api.frankfurter.app/latest?from=USD&to=EUR", timeout=5)
        data = r.json()
        return data["rates"]["EUR"], data["date"]
    except Exception:
        return 0.92, "fallback"

spy_price, spy_ts  = get_spy_price()
fx_rate,   fx_date = get_fx_rate()

# Derived position value from live price × fixed share count
spy_value_usd = spy_price * SPY_SHARES

def usd_to_eur(v): return v * fx_rate
def fmtu(v):       return f"${v:,.0f}"
def fmte(v):       return f"€{v:,.0f}"        # v already in EUR
def fmtu_eur(v):   return fmte(usd_to_eur(v)) # convert USD → EUR → format

# ─── Tax Constants ────────────────────────────────────────────────────────────
# IRPEF 2026: 23% / 33% / 43% national + ~3.3% regional/municipal (Rome estimate)
IRPEF_BRACKETS = [(28_000, 0.23), (50_000, 0.33), (float("inf"), 0.43)]
SURCHARGE      = 0.033
CGT_RATE       = 0.26     # standard substitute tax (UCITS / qualifying gains)
SPY_DIV_YIELD  = 0.0125   # ~1.25% trailing dividend yield
FLAT_TAX_LUMP  = 300_000  # €300k/yr from 1 Jan 2026 (2026 Budget Law)

def compute_irpef_eur(gain_eur, other_income_eur=0):
    """Progressive IRPEF on gain_eur stacked on top of other_income_eur. Returns (tax, eff_rate)."""
    tax, prev = 0, 0
    for ceiling, rate in IRPEF_BRACKETS:
        ceil_val = ceiling if ceiling != float("inf") else other_income_eur + gain_eur + 1
        in_band  = max(0, min(other_income_eur + gain_eur, ceil_val) - max(other_income_eur, prev))
        tax     += in_band * rate
        prev     = ceiling
        if ceil_val > other_income_eur + gain_eur:
            break
    tax += gain_eur * SURCHARGE
    return tax, (tax / gain_eur if gain_eur > 0 else 0)

# ─── SIDEBAR ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## Portfolio Parameters")
    st.markdown("---")

    # SPY position is fixed at 2707 shares × live price — no slider needed
    st.markdown("### SPY Position")
    st.markdown(f"""
**Shares held:** 2,707  
**Live price:** ${spy_price:,.2f}  
**Position value:** ${spy_value_usd:,.0f}  
*(≈ €{usd_to_eur(spy_value_usd):,.0f} at live FX)*  
*Price as of: {spy_ts}*
    """)

    st.markdown("---")
    st.markdown("### Cost Basis")
    spy_cost_usd = st.slider(
        "Total cost basis ($)",
        min_value=500_000, max_value=750_000,
        value=600_000, step=5_000, format="$%d",
        help="Your total acquisition cost for the 2,707 SPY shares"
    )

    st.markdown("---")
    st.markdown("### Income & Other Gains")
    other_income_usd = st.slider(
        "Other annual taxable income ($)",
        min_value=0, max_value=500_000,
        value=80_000, step=5_000, format="$%d",
        help="Pre-existing income — determines which IRPEF bracket the SPY gain is stacked into"
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
        help="0 = sell immediately. Otherwise models future SPY value at the selected growth rate."
    )
    portfolio_growth_rate = st.slider(
        "Portfolio growth rate (% p.a.)",
        min_value=0, max_value=20, value=10, step=1, format="%d%%",
        help="Annual CAGR assumption for SPY. 10% approximates SPY's historical long-run average."
    )

    st.markdown("---")
    st.markdown("### Flat Tax — Multi-Year")
    flat_other_yrs = st.slider(
        "Extra regime years to crystalise other foreign gains",
        min_value=0, max_value=5, value=2,
        help="Additional years (beyond the SPY year) during which the lump sum shelters other foreign-source gains"
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
    <div class='info-box' style='font-size:11px;margin-top:16px'>
    ⚠️ Illustrative only. Not tax advice.<br>Consult a <em>commercialista</em>.
    </div>""", unsafe_allow_html=True)

# ─── Convert inputs to EUR for all tax calculations ──────────────────────────
spy_value_eur       = usd_to_eur(spy_value_usd)
spy_cost_eur        = usd_to_eur(spy_cost_usd)
other_income_eur    = usd_to_eur(other_income_usd)
other_cap_gains_eur = usd_to_eur(other_capital_gains_usd)

spy_gain_usd        = max(0, spy_value_usd - spy_cost_usd)
spy_gain_eur        = max(0, spy_value_eur - spy_cost_eur)
gain_pct            = spy_gain_usd / spy_cost_usd * 100 if spy_cost_usd > 0 else 0
cost_per_share      = spy_cost_usd / SPY_SHARES

# ─── Future value projections ─────────────────────────────────────────────────
cagr = portfolio_growth_rate / 100
if holding_years == 0:
    future_spy_usd = spy_value_usd
    future_spy_eur = spy_value_eur
else:
    future_spy_usd = spy_value_usd * ((1 + cagr) ** holding_years)
    future_spy_eur = usd_to_eur(future_spy_usd)

future_gain_eur                    = max(0, future_spy_eur - spy_cost_eur)
future_irpef_eur, future_irpef_eff = compute_irpef_eur(future_gain_eur, other_income_eur)

# Dividends — taxed at IRPEF each year as redditi di capitale (non-UCITS)
annual_div_eur                      = spy_value_eur * SPY_DIV_YIELD
annual_div_irpef_eur, _             = compute_irpef_eur(annual_div_eur, other_income_eur)
cumul_div_tax_eur                   = annual_div_irpef_eur * holding_years

# IVAFE 0.2%/yr
ivafe_annual_eur = spy_value_eur * 0.002
ivafe_total_eur  = ivafe_annual_eur * holding_years

# Other gains at 26% CGT
other_cgt_eur = other_cap_gains_eur * CGT_RATE

# ─── Scenario computations ────────────────────────────────────────────────────
# ① Baseline: sell at end of holding period at IRPEF
s_sell_tax_eur  = future_irpef_eur + cumul_div_tax_eur + ivafe_total_eur + other_cgt_eur
s_sell_net_eur  = future_spy_eur - future_irpef_eur

# ② Flat Tax 1 Year
s2_tax_eur    = float(FLAT_TAX_LUMP)
s2_net_eur    = spy_value_eur - s2_tax_eur
s2_total_eur  = s2_tax_eur + other_cgt_eur
s2_saved_eur  = s_sell_tax_eur - s2_total_eur

# ③ Flat Tax Multi-Year
multi_yrs     = 1 + flat_other_yrs
s3_lump_eur   = FLAT_TAX_LUMP * multi_yrs
s3_total_eur  = s3_lump_eur + other_cgt_eur
s3_saved_eur  = s_sell_tax_eur - s3_total_eur
s3_net_eur    = spy_value_eur - FLAT_TAX_LUMP

# ④ Relocation
reloc_cgt_eur     = spy_gain_eur * reloc_rate
reloc_running_eur = reloc_cost_annual * reloc_years
s4_cost_eur       = reloc_cgt_eur + reloc_running_eur
s4_total_eur      = s4_cost_eur + other_cgt_eur
s4_net_eur        = spy_value_eur - s4_cost_eur
s4_saved_eur      = s_sell_tax_eur - s4_total_eur

# ─── HEADER ──────────────────────────────────────────────────────────────────
holding_label = "Now" if holding_years == 0 else f"in {holding_years}yr"
fx_src        = f"ECB · {fx_date}" if fx_date != "fallback" else "fallback rate"
price_src     = spy_ts if spy_ts != "fallback" else "fallback price"

st.markdown(f"""
<div style='padding:24px 0 4px'>
  <h1 style='color:#ddd8cc;font-size:30px;margin:0'>
    SPY Disposal Options Modeller
    <span class='price-badge'>SPY <b>${spy_price:,.2f}</b> · {price_src}</span>
    <span class='price-badge'>1 USD = <b>€{fx_rate:.4f}</b> · {fx_src}</span>
  </h1>
  <p style='color:#7a8090;font-size:14px;margin:6px 0 0'>
    Italian Fiscal Resident · 2,707 Shares · Non-UCITS · IRPEF Analysis ·
    Header in USD · Analysis in EUR at live FX
  </p>
</div>""", unsafe_allow_html=True)

# ── KPI Strip: header in USD with EUR sub-value ───────────────────────────────
k1, k2, k3, k4, k5, k6, k7 = st.columns(7)
k1.metric("SPY Price",          f"${spy_price:,.2f}")
k2.metric("Shares Held",        f"{SPY_SHARES:,}")
k3.metric("Position Value",     fmtu(spy_value_usd),   delta=fmtu_eur(spy_value_usd))
k4.metric("Cost Basis",         fmtu(spy_cost_usd),    delta=fmtu_eur(spy_cost_usd))
k5.metric("Unrealised Gain",    fmtu(int(spy_gain_usd)), delta=f"+{gain_pct:.1f}%")
k6.metric("IRPEF on Future Gain", fmte(int(future_irpef_eur)))
k7.metric("Cumul. Dividend Tax",  fmte(int(cumul_div_tax_eur)),
          delta=f"{holding_years}yr @ IRPEF" if holding_years > 0 else "No holding",
          delta_color="inverse")

# ── Non-UCITS Warning ─────────────────────────────────────────────────────────
div_note = (
    f"Over the {holding_years}-year holding period, cumulative dividend IRPEF is estimated at "
    f"<b>€{cumul_div_tax_eur:,.0f}</b>, included in the baseline."
    if holding_years > 0
    else "With a 0-year holding period, no dividend tax accrues."
)
cur_irpef_eff = compute_irpef_eur(spy_gain_eur, other_income_eur)[1]
st.markdown(f"""
<div class='warn-box'>
⚠️ <b>SPY is non-UCITS — two distinct tax problems.</b><br><br>
<b>1. Capital gains:</b> The 26% <em>imposta sostitutiva</em> does not apply. Gains are subject to
full progressive IRPEF (up to 43% + ~3.3% surcharge). At your income level the effective rate on
the current gain is <b>{cur_irpef_eff*100:.1f}%</b> vs 26% for a UCITS equivalent.<br><br>
<b>2. Dividends:</b> SPY distributes quarterly (~1.25% yield, ~€{annual_div_eur:,.0f}/yr).
As a non-UCITS fund these are <em>redditi di capitale</em> under Art. 44 TUIR, taxed at full IRPEF
rates — not the 26% substitute available on UCITS distributions. {div_note}<br><br>
All figures below are in <b>EUR at the live FX rate</b> (1 USD = €{fx_rate:.4f}).
</div>""", unsafe_allow_html=True)

# ── IRPEF detail expander ─────────────────────────────────────────────────────
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
    | SPY: 2,707 shares × ${spy_price:,.2f} = ${spy_value_usd:,.0f} | €{spy_value_eur:,.0f} |
    | Cost basis | €{spy_cost_eur:,.0f} (${spy_cost_usd:,} · ${cost_per_share:,.2f}/share avg) |
    | Current gain | €{spy_gain_eur:,.0f} |
    | Future value ({holding_label} at {portfolio_growth_rate}% CAGR) | €{future_spy_eur:,.0f} |
    | Future gain | €{future_gain_eur:,.0f} |
    | IRPEF on future gain | €{future_irpef_eur:,.0f} (eff. {future_irpef_eff*100:.1f}%) |
    | Cumulative dividends (~1.25%/yr × {holding_years}yr) | €{annual_div_eur*holding_years:,.0f} |
    |