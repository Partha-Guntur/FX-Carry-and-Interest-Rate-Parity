"""
FX Carry Trade Portfolio - Construction, Crash Risk & Factor Analysis
=====================================================================
Single, reproducible pipeline. Run from the project root:

    python src/carry_project.py

Inputs  : data/forward_series_1m.xlsx  (Bloomberg GP spot + FRD 1M forward points)
          data/s&p_vix.xlsx            (Bloomberg GP: SPX, VIX)
          data/wirp_cleaned.xlsx       (Bloomberg WIRP snapshot, 17-Aug-2026)
          data/interest rates.xlsx     (policy rates, quarter-end; robustness only)
Outputs : outputs/final/figures/*.png, outputs/final/tables/*.csv,
          outputs/final/carry_results.xlsx, outputs/final/key_results.json

Conventions
-----------
* Every currency is expressed as USD per 1 unit of foreign currency (S, F).
  EURUSD, GBPUSD, AUDUSD, NZDUSD are already in that form; USDJPY, USDCHF,
  USDCAD, USDNOK are inverted. A positive spot return = foreign currency
  appreciates against USD.
* Carry signal at month-end t: c_t = S_t / F_t - 1 (1M forward discount).
  By covered interest parity this is approx. (i_foreign - i_USD)/12.
* Excess return of a long foreign-currency forward bought at t and settled at
  t+1 (next month-end): x_{t+1} = S_{t+1} / F_t - 1
                                 = spot component (S_{t+1}/S_t - 1)
                                 + carry component (S_t/F_t - 1) + cross term.
  This is the return a carry investor actually earns (Lustig, Roussanov &
  Verdelhan, 2011) - no separate financing assumption is needed.
* Portfolio: at each month-end rank the 8 currencies by c_t, long the top 3
  (+1/3 each), short the bottom 3 (-1/3 each), hold to the next month-end.
  The signal uses only information available at t (no look-ahead).
* Sharpe = (mean monthly return x 12) / (monthly st.dev x sqrt(12)); returns
  are already excess returns. Sortino uses downside deviation below 0.
  CAGR is the geometric annual growth rate. Calmar = CAGR / |max drawdown|.
"""

import json
import pathlib

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats

# --------------------------------------------------------------------------
# Paths & constants
# --------------------------------------------------------------------------
ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "outputs" / "final"
FIG = OUT / "figures"
TAB = OUT / "tables"
for p in (FIG, TAB):
    p.mkdir(parents=True, exist_ok=True)

CCY = ["EUR", "GBP", "JPY", "CHF", "NOK", "AUD", "NZD", "CAD"]
DIRECT = {"EUR", "GBP", "AUD", "NZD"}           # quoted as USD per foreign
SHEET = {c: (f"{c.lower()}usd" if c in DIRECT else f"usd{c.lower()}") for c in CCY}
N_LEG = 3                                       # top-3 / bottom-3
TC_BPS = 5.0                                    # baseline cost per unit one-way turnover
NW_LAGS = 3                                     # Newey-West lags (monthly)

COL = {"carry": "#1F4E79", "mom": "#C55A11", "dol": "#7F7F7F",
       "static": "#548235", "spx": "#A5A5A5", "neg": "#C00000"}
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9,
                     "axes.spines.top": False, "axes.spines.right": False,
                     "axes.titlesize": 10, "axes.titleweight": "bold",
                     "figure.dpi": 110, "savefig.dpi": 300})

TABLES: dict[str, pd.DataFrame] = {}
KEY: dict = {}


def save_table(name: str, df: pd.DataFrame, index: bool = True) -> None:
    TABLES[name] = df
    df.to_csv(TAB / f"{name}.csv", index=index)


def savefig(name: str) -> None:
    import re as _re
    fig = plt.gcf()
    for ax in fig.axes:  # numbering is applied in the paper, not in the image
        ax.set_title(_re.sub(r"^Figure \d+\.\s*", "", ax.get_title()))
    if fig._suptitle is not None:
        fig._suptitle.set_text(_re.sub(r"^Figure \d+\.\s*", "", fig._suptitle.get_text()))
    plt.tight_layout()
    plt.savefig(FIG / f"{name}.png", bbox_inches="tight")
    plt.close()


def hac(y, X, lags=NW_LAGS):
    return sm.OLS(y, X, missing="drop").fit(cov_type="HAC", cov_kwds={"maxlags": lags})


# --------------------------------------------------------------------------
# 1. Data
# --------------------------------------------------------------------------
def load_fx():
    spot, fwd = {}, {}
    for c in CCY:
        df = pd.read_excel(DATA / "forward_series_1m.xlsx", sheet_name=SHEET[c])
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        for k in ("spot", "forward_1m"):
            df[k] = pd.to_numeric(df[k], errors="coerce")
        df = (df.dropna(subset=["date", "spot", "forward_1m"])
                .drop_duplicates("date", keep="last").set_index("date").sort_index())
        s, f = df["spot"], df["forward_1m"]
        if c not in DIRECT:
            s, f = 1.0 / s, 1.0 / f
        spot[c], fwd[c] = s, f
    S = pd.DataFrame(spot).sort_index().ffill(limit=3).dropna()
    F = pd.DataFrame(fwd).reindex(S.index).ffill(limit=3)
    ok = F.notna().all(axis=1)
    return S[ok], F[ok]


def load_bbg_series(sheet):
    df = pd.read_excel(DATA / "s&p_vix.xlsx", sheet_name=sheet)
    df.columns = ["date", "px"]
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["px"] = pd.to_numeric(df["px"], errors="coerce")
    return df.dropna().drop_duplicates("date").set_index("date")["px"].sort_index()


S, F = load_fx()
SPX = load_bbg_series("price")
VIX = load_bbg_series("Sheet2")

daily_spot_ret = S.pct_change().dropna()
data_check = pd.DataFrame({
    "first_date": S.index.min().date(), "last_date": S.index.max().date(),
    "trading_days": len(S),
    "max_abs_daily_spot_move_%": (daily_spot_ret.abs().max() * 100).round(2),
    "mean_ann_fwd_implied_diff_%": ((S / F - 1).mean() * 1200).round(2),
})
save_table("00_data_check", data_check)

# Month-end sampling
me = S.index.to_series().groupby(S.index.to_period("M")).max()
# drop a final partial month (last observation > 5 days before calendar month end)
last_p = me.index[-1]
if (last_p.end_time.normalize() - me.iloc[-1]).days > 5:
    me = me.iloc[:-1]
S_m, F_m = S.loc[me.values], F.loc[me.values]
S_m.index = F_m.index = me.index                     # Period index (month-end of that month)

carry_sig = S_m / F_m - 1                            # monthly forward discount at t
diff_ann = carry_sig * 1200                          # approx i_for - i_usd, % p.a.

# Holding-month returns: label = holding month m; formation = m-1
x_ex = (S_m / F_m.shift(1) - 1).iloc[1:]             # excess return
x_spot = (S_m / S_m.shift(1) - 1).iloc[1:]           # spot component
x_carry = carry_sig.shift(1).iloc[1:]                # carry component (known at t)
sig_form = carry_sig.shift(1).iloc[1:]               # signal used for holding month m
months = x_ex.index
KEY["sample"] = {"daily_start": str(S.index.min().date()), "daily_end": str(S.index.max().date()),
                 "first_holding_month": str(months[0]), "last_holding_month": str(months[-1]),
                 "n_months": int(len(months)), "n_days": int(len(S))}

# --------------------------------------------------------------------------
# 2. Portfolio construction
# --------------------------------------------------------------------------
def carry_weights(sig: pd.DataFrame, n=N_LEG) -> pd.DataFrame:
    W = pd.DataFrame(0.0, index=sig.index, columns=CCY)
    for m, row in sig.iterrows():
        r = row.dropna()
        W.loc[m, r.nlargest(n).index] = 1.0 / n
        W.loc[m, r.nsmallest(n).index] = -1.0 / n
    return W


def run_portfolio(W: pd.DataFrame, tc_bps=TC_BPS):
    W = W.reindex(months).fillna(0.0)
    gross = (W * x_ex).sum(axis=1)
    spot_c = (W * x_spot).sum(axis=1)
    carry_c = (W * x_carry).sum(axis=1)
    turnover = 0.5 * W.diff().abs().sum(axis=1)
    turnover.iloc[0] = 0.5 * W.iloc[0].abs().sum()
    cost = turnover * tc_bps / 1e4
    return pd.DataFrame({"gross": gross, "net": gross - cost, "spot": spot_c,
                         "carry": carry_c, "turnover": turnover, "cost": cost,
                         "long_leg": (W.clip(lower=0) * x_ex).sum(axis=1),
                         "short_leg": (W.clip(upper=0) * x_ex).sum(axis=1)})


W_carry = carry_weights(sig_form)
P = run_portfolio(W_carry)

# Momentum: 3-month spot momentum known at formation date
mom3 = (S_m / S_m.shift(3) - 1).shift(1).reindex(months)


def momentum_filter_weights(sig, mom, n=N_LEG):
    W = pd.DataFrame(0.0, index=sig.index, columns=CCY)
    for m in sig.index:
        s, mo = sig.loc[m], mom.loc[m]
        if mo.isna().any():
            continue
        longs = [c for c in s.nlargest(n).index if mo[c] > 0]
        shorts = [c for c in s.nsmallest(n).index if mo[c] < 0]
        if longs:
            W.loc[m, longs] = 1.0 / len(longs)
        if shorts:
            W.loc[m, shorts] = -1.0 / len(shorts)
    return W


def composite_weights(sig, mom, n=N_LEG):
    score = sig.rank(axis=1) + mom.rank(axis=1)
    score = score.where(mom.notna().all(axis=1), np.nan)
    W = pd.DataFrame(0.0, index=sig.index, columns=CCY)
    for m, row in score.iterrows():
        if row.isna().any():
            continue
        W.loc[m, row.nlargest(n).index] = 1.0 / n
        W.loc[m, row.nsmallest(n).index] = -1.0 / n
    return W


W_mom = momentum_filter_weights(sig_form, mom3)
W_comp = composite_weights(sig_form, mom3)
P_mom = run_portfolio(W_mom)
P_comp = run_portfolio(W_comp)
P_puremom = run_portfolio(carry_weights(mom3.where(mom3.notna().all(axis=1))))  # reference: pure 3m momentum

# Benchmarks
W_dol = pd.DataFrame(1.0 / len(CCY), index=months, columns=CCY)
P_dol = run_portfolio(W_dol, tc_bps=0)
W_static = pd.DataFrame(np.repeat(W_carry.iloc[[0]].values, len(months), axis=0),
                        index=months, columns=CCY)
P_static = run_portfolio(W_static)
static_desc = (f"long {', '.join(W_carry.columns[W_carry.iloc[0] > 0])} / "
               f"short {', '.join(W_carry.columns[W_carry.iloc[0] < 0])} (fixed from {months[0]})")

# S&P 500 monthly price return over the same holding months
spx_m = SPX.groupby(SPX.index.to_period("M")).last().reindex(
    pd.period_range(months[0] - 1, months[-1], freq="M")).ffill()
spx_ret = spx_m.pct_change().reindex(months)
vix_end = VIX.groupby(VIX.index.to_period("M")).last()
vix_avg = VIX.groupby(VIX.index.to_period("M")).mean().reindex(months)
vix_max = VIX.groupby(VIX.index.to_period("M")).max().reindex(months)
dvix = (vix_end - vix_end.shift(1)).reindex(months)
vix_form = vix_end.shift(1).reindex(months)

# Daily portfolio returns (weights fixed through each holding month)
def daily_returns(W: pd.DataFrame, tc_bps=TC_BPS):
    out = []
    W = W.reindex(months).fillna(0.0)
    turnover = 0.5 * W.diff().abs().sum(axis=1)
    turnover.iloc[0] = 0.5 * W.iloc[0].abs().sum()
    for m in months:
        t0, t1 = me[m - 1], me[m]
        idx = S.index[(S.index > t0) & (S.index <= t1)]
        sp = S.loc[idx] / S.shift(1).loc[idx] - 1
        cr = carry_sig.loc[m - 1] / len(idx)
        r = (sp + cr).mul(W.loc[m]).sum(axis=1)
        r.iloc[0] -= turnover[m] * tc_bps / 1e4
        out.append(r)
    return pd.concat(out)


D_carry = daily_returns(W_carry)
D_mom = daily_returns(W_mom)
D_dol = daily_returns(W_dol, tc_bps=0)

# --------------------------------------------------------------------------
# 3. Performance statistics
# --------------------------------------------------------------------------
def max_dd(r):
    w = (1 + r).cumprod()
    dd = w / w.cummax() - 1
    return dd.min(), dd


def perf(r: pd.Series, freq=12) -> dict:
    r = r.dropna()
    n = len(r)
    mu, sd = r.mean(), r.std(ddof=1)
    dd_min, _ = max_dd(r)
    cagr = (1 + r).prod() ** (freq / n) - 1
    down = np.sqrt((np.minimum(r, 0) ** 2).mean())
    t_nw = hac(r.values, np.ones(n)).tvalues[0]
    k = max(1, int(np.ceil(0.05 * n)))
    srt = np.sort(r.values)
    return {"Obs": n,
            "Mean ann. (%)": mu * freq * 100,
            "CAGR (%)": cagr * 100,
            "Vol ann. (%)": sd * np.sqrt(freq) * 100,
            "Sharpe": mu / sd * np.sqrt(freq),
            "Sortino": mu / down * np.sqrt(freq) if down > 0 else np.nan,
            "Max drawdown (%)": dd_min * 100,
            "Calmar": cagr / abs(dd_min) if dd_min < 0 else np.nan,
            "Skewness": stats.skew(r, bias=False),
            "Excess kurtosis": stats.kurtosis(r, bias=False),
            "Worst period (%)": r.min() * 100,
            "Best period (%)": r.max() * 100,
            "Hit rate (%)": (r > 0).mean() * 100,
            "Tail ratio (|mean worst 5%| / mean best 5%)": abs(srt[:k].mean()) / srt[-k:].mean(),
            "NW t-stat (mean=0)": t_nw}


strategies = {"Carry (net)": P["net"], "Carry (gross)": P["gross"],
              "Carry + momentum filter (net)": P_mom["net"],
              "Carry/momentum composite (net)": P_comp["net"],
              "Static carry, buy-and-hold (net)": P_static["net"],
              "Dollar basket DOL, buy-and-hold": P_dol["net"],
              "Carry long leg": P["long_leg"], "Carry short leg (as held)": P["short_leg"],
              "S&P 500 (price)": spx_ret}
perf_tab = pd.DataFrame({k: perf(v) for k, v in strategies.items()}).T
save_table("01_performance_monthly", perf_tab.round(3))

common = P_mom["net"].index[mom3.notna().all(axis=1)]
perf_common = pd.DataFrame({k: perf(v.loc[common]) for k, v in
                            {"Carry (net)": P["net"], "Carry + momentum filter (net)": P_mom["net"],
                             "Carry/momentum composite (net)": P_comp["net"],
                             "Pure 3m momentum, long-short (net, reference)": P_puremom["net"]}.items()}).T
save_table("02_performance_common_sample_momentum", perf_common.round(3))

perf_daily = pd.DataFrame({k: perf(v, freq=252) for k, v in
                           {"Carry (net), daily": D_carry, "Carry + momentum (net), daily": D_mom,
                            "DOL, daily": D_dol,
                            "S&P 500, daily": SPX.pct_change().loc[D_carry.index.min():D_carry.index.max()]}.items()}).T
save_table("03_performance_daily", perf_daily.round(3))

KEY["carry_net"] = {k: float(v) for k, v in perf_tab.loc["Carry (net)"].items()}
KEY["carry_gross"] = {k: float(v) for k, v in perf_tab.loc["Carry (gross)"].items()}
KEY["dol"] = {k: float(v) for k, v in perf_tab.loc["Dollar basket DOL, buy-and-hold"].items()}
KEY["static"] = {k: float(v) for k, v in perf_tab.loc["Static carry, buy-and-hold (net)"].items()}
KEY["static_desc"] = static_desc
KEY["daily_carry"] = {k: float(v) for k, v in perf_daily.loc["Carry (net), daily"].items()}

# Return decomposition
decomp = pd.DataFrame({
    "Mean monthly (%)": [P["spot"].mean() * 100, P["carry"].mean() * 100,
                         (P["gross"] - P["spot"] - P["carry"]).mean() * 100,
                         P["gross"].mean() * 100, P["cost"].mean() * 100, P["net"].mean() * 100],
    "Annualised (%)": [P["spot"].mean() * 1200, P["carry"].mean() * 1200,
                       (P["gross"] - P["spot"] - P["carry"]).mean() * 1200,
                       P["gross"].mean() * 1200, P["cost"].mean() * 1200, P["net"].mean() * 1200]},
    index=["Spot (FX) component", "Carry (forward discount) component", "Cross term",
           "Gross excess return", "Transaction costs", "Net return"])
decomp["NW t-stat"] = [hac(s.values, np.ones(len(s))).tvalues[0] for s in
                       [P["spot"], P["carry"], P["gross"] - P["spot"] - P["carry"],
                        P["gross"], P["cost"], P["net"]]]
save_table("04_return_decomposition", decomp.round(3))
KEY["decomp_ann"] = decomp["Annualised (%)"].round(3).to_dict()
KEY["decomp_t"] = decomp["NW t-stat"].round(3).to_dict()
KEY["avg_turnover"] = float(P["turnover"].mean())
KEY["avg_spread_long_minus_short_ann_%"] = float(((W_carry * sig_form).sum(axis=1) * 1200).mean())

# Annual and sub-period returns
yr = months.year
annual = pd.DataFrame({
    "Carry (net)": P["net"].groupby(yr).apply(lambda r: (1 + r).prod() - 1) * 100,
    "Carry + momentum (net)": P_mom["net"].groupby(yr).apply(lambda r: (1 + r).prod() - 1) * 100,
    "Static carry": P_static["net"].groupby(yr).apply(lambda r: (1 + r).prod() - 1) * 100,
    "DOL": P_dol["net"].groupby(yr).apply(lambda r: (1 + r).prod() - 1) * 100,
    "Months": P["net"].groupby(yr).size()})
annual.index.name = "Year"
save_table("05_annual_returns", annual.round(2))

sub = {"2016-09 to 2019-12": (months <= pd.Period("2019-12", "M")),
       "2020-01 to 2022-12": (months >= pd.Period("2020-01", "M")) & (months <= pd.Period("2022-12", "M")),
       "2023-01 to end": (months >= pd.Period("2023-01", "M"))}
subtab = pd.DataFrame({k: perf(P["net"][v]) for k, v in sub.items()}).T
save_table("06_subperiod_performance", subtab.round(3))

# Per-currency statistics
pc = pd.DataFrame({
    "Avg fwd-implied differential vs USD (% p.a.)": diff_ann.loc[months - 1].mean().values,
    "Mean spot return (% p.a.)": x_spot.mean().values * 1200,
    "Mean excess return (% p.a.)": x_ex.mean().values * 1200,
    "Vol (% p.a.)": x_ex.std().values * np.sqrt(12) * 100,
    "Months long (%)": (W_carry > 0).mean().values * 100,
    "Months short (%)": (W_carry < 0).mean().values * 100}, index=CCY)
pc["Sharpe"] = pc["Mean excess return (% p.a.)"] / pc["Vol (% p.a.)"]
save_table("07_currency_statistics", pc.round(2))

# Transaction cost robustness
tc_rows = {}
for bps in [0, 2.5, 5, 10, 20]:
    r = P["gross"] - P["turnover"] * bps / 1e4
    d = perf(r)
    tc_rows[f"{bps} bps"] = {k: d[k] for k in ["Mean ann. (%)", "CAGR (%)", "Sharpe", "Max drawdown (%)"]}
save_table("08_transaction_cost_robustness", pd.DataFrame(tc_rows).T.round(3))

# Robustness: policy-rate signal (quarter-end Bloomberg policy rates, step function)
try:
    ir = {}
    for c in ["usd"] + [c.lower() for c in CCY]:
        d = pd.read_excel(DATA / "interest rates.xlsx", sheet_name=f"{c}_ir")
        d.columns = ["date", "rate"]
        d["date"] = pd.to_datetime(d["date"], errors="coerce")
        d = d.dropna().set_index("date")["rate"].sort_index()
        ir[c.upper()] = d.groupby(level=0).last()
    pr = pd.DataFrame({c: ir[c].reindex(ir[c].index.union(me.values)).ffill().loc[me.values].values
                       for c in ir}, index=me.index)
    pol_sig = pr[CCY].sub(pr["USD"], axis=0).shift(1).reindex(months)
    P_pol = run_portfolio(carry_weights(pol_sig))
    rb = pd.DataFrame({"Forward-discount signal (baseline)": perf(P["net"]),
                       "Policy-rate differential signal": perf(P_pol["net"]),
                       "Top-2 / bottom-2 (forward signal)": perf(run_portfolio(carry_weights(sig_form, 2))["net"])}).T
    save_table("09_signal_robustness", rb.round(3))
except Exception as e:  # noqa
    print("policy-rate robustness skipped:", e)

# --------------------------------------------------------------------------
# 4. UIP / Fama regression
# --------------------------------------------------------------------------
ds = np.log(S_m).diff().iloc[1:] * 1200                    # % p.a., + = foreign appreciation
fp = (np.log(F_m) - np.log(S_m)).shift(1).iloc[1:] * 1200   # f_t - s_t = i_USD - i_for (% p.a.)
uip_rows = {}
for c in CCY:
    y, xv = ds[c], fp[c]
    m_ = hac(y.values, sm.add_constant(xv.values))
    b, se = m_.params[1], m_.bse[1]
    uip_rows[c] = {"alpha": m_.params[0], "beta": b, "HAC s.e.": se,
                   "t (beta=0)": b / se, "t (beta=1)": (b - 1) / se,
                   "p (beta=1)": 2 * stats.norm.sf(abs((b - 1) / se)),
                   "R2": m_.rsquared, "Obs": int(m_.nobs)}
panel = pd.DataFrame({"y": ds.stack(), "x": fp.stack()}).dropna().reset_index()
panel.columns = ["month", "ccy", "y", "x"]
Xp = pd.get_dummies(panel["ccy"], drop_first=True, dtype=float)
Xp.insert(0, "x", panel["x"])
Xp = sm.add_constant(Xp)
mp = sm.OLS(panel["y"], Xp).fit(cov_type="cluster",
                                 cov_kwds={"groups": panel["month"].astype(str).factorize()[0]})
b, se = mp.params["x"], mp.bse["x"]
uip_rows["Pooled (currency FE, s.e. clustered by month)"] = {
    "alpha": np.nan, "beta": b, "HAC s.e.": se, "t (beta=0)": b / se, "t (beta=1)": (b - 1) / se,
    "p (beta=1)": 2 * stats.norm.sf(abs((b - 1) / se)), "R2": mp.rsquared, "Obs": int(mp.nobs)}
uip = pd.DataFrame(uip_rows).T
save_table("10_uip_fama_regressions", uip.round(3))
KEY["uip"] = uip[["beta", "HAC s.e.", "t (beta=1)", "p (beta=1)"]].round(3).to_dict(orient="index")

# Portfolio-level UIP: did high-yielders depreciate by the differential?
pl = pd.DataFrame({"Long leg (high-yield)": [(W_carry.clip(lower=0) * x_carry).sum(axis=1).mean() * 1200,
                                             (W_carry.clip(lower=0) * x_spot).sum(axis=1).mean() * 1200],
                   "Short leg (low-yield)": [(-W_carry.clip(upper=0) * x_carry).sum(axis=1).mean() * 1200,
                                             (-W_carry.clip(upper=0) * x_spot).sum(axis=1).mean() * 1200]},
                  index=["Avg forward-implied carry vs USD (% p.a.)", "Avg spot change vs USD (% p.a.)"])
pl["Long minus short"] = pl.iloc[:, 0] - pl.iloc[:, 1]
pl.loc["UIP-predicted spot change (% p.a.) = -carry"] = -pl.loc["Avg forward-implied carry vs USD (% p.a.)"]
save_table("11_uip_portfolio_level", pl.round(3))

# --------------------------------------------------------------------------
# 5. Crash risk
# --------------------------------------------------------------------------
_, dd_series = max_dd(P["net"])
worst = P["net"].nsmallest(5).index
crash = pd.DataFrame({
    "Net return (%)": P.loc[worst, "net"] * 100,
    "Spot component (%)": P.loc[worst, "spot"] * 100,
    "Carry component (%)": P.loc[worst, "carry"] * 100,
    "Long leg (%)": P.loc[worst, "long_leg"] * 100,
    "Short leg (%)": P.loc[worst, "short_leg"] * 100,
    "Longs": [", ".join(W_carry.columns[W_carry.loc[m] > 0]) for m in worst],
    "Shorts": [", ".join(W_carry.columns[W_carry.loc[m] < 0]) for m in worst],
    "Biggest drag": [", ".join((W_carry.loc[m] * x_ex.loc[m]).nsmallest(2).index) for m in worst],
    "Avg VIX": vix_avg.loc[worst].values, "Change in VIX": dvix.loc[worst].values,
    "S&P 500 (%)": spx_ret.loc[worst].values * 100}, index=worst.astype(str))
crash.index.name = "Holding month"
save_table("12_worst_5_months", crash.round(2))

best = P["net"].nlargest(5).index
save_table("13_best_5_months", pd.DataFrame({
    "Net return (%)": P.loc[best, "net"] * 100, "Avg VIX": vix_avg.loc[best].values,
    "S&P 500 (%)": spx_ret.loc[best].values * 100}, index=best.astype(str)).round(2))

wd = D_carry.nsmallest(10)
save_table("14_worst_10_days", pd.DataFrame({
    "Carry net (%)": wd * 100,
    "S&P 500 (%)": SPX.pct_change().reindex(wd.index).values * 100,
    "VIX change": VIX.diff().reindex(wd.index).values}, index=wd.index.date).round(2))


def dd_episodes(r, top=5):
    w = (1 + r).cumprod()
    peak = w.cummax()
    dd = w / peak - 1
    eps, in_dd, start = [], False, None
    for t, v in dd.items():
        if v < 0 and not in_dd:
            in_dd, start = True, t
        elif v == 0 and in_dd:
            seg = dd.loc[start:t]
            eps.append((start, seg.idxmin(), t, seg.min()))
            in_dd = False
    if in_dd:
        seg = dd.loc[start:]
        eps.append((start, seg.idxmin(), None, seg.min()))
    df = pd.DataFrame(eps, columns=["Start (first down month)", "Trough", "Recovered", "Depth (%)"])
    df["Depth (%)"] *= 100
    return df.nsmallest(top, "Depth (%)").astype({"Start (first down month)": str, "Trough": str, "Recovered": str})


save_table("15_drawdown_episodes", dd_episodes(P["net"]).round(2), index=False)

# --------------------------------------------------------------------------
# 6. Regimes & risk factors
# --------------------------------------------------------------------------
med = vix_avg.median()
reg = {"Low VIX (avg VIX < median %.1f)" % med: vix_avg < med,
       "High VIX (avg VIX >= median)": vix_avg >= med,
       "Crisis (intra-month VIX peak >= 30)": vix_max >= 30,
       "Ex-ante low VIX (VIX at formation < median)": vix_form < vix_form.median(),
       "Ex-ante high VIX (VIX at formation >= median)": vix_form >= vix_form.median()}
regtab = pd.DataFrame({k: {**{kk: perf(P["net"][v])[kk] for kk in
                              ["Obs", "Mean ann. (%)", "Vol ann. (%)", "Sharpe", "Skewness",
                               "Worst period (%)", "Hit rate (%)"]},
                           "Momentum overlay Sharpe": perf(P_mom["net"][v & mom3.notna().all(axis=1)])["Sharpe"]}
                       for k, v in reg.items()}).T
save_table("16_vix_regimes", regtab.round(3))
KEY["vix_median"] = float(med)
KEY["crisis_months"] = [str(m) for m in months[vix_max >= 30]]

# Correlations
cor_full = pd.DataFrame({
    "Monthly corr with S&P 500": [P["net"].corr(spx_ret)],
    "Monthly corr with change in VIX": [P["net"].corr(dvix)],
    "Daily corr with S&P 500": [D_carry.corr(SPX.pct_change().reindex(D_carry.index))],
    "Daily corr with change in VIX": [D_carry.corr(VIX.diff().reindex(D_carry.index))]}, index=["Full sample"])
for k, v in sub.items():
    cor_full.loc[k] = [P["net"][v].corr(spx_ret[v]), P["net"][v].corr(dvix[v]),
                       np.nan, np.nan]
    dmask = (D_carry.index >= pd.Period(k[:7], "M").start_time) & \
            (D_carry.index <= (months[v][-1]).end_time)
    dc = D_carry[dmask]
    cor_full.loc[k, "Daily corr with S&P 500"] = dc.corr(SPX.pct_change().reindex(dc.index))
    cor_full.loc[k, "Daily corr with change in VIX"] = dc.corr(VIX.diff().reindex(dc.index))
save_table("17_correlations", cor_full.round(3))

_dj = pd.concat({"c": D_carry, "spx": SPX.pct_change().reindex(D_carry.index),
                 "dvix": VIX.diff().reindex(D_carry.index)}, axis=1).dropna()
roll_spx = _dj["c"].rolling(252).corr(_dj["spx"])
roll_vix = _dj["c"].rolling(252).corr(_dj["dvix"])
save_table("18_rolling_252d_correlations", pd.DataFrame({"corr_SPX": roll_spx, "corr_dVIX": roll_vix}).dropna().round(4))

# Factor regressions: carry on S&P, dVIX, FX volatility innovations
fxvol = daily_spot_ret.abs().mean(axis=1)
fxvol_m = fxvol.groupby(fxvol.index.to_period("M")).mean()
ar = sm.OLS(fxvol_m.iloc[1:].values, sm.add_constant(fxvol_m.shift(1).iloc[1:].values)).fit()
fxvol_innov = pd.Series(ar.resid, index=fxvol_m.index[1:]).reindex(months) * 100
fr = {}
for name, Xv in {"S&P 500 return": spx_ret, "Change in VIX": dvix,
                 "Global FX volatility innovation": fxvol_innov}.items():
    d = pd.concat([P["net"], Xv], axis=1).dropna()
    m_ = hac(d.iloc[:, 0].values * 100, sm.add_constant(d.iloc[:, 1].values))
    fr[name] = {"alpha (% per month)": m_.params[0], "t(alpha)": m_.tvalues[0],
                "beta": m_.params[1], "t(beta)": m_.tvalues[1], "R2": m_.rsquared, "Obs": int(m_.nobs)}
d = pd.concat([P["net"], spx_ret, dvix], axis=1).dropna()
m_ = hac(d.iloc[:, 0].values * 100, sm.add_constant(d.iloc[:, 1:].values))
fr["S&P 500 + change in VIX (joint)"] = {"alpha (% per month)": m_.params[0], "t(alpha)": m_.tvalues[0],
                                          "beta": m_.params[1], "t(beta)": m_.tvalues[1],
                                          "R2": m_.rsquared, "Obs": int(m_.nobs)}
save_table("19_carry_risk_exposures", pd.DataFrame(fr).T.round(4))

# Asset-pricing test in the spirit of Lustig et al. (2011): DOL + HML_FX
HML = P["gross"]
DOL = P_dol["gross"]
betas = {}
for c in CCY:
    m_ = sm.OLS(x_ex[c].values * 100, sm.add_constant(np.column_stack([DOL.values, HML.values]) * 100)).fit()
    betas[c] = {"beta_DOL": m_.params[1], "beta_HML": m_.params[2],
                "mean excess (% p.m.)": x_ex[c].mean() * 100}
B = pd.DataFrame(betas).T
lam = []
for m in months:
    yv = x_ex.loc[m].values * 100
    lam.append(sm.OLS(yv, sm.add_constant(B[["beta_DOL", "beta_HML"]].values)).fit().params)
lam = pd.DataFrame(lam, index=months, columns=["const", "lambda_DOL", "lambda_HML"])
fmb = pd.DataFrame({c: {"mean (% p.m.)": lam[c].mean(),
                        "NW t-stat": hac(lam[c].values, np.ones(len(lam))).tvalues[0]} for c in lam}).T
fmb.loc["Factor mean: DOL"] = [DOL.mean() * 100, hac(DOL.values, np.ones(len(DOL))).tvalues[0]]
fmb.loc["Factor mean: HML_FX"] = [HML.mean() * 100, hac(HML.values, np.ones(len(HML))).tvalues[0]]
fitted = (B["beta_DOL"] * lam["lambda_DOL"].mean() + B["beta_HML"] * lam["lambda_HML"].mean()
          + lam["const"].mean())
xs_r2 = 1 - ((B["mean excess (% p.m.)"] - fitted) ** 2).sum() / \
    ((B["mean excess (% p.m.)"] - B["mean excess (% p.m.)"].mean()) ** 2).sum()
fmb.loc["Cross-sectional R2"] = [xs_r2, np.nan]
save_table("20_factor_betas", B.round(3))
save_table("21_fama_macbeth", fmb.round(3))

# --------------------------------------------------------------------------
# 7. WIRP forward-looking signal (snapshot 17-Aug-2026)
# --------------------------------------------------------------------------
try:
    wx = pd.ExcelFile(DATA / "wirp_cleaned.xlsx")
    rows = {}
    for sh in wx.sheet_names:
        d = pd.read_excel(wx, sheet_name=sh).sort_values("meeting_date")
        cur = d["implied_rate"].iloc[0] - d["implied_rate_delta"].iloc[0]
        rows[sh.upper()] = {"Current implied O/N rate (%)": cur,
                            "Implied rate at last priced meeting (%)": d["implied_rate"].iloc[-1],
                            "Last meeting priced": str(pd.to_datetime(d["meeting_date"].iloc[-1]).date()),
                            "Expected change (bp)": d["implied_rate_delta"].iloc[-1] * 100}
    wr = pd.DataFrame(rows).T
    usd_now = wr.loc["USD", "Current implied O/N rate (%)"]
    usd_fwd = wr.loc["USD", "Implied rate at last priced meeting (%)"]
    wr["Current differential vs USD (pp)"] = wr["Current implied O/N rate (%)"] - usd_now
    wr["Expected differential vs USD in ~11m (pp)"] = wr["Implied rate at last priced meeting (%)"] - usd_fwd
    wr["Change in differential (bp)"] = (wr["Expected differential vs USD in ~11m (pp)"]
                                         - wr["Current differential vs USD (pp)"]) * 100
    latest_fwd = (S.iloc[-1] / F.iloc[-1] - 1) * 1200
    wr["Forward-implied differential, 17-Aug-2026 (% p.a.)"] = latest_fwd.reindex(wr.index)
    wr = wr.drop(index="USD")
    wr["Rank: WIRP expected differential"] = wr["Expected differential vs USD in ~11m (pp)"].rank(ascending=False)
    wr["Rank: current forward carry"] = wr["Forward-implied differential, 17-Aug-2026 (% p.a.)"].rank(ascending=False)
    save_table("22_wirp_forward_looking_carry", wr.round(3))
    KEY["wirp_rank_corr"] = float(wr["Rank: WIRP expected differential"].corr(wr["Rank: current forward carry"], method="spearman"))
except Exception as e:  # noqa
    print("WIRP skipped:", e)

# Latest positions
latest_sig = (S.iloc[-1] / F.iloc[-1] - 1)
KEY["latest_signal_date"] = str(S.index[-1].date())
KEY["latest_longs"] = list(latest_sig.nlargest(3).index)
KEY["latest_shorts"] = list(latest_sig.nsmallest(3).index)

# Selection frequency & monthly results
sel = pd.DataFrame({"Long (%)": (W_carry > 0).mean() * 100, "Short (%)": (W_carry < 0).mean() * 100,
                    "Long, momentum overlay (%)": (W_mom > 0).mean() * 100,
                    "Short, momentum overlay (%)": (W_mom < 0).mean() * 100})
save_table("23_selection_frequency", sel.round(1))
KEY["mom_months_long_active_%"] = float(((W_mom > 0).any(axis=1)).loc[common].mean() * 100)
KEY["mom_months_short_active_%"] = float(((W_mom < 0).any(axis=1)).loc[common].mean() * 100)
KEY["mom_avg_turnover"] = float(P_mom["turnover"].loc[common].mean())

monthly_out = pd.DataFrame({
    "longs": [", ".join(W_carry.columns[W_carry.loc[m] > 0]) for m in months],
    "shorts": [", ".join(W_carry.columns[W_carry.loc[m] < 0]) for m in months],
    "carry_net": P["net"], "carry_gross": P["gross"], "spot_comp": P["spot"],
    "carry_comp": P["carry"], "turnover": P["turnover"], "momentum_net": P_mom["net"],
    "composite_net": P_comp["net"], "static_net": P_static["net"], "DOL": P_dol["net"],
    "SPX": spx_ret, "VIX_avg": vix_avg, "dVIX": dvix}, index=months.astype(str))
monthly_out.index.name = "holding_month"
save_table("24_monthly_results", monthly_out.round(6))
pd.DataFrame({"carry_net": D_carry, "carry_momentum_net": D_mom, "DOL": D_dol}).to_csv(TAB / "25_daily_returns.csv")
# Position history: periods in which the long and short baskets did not change
_l = [", ".join(sorted(W_carry.columns[W_carry.loc[m] > 0])) for m in months]
_s = [", ".join(sorted(W_carry.columns[W_carry.loc[m] < 0])) for m in months]
_hist, _start = [], 0
for i in range(1, len(months) + 1):
    if i == len(months) or (_l[i], _s[i]) != (_l[_start], _s[_start]):
        seg = P["net"].iloc[_start:i]
        _hist.append({"From": str(months[_start]), "To": str(months[i - 1]), "Months": i - _start,
                      "Long (high-yield)": _l[_start], "Short (funding)": _s[_start],
                      "Return over period (%)": ((1 + seg).prod() - 1) * 100})
        _start = i
save_table("27_position_history", pd.DataFrame(_hist).round(2), index=False)

(diff_ann.round(4)).to_csv(TAB / "26_forward_implied_differentials_monthly.csv")

# --------------------------------------------------------------------------
# 8. Figures
# --------------------------------------------------------------------------
x_dates = months.to_timestamp(how="end")
EVENTS = [("2018-12", "Q4-2018 sell-off"), ("2020-03", "COVID"), ("2022-09", "Fed 75bp /\nUK gilt crisis"),
          ("2024-07", "Yen-carry\nunwind"), ("2025-04", "Liberation\nDay tariffs"), ("2026-03", "Iran war\noil shock")]

# F1 cumulative
plt.figure(figsize=(9, 4.2))
for s, lab, c, lw in [(P["net"], "Carry (net)", COL["carry"], 2), (P_mom["net"], "Carry + momentum filter", COL["mom"], 1.4),
                      (P_static["net"], "Static carry (buy-and-hold)", COL["static"], 1.2),
                      (P_dol["net"], "Dollar basket DOL (buy-and-hold)", COL["dol"], 1.2)]:
    plt.plot(x_dates, ((1 + s.fillna(0)).cumprod() - 1) * 100, label=lab, color=c, lw=lw)
plt.axhline(0, color="black", lw=0.6)
for m, lab in EVENTS:
    t = pd.Period(m, "M").to_timestamp(how="end")
    plt.axvline(t, color="grey", lw=0.5, ls=":")
    plt.text(t, plt.ylim()[1] * 0.97, lab, fontsize=6.5, ha="center", va="top", color="dimgrey")
plt.ylabel("Cumulative return (%)")
plt.title("Figure 1. Cumulative returns: carry vs. momentum overlay and buy-and-hold benchmarks")
plt.legend(frameon=False, fontsize=7.5, loc="upper left", bbox_to_anchor=(0.0, 0.88))
savefig("F01_cumulative_returns")

# F2 decomposition
plt.figure(figsize=(9, 3.8))
plt.plot(x_dates, P["carry"].cumsum() * 100, label="Carry (forward discount) component", color=COL["static"])
plt.plot(x_dates, P["spot"].cumsum() * 100, label="Spot (FX) component", color=COL["neg"])
plt.plot(x_dates, P["net"].cumsum() * 100, label="Net total", color=COL["carry"], lw=2)
plt.axhline(0, color="black", lw=0.6)
plt.ylabel("Cumulative sum of monthly returns (%)")
plt.title("Figure 2. Return decomposition of the carry portfolio")
plt.legend(frameon=False, fontsize=7.5)
savefig("F02_return_decomposition")

# F3 annual bars
plt.figure(figsize=(9, 3.6))
yrs = annual.index.values
w = 0.38
plt.bar(yrs - w / 2, annual["Carry (net)"], w, label="Carry (net)", color=COL["carry"])
plt.bar(yrs + w / 2, annual["Carry + momentum (net)"], w, label="Carry + momentum", color=COL["mom"])
plt.axhline(0, color="black", lw=0.6)
plt.xticks(yrs, [f"{y}\n({int(n)}m)" if n < 12 else str(y) for y, n in zip(yrs, annual["Months"])], fontsize=7.5)
plt.ylabel("Annual return (%)")
plt.title("Figure 3. Annual net returns")
plt.legend(frameon=False, fontsize=7.5)
savefig("F03_annual_returns")

# F4 rolling Sharpe
rs = P["net"].rolling(12).mean() / P["net"].rolling(12).std() * np.sqrt(12)
rsm = P_mom["net"].rolling(12).mean() / P_mom["net"].rolling(12).std() * np.sqrt(12)
plt.figure(figsize=(9, 3.4))
plt.plot(x_dates, rs, color=COL["carry"], label="Carry")
plt.plot(x_dates, rsm, color=COL["mom"], lw=1, label="Carry + momentum")
plt.axhline(0, color="black", lw=0.6)
plt.ylabel("Rolling 12-month Sharpe")
plt.title("Figure 4. Rolling 12-month Sharpe ratio")
plt.legend(frameon=False, fontsize=7.5)
savefig("F04_rolling_sharpe")

# F5 drawdown
plt.figure(figsize=(9, 3.4))
plt.fill_between(x_dates, dd_series * 100, 0, color=COL["neg"], alpha=0.35)
plt.plot(x_dates, dd_series * 100, color=COL["neg"], lw=0.8)
for m, lab in EVENTS:
    t = pd.Period(m, "M").to_timestamp(how="end")
    plt.axvline(t, color="grey", lw=0.5, ls=":")
plt.ylabel("Drawdown (%)")
plt.title("Figure 5. Drawdown of the carry portfolio (net)")
savefig("F05_drawdown")

# F6 distribution
plt.figure(figsize=(6.5, 3.6))
r = P["net"] * 100
plt.hist(r, bins=24, density=True, color=COL["carry"], alpha=0.75, label="Carry monthly returns")
xs = np.linspace(r.min() - 1, r.max() + 1, 200)
plt.plot(xs, stats.norm.pdf(xs, r.mean(), r.std()), color="black", lw=1, label="Normal, same mean/vol")
for m in worst:
    plt.axvline(P.loc[m, "net"] * 100, color=COL["neg"], lw=0.7, ls="--")
plt.xlabel("Monthly return (%)")
plt.title("Figure 6. Distribution of monthly carry returns (dashed = worst 5)")
plt.legend(frameon=False, fontsize=7.5)
savefig("F06_return_distribution")

# F7 rolling correlations
plt.figure(figsize=(9, 3.6))
plt.plot(roll_spx.index, roll_spx, color=COL["carry"], label="Corr with S&P 500 daily return")
plt.plot(roll_vix.index, roll_vix, color=COL["mom"], label="Corr with daily change in VIX")
plt.axhline(0, color="black", lw=0.6)
plt.ylabel("Rolling 252-day correlation")
plt.title("Figure 7. Time-varying correlation of carry with equity risk proxies")
plt.legend(frameon=False, fontsize=7.5)
savefig("F07_rolling_correlations")

# F8 regimes
rt = regtab.iloc[:3]
fig, ax = plt.subplots(1, 2, figsize=(9, 3.2))
labels = ["Low VIX", "High VIX", "Crisis\n(VIX peak >= 30)"]
ax[0].bar(labels, rt["Mean ann. (%)"], color=[COL["static"], COL["mom"], COL["neg"]])
ax[0].axhline(0, color="black", lw=0.6)
ax[0].set_title("Mean return (% p.a.)")
ax[1].bar(labels, rt["Sharpe"], color=[COL["static"], COL["mom"], COL["neg"]])
ax[1].axhline(0, color="black", lw=0.6)
ax[1].set_title("Sharpe ratio")
fig.suptitle("Figure 8. Carry performance by VIX regime", fontsize=10, fontweight="bold")
savefig("F08_vix_regimes")

# F9 UIP betas
u = uip.loc[CCY + ["Pooled (currency FE, s.e. clustered by month)"]]
plt.figure(figsize=(8, 3.6))
lab = CCY + ["Pooled"]
plt.errorbar(range(len(u)), u["beta"], yerr=1.96 * u["HAC s.e."], fmt="o", color=COL["carry"], capsize=3)
plt.axhline(1, color=COL["static"], ls="--", lw=1, label="UIP (beta = 1)")
plt.axhline(0, color="black", lw=0.6, label="Random walk (beta = 0)")
plt.xticks(range(len(u)), lab)
plt.ylabel("Fama slope beta (95% CI)")
plt.title("Figure 9. UIP (Fama) regression slopes")
plt.legend(frameon=False, fontsize=7.5)
savefig("F09_uip_betas")

# F10 differentials heat map
plt.figure(figsize=(9, 3.4))
hm = diff_ann.loc[months - 1]
plt.imshow(hm.T.values, aspect="auto", cmap="RdBu", vmin=-6, vmax=6,
           extent=[0, len(hm), len(CCY), 0])
plt.yticks(np.arange(len(CCY)) + 0.5, CCY)
ticks = [i for i, m in enumerate(hm.index) if m.month == 1]
plt.xticks(ticks, [str(hm.index[i].year) for i in ticks])
plt.colorbar(label="Forward-implied rate differential vs USD (% p.a.)")
plt.title("Figure 10. Carry signal: forward-implied interest differentials vs USD")
savefig("F10_differential_heatmap")

# F11 worst months contributions
contrib = (W_carry.loc[worst] * x_ex.loc[worst]) * 100
plt.figure(figsize=(8, 3.6))
bottom_pos = np.zeros(len(worst)); bottom_neg = np.zeros(len(worst))
cmap = plt.get_cmap("tab10")
for i, c in enumerate(CCY):
    v = contrib[c].values
    pos, neg = np.where(v > 0, v, 0), np.where(v < 0, v, 0)
    plt.bar(range(len(worst)), pos, bottom=bottom_pos, color=cmap(i), label=c)
    plt.bar(range(len(worst)), neg, bottom=bottom_neg, color=cmap(i))
    bottom_pos += pos; bottom_neg += neg
plt.axhline(0, color="black", lw=0.6)
plt.scatter(range(len(worst)), P.loc[worst, "net"] * 100, color="black", zorder=5, s=18, label="Net return")
plt.margins(y=0.12)
plt.xticks(range(len(worst)), worst.astype(str))
plt.ylabel("Contribution to monthly return (%)")
plt.title("Figure 11. Currency contributions in the five worst carry months")
plt.legend(frameon=False, fontsize=7, ncol=4)
savefig("F11_worst_month_contributions")

# --------------------------------------------------------------------------
# 9. Excel workbook + key results
# --------------------------------------------------------------------------
with pd.ExcelWriter(OUT / "carry_results.xlsx", engine="openpyxl") as xw:
    readme = pd.DataFrame({"Notes": [
        "FX carry trade - results workbook generated by src/carry_project.py",
        f"Sample: daily {KEY['sample']['daily_start']} to {KEY['sample']['daily_end']}; "
        f"holding months {KEY['sample']['first_holding_month']} to {KEY['sample']['last_holding_month']} "
        f"({KEY['sample']['n_months']} months)",
        "Returns are forward-based excess returns (S_t+1/F_t - 1), USD per foreign currency.",
        "Portfolio: long top-3 / short bottom-3 by 1M forward discount, monthly rebalance, 5 bp per unit turnover.",
        "Sharpe = mean*12 / (sd*sqrt(12)); Calmar = CAGR/|MaxDD|; tail ratio = |mean of worst 5%| / mean of best 5%."]})
    readme.to_excel(xw, sheet_name="README", index=False)
    for name, df in TABLES.items():
        df.to_excel(xw, sheet_name=name[:31])


def _clean(o):
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, (np.floating, float)):
        return None if np.isnan(o) else round(float(o), 4)
    if isinstance(o, np.integer):
        return int(o)
    return o


(OUT / "key_results.json").write_text(json.dumps(_clean(KEY), indent=2))
print("Done. Outputs in", OUT)
