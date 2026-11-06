# FX Carry Trade — Portfolio Construction, Crash Risk & Factor Analysis

Topic 9 (Carry & Macro Strategies). A systematic long–short carry portfolio across eight G10 currencies
vs USD (EUR, GBP, JPY, CHF, NOK, AUD, NZD, CAD), Bloomberg data, August 2016 – August 2026.

**Paper:** `paper/FX_Carry_Paper.pdf`, written in LaTeX (`paper/latex/main.tex` + `paper/latex/figures/`; upload that folder to Overleaf or run `pdflatex main.tex` twice). 17 pages in total: about 11 pages of main text, then references and annexures.

## How to reproduce

```text
python src/carry_project.py    # all analysis -> outputs/final/ (tables, figures, carry_results.xlsx, key_results.json)
python src/build_latex.py      # rebuilds paper/latex/main.tex from those outputs and compiles it (needs pdflatex)
```
Packages: numpy, pandas, scipy, statsmodels, matplotlib, openpyxl; a LaTeX install (pdflatex) for the paper.

## Method (short)

* All pairs converted to USD per unit of foreign currency (positive return = foreign currency appreciates).
* Signal at each month-end: 1M forward discount `c = S/F − 1` (≈ (i_foreign − i_USD)/12 by CIP).
* Long top-3 / short bottom-3 (±1/3 each), held to the next month-end; no look-ahead.
* Return = forward-based excess return `S(t+1)/F(t) − 1`, split into spot and carry components.
* Costs: 5 bp per unit of one-way turnover (robustness 0–20 bp).
* Sharpe = mean×12 / (sd×√12); Sortino uses downside deviation; Calmar = CAGR/|MaxDD|;
  tail ratio = |mean worst 5% months| / mean best 5%.
* UIP: Fama regression Δs(t+1) on (f − s)(t), H0: β = 1 (per currency, HAC; pooled with FE, clustered).
* Extras: VIX regimes, rolling correlations with S&P 500/VIX, factor regressions, Fama–MacBeth (DOL, HML_FX),
  3-month momentum overlay, buy-and-hold benchmarks (static carry, DOL), WIRP forward-looking check.

## Key results (119 holding months, Sep 2016 – Jul 2026)

| Metric | Carry (net) |
|---|---|
| Mean return / CAGR | 2.92% / 2.73% p.a. |
| Volatility | 6.61% p.a. |
| Sharpe / Sortino / Calmar | 0.44 / 0.64 / 0.19 |
| Max drawdown | −14.0% (Aug 2017 → Mar 2020, recovered Mar 2021) |
| Skewness / excess kurtosis (monthly) | −0.54 / 0.99 (daily: −0.74 / 8.2) |
| Tail ratio | 1.08 |
| Newey–West t (mean = 0) | 1.79 |

* Return decomposition: carry component 2.48% p.a. (t = 14.2), spot component 0.49% p.a. (t = 0.30) →
  low-yielders did not appreciate as UIP predicts (forward premium puzzle at portfolio level).
* Fama β per currency between −3.0 and 3.9, pooled 1.15 (s.e. 1.61): no rejection of UIP *or* random walk — low power.
* Worst months: 2020-03 (COVID/oil war), 2018-12 (Fed hike/QT), 2021-11 (Omicron), 2022-09 (Fed 75bp / UK gilts /
  yen intervention), 2024-07 (yen-carry unwind).
* VIX regimes: Sharpe 0.64 (low VIX), 0.32 (high VIX), −0.13 (crisis months, VIX ≥ 30).
* Corr with S&P 500 0.56, with ΔVIX −0.57; alpha after S&P + ΔVIX = 0.10%/month (t = 0.73).
* Momentum filter hurts (Sharpe −0.23 vs 0.38 on common sample): 3-month G10 spot momentum reversed (−5.4% p.a.).
* Benchmarks: static carry Sharpe 0.23, dollar basket (DOL) −0.23.
* Positions: short CHF (100% of months), JPY (99%), EUR (98%); long side rotated — AUD/NZD/CAD (2016–19),
  NOK/NZD/CAD (2019–22), GBP/NZD/CAD (2023–24), AUD/GBP/NOK (Dec 2024–2026). Full history: `outputs/final/tables/27_position_history.csv`.

## Folder

```text
data/            Bloomberg exports (GP, FRD, WIRP, FXIP, SPX/VIX, policy rates) + macro_event_log.xlsx
src/             carry_project.py (analysis), build_latex.py (paper)
outputs/final/   figures/ (F01–F11), tables/ (00–26 CSV), carry_results.xlsx, key_results.json
paper/           FX_Carry_Paper.pdf, latex/ (main.tex + figures)
archive/         first version (notebooks + outputs) — superseded; its UIP test was mis-scaled
```

## Still to do on the Bloomberg terminal

* **CORR**: rolling 252-day correlation of the carry series (`outputs/final/tables/25_daily_returns.csv`) with SPX and VIX; screenshot into Annex D.
* **REGR**: carry on SPX return and ΔVIX (compare with Table 11); screenshot into Annex D.
* Optional: **BTST** cross-check of Table 2. FXIP positioning data were not available for this universe.

## Author

Partha Gunturu
