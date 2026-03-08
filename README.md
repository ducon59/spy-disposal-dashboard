# SPY Disposal Options Modeller
### Italian Fiscal Resident · Non-UCITS Security · Capital Gains Analysis

An interactive Streamlit dashboard modelling the tax implications of disposing of a large SPY (non-UCITS) holding as an Italian fiscal resident.

---

## Scenarios Modelled

| # | Scenario | Key Tax Mechanism |
|---|----------|-------------------|
| ① | **Do Nothing** | No tax event; latent gain persists. Non-UCITS phantom income risk noted. |
| ② | **Sell Now (Standard)** | 26% CGT on capital gain (regime dichiarativo) |
| ③ | **Flat Tax — 1 Year** | Art. 24-bis TUIR; €100k lump sum covers all foreign gains |
| ④ | **Flat Tax — Multi-Year** | Multiple years of lump sum; crystalise SPY *and* other latent gains via slider |
| ⑤ | **Relocate to Low-Tax Jurisdiction** | 0%/5%/10% CGT + estimated running/relocation costs |

---

## Running Locally

```bash
# 1. Clone the repo
git clone https://github.com/YOUR_USERNAME/spy-disposal-dashboard.git
cd spy-disposal-dashboard

# 2. Create a virtual environment (optional but recommended)
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run
streamlit run app.py
```

The app will open at `http://localhost:8501`.

---

## Deploy to Streamlit Cloud (Free)

1. **Push to GitHub:**
   ```bash
   git init
   git add .
   git commit -m "Initial commit: SPY disposal dashboard"
   git branch -M main
   git remote add origin https://github.com/YOUR_USERNAME/spy-disposal-dashboard.git
   git push -u origin main
   ```

2. **Deploy:**
   - Go to [share.streamlit.io](https://share.streamlit.io)
   - Sign in with GitHub
   - Click **"New app"**
   - Select your repo, branch `main`, and set **Main file path** to `app.py`
   - Click **Deploy**

Your app will be live at `https://YOUR_USERNAME-spy-disposal-dashboard-app-XXXXX.streamlit.app`

---

## Key Assumptions & Notes

- **Flat Tax (Art. 24-bis TUIR):** Annual lump-sum of €100,000 covers all foreign-source income and capital gains. Eligibility requires not having been an Italian fiscal resident for 9 of the previous 10 fiscal years.
- **SPY as non-UCITS:** SPY is US-domiciled and not UCITS-compliant. Under Italian tax rules, non-UCITS ETFs may be subject to annual phantom income accrual. The "Do Nothing" option is therefore not fully tax-neutral.
- **Relocation running costs:** Estimated at 1.5% of portfolio value per annum (professional advisors, dual-domicile costs, travel, administration).
- **Italian exit tax:** Not modelled in full; users with holdings potentially exceeding €2m unrealised gains should seek specific advice on Art. 166-bis TUIR.
- **All figures in EUR.** USD/EUR conversion assumed at par for simplicity in the base model.

---

## Disclaimer

This tool is for **illustrative and educational purposes only**. It does not constitute tax, legal, or investment advice. Italian tax law is complex and subject to change. Please consult a qualified *commercialista* or international tax advisor before taking any action.

---

## Tech Stack

- [Streamlit](https://streamlit.io) — app framework
- [Plotly](https://plotly.com/python/) — interactive charts
- [Pandas](https://pandas.pydata.org) — data handling
