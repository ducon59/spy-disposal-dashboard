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

# Other gains:
# - Baseline (Italy, IRPEF regime): taxed at 26% Italian CGT
# - Flat Tax ②: lump sum covers foreign-source gains in Year 1 — no extra CGT
# - Flat Tax ③: lump sum covers foreign-source gains across all regime years — no extra CGT
# - Relocation ④: gains crystalised while non-resident — taxed at jurisdiction rate (same as SPY)
other_cgt_baseline_eur  = other_cap_gains_eur * CGT_RATE   # 26% — only applies in baseline
other_cgt_reloc_eur     = other_cap_gains_eur * reloc_rate  # jurisdiction rate while abroad

# ─── Scenario computations ────────────────────────────────────────────────────
# ① Baseline: sell at end of holding period at full IRPEF — other foreign gains taxed at 26%
s_sell_tax_eur  = future_irpef_eur + cumul_div_tax_eur + ivafe_total_eur + other_cgt_baseline_eur
s_sell_net_eur  = future_spy_eur - future_irpef_eur

# ② Flat Tax 1 Year — €300k lump sum covers ALL foreign-source income incl. other gains
s2_tax_eur    = float(FLAT_TAX_LUMP)
s2_net_eur    = spy_value_eur - s2_tax_eur
s2_total_eur  = s2_tax_eur   # other foreign gains sheltered by lump sum — no extra CGT
s2_saved_eur  = s_sell_tax_eur - s2_total_eur

# ③ Flat Tax Multi-Year — each additional regime year shelters further foreign gains
multi_yrs     = 1 + flat_other_yrs
s3_lump_eur   = FLAT_TAX_LUMP * multi_yrs
s3_total_eur  = s3_lump_eur  # other foreign gains covered by additional regime years
s3_saved_eur  = s_sell_tax_eur - s3_total_eur
s3_net_eur    = spy_value_eur - FLAT_TAX_LUMP

# ④ Relocation — other foreign gains also crystalised at jurisdiction CGT rate while non-resident
reloc_cgt_eur     = spy_gain_eur * reloc_rate
reloc_running_eur = reloc_cost_annual * reloc_years
s4_cost_eur       = reloc_cgt_eur + reloc_running_eur + other_cgt_reloc_eur
s4_total_eur      = s4_cost_eur
s4_net_eur        = spy_value_eur - reloc_cgt_eur - reloc_running_eur
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
    | IRPEF on dividends (per year × {holding_years}) | €{cumul_div_tax_eur:,.0f} |
    | IVAFE (0.2%/yr × {holding_years}yr) | €{ivafe_total_eur:,.0f} |
    | Other gains CGT (€{other_cap_gains_eur:,.0f} × 26%, Italian resident) | €{other_cgt_baseline_eur:,.0f} |
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
     s_sell_tax_eur, "IRPEF on gain + divs + IVAFE + 26% other",
     s_sell_net_eur, 0,
     f"Baseline. {'Sell immediately.' if holding_years==0 else f'Hold {holding_years}yr at {portfolio_growth_rate}% CAGR → €{future_spy_eur:,.0f}.'} "
     f"IRPEF on gain: €{future_irpef_eur:,.0f}. Dividend IRPEF ({holding_years}yr): €{cumul_div_tax_eur:,.0f}. "
     f"IVAFE: €{ivafe_total_eur:,.0f}. Other foreign gains (26% CGT): €{other_cgt_baseline_eur:,.0f}. "
     f"Total: <b style='color:#f87171'>€{s_sell_tax_eur:,.0f}</b>.")

card(c2, "②", "Flat Tax — 1 Year",
     s2_total_eur, "€300k lump sum + 26% on other gains",
     s2_net_eur, s2_saved_eur,
     f"Elect Art. 24-bis, sell SPY this year. €300k lump sum replaces all IRPEF on SPY gain and dividends. "
     f"Other foreign gains sheltered by lump sum — €0 extra CGT. Total: €{s2_total_eur:,.0f}. "
     f"Saving: <b style='color:#4ade80'>€{s2_saved_eur:,.0f}</b>. "
     f"Condition: not resident for 9 of prior 10 years.")

card(c3, "③", f"Flat Tax — {multi_yrs} Years",
     s3_total_eur, f"€300k × {multi_yrs}yr + 26% other gains",
     s3_net_eur, s3_saved_eur,
     f"Year 1: sell SPY. {f'Years 2–{multi_yrs}: crystalise other foreign gains.' if flat_other_yrs > 0 else 'No additional years.'} "
     f"Total lump sum: €{s3_lump_eur:,.0f}. Other foreign gains sheltered by regime — €0 extra CGT. "
     f"Total: €{s3_total_eur:,.0f}. Saving: <b style='color:#4ade80'>€{s3_saved_eur:,.0f}</b>.")

card(c4, "④", f"Relocate ({int(reloc_rate*100)}% CGT)",
     s4_total_eur, f"{reloc_years}yr relocation + €{reloc_cost_annual:,}/yr costs",
     s4_net_eur, s4_saved_eur,
     f"CGT at {int(reloc_rate*100)}%: €{reloc_cgt_eur:,.0f}. "
     f"Running costs (€{reloc_cost_annual:,}/yr × {reloc_years}yr): €{reloc_running_eur:,.0f}. "
     f"Other foreign gains at {int(reloc_rate*100)}% CGT (jurisdiction rate): €{other_cgt_reloc_eur:,.0f}. Total: €{s4_total_eur:,.0f}. "
     f"Saving: <b style='color:{'#4ade80' if s4_saved_eur>0 else '#f87171'}'>€{s4_saved_eur:,.0f}</b>. "
     f"Key risk: Italian exit tax (Art. 166-bis TUIR).")

# ─── Charts ──────────────────────────────────────────────────────────────────
st.markdown("""<div class='section-header'><h2>Visual Comparison (EUR)</h2></div>""", unsafe_allow_html=True)

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
    layout3["barmode"] = "stack"
    layout3["showlegend"] = True
    layout3["legend"] = dict(font=dict(color="#9ca3af"), bgcolor=DARK_BG)
    fig3.update_layout(**layout3)
    st.plotly_chart(fig3, use_container_width=True)

with ch4:
    wf_x = ["IRPEF:\nSPY gain", "Dividend\nIRPEF", "IVAFE", "Other gains\n26% CGT", "TOTAL\ncost"]
    wf_y = [future_irpef_eur, cumul_div_tax_eur, ivafe_total_eur, other_cgt_baseline_eur, s_sell_tax_eur]
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
layout5["barmode"] = "group"
layout5["showlegend"] = True
layout5["legend"] = dict(font=dict(color="#9ca3af"), bgcolor=DARK_BG)
fig5.update_layout(**layout5)
st.plotly_chart(fig5, use_container_width=True)

# ─── Summary Table ────────────────────────────────────────────────────────────
st.markdown("""<div class='section-header'><h2>Summary Table (EUR)</h2></div>""", unsafe_allow_html=True)

df = pd.DataFrame([
    {"Scenario": f"① Sell {holding_label} (IRPEF)",
     "SPY Tax (€)": f"€{future_irpef_eur:,.0f}", "Div Tax (€)": f"€{cumul_div_tax_eur:,.0f}",
     "IVAFE (€)": f"€{ivafe_total_eur:,.0f}", "Other CGT (€)": f"€{other_cgt_baseline_eur:,.0f} (26%)",
     "Total Cost (€)": f"€{s_sell_tax_eur:,.0f}", "Net SPY (€)": f"€{s_sell_net_eur:,.0f}",
     "Saved vs Baseline": "Baseline", "Key Risk": "IRPEF ~46% on gain + dividend drag"},
    {"Scenario": "② Flat Tax 1yr (€300k)",
     "SPY Tax (€)": f"€{FLAT_TAX_LUMP:,}", "Div Tax (€)": "€0",
     "IVAFE (€)": "€0", "Other CGT (€)": "€0 (sheltered)",
     "Total Cost (€)": f"€{s2_total_eur:,.0f}", "Net SPY (€)": f"€{s2_net_eur:,.0f}",
     "Saved vs Baseline": f"+€{s2_saved_eur:,.0f}", "Key Risk": "9/10yr non-residency required"},
    {"Scenario": f"③ Flat Tax {multi_yrs}yr",
     "SPY Tax (€)": f"€{FLAT_TAX_LUMP:,}", "Div Tax (€)": "€0",
     "IVAFE (€)": "€0", "Other CGT (€)": "€0 (sheltered)",
     "Total Cost (€)": f"€{s3_total_eur:,.0f}", "Net SPY (€)": f"€{s3_net_eur:,.0f}",
     "Saved vs Baseline": f"+€{s3_saved_eur:,.0f}", "Key Risk": "Regime eligibility; foreign gains only"},
    {"Scenario": f"④ Relocate {int(reloc_rate*100)}%",
     "SPY Tax (€)": f"€{reloc_cgt_eur:,.0f}", "Div Tax (€)": "€0",
     "IVAFE (€)": f"€{reloc_running_eur:,.0f}", "Other CGT (€)": f"€{other_cgt_reloc_eur:,.0f} ({int(reloc_rate*100)}%)",
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
    no_growth = f"No growth assumed — current gain of **€{spy_gain_eur:,.0f}** is the taxable amount."
    with_growth = f"At **{portfolio_growth_rate}% CAGR** over {holding_years} years SPY grows to **€{future_spy_eur:,.0f}**. Future gain: **€{future_gain_eur:,.0f}**."
    div_line = f"Annual dividend IRPEF: ~€{annual_div_irpef_eur:,.0f}. Over {holding_years} years: **€{cumul_div_tax_eur:,.0f}**." if holding_years > 0 else "No dividend tax as holding period is zero."
    st.markdown(f"""
**The baseline.** SPY is sold {hold_desc}.
{no_growth if holding_years == 0 else with_growth}

**Capital gains — IRPEF:** SPY is non-UCITS so the 26% *imposta sostitutiva* does not apply.
Gain stacked on top of your €{other_income_eur:,.0f} other income.
IRPEF on gain: **€{future_irpef_eur:,.0f}** (effective rate: **{future_irpef_eff*100:.1f}%**).

**Dividends — also IRPEF, not 26%:** ~1.25% yield, ~€{annual_div_eur:,.0f}/yr.
*Redditi di capitale* under Art. 44 TUIR — full IRPEF applies. {div_line}

**IVAFE:** 0.2%/yr → **€{ivafe_total_eur:,.0f}** over {holding_years} year(s).

**Other foreign gains:** €{other_cap_gains_eur:,.0f} at 26% CGT (Italian resident rate) → **€{other_cgt_baseline_eur:,.0f}**.

**Total baseline cost: €{s_sell_tax_eur:,.0f}**.
    """)

with st.expander("② Flat Tax — 1 Year — full analysis"):
    st.markdown(f"""
**The regime:** Art. 24-bis TUIR — a flat **€300,000 annual lump sum** replaces IRPEF on all
foreign-source income and capital gains (2026 Budget Law rate for new entrants).

**Coverage:**
- SPY capital gain ✓ — IRPEF of **€{future_irpef_eur:,.0f}** replaced by €300,000
- SPY dividends in regime year ✓
- Other foreign-source income in the same year ✓
- Italian-source income ✗ — taxed normally
- Other foreign gains ✓ — sheltered by the lump sum (they are foreign-source) → **€0 extra CGT**

**Total cost:** €300,000 lump sum = **€{s2_total_eur:,.0f}** · Other foreign gains sheltered · **Saved: €{s2_saved_eur:,.0f}**

**Grandfathered rates:** €100k (pre-2025) · €200k (from 2025) · €300k (from 2026)

**Eligibility:** Not resident 9 of prior 10 fiscal years · Elected in first Italian return
(*Modello Redditi PF*) · Valid up to 15 years · €25k/yr per additional family member.
    """)

with st.expander(f"③ Flat Tax — {multi_yrs} Years — full analysis"):
    extra_years_line = f"Years 2–{multi_yrs}: crystalise other foreign-source gains. Additional lump sums: **€{int(FLAT_TAX_LUMP * flat_other_yrs):,}**" if flat_other_yrs > 0 else "No additional years selected."
    st.markdown(f"""
**Strategy:** Use the flat tax regime for {multi_yrs} year(s).

- **Year 1:** Sell SPY. Lump sum: **€300,000**. IRPEF avoided: **€{future_irpef_eur:,.0f}**
- **{extra_years_line}**
- **Total flat tax:** €{s3_lump_eur:,.0f} · **Other foreign gains: sheltered by regime (€0 extra CGT)**
- **Total cost:** €{s3_total_eur:,.0f} · **Saved: €{s3_saved_eur:,.0f}**

The €300k lump sum covers *all* foreign-source income in a given year simultaneously.
The other foreign gains of €{other_cap_gains_eur:,.0f} are sheltered by the regime years — no 26% CGT applies to foreign-source gains while the lump sum is in force.
    """)

with st.expander(f"④ Relocation to {int(reloc_rate*100)}% Jurisdiction — full analysis"):
    st.markdown(f"""
**Approach:** Genuine fiscal residency in a {int(reloc_rate*100)}% CGT jurisdiction, sell SPY, repatriate.

| Component | EUR |
|-----------|-----|
| CGT at {int(reloc_rate*100)}% on gain €{spy_gain_eur:,.0f} | €{reloc_cgt_eur:,.0f} |
| Running costs (€{reloc_cost_annual:,}/yr × {reloc_years}yr) | €{reloc_running_eur:,.0f} |
| Other foreign gains at {int(reloc_rate*100)}% (jurisdiction rate) | €{other_cgt_reloc_eur:,.0f} |
| **Total cost** | **€{s4_total_eur:,.0f}** |
| **Saved vs baseline** | **€{s4_saved_eur:,.0f}** |
| **Net SPY proceeds** | **€{s4_net_eur:,.0f}** |

**Critical risks:**
1. **Exit tax (Art. 166-bis TUIR):** Deemed disposal on fiscal emigration crystallises full IRPEF immediately.
2. **Genuine residency:** *Anagrafe*, habitual abode, centre of vital interests must genuinely transfer.
3. **183-day rule:** Fewer than 183 days/yr in Italy — document meticulously.
4. **Re-entry:** Clean after genuine non-residency — no Italian CGT on already-realised gain.
    """)

# ─── Disclaimer ──────────────────────────────────────────────────────────────
fx_src = f"ECB · {fx_date}" if fx_date != "fallback" else "fallback rate"
st.markdown(f"""
<div class='info-box' style='margin-top:32px;font-size:11px;color:#6a7080'>
<b>Disclaimer:</b> Illustrative only. Not tax, legal, or investment advice. IRPEF rates: 23%/33%/43%
national + ~3.3% surcharge (Rome estimate). Flat tax lump sums: €100k (pre-2025), €200k (2025),
€300k (2026+). SPY dividend yield ~1.25% approximate. SPY price refreshed every 5 min (Yahoo Finance);
FX rate (1 USD = €{fx_rate:.4f}) refreshed hourly ({fx_src}). Consult a qualified
<em>commercialista</em> or international tax counsel before acting.
</div>""", unsafe_allow_html=True)
