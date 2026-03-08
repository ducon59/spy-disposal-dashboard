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
  [data-testid="stSidebar"] { background-color: #111318; border-right: 1px solid #252830; }
  .scenario-card {
    background: #161921; border: 1px solid #252830; border-radius: 10px;
    padding: 18px 20px; height: 100%;
  }
  .sc-title { font-size: 11px; letter-spacing: 0.15em; text-transform: uppercase; color: #5a6070; margin-bottom: 10px; }
  .sc-main  { font-family: 'Playfair Display', serif; font-size: 24px; color: #ddd8cc; margin-bottom: 4px; }
  .sc-sub   { font-size: 12px; color: #5a6070; margin-bottom: 8px; }
  .sc-saved { font-size: 14px; font-weight: 600; margin-bottom: 6px; }
  .sc-net   { font-size: 12px; color: #5a6070; margin-bottom: 10px; }
  .sc-hr    { border: none; border-top: 1px solid #252830; margin: 10px 0; }
  .sc-analysis { font-size: 12px; color: #8a95a0; line-height: 1.65; }
  .green { color: #4ade80 !important; }
  .red   { color: #f87171 !important; }
  .gold  { color: #d4a843 !important; }
  .section-header { border-left: 3px solid #d4a843; padding-left: 12px; margin: 32px 0 16px; }
  .section-header h2 { color: #ddd8cc; font-size: 19px; margin: 0; }
  .section-header p  { color: #5a6070; font-size: 13px; margin: 4px 0 0; }
  .info-box {
    background: #161921; border: 1px solid #d4a84344;
    border-left: 3px solid #d4a843; border-radius: 8px;
    padding: 14px 18px; font-size: 13px; color: #9a8860; margin: 12px 0;
  }
  .warn-box {
    background: #161921; border: 1px solid #f8717144;
    border-left: 3px solid #f87171; border-radius: 8px;
    padding: 14px 18px; font-size: 13px; color: #a07070; margin: 12px 0;
  }
  [data-testid="stMetricValue"] { color: #ddd8cc !important; font-family: 'Playfair Display', serif; }
  [data-testid="stMetricLabel"] { color: #5a6070 !important; font-size: 12px; }
</style>
""", unsafe_allow_html=True)

# ─── IRPEF Calculator ─────────────────────────────────────────────────────────
# 2026 rates: 23% / 33% / 43% national + ~3.3% regional/municipal (Rome estimate)
IRPEF_BRACKETS = [(28_000, 0.23), (50_000, 0.33), (float("inf"), 0.43)]
SURCHARGE = 0.033

def compute_irpef(gain, other_income=0):
    """Tax on gain, stacked on top of other_income."""
    tax = 0
    prev = 0
    for ceiling, rate in IRPEF_BRACKETS:
        ceil_val = ceiling if ceiling != float("inf") else other_income + gain + 1
        low  = max(other_income, prev)
        high = min(other_income + gain, ceil_val)
        in_band = max(0, high - low)
        tax += in_band * rate
        prev = ceiling
        if ceil_val > other_income + gain:
            break
    tax += gain * SURCHARGE
    eff = tax / gain if gain > 0 else 0
    return tax, eff

def fmt(v):
    return f"${v:,.0f}"

# ─── Flat tax lump sum ────────────────────────────────────────────────────────
# From 1 Jan 2026: €300,000 for new entrants per 2026 Budget Law
# Treated as USD at parity for the model
FLAT_TAX_LUMP = 300_000

# ─── SIDEBAR ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## Portfolio Parameters")
    st.markdown("---")
    st.markdown("**SPY Position (USD)**")
    spy_value = st.number_input("Current Market Value ($)", min_value=100_000,
        max_value=50_000_000, value=1_800_000, step=50_000, format="%d")
    spy_cost = st.number_input("Cost Basis ($)", min_value=0,
        max_value=int(spy_value), value=600_000, step=50_000, format="%d")

    st.markdown("---")
    st.markdown("**Your Other Annual Income**")
    other_income = st.number_input("Other taxable income ($/yr)",
        min_value=0, max_value=1_000_000, value=80_000, step=5_000, format="%d",
        help="Determines which IRPEF bracket the SPY gain is stacked into")

    st.markdown("---")
    st.markdown("**Flat Tax — Multi-Year**")
    flat_spy_yrs   = st.slider("Years to crystalise SPY gain", 1, 5, 1)
    other_gain     = st.slider("Other latent gains ($)", 0, 2_000_000, 400_000, 50_000, format="$%d")
    flat_other_yrs = st.slider("Years to crystalise other gains", 0, 5, 2)

    st.markdown("---")
    st.markdown("**Relocation Option**")
    reloc_rate = st.selectbox("Jurisdiction CGT Rate", options=[0.00, 0.05, 0.10],
        format_func=lambda x: f"{int(x*100)}% — {'Dubai/Monaco' if x==0 else 'Malta/Cyprus' if x==0.05 else 'Portugal'}")
    reloc_years    = st.slider("Years of relocation", 1, 5, 1)
    reloc_cost_pct = st.slider("Annual running costs (% of portfolio)", 0.5, 3.0, 1.5, 0.1)

    st.markdown("""<div class='info-box' style='font-size:11px'>
    ⚠️ Illustrative only. Not tax advice. Consult a <em>commercialista</em>.</div>""",
    unsafe_allow_html=True)

# ─── Compute all scenarios ────────────────────────────────────────────────────
spy_gain   = spy_value - spy_cost
gain_pct   = spy_gain / spy_cost * 100 if spy_cost > 0 else 0
irpef_tax, irpef_eff = compute_irpef(spy_gain, other_income)

# S2: Flat tax 1 year
s2_tax   = float(FLAT_TAX_LUMP)
s2_net   = spy_value - s2_tax
s2_saved = irpef_tax - s2_tax

# S3: Flat tax multi-year (SPY + other gains)
multi_yrs    = max(flat_spy_yrs, flat_other_yrs)
s3_lump      = FLAT_TAX_LUMP * multi_yrs
other_irpef, _ = compute_irpef(other_gain, other_income)
total_irpef  = irpef_tax + other_irpef
s3_saved     = total_irpef - s3_lump
s3_net       = spy_value - (FLAT_TAX_LUMP * flat_spy_yrs)

# S4: Relocation
reloc_cgt      = max(0, spy_gain) * reloc_rate
reloc_running  = spy_value * (reloc_cost_pct / 100) * reloc_years
s4_total_cost  = reloc_cgt + reloc_running
s4_net         = spy_value - s4_total_cost
s4_saved       = irpef_tax - s4_total_cost

# ─── HEADER ──────────────────────────────────────────────────────────────────
st.markdown("""
<div style='padding:24px 0 4px'>
  <h1 style='color:#ddd8cc;font-size:30px;margin:0'>SPY Disposal Options Modeller</h1>
  <p style='color:#5a6070;font-size:14px;margin:6px 0 0'>
    Italian Fiscal Resident · Non-UCITS Security · IRPEF Progressive Tax Analysis
  </p>
</div>""", unsafe_allow_html=True)

# KPI strip
k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("SPY Market Value",     fmt(spy_value))
k2.metric("Cost Basis",           fmt(spy_cost))
k3.metric("Unrealised Gain",      fmt(spy_gain),    delta=f"+{gain_pct:.1f}%")
k4.metric("IRPEF if Sold Now",    fmt(int(irpef_tax)))
k5.metric("Effective IRPEF Rate", f"{irpef_eff*100:.1f}%")

st.markdown(f"""
<div class='warn-box'>
⚠️ <b>SPY is non-UCITS:</b> As a US-domiciled ETF, SPY does not qualify for Italy's 26%
<em>imposta sostitutiva</em>. Capital gains are subject to full progressive <b>IRPEF</b>
(23%–43% national + regional/municipal surcharges). With your other income of {fmt(other_income)},
the marginal rate on the SPY gain reaches approximately {irpef_eff*100:.1f}%.
<b>All "savings" below are measured against the IRPEF cost of selling today: {fmt(int(irpef_tax))}.</b>
</div>""", unsafe_allow_html=True)

with st.expander("📐 IRPEF Calculation Detail"):
    # Band breakdown
    rows = []
    prev = 0
    for ceiling, rate in IRPEF_BRACKETS:
        ceil_val = ceiling if ceiling != float("inf") else other_income + spy_gain + 1
        low  = max(other_income, prev)
        high = min(other_income + spy_gain, ceil_val)
        in_band = max(0, high - low)
        if in_band > 0:
            rows.append({"Band": f"{int(rate*100)}% national", "Gain in Band ($)": int(in_band),
                         "National Tax ($)": int(in_band * rate)})
        prev = ceiling
        if ceil_val > other_income + spy_gain:
            break
    rows.append({"Band": f"~3.3% surcharge (regional/municipal)", "Gain in Band ($)": int(spy_gain),
                 "National Tax ($)": int(spy_gain * SURCHARGE)})
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    st.markdown(f"""
    Other income **{fmt(other_income)}** occupies lower brackets. SPY gain **{fmt(spy_gain)}**
    is stacked on top → mostly at **43% + 3.3% = ~46.3%**. Total IRPEF: **{fmt(int(irpef_tax))}**.
    Net proceeds after tax: **{fmt(int(spy_value - irpef_tax))}**.
    """)

# ─── Scenario Cards ──────────────────────────────────────────────────────────
st.markdown("""
<div class='section-header'>
  <h2>Scenario Analysis</h2>
  <p>Key figure: dollars saved vs. disposing of SPY at full IRPEF rates. All figures in USD.</p>
</div>""", unsafe_allow_html=True)

def saved_str(saved, colour):
    if saved is None: return ""
    label = "Saved vs IRPEF" if saved >= 0 else "Extra cost vs IRPEF"
    return f"<div class='sc-saved {colour}'>{label}: {fmt(int(abs(saved)))}</div>"

def card(col, num, title, tax_val, tax_label, net, saved, colour, analysis_html):
    with col:
        st.markdown(f"""
        <div class='scenario-card'>
          <div class='sc-title'>{num} · {title}</div>
          <div class='sc-main'>{fmt(int(tax_val))}</div>
          <div class='sc-sub'>{tax_label}</div>
          {saved_str(saved, colour)}
          <div class='sc-net'>Net SPY proceeds: <b style='color:#ddd8cc'>{fmt(int(net))}</b></div>
          <hr class='sc-hr'/>
          <div class='sc-analysis'>{analysis_html}</div>
        </div>""", unsafe_allow_html=True)

c1, c2, c3, c4, c5 = st.columns(5)

card(c1, "①", "Do Nothing",
     0, "No tax event today", spy_value, None, "gold",
     f"Position stays open. No immediate tax. However SPY's non-UCITS status means Italy may impute <b>annual phantom income</b> on NAV increases under Art. 44 TUIR — deferral is not guaranteed. IVAFE at 0.2%/yr ({fmt(int(spy_value*0.002))}) is due regardless. Latent IRPEF exposure: <b style='color:#f87171'>{fmt(int(irpef_tax))}</b>. Every year of appreciation grows that liability further at ~46% marginal."
)
card(c2, "②", "Sell Now (IRPEF)",
     irpef_tax, f"IRPEF at {irpef_eff*100:.1f}% effective", spy_value - irpef_tax, 0, "red",
     f"The benchmark. SPY is non-UCITS so the 26% substitute tax does not apply. The gain is stacked on top of {fmt(other_income)} other income, hitting the 43% national band + 3.3% surcharge. Effective rate: <b>{irpef_eff*100:.1f}%</b>. This is the worst-case disposal outcome and the cost all alternatives aim to beat."
)
card(c3, "③", "Flat Tax — 1 Year",
     FLAT_TAX_LUMP, "Art. 24-bis lump sum (€300k)", s2_net, s2_saved, "green",
     f"Under Art. 24-bis TUIR, new Italian residents pay <b>€300,000/yr</b> covering all foreign-source income — including the SPY gain. Replaces {fmt(int(irpef_tax))} IRPEF with {fmt(FLAT_TAX_LUMP)}. <b>Condition:</b> not resident for 9 of prior 10 fiscal years. If already long-term resident, cannot newly elect. The regime lasts up to 15 years at the applicable lump sum rate."
)
card(c4, f"④", f"Flat Tax — {multi_yrs} Yrs",
     s3_lump, f"€300k × {multi_yrs} yrs (SPY + other gains)", s3_net, s3_saved, "green",
     f"Extends the regime to also crystalise <b>{fmt(other_gain)}</b> in other gains. Without it: {fmt(int(total_irpef))} total IRPEF. With it: {fmt(int(s3_lump))} in flat tax. Regime covers <em>all</em> foreign income in each year, so if you have other foreign income too, the per-gain cost falls further. Most powerful when other latent gains are large."
)
card(c5, "⑤", f"Relocate {int(reloc_rate*100)}%",
     s4_total_cost, f"{reloc_years}yr stay + running costs", s4_net, s4_saved,
     "green" if s4_saved > 0 else "red",
     f"Establish genuine residency in a {int(reloc_rate*100)}% CGT jurisdiction, sell SPY, return. CGT: {fmt(int(reloc_cgt))}. Running costs ({reloc_cost_pct}%/yr × {reloc_years}yr): {fmt(int(reloc_running))}. <b>Key risk:</b> Italy's exit tax (Art. 166-bis TUIR) may deem departure a fiscal emigration and crystallise IRPEF immediately. Residency must be genuine — heavily scrutinised."
)

# ─── Charts ──────────────────────────────────────────────────────────────────
st.markdown("""<div class='section-header'>
  <h2>Visual Comparison</h2>
</div>""", unsafe_allow_html=True)

sc_labels = ["① Do Nothing\n(latent)", "② Sell Now\nIRPEF", "③ Flat Tax\n1 Year",
             f"④ Flat Tax\n{multi_yrs} Years", f"⑤ Relocate\n{int(reloc_rate*100)}%"]
tax_vals   = [irpef_tax, irpef_tax, FLAT_TAX_LUMP, s3_lump, s4_total_cost]
saved_vals = [0, 0, s2_saved, s3_saved, s4_saved]
net_vals   = [spy_value, spy_value - irpef_tax, s2_net, s3_net, s4_net]
colours    = ["#5a6070", "#f87171", "#60a5fa", "#4ade80", "#fbbf24"]

DARK_BG = "#111318"
GRID    = "#252830"
FONT_C  = "#8a9080"
LABEL_C = "#5a6070"

def base_layout(title):
    return dict(
        title=dict(text=title, font=dict(color="#ddd8cc", size=14), x=0),
        paper_bgcolor=DARK_BG, plot_bgcolor=DARK_BG,
        font=dict(color=FONT_C, family="IBM Plex Sans"),
        yaxis=dict(tickprefix="$", tickformat=",.0f", gridcolor=GRID, color=LABEL_C),
        xaxis=dict(color=LABEL_C),
        height=370, margin=dict(t=50, b=10, l=10, r=10),
    )

ch1, ch2 = st.columns(2)

with ch1:
    fig = go.Figure()
    fig.add_bar(x=sc_labels, y=tax_vals, marker_color=colours,
                text=[fmt(int(v)) for v in tax_vals],
                textposition="outside", textfont=dict(color="#ddd8cc", size=10))
    fig.update_layout(**base_layout("Total Tax / Cost by Scenario"), showlegend=False)
    st.plotly_chart(fig, use_container_width=True)

with ch2:
    sv_colours = ["#5a6070", "#5a6070"] + ["#4ade80" if v > 0 else "#f87171" for v in saved_vals[2:]]
    fig2 = go.Figure()
    fig2.add_bar(x=sc_labels, y=saved_vals, marker_color=sv_colours,
                 text=["—", "—"] + [fmt(int(v)) for v in saved_vals[2:]],
                 textposition="outside", textfont=dict(color="#ddd8cc", size=10))
    fig2.add_hline(y=0, line_dash="dash", line_color="#5a6070", line_width=1)
    fig2.update_layout(**base_layout("$ Saved vs. Selling at IRPEF Today"), showlegend=False)
    st.plotly_chart(fig2, use_container_width=True)

ch3, ch4 = st.columns(2)

with ch3:
    fig3 = go.Figure()
    fig3.add_bar(name="Net Proceeds", x=sc_labels, y=net_vals,
                 marker_color="rgba(74, 222, 128, 0.4)",
                 text=[fmt(int(v)) for v in net_vals],
                 textposition="inside", textfont=dict(color="#ddd8cc", size=10))
    fig3.add_bar(name="Tax / Cost", x=sc_labels, y=tax_vals,
                 marker_color="rgba(248, 113, 113, 0.4)",
                 text=[fmt(int(v)) for v in tax_vals],
                 textposition="inside", textfont=dict(color="#ddd8cc", size=10))
    layout3 = base_layout("Net Proceeds vs. Tax Cost (SPY only)")
    layout3["barmode"] = "stack"
    layout3["legend"]  = dict(font=dict(color="#9ca3af"), bgcolor=DARK_BG)
    fig3.update_layout(**layout3)
    st.plotly_chart(fig3, use_container_width=True)

with ch4:
    # IRPEF band breakdown
    band_labels, band_gains, band_taxes = [], [], []
    prev = 0
    for ceiling, rate in IRPEF_BRACKETS:
        ceil_val = ceiling if ceiling != float("inf") else other_income + spy_gain + 1
        low  = max(other_income, prev)
        high = min(other_income + spy_gain, ceil_val)
        in_band = max(0, high - low)
        if in_band > 0:
            band_labels.append(f"{int(rate*100)}% band")
            band_gains.append(in_band)
            band_taxes.append(in_band * rate)
        prev = ceiling
        if ceil_val > other_income + spy_gain:
            break
    fig4 = go.Figure()
    fig4.add_bar(name="Gain in band", x=band_labels, y=band_gains,
                 marker_color="rgba(96, 165, 250, 0.55)",
                 text=[fmt(int(v)) for v in band_gains],
                 textposition="outside", textfont=dict(color="#ddd8cc", size=10))
    fig4.add_bar(name="Tax in band", x=band_labels, y=band_taxes,
                 marker_color="rgba(248, 113, 113, 0.55)",
                 text=[fmt(int(v)) for v in band_taxes],
                 textposition="outside", textfont=dict(color="#ddd8cc", size=10))
    layout4 = base_layout("IRPEF Band Breakdown on SPY Gain")
    layout4["barmode"] = "group"
    layout4["legend"]  = dict(font=dict(color="#9ca3af"), bgcolor=DARK_BG)
    fig4.update_layout(**layout4)
    st.plotly_chart(fig4, use_container_width=True)

# ─── Multi-year waterfall ────────────────────────────────────────────────────
st.markdown("""<div class='section-header'>
  <h2>Multi-Year Flat Tax: Gain Crystallisation Waterfall</h2>
  <p>Total IRPEF across SPY and other latent gains vs. flat tax lump sums across years.</p>
</div>""", unsafe_allow_html=True)

spy_lump_cost   = FLAT_TAX_LUMP * flat_spy_yrs
other_lump_cost = FLAT_TAX_LUMP * flat_other_yrs

wf_x = ["IRPEF: SPY", f"Flat Tax\n({flat_spy_yrs}yr SPY)", "SPY saving",
         "IRPEF:\nOther gains", f"Flat Tax\n({flat_other_yrs}yr other)", "Other saving", "TOTAL saving"]
wf_y = [irpef_tax, spy_lump_cost, irpef_tax - spy_lump_cost,
        other_irpef, other_lump_cost, other_irpef - other_lump_cost, s3_saved]
wf_m = ["absolute", "absolute", "relative", "absolute", "absolute", "relative", "total"]

fig_wf = go.Figure(go.Waterfall(
    orientation="v", measure=wf_m, x=wf_x, y=wf_y,
    connector=dict(line=dict(color="#252830", width=1)),
    increasing=dict(marker=dict(color="#f87171")),
    decreasing=dict(marker=dict(color="#4ade80")),
    totals=dict(marker=dict(color="#d4a843")),
    text=[fmt(int(v)) for v in wf_y],
    textposition="outside", textfont=dict(color="#ddd8cc", size=11),
))
fig_wf.update_layout(
    paper_bgcolor=DARK_BG, plot_bgcolor=DARK_BG,
    font=dict(color=FONT_C, family="IBM Plex Sans"),
    yaxis=dict(tickprefix="$", tickformat=",.0f", gridcolor=GRID, color=LABEL_C),
    xaxis=dict(color=LABEL_C),
    height=400, margin=dict(t=30, b=10, l=10, r=10),
)
st.plotly_chart(fig_wf, use_container_width=True)

# ─── Summary Table ────────────────────────────────────────────────────────────
st.markdown("""<div class='section-header'><h2>Summary Table</h2></div>""", unsafe_allow_html=True)

df = pd.DataFrame([
    {"Scenario": "① Do Nothing",
     "Tax on SPY ($)": 0, "Other Costs ($)": 0, "Total Cost ($)": 0,
     "Net Proceeds ($)": int(spy_value), "Eff. Rate": "—",
     "Saved vs IRPEF ($)": "—", "Key Risk": "Phantom income; IVAFE 0.2%/yr"},
    {"Scenario": "② Sell Now (IRPEF)",
     "Tax on SPY ($)": int(irpef_tax), "Other Costs ($)": 0, "Total Cost ($)": int(irpef_tax),
     "Net Proceeds ($)": int(spy_value - irpef_tax), "Eff. Rate": f"{irpef_eff*100:.1f}%",
     "Saved vs IRPEF ($)": "Baseline", "Key Risk": "Highest tax — benchmark"},
    {"Scenario": "③ Flat Tax 1yr (€300k)",
     "Tax on SPY ($)": FLAT_TAX_LUMP, "Other Costs ($)": 0, "Total Cost ($)": FLAT_TAX_LUMP,
     "Net Proceeds ($)": int(s2_net), "Eff. Rate": f"{FLAT_TAX_LUMP/spy_value*100:.1f}%",
     "Saved vs IRPEF ($)": f"+{fmt(int(s2_saved))}", "Key Risk": "Must not be existing long-term resident"},
    {"Scenario": f"④ Flat Tax {multi_yrs}yr",
     "Tax on SPY ($)": int(FLAT_TAX_LUMP * flat_spy_yrs), "Other Costs ($)": int(FLAT_TAX_LUMP * flat_other_yrs),
     "Total Cost ($)": int(s3_lump), "Net Proceeds ($)": int(s3_net),
     "Eff. Rate": f"{s3_lump/(spy_value+other_gain)*100:.1f}%",
     "Saved vs IRPEF ($)": f"+{fmt(int(s3_saved))}", "Key Risk": "Total IRPEF on all gains vs lump sums"},
    {"Scenario": f"⑤ Relocate {int(reloc_rate*100)}%",
     "Tax on SPY ($)": int(reloc_cgt), "Other Costs ($)": int(reloc_running),
     "Total Cost ($)": int(s4_total_cost), "Net Proceeds ($)": int(s4_net),
     "Eff. Rate": f"{s4_total_cost/spy_value*100:.1f}%",
     "Saved vs IRPEF ($)": f"+{fmt(int(s4_saved))}" if s4_saved > 0 else fmt(int(s4_saved)),
     "Key Risk": "Exit tax; genuine residency required"},
])
st.dataframe(df.set_index("Scenario"), use_container_width=True, height=215)

# ─── Detailed text analysis per scenario ─────────────────────────────────────
st.markdown("""<div class='section-header'>
  <h2>Detailed Scenario Analysis</h2>
  <p>Expand each section for full legal, tax, and practical commentary.</p>
</div>""", unsafe_allow_html=True)

with st.expander("① Do Nothing — full analysis"):
    st.markdown(f"""
**Tax position today:** No immediate tax crystallisation. The unrealised gain of **{fmt(spy_gain)}**
remains latent and no filing obligation arises solely from holding.

**The non-UCITS phantom income problem:** SPY is a US-domiciled ETF and is not UCITS-compliant.
Under Italian tax law, gains from non-harmonised foreign collective investment vehicles (*fondi
non armonizzati*) are classified as *redditi di capitale* under Art. 44 TUIR. The Agenzia delle
Entrate's interpretation is that annual increases in NAV can constitute deemed income, taxable at
IRPEF progressive rates, even without a disposal. This is not merely theoretical — it has been
applied in practice and is increasingly enforced. True tax deferral of a non-UCITS position
cannot be assumed.

**IVAFE:** An annual wealth tax of **0.2%** applies to the market value of financial assets held
abroad. At the current value of {fmt(spy_value)}, that is approximately **{fmt(int(spy_value * 0.002))}
per year** — unavoidable regardless of whether you sell.

**Growing terminal liability:** Every year the position appreciates, the eventual IRPEF bill
increases. At your current income and bracket stacking, marginal gains are taxed at
approximately **{irpef_eff*100:.1f}%**. A 10% increase in SPY value would add roughly
**{fmt(int(spy_gain * 0.1 * irpef_eff))}** to the tax liability.

**Conclusion:** "Do nothing" is not a stable tax-neutral posture for a non-UCITS holding.
It is uncertain annual exposure plus a large and growing terminal IRPEF liability of currently
**{fmt(int(irpef_tax))}**. The decision to hold should be deliberate and informed by advice on
whether phantom income is being assessed on your specific return.
    """)

with st.expander("② Sell Now at IRPEF — full analysis"):
    st.markdown(f"""
**Why IRPEF and not 26%?** Italy's 26% *imposta sostitutiva* applies to capital gains and investment
income from UCITS-compliant instruments and certain regulated securities. SPY, as a US-registered
ETF, is not UCITS-passported into the EU. The gain therefore falls outside the substitute tax
regime and is assessed to full progressive IRPEF under Art. 44 or Art. 67 TUIR.

**Bracket stacking mechanics:** Your other income of **{fmt(other_income)}** already partially
fills the lower IRPEF bands. The SPY gain of **{fmt(spy_gain)}** is added on top of this,
meaning the entire gain — net of whatever remains in sub-43% bands — is taxed at:
- **43% national IRPEF** (income above €50,000)
- **~3.3% regional and municipal surcharge** (varies; Rome estimate used here)
- **Effective rate on the gain: {irpef_eff*100:.1f}%**

**Tax: {fmt(int(irpef_tax))}** | **Net proceeds: {fmt(int(spy_value - irpef_tax))}**

**USD/EUR consideration:** The gain is computed in EUR for Italian tax purposes. USD appreciation
against EUR since purchase increases the EUR-denominated gain and therefore the tax bill. This
model treats USD/EUR at parity; the real figure may be higher or lower.

**Conclusion:** This is the benchmark — the maximum tax cost of disposal. All other strategies
are measured against this figure of **{fmt(int(irpef_tax))}**. No structuring is involved;
this is simply the cost of selling as a standard Italian fiscal resident with no special regime.
    """)

with st.expander("③ Flat Tax — 1 Year — full analysis"):
    st.markdown(f"""
**The regime:** Art. 24-bis TUIR (*regime dei neo-residenti*) provides that individuals who
transfer their fiscal residence to Italy may elect to pay a **fixed annual lump sum** in lieu of
IRPEF on all foreign-source income and capital gains. The lump sum from 1 January 2026 is
**€300,000** per the 2026 Budget Law (Law No. 199 of 30 December 2025).

**Why it covers SPY fully:** SPY is a US-domiciled fund. The capital gain on disposal is
unambiguously foreign-source income. It is therefore entirely covered by the lump sum. The
IRPEF liability of **{fmt(int(irpef_tax))}** is replaced in its entirety by the **{fmt(FLAT_TAX_LUMP)}**
lump sum payment — a saving of **{fmt(int(s2_saved))}**.

**Historical lump sum rates:**
- Opted in from 2024 tax year → **€100,000/yr** (grandfathered)
- Opted in from 2025 tax year → **€200,000/yr** (grandfathered)
- Opted in from 1 January 2026 → **€300,000/yr** (current new entrant rate)
This model uses €300,000 as the applicable rate for a new election.

**Eligibility conditions (all must be met):**
1. Must not have been Italian tax resident for **at least 9 of the prior 10 fiscal years**
2. Must transfer tax residency to Italy and elect the regime in the first Italian tax return
3. The election is made in *Modello Redditi PF* — it is not automatic
4. The regime lasts up to **15 years**; it must be actively renewed annually

**If you are already a long-term Italian resident:** You cannot newly elect this regime. It is
available only upon establishing or re-establishing Italian residency after a qualifying period
of non-residence.

**What it does NOT cover:** Italian-source income (employment in Italy, Italian rental income,
gains on Italian assets) is taxed normally under IRPEF. Only foreign-source income benefits.

**Net proceeds: {fmt(int(s2_net))}** | **Effective rate on SPY value: {FLAT_TAX_LUMP/spy_value*100:.1f}%**
    """)

with st.expander(f"④ Flat Tax — {multi_yrs} Years — full analysis"):
    st.markdown(f"""
**The strategy:** Rather than paying {fmt(int(total_irpef))} in IRPEF across both the SPY gain
({fmt(int(irpef_tax))}) and other latent gains of {fmt(other_gain)} ({fmt(int(other_irpef))}),
you use the flat tax regime over {multi_yrs} year(s) to crystalise all positions under the
lump sum umbrella.

**Year-by-year structure:**
- **SPY disposal:** Sell in year(s) 1–{flat_spy_yrs}. Lump sum(s) cost: {fmt(int(FLAT_TAX_LUMP * flat_spy_yrs))}
- **Other gains:** Crystalise in year(s) 1–{flat_other_yrs}. Additional lump sum cost: {fmt(int(FLAT_TAX_LUMP * flat_other_yrs))}
- **Total flat tax paid:** {fmt(int(s3_lump))}
- **Total IRPEF avoided:** {fmt(int(total_irpef))}
- **Net saving: {fmt(int(s3_saved))}**

**The compounding advantage:** The lump sum covers *all* foreign income in a given year —
not just SPY. Foreign dividends, bond interest, gains on other foreign securities — all are
sheltered by the single annual payment. If you have significant other foreign income streams,
the effective per-gain cost of the regime falls further.

**Break-even analysis:** The regime costs {fmt(FLAT_TAX_LUMP)}/yr. In any year where your
total foreign-source IRPEF exposure exceeds {fmt(FLAT_TAX_LUMP)}, the regime is financially
worthwhile. With your SPY gain alone, the IRPEF exposure is {fmt(int(irpef_tax))} — the
regime pays for itself {irpef_tax/FLAT_TAX_LUMP:.1f}x over.

**Practical consideration:** The gains from the other assets must also be foreign-source to
be covered. Italian-source gains remain subject to normal IRPEF.
    """)

with st.expander(f"⑤ Relocation to {int(reloc_rate*100)}% Jurisdiction — full analysis"):
    st.markdown(f"""
**The approach:** Establish genuine tax residency in a jurisdiction that applies {int(reloc_rate*100)}%
CGT (or none), sell SPY there, then repatriate to Italy or another jurisdiction.

**Cost breakdown:**
| Component | Amount |
|-----------|--------|
| CGT at {int(reloc_rate*100)}% on gain {fmt(spy_gain)} | {fmt(int(reloc_cgt))} |
| Running costs ({reloc_cost_pct}%/yr × {reloc_years}yr) | {fmt(int(reloc_running))} |
| **Total cost** | **{fmt(int(s4_total_cost))}** |
| **Saved vs IRPEF** | **{fmt(int(s4_saved))}** |
| **Net proceeds** | **{fmt(int(s4_net))}** |

**Running cost components (estimate at {reloc_cost_pct}%/yr):** Legal and tax advice (Italian
exit structuring, local tax filings), rental and property costs in new jurisdiction,
travel, admin, possible double filings.

**Critical legal risks:**

**1. Italian exit tax — Art. 166-bis TUIR:** If Italy determines that the move constitutes
fiscal emigration motivated by tax avoidance, it can impose a deemed disposal of all assets
at fair market value at departure, crystallising the full IRPEF liability immediately —
exactly what the relocation was designed to avoid. This risk is highest for large portfolios
and is actively assessed by the Guardia di Finanza.

**2. Genuine residency:** Under Italian law, residency is determined by registration in the
*anagrafe*, habitual abode, and centre of vital interests. A relocation that does not genuinely
transfer the centre of life (family, business, social connections) is unlikely to survive
challenge. Courts have repeatedly overturned claimed non-residency where individuals maintained
Italian homes, families, and business activities.

**3. The 183-day rule:** You must spend fewer than 183 days per year in Italy. This must be
documented rigorously — travel records, utility bills, etc.

**4. Re-entry planning:** Returning to Italy after disposal triggers no Italian CGT on the
already-realised gain. However, the period of foreign residency must be demonstrably genuine.

**Conclusion:** Viable for large positions where the saving ({fmt(int(s4_saved))}) justifies
the complexity, disruption, and legal risk — particularly if the relocation aligns with
genuine life plans (e.g. a period working or living abroad). As a purely tax-motivated manoeuvre
on a {fmt(spy_value)} position, the legal risk may outweigh the benefit relative to the flat
tax alternative.
    """)

# ─── Disclaimer ──────────────────────────────────────────────────────────────
st.markdown("""
<div class='info-box' style='margin-top:32px;font-size:11px;color:#5a6070'>
<b>Disclaimer:</b> This model is for illustrative purposes only and does not constitute tax, legal,
or investment advice. IRPEF calculations are approximate; surcharge rates vary by region and municipality
(Rome rates used as estimate). Flat tax lump sums: €100k (pre-2025 entrants), €200k (2025 entrants),
€300k (2026+ entrants). USD/EUR treated at parity for simplicity. Please consult a qualified
<em>commercialista</em> or international tax counsel before taking any action.
</div>""", unsafe_allow_html=True)
