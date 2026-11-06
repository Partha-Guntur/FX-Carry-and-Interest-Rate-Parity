"""
Builds the LaTeX paper (paper/latex/main.tex) from the pipeline outputs and compiles it.

    python src/build_latex.py          (run src/carry_project.py first)

All numbers in tables are read from outputs/final/carry_results.xlsx, so the paper always
matches the latest run. Figures are copied into paper/latex/figures/ so the folder can be
uploaded to Overleaf as it is.
"""
import pathlib, shutil, subprocess, sys
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
FINAL = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "outputs" / "final"
LTX = pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "paper" / "latex"
(LTX / "figures").mkdir(parents=True, exist_ok=True)
for f in (FINAL / "figures").glob("*.png"):
    shutil.copy(f, LTX / "figures" / f.name)

XL = FINAL / "carry_results.xlsx"
T = lambda s: pd.read_excel(XL, s, index_col=0)


def esc(x):
    s = str(x)
    for a, b in [("\\", r"\textbackslash{}"), ("&", r"\&"), ("%", r"\%"), ("_", r"\_"), ("#", r"\#"),
                 ("$", r"\$"), ("~", r"\textasciitilde{}"), ("^", r"\^{}"), (">=", r"$\geq$"), ("<", r"$<$")]:
        s = s.replace(a, b)
    return s


def f(x, d=2, sign=False):
    if pd.isna(x):
        return "--"
    s = f"{x:+.{d}f}" if sign else f"{x:.{d}f}"
    return s.replace("-", "$-$") if s.startswith("-") or "-" in s else s


def table(caption, label, header, rows, colspec, note=None, size=r"\small", long=False, pos="!htbp"):
    out = []
    if long:
        out.append(r"{" + size)
        out.append(r"\begin{longtable}{" + colspec + "}")
        out.append(r"\caption{" + caption + r"}\label{" + label + r"}\\")
        out.append(r"\toprule " + " & ".join(header) + r" \\ \midrule \endfirsthead")
        out.append(r"\toprule " + " & ".join(header) + r" \\ \midrule \endhead")
        out.append(r"\bottomrule \endlastfoot")
        for r in rows:
            out.append(" & ".join(r) + r" \\")
        out.append(r"\end{longtable}")
        if note:
            out.append(r"\vspace{-0.6em}\par\footnotesize\emph{" + note + r"}\par")
        out.append(r"}")
        return "\n".join(out) + "\n"
    out.append(r"\begin{table}[" + pos + r"]\centering" + size)
    out.append(r"\caption{" + caption + r"}\label{" + label + "}")
    out.append(r"\begin{tabularx}{\textwidth}{" + colspec + "}")
    out.append(r"\toprule " + " & ".join(header) + r" \\ \midrule")
    for r in rows:
        out.append(" & ".join(r) + r" \\")
    out.append(r"\bottomrule\end{tabularx}")
    if note:
        out.append(r"\par\vspace{0.3em}\footnotesize\emph{" + note + "}")
    out.append(r"\end{table}")
    return "\n".join(out) + "\n"


def fig(fname, caption, label, width=0.8):
    return (r"\begin{figure}[!htbp]\centering\includegraphics[width=" + str(width) + r"\textwidth]{figures/" + fname +
            r"}\caption{" + caption + r"}\label{" + label + r"}\end{figure}" + "\n")


L = []
A = L.append
ANX = []

# ------------------------------------------------------------------ preamble
A(r"""\documentclass[11pt,a4paper]{article}
\usepackage[margin=2.2cm]{geometry}
\usepackage[T1]{fontenc}
\usepackage{lmodern}
\usepackage{graphicx,booktabs,tabularx,longtable,float,amsmath,array}
\usepackage[font=small,labelfont=bf]{caption}
\usepackage[authoryear,round]{natbib}
\usepackage[hidelinks]{hyperref}
\usepackage{setspace}
\setstretch{1.05}
\setlength{\parskip}{0.4em}
\setlength{\parindent}{0pt}
\renewcommand{\topfraction}{0.9}\renewcommand{\bottomfraction}{0.8}
\renewcommand{\textfraction}{0.07}\renewcommand{\floatpagefraction}{0.85}
\setcounter{topnumber}{3}\setcounter{bottomnumber}{2}\setcounter{totalnumber}{5}
\renewcommand{\arraystretch}{1.12}
\newcolumntype{Y}{>{\raggedright\arraybackslash}X}
\newcolumntype{C}{>{\centering\arraybackslash}X}
\graphicspath{{figures/}}
\title{\textbf{FX Carry Trade: Portfolio Construction, Crash Risk and Factor Analysis}\\[0.3em]
\large Eight G10 currencies against the US dollar, August 2016 -- August 2026}
\author{Partha Gunturu\\ \small M.Sc. Quantitative Finance, Ahmedabad University \quad Topic 9: Carry \& Macro Strategies}
\date{November 2026}
\begin{document}
\maketitle
""")

# ------------------------------------------------------------------ summary
A(r"""\begin{abstract}
\noindent We test a monthly long-short carry strategy on eight major currencies against the US dollar (EUR, GBP, JPY, CHF,
NOK, AUD, NZD, CAD) using Bloomberg spot and one-month forward data, September 2016 to July 2026 (119 months). Buying the
three highest-rate and selling the three lowest-rate currencies made 2.92\% a year after costs, with a Sharpe ratio of 0.44.
The profit came almost entirely from the interest-rate gap; exchange-rate moves added nothing, against uncovered interest
parity (UIP). Returns are skewed to the downside, and the five worst months all match global shocks (COVID-19, the Fed hikes
of 2018 and 2022, Omicron and the 2024 yen-carry unwind). Carry does well in calm markets, loses in crises and moves with
equities; after controlling for equity and volatility risk its extra return is close to zero. A three-month momentum filter
made results worse. Carry is a reward for crash risk, not a free lunch.
\end{abstract}
""")

# ------------------------------------------------------------------ 1 intro
A(r"""\section{Introduction}
A carry trade borrows in a low-rate currency and invests in a high-rate one. Under uncovered interest parity (UIP) the
high-rate currency should fall by the rate gap, leaving no profit. In practice it usually does not fall enough, so carry
makes money over long periods \citep{fama1984,engel1996,lrv2011}. The risk is sudden crashes, such as the yen-carry unwind
of 2008: carry goes ``up the stairs and down the elevator'' \citep{bnp2009}.

The period 2016--2026 is a good test. It covers the Fed hikes of 2017--18, the COVID-19 crash, the 2022--23 global rate
rises, the end of negative rates in Japan and the August 2024 yen unwind, the April 2025 tariff shock and the 2026 oil
shock. We ask: (1) Does carry earn a positive Sharpe ratio, and how does it vary between calm and stressed markets?
(2) Does UIP hold, and where does the return come from? (3) How large is crash risk, and which events caused it?
(4) Is carry a risk factor linked to equities and the VIX? (5) Does a momentum filter help?
""")

# ------------------------------------------------------------------ 2 literature
A(r"""\section{Literature Review}
\textbf{UIP and its failure.} Under UIP, the forward rate should predict the future spot rate. \citet{fama1984} regressed
spot changes on the forward premium and found slopes below one and often negative (the \emph{forward premium puzzle});
\citet{hansenhodrick1980} and \citet{engel1996} confirm this across currencies. Since 2008, covered-parity gaps also affect
JPY and CHF forwards \citep{dtv2018}.

\textbf{Carry as a risk premium.} \citet{lrv2011} show that a dollar factor (DOL) and a carry factor (HML\textsubscript{FX})
explain most currency returns, with high-rate currencies loading positively on carry. \citet{msss2012a} find carry loses
when global FX volatility rises, while JPY and CHF hedge. \citet{koijen2018} find carry across asset classes, and
\citet{burnside2012} reviews the risk-based explanations.

\textbf{Crash risk.} \citet{bnp2009} show carry is negatively skewed and crashes when the VIX rises and traders unwind.
\citet{jurek2014} finds option hedges remove part of the return; \citet{burnside2011} point to rare unseen disasters;
\citet{dhl2017} document large drawdowns. \citet{msss2012b} find momentum weak among major currencies. The BIS
\citep{bis2025,bis2024} documents the size of FX funding markets and links August 2024 to the unwinding of yen carry.
""")

# ------------------------------------------------------------------ 3 data
pc = T("07_currency_statistics")
rows = [[c, f(r["Avg fwd-implied differential vs USD (% p.a.)"]), f(r["Mean spot return (% p.a.)"], sign=True),
         f(r["Mean excess return (% p.a.)"], sign=True), f(r["Vol (% p.a.)"]), f(r["Months long (%)"], 0),
         f(r["Months short (%)"], 0)] for c, r in pc.iterrows()]
A(r"""\section{Data and Method}
\subsection{Bloomberg data}
\textbf{GP}: daily spot rates for EURUSD, GBPUSD, AUDUSD, NZDUSD, USDJPY, USDCHF, USDCAD, USDNOK, plus the S\&P 500 and VIX
(18 Aug 2016 -- 17 Aug 2026, 2,608 days). \textbf{FRD}: one-month forward points (forward = spot + points/10,000; /100 for
JPY). \textbf{WIRP}: implied central-bank paths on 17 Aug 2026, used as a forward-looking check only. \textbf{FXIP}: forward
points grid; positioning data were not available. All rates are quoted as USD per foreign currency, so a positive return
means the currency rose against USD. We use month-end data and drop the partial August 2026, leaving 119 holding months.
""")
A(table("The eight currencies against the US dollar, September 2016 -- July 2026", "tab:ccy",
        ["Currency", "Rate gap vs USD (\\% p.a.)", "Spot change (\\% p.a.)", "Carry return (\\% p.a.)", "Volatility (\\% p.a.)",
         "Months long (\\%)", "Months short (\\%)"], rows, "lCCCCCC",
        "Rate gap = one-month forward discount, annualised (roughly foreign rate minus US rate). Carry return = return from holding "
        "a one-month forward and rolling it each month."))
A(r"""Over this period the US dollar paid more than every other currency
(Table~\ref{tab:ccy}). CHF ($-$3.0 points), JPY ($-$2.9) and EUR ($-$1.9) were the cheapest to borrow. Because the strategy
ranks currencies against each other, the bought basket still paid 2.48 points more than the sold basket on average.

\subsection{Portfolio construction}
At each month-end the carry signal is the one-month forward discount:
\begin{equation}
c_{i,t} = \frac{S_{i,t}}{F_{i,t}} - 1 \;\approx\; \frac{i_{\text{foreign},t} - i_{\text{USD},t}}{12}
\end{equation}
We buy the top three and sell the bottom three (one third each) and hold to the next month-end. The return of a forward
position splits into a spot part and a carry part:
\begin{equation}
x_{i,t+1} = \frac{S_{i,t+1}}{F_{i,t}} - 1 \;=\; \underbrace{\left(\frac{S_{i,t+1}}{S_{i,t}} - 1\right)}_{\text{spot}}
\;+\; \underbrace{c_{i,t}}_{\text{carry}} \;+\; \text{cross term}
\end{equation}
Costs are 5 bp per unit of turnover. Benchmarks: a \textbf{dollar basket (DOL)} holding all eight currencies, and
\textbf{static carry}, which keeps the first month's positions throughout.

\subsection{Measures}
Sharpe = mean $\times12$ / volatility $\times\sqrt{12}$; Sortino uses downside volatility; Calmar = growth rate / maximum
drawdown; tail ratio = average of the worst 5\% of months / average of the best 5\%. UIP is tested with the
\citet{fama1984} regression $\Delta s_{i,t+1} = \alpha_i + \beta_i (f_{i,t} - s_{i,t}) + \varepsilon$, where UIP means
$\beta = 1$. Regimes split months by the VIX median (17.5) and flag crisis months (VIX $\geq$ 30). The momentum filter keeps a
long only if the currency rose over three months and a short only if it fell. Standard errors are Newey--West (3 lags).
Code: \texttt{src/carry\_project.py}.
""")

# ------------------------------------------------------------------ 4 positions
ph = pd.read_excel(XL, "27_position_history", index_col=0).reset_index()
rows = [[r["From"], r["To"], str(int(r["Months"])), esc(r["Long (high-yield)"]), esc(r["Short (funding)"]),
         f(r["Return over period (%)"], sign=True)] for _, r in ph.iterrows()]
sel = T("23_selection_frequency")
PAIR = {"EUR": ("EURUSD", "Buy EURUSD", "Sell EURUSD"), "GBP": ("GBPUSD", "Buy GBPUSD", "Sell GBPUSD"),
        "AUD": ("AUDUSD", "Buy AUDUSD", "Sell AUDUSD"), "NZD": ("NZDUSD", "Buy NZDUSD", "Sell NZDUSD"),
        "JPY": ("USDJPY", "Sell USDJPY", "Buy USDJPY"), "CHF": ("USDCHF", "Sell USDCHF", "Buy USDCHF"),
        "CAD": ("USDCAD", "Sell USDCAD", "Buy USDCAD"), "NOK": ("USDNOK", "Sell USDNOK", "Buy USDNOK")}
order = ["NZD", "CAD", "AUD", "NOK", "GBP", "EUR", "JPY", "CHF"]
prow = [[c, PAIR[c][0], f(sel.loc[c, "Long (%)"], 1), PAIR[c][1], f(sel.loc[c, "Short (%)"], 1), PAIR[c][2]] for c in order]
A(r"""\section{The Long and Short Positions}
\textbf{Short side.} The funding basket barely changed: CHF was sold in 100\% of months, JPY in 99\% and EUR in 98\%. All
three central banks kept rates at or below zero for most of the period. The only swaps were GBP for JPY in December 2021,
and CAD for EUR from June 2026 after the ECB hiked.

\textbf{Long side.} The long basket rotated as central banks diverged:
\begin{itemize}\setlength{\itemsep}{0pt}
\item \textbf{2016--2019: AUD, NZD, CAD} --- highest rates at the start; held two years (July 2017 -- June 2019).
\item \textbf{2019--2022: NOK, NZD, CAD} --- frequent changes as COVID cuts squeezed all rate gaps.
\item \textbf{2023 -- mid 2024: GBP, NZD, CAD} --- the Bank of England hiked to 5.25\%; held 19 months.
\item \textbf{Dec 2024 -- 2026: AUD, GBP, NOK} --- the RBA and Norges Bank kept rates high and hiked again in 2026.
\end{itemize}
Every position is against USD, so the dollar legs largely cancel and the portfolio is in effect long crosses such as NZD/JPY,
CAD/CHF and GBP/EUR (Tables~\ref{tab:pairs} and~\ref{tab:history}).
""")
A(table("How each currency position is traded, and how often it was used", "tab:pairs",
        ["Currency", "Bloomberg pair", "Months long (\\%)", "Trade when long", "Months short (\\%)", "Trade when short"], prow,
        "llCYCY", "Long a currency = buy it against USD; short = sell it against USD. For pairs quoted as USD per currency "
        "(USDJPY, USDCHF, USDCAD, USDNOK) the trade direction is reversed."))
A(table("Position history: every period in which the long and short baskets stayed the same", "tab:history",
        ["From", "To", "Months", "Long (high-rate)", "Short (funding)", "Return (\\%)"], rows,
        "llcp{3.6cm}p{3.6cm}c", "Return = compounded net return of the portfolio over the period.", size=r"\small", long=True))
A(r"""The two longest holding periods were the most profitable ($+$7.1\% and $+$11.2\%); the worst was
July 2019 -- March 2020 ($-$10.3\%), long NOK, NZD and CAD into COVID and the oil collapse.
""")

# ------------------------------------------------------------------ 5 performance
perf = T("01_performance_monthly")
cols = ["Carry (net)", "Carry (gross)", "Static carry, buy-and-hold (net)", "Dollar basket DOL, buy-and-hold", "S&P 500 (price)"]
metrics = [("Mean ann. (%)", "Average return (\\% p.a.)", 2), ("CAGR (%)", "Growth rate, CAGR (\\%)", 2),
           ("Vol ann. (%)", "Volatility (\\% p.a.)", 2), ("Sharpe", "Sharpe ratio", 2), ("Sortino", "Sortino ratio", 2),
           ("Max drawdown (%)", "Maximum drawdown (\\%)", 2), ("Calmar", "Calmar ratio", 2), ("Skewness", "Skewness", 2),
           ("Excess kurtosis", "Excess kurtosis", 2), ("Worst period (%)", "Worst month (\\%)", 2),
           ("Best period (%)", "Best month (\\%)", 2), ("Hit rate (%)", "Positive months (\\%)", 1),
           ("Tail ratio (|mean worst 5%| / mean best 5%)", "Tail ratio", 2), ("NW t-stat (mean=0)", "t-statistic (mean = 0)", 2)]
rows = [[n] + [f(perf.loc[c, m], d) for c in cols] for m, n, d in metrics]
A(r"""\section{Results: Portfolio Performance}""")
A(table("Performance summary, monthly returns, September 2016 -- July 2026 (119 months)", "tab:perf",
        ["", "Carry (net)", "Carry (gross)", "Static carry", "Dollar basket", "S\\&P 500"], rows, "lCCCCC",
        "Net = after 5 bp per unit of turnover. Static carry keeps the September 2016 positions. Dollar basket = equal weights in all "
        "eight currencies against USD. S\\&P 500 = price return."))
A(r"""\textbf{Main result.} Carry made 2.92\% a year after costs, with 6.61\% volatility, Sharpe 0.44 and Sortino 0.64
(Table~\ref{tab:perf}). It was positive in 59\% of months, but the t-statistic of 1.79 is significant only at 10\%. The
maximum drawdown was 14.0\% (August 2017 -- March 2020, recovered March 2021). Costs are negligible: only 8\% of the
portfolio is traded per month.

\textbf{Against buy-and-hold.} Rebalancing added value. Static carry made 1.76\% (Sharpe 0.23) because it held NZD and AUD
after their rates fell. The dollar basket lost 1.69\% (Sharpe $-$0.23) against a strong, high-yielding dollar. The S\&P 500
made 13.7\%, but carry rises and falls with it (Section 8), so it does not diversify equities.
""")
A(fig("F01_cumulative_returns.png", "Cumulative returns of carry, carry with the momentum filter, and the two buy-and-hold portfolios. "
      "Dotted lines mark the main market shocks.", "fig:cum", 0.78))
dec = T("04_return_decomposition")
rows = [[esc(i), f(r["Mean monthly (%)"], 3), f(r["Annualised (%)"]), f(r["NW t-stat"])] for i, r in dec.iterrows()]
A(table("Where the return comes from", "tab:dec", ["Part of return", "Average per month (\\%)", "Per year (\\%)", "t-statistic"],
        rows, "p{5.5cm}CCC"))
A(r"""\textbf{Source of return.} The carry part gave 2.48\% a year (t = 14.2); the spot part gave 0.49\% (t = 0.30), i.e.
nothing (Table~\ref{tab:dec}, Figure~\ref{fig:dec}). The strategy earned the rate gap and exchange rates did not take it away.
""")
A(fig("F02_return_decomposition.png", "Cumulative carry part and spot part of the portfolio return.", "fig:dec", 0.75))
sub = T("06_subperiod_performance")
rows = [[esc(i), str(int(r["Obs"])), f(r["Mean ann. (%)"]), f(r["Vol ann. (%)"]), f(r["Sharpe"]), f(r["Max drawdown (%)"]),
         f(r["NW t-stat (mean=0)"])] for i, r in sub.iterrows()]
A(table("Performance by sub-period (net)", "tab:sub", ["Period", "Months", "Return (\\% p.a.)", "Volatility (\\% p.a.)", "Sharpe",
                                                      "Max drawdown (\\%)", "t-stat"], rows, "lCCCCCC"))
A(r"""\textbf{Over time.} Before 2023 the Sharpe ratio was about 0.2 (Table~\ref{tab:sub}, Figures~\ref{fig:annual}
and~\ref{fig:rs}): 2018 lost 4.6\% on Fed hikes and the US--China trade war, and 2020 was slightly negative. From 2023 carry
made 5.39\% a year (Sharpe 1.24) as Japan and Switzerland stayed near zero while the UK, Norway and Australia kept rates
high. January--July 2026 made 7.6\%.
""")
A(fig("F03_annual_returns.png", "Yearly net returns of carry and carry with the momentum filter (2016: Sep--Dec; 2026: Jan--Jul).", "fig:annual", 0.7))
A(fig("F04_rolling_sharpe.png", "Rolling 12-month Sharpe ratio.", "fig:rs", 0.7))

reg = T("16_vix_regimes")
names = ["Low VIX (below median 17.5)", "High VIX (above median)", "Crisis (VIX $\\geq$ 30 in month)",
         "VIX low at start of month", "VIX high at start of month"]
rows = [[n, str(int(r["Obs"])), f(r["Mean ann. (%)"]), f(r["Vol ann. (%)"]), f(r["Sharpe"]), f(r["Worst period (%)"]),
         f(r["Hit rate (%)"], 1)] for n, (_, r) in zip(names, reg.iterrows())]
A(table("Carry performance in calm and stressed markets", "tab:reg",
        ["Market regime", "Months", "Return (\\% p.a.)", "Volatility (\\% p.a.)", "Sharpe", "Worst month (\\%)",
         "Positive months (\\%)"], rows, "p{4.0cm}CCCCCC",
        "Regimes use the average VIX in the month, or the VIX at the start of the month. Crisis months: 25, mostly in 2020 and 2022."))
A(r"""\textbf{Calm versus stressed markets.} Carry is a good-weather strategy (Table~\ref{tab:reg}, Figure~\ref{fig:reg}):
Sharpe 0.64 when the VIX is low, 0.32 when it is high, and $-$0.13 in crisis months. But months that \emph{start} with a
high VIX earned 5.94\% a year (Sharpe 0.82), because they include the rebounds after sell-offs. Holding carry through fear
was rewarded, as a risk premium should be.
""")
A(fig("F08_vix_regimes.png", "Average return and Sharpe ratio of carry in low-VIX, high-VIX and crisis months.", "fig:reg", 0.7))

# ------------------------------------------------------------------ 6 UIP
uip = T("10_uip_fama_regressions")
rows = [[("Pooled" if i.startswith("Pooled") else i), f(r["beta"]), f(r["HAC s.e."]), f(r["t (beta=0)"]), f(r["t (beta=1)"]),
         f(r["p (beta=1)"], 3), f(r["R2"], 3), str(int(r["Obs"]))] for i, r in uip.iterrows()]
upl = T("11_uip_portfolio_level")
urows = [["Average rate gap vs USD (carry)", *[f(v, sign=True) for v in upl.iloc[0]]],
         ["Actual spot change vs USD", *[f(v, sign=True) for v in upl.iloc[1]]],
         ["Spot change UIP predicts", *[f(v, sign=True) for v in upl.iloc[2]]]]
A(r"""\section{Results: UIP and the Forward Premium Puzzle}""")
A(table("UIP test (Fama regression), monthly data, annualised", "tab:uip",
        ["Currency", "$\\beta$", "Std. error", "t ($\\beta=0$)", "t ($\\beta=1$)", "p-value ($\\beta=1$)", "R$^2$", "Months"], rows,
        "lCCCCCCC", "UIP holds if $\\beta = 1$; a random walk gives $\\beta = 0$. Pooled = all currencies together with "
        "currency fixed effects and standard errors clustered by month.", pos="H"))
A(r"""\textbf{Currency by currency.} Slopes range from $-$3.0 (NOK) to 3.9 (CAD); pooled 1.15 (s.e. 1.61)
(Table~\ref{tab:uip}, Figure~\ref{fig:uip}). No currency rejects UIP, but none rejects a random walk either, and R$^2$ is
below 1.4\%. Ten years of monthly data cannot settle the question: rate gaps moved with the US cycle, while exchange rates
were driven by much larger shocks.
""")
A(fig("F09_uip_betas.png", "UIP slopes with 95\\% confidence intervals. UIP predicts $\\beta = 1$ (dashed line).", "fig:uip", 0.7))
A(table("UIP at the portfolio level (\\% per year)", "tab:uipp", ["", "Long basket", "Short basket", "Long minus short"], urows,
        "p{5.5cm}CCC"))
A(r"""\textbf{Portfolio level.} The portfolio test is clearer (Table~\ref{tab:uipp}). The sold currencies paid 2.6
points less than USD, so UIP says they should have risen 2.6\% a year; they fell 0.23\%. Long minus short, UIP predicts a
spot loss of 2.48\%; the actual result was a gain of 0.49\%. The yen paid 2.9 points less than the dollar and still fell
3.8\% a year as the Bank of Japan stayed near zero while the Fed went to 5.25--5.50\%. This is the forward premium puzzle.

\textbf{Implication.} The carry return is the rate gap; the risk is in the spot part, which Sections 7 and 8 examine. Ranking
on policy rates instead of forwards gives a similar result (Sharpe 0.35).
""")

# ------------------------------------------------------------------ 7 crash
cr = T("12_worst_5_months")
EV = {"2020-03": "COVID-19 declared a pandemic; Saudi--Russia oil price war (9 Mar) hit NOK and CAD; rush into dollars; "
                 "Fed cut rates to zero (15 Mar).",
      "2018-12": "Fed hiked to 2.25--2.50\\% and kept shrinking its balance sheet (19 Dec); oil and stocks fell; US government "
                 "shutdown (22 Dec).",
      "2021-11": "Omicron variant (26 Nov) caused an oil sell-off that hit NOK and CAD; Fed dropped the word "
                 "``transitory'' (30 Nov).",
      "2022-09": "Fed hiked 75 bp (21 Sep) and the dollar peaked; UK mini-budget crisis (23 Sep); Japan bought yen for the "
                 "first time since 1998 (22 Sep).",
      "2024-07": "Japan intervened to support the yen (11--12 Jul) and the BoJ hiked (31 Jul); the yen jumped and the short-yen "
                 "leg lost; the unwind peaked on 5 Aug."}
rows = [[m, f(r["Net return (%)"]), f(r["Long leg (%)"]), f(r["Short leg (%)"]), esc(r["Longs"]) + " / " + esc(r["Shorts"]),
         f(r["Avg VIX"], 1), EV[m]] for m, r in cr.iterrows()]
wd = T("14_worst_10_days")
DE = {"2020-03-09": "Saudi--Russia oil price war; global stock crash", "2020-03-18": "Rush into US dollars",
      "2025-04-04": "China retaliates against US tariffs", "2020-03-12": "Stock market crash; ECB disappoints",
      "2021-11-26": "Omicron variant; oil falls 13\\%", "2025-04-10": "US--China tariff escalation",
      "2020-03-16": "Fed cuts to zero, markets still fall", "2020-06-11": "Fed outlook and second-wave fears",
      "2022-05-18": "US retail earnings shock", "2025-04-03": "Day after US ``Liberation Day'' tariffs"}
drows = [[str(i)[:10], f(r["Carry net (%)"]), f(r["S&P 500 (%)"]), f(r["VIX change"], 1), DE.get(str(i)[:10], "")]
         for i, r in wd.iterrows()]
A(r"""\section{Results: Crash Risk}
\textbf{Shape of returns.} Monthly skewness is $-$0.54 and excess kurtosis 0.99; daily figures are $-$0.74 and 8.2. The tail
ratio is 1.08: the six worst months averaged $-$4.36\% against $+$4.02\% for the six best. The dollar basket, by contrast, is
symmetric (skewness 0.03). The pattern matches \citet{bnp2009}, although milder because G10 rate gaps were small.
""")
A(fig("F06_return_distribution.png", "Monthly carry returns against a normal distribution with the same mean and volatility. "
      "Dashed lines mark the five worst months.", "fig:dist", 0.55))
A(table("The five worst months and what caused them", "tab:worst",
        ["Month", "Return (\\%)", "Long side (\\%)", "Short side (\\%)", "Long / short", "VIX", "What happened"], rows,
        "p{1.1cm}p{1.0cm}p{1.0cm}p{1.0cm}>{\\raggedright\\arraybackslash}p{2.3cm}p{0.6cm}Y",
        "Long/short basket = contribution of each side to the monthly return.", size=r"\footnotesize"))
A(r"""\textbf{Linking crashes to events.} All five worst months were global sell-offs (Table~\ref{tab:worst},
Figure~\ref{fig:contrib}), and all losses came from exchange rates, not carry. Two patterns:
\begin{itemize}\setlength{\itemsep}{0pt}
\item \textbf{Long basket fell} (Mar 2020, Dec 2018, Nov 2021, Sep 2022): NOK, NZD, AUD and CAD fell with oil and equities as
the dollar rose.
\item \textbf{Short basket rose} (Jul 2024): the yen jumped on the BoJ hike and Japanese intervention, forcing yen-funded
traders to unwind at once --- the 2008 pattern again.
\end{itemize}
""")
A(fig("F11_worst_month_contributions.png", "Contribution of each currency to the return in the five worst months (dots = total).",
      "fig:contrib", 0.72))
ANX.append(table("The ten worst days", "tab:days", ["Date", "Carry (\\%)", "S\\&P 500 (\\%)", "VIX change", "Event"], drows, "lcccY",
        size=r"\small"))
A(r"""Seven of the ten worst days were in March 2020 or April 2025 (Annex Table~\ref{tab:days}). In April
2025 the dollar fell, yet carry lost 3.0\% because CHF, JPY and EUR rose even faster than the high-rate currencies: carry
crash risk is about safe havens versus risky currencies, not the dollar. The 2026 Iran-war oil shock did not hurt
(March 2026: $+$0.6\%), since the strategy was long NOK and AUD and short oil importers JPY and EUR.
""")
ANX.append(fig("F05_drawdown.png", "Drawdown of the carry portfolio (net), with the main market shocks marked.", "fig:dd", 0.75))

# ------------------------------------------------------------------ 8 factor
cor = T("17_correlations")
crow = [[esc(i), *[f(v) for v in r.values]] for i, r in cor.iterrows()]
rx = T("19_carry_risk_exposures")
xn = ["S\\&P 500 return", "Change in VIX", "Global FX volatility shock", "S\\&P 500 and VIX change together"]
xrow = [[n, f(r.iloc[0], 3), f(r.iloc[1]), f(r.iloc[2] / 100 if "S\\&P" in n else r.iloc[2], 3), f(r.iloc[3]), f(r.iloc[4])]
        for n, (_, r) in zip(xn, rx.iterrows())]
fb = T("20_factor_betas"); fmb = T("21_fama_macbeth")
brow = [[c, f(r["beta_DOL"]), f(r["beta_HML"]), f(r["mean excess (% p.m.)"], 3)] for c, r in fb.iterrows()]
fnames = {"const": "Constant", "lambda_DOL": "Price of dollar risk", "lambda_HML": "Price of carry risk",
          "Factor mean: DOL": "Average return of DOL", "Factor mean: HML_FX": "Average return of carry factor",
          "Cross-sectional R2": "R$^2$ across currencies"}
frow = [[fnames.get(i, esc(i)), f(r.iloc[0], 3), f(r.iloc[1])] for i, r in fmb.iterrows()]
A(r"""\section{Results: Is Carry a Risk Factor?}""")
A(table("Correlation of carry with the S\\&P 500 and the VIX", "tab:corr",
        ["Period", "Monthly: S\\&P 500", "Monthly: VIX change", "Daily: S\\&P 500", "Daily: VIX change"], crow, "lCCCC"))
A(r"""\textbf{Correlation over time.} Carry moves with equities: correlation 0.56 with the S\&P 500 and $-$0.57 with
VIX changes (monthly; Table~\ref{tab:corr}). The rolling one-year correlation (Figure~\ref{fig:roll}) stayed between 0.30 and
0.79: about 0.75 after March 2020, 0.30--0.40 in calm 2023--24, and back near 0.7 after April 2025. It rises exactly when
diversification is needed --- the mark of a risk factor.
""")
A(fig("F07_rolling_correlations.png", "Rolling one-year (252-day) correlation of daily carry returns with the S\\&P 500 and with "
      "daily VIX changes.", "fig:roll", 0.8))
A(table("Carry regressed on market risk (dependent variable: monthly carry return, \\%)", "tab:risk",
        ["Risk measure", "$\\alpha$ (\\% per month)", "t($\\alpha$)", "$\\beta$", "t($\\beta$)", "R$^2$"], xrow, "p{4.5cm}CCCCC",
        "$\\beta$ on the S\\&P 500: carry return per 1\\% S\\&P move. $\\beta$ on the VIX: carry return (\\%) per VIX point. "
        "FX volatility shock = unexpected change in average daily moves of the eight currencies."))
A(r"""\textbf{Risk-adjusted return.} The S\&P 500 alone explains 31\% of carry's variation ($\beta$ = 0.24) and VIX
changes 33\% ($-$0.20\% per VIX point); FX volatility shocks also hurt (Table~\ref{tab:risk}). With both controls, the alpha
falls from 0.24\% to 0.10\% a month and is insignificant (t = 0.73).
""")
ANX.append(table("Factor betas of each currency (dollar factor and carry factor)", "tab:betas",
        ["Currency", "Beta to dollar factor", "Beta to carry factor", "Average return (\\% per month)"], brow, "lCCC"))
A(table("Fama--MacBeth test: is carry risk priced? (\\% per month)", "tab:fmb", ["", "Estimate", "t-statistic"], frow, "p{6cm}CC",
        "If the factor is priced correctly, its price of risk should equal its average return. 8 currencies, 119 months."))
A(r"""\textbf{Priced like a Fama--French factor?} Funding currencies have negative carry betas (JPY $-$0.82, CHF
$-$0.51, EUR $-$0.32) and high-rate currencies positive ones (AUD 0.48, NOK 0.45, NZD 0.42, CAD 0.31; Annex
Table~\ref{tab:betas}). The estimated price of carry risk (0.233\% a month) is almost equal to the factor's average return
(0.247\%), and the two factors explain 46\% of cross-currency returns (Table~\ref{tab:fmb}). With eight currencies the
estimate is imprecise (t = 1.49), so this supports, but does not prove, a priced carry factor.
""")

# ------------------------------------------------------------------ 9 momentum
mo = T("02_performance_common_sample_mo")
mn = ["Carry", "Carry + momentum filter", "Carry and momentum combined rank", "Momentum only (reference)"]
mrow = [[n, f(r["Mean ann. (%)"]), f(r["Vol ann. (%)"]), f(r["Sharpe"]), f(r["Max drawdown (%)"]), f(r["Skewness"]),
         f(r["NW t-stat (mean=0)"])] for n, (_, r) in zip(mn, mo.iterrows())]
A(r"""\section{Results: Momentum Filter}""")
A(table("Carry with and without the three-month momentum filter (December 2016 -- July 2026, 116 months, net)", "tab:mom",
        ["Strategy", "Return (\\% p.a.)", "Volatility (\\% p.a.)", "Sharpe", "Max drawdown (\\%)", "Skewness", "t-stat"], mrow,
        "p{4.2cm}CCCCCC", "Filter: keep a long only if the currency rose over the last three months, and a short only if it fell. "
        "Combined rank: average of the carry rank and the momentum rank. Momentum only: buy the three best and sell the three "
        "worst performers of the last three months."))
A(r"""The filter made things worse (Table~\ref{tab:mom}): $-$1.63\% a year (Sharpe $-$0.23) against $+$2.52\%
(Sharpe 0.38) for plain carry, with twice the drawdown. Pure three-month momentum lost 5.41\% a year (t = $-$2.84): major
currencies reversed at this horizon, so the filter dropped positions just before they recovered, in line with
\citet{msss2012b}. It also left one side empty in a quarter to a third of months (a hidden dollar bet) and raised turnover
from 8\% to 62\%. It helped slightly in crises (Sharpe 0.04 vs $-$0.13) but cost far more in calm markets ($-$0.70 vs 0.64).
Volatility-based sizing or option hedges \citep{jurek2014} are better crash protection.
""")

# ------------------------------------------------------------------ 10 discussion
tc = T("08_transaction_cost_robustness"); sg = T("09_signal_robustness")
rrows = [[esc(i), f(r["Mean ann. (%)"]), f(r["Sharpe"], 3), f(r["Max drawdown (%)"])] for i, r in tc.iterrows()]
rrows += [[esc(i), f(r["Mean ann. (%)"]), f(r["Sharpe"], 3), f(r["Max drawdown (%)"])] for i, r in sg.iterrows()]
A(r"""\section{Discussion}
\textbf{Risk premium or inefficiency?} A risk premium: the return is the rate gap, earned slowly and lost in global
sell-offs; returns are left-skewed; carry moves with equities and against the VIX, more so in crises; alpha disappears after
risk controls; and the price of carry risk matches its mean. Two cautions: significance is only at 10\%, and the result rests
on one trade --- short CHF, JPY and EUR against a high-yielding dollar. The long basket alone made only 0.13\% a year.
""")
ANX.append(table("Robustness checks (net)", "tab:rob", ["Version", "Return (\\% p.a.)", "Sharpe", "Max drawdown (\\%)"], rrows, "p{5.5cm}CCC"))
A(r"""\textbf{Costs and robustness.} Raising costs from 0 to 20 bp only lowers the Sharpe from 0.45 to 0.42 (Annex
Table~\ref{tab:rob}); FXIP forward spreads (e.g. 15.03/15.09 for EURUSD) imply under 1 bp a month. Policy-rate ranking
(Sharpe 0.35) and two-by-two legs (0.40) give similar results.

\textbf{Capacity.} USD, EUR and JPY are the most traded currencies \citep{bis2025}, so size is not the limit; crowding is.
When many leveraged traders fund in the same currency, as with the yen in 2007 and 2024, the unwind becomes the crash.

\textbf{Outlook (WIRP).} On 17 August 2026 WIRP ranks the currencies like the forwards do (rank correlation 0.98; Annex
Table~\ref{tab:wirp}). The current portfolio is long AUD, NOK, GBP and short CHF, JPY, CAD. Markets price about 82 bp of
BoJ hikes against 38 bp from the Fed, so the yen funding gap is expected to shrink --- the set-up behind the 2024 crash.

\textbf{Limitations.} Eight currencies; one deep crisis in the sample; daily returns approximated; fixed costs; WIRP is one
snapshot and positioning data were unavailable.

\section{Conclusion}
A simple G10 carry strategy made 2.9\% a year (Sharpe 0.44) in 2016--2026, beating static carry and a dollar basket. It was
short CHF, JPY and EUR almost every month and rotated its longs among AUD, NZD, CAD, NOK and GBP. The return was the rate
gap: low-rate currencies, especially the yen, did not rise as UIP predicts. The cost is crash risk --- left-skewed returns,
losses in global shocks and crises, and higher equity correlation under stress. Equity and volatility risk explain most of
the return, so carry is a risk premium, not a market error. Momentum filters do not help; sizing and option hedges are
better tools. With the BoJ now hiking, the short-yen trade that drove the decade's profits is also its biggest risk.
""")

# ------------------------------------------------------------------ references
A(r"""\begin{thebibliography}{99}\setlength{\itemsep}{2pt}\small
\bibitem[Bank for International Settlements(2024)]{bis2024} Bank for International Settlements. (2024, September). \emph{BIS Quarterly Review: International banking and financial market developments}. BIS. https://www.bis.org/publ/qtrpdf/r\_qt2409.htm
\bibitem[Bank for International Settlements(2025)]{bis2025} Bank for International Settlements. (2025). \emph{Triennial Central Bank Survey of foreign exchange and over-the-counter (OTC) derivatives markets in 2025}. BIS. https://www.bis.org/statistics/rpfx25.htm
\bibitem[Brunnermeier et~al.(2009)]{bnp2009} Brunnermeier, M. K., Nagel, S., \& Pedersen, L. H. (2009). Carry trades and currency crashes. \emph{NBER Macroeconomics Annual, 23}(1), 313--348.
\bibitem[Burnside(2012)]{burnside2012} Burnside, C. (2012). Carry trades and risk. In J. James, I. Marsh, \& L. Sarno (Eds.), \emph{Handbook of exchange rates} (pp. 283--312). Wiley.
\bibitem[Burnside et~al.(2011)]{burnside2011} Burnside, C., Eichenbaum, M., Kleshchelski, I., \& Rebelo, S. (2011). Do peso problems explain the returns to the carry trade? \emph{Review of Financial Studies, 24}(3), 853--891.
\bibitem[Daniel et~al.(2017)]{dhl2017} Daniel, K., Hodrick, R. J., \& Lu, Z. (2017). The carry trade: Risks and drawdowns. \emph{Critical Finance Review, 6}(2), 211--262.
\bibitem[Du et~al.(2018)]{dtv2018} Du, W., Tepper, A., \& Verdelhan, A. (2018). Deviations from covered interest rate parity. \emph{Journal of Finance, 73}(3), 915--957.
\bibitem[Engel(1996)]{engel1996} Engel, C. (1996). The forward discount anomaly and the risk premium: A survey of recent evidence. \emph{Journal of Empirical Finance, 3}(2), 123--192.
\bibitem[Fama(1984)]{fama1984} Fama, E. F. (1984). Forward and spot exchange rates. \emph{Journal of Monetary Economics, 14}(3), 319--338.
\bibitem[Fama and MacBeth(1973)]{fm1973} Fama, E. F., \& MacBeth, J. D. (1973). Risk, return, and equilibrium: Empirical tests. \emph{Journal of Political Economy, 81}(3), 607--636.
\bibitem[Hansen and Hodrick(1980)]{hansenhodrick1980} Hansen, L. P., \& Hodrick, R. J. (1980). Forward exchange rates as optimal predictors of future spot rates: An econometric analysis. \emph{Journal of Political Economy, 88}(5), 829--853.
\bibitem[Jurek(2014)]{jurek2014} Jurek, J. W. (2014). Crash-neutral currency carry trades. \emph{Journal of Financial Economics, 113}(3), 325--347.
\bibitem[Koijen et~al.(2018)]{koijen2018} Koijen, R. S. J., Moskowitz, T. J., Pedersen, L. H., \& Vrugt, E. B. (2018). Carry. \emph{Journal of Financial Economics, 127}(2), 197--225.
\bibitem[Lustig et~al.(2011)]{lrv2011} Lustig, H., Roussanov, N., \& Verdelhan, A. (2011). Common risk factors in currency markets. \emph{Review of Financial Studies, 24}(11), 3731--3777.
\bibitem[Menkhoff et~al.(2012a)]{msss2012a} Menkhoff, L., Sarno, L., Schmeling, M., \& Schrimpf, A. (2012a). Carry trades and global foreign exchange volatility. \emph{Journal of Finance, 67}(2), 681--718.
\bibitem[Menkhoff et~al.(2012b)]{msss2012b} Menkhoff, L., Sarno, L., Schmeling, M., \& Schrimpf, A. (2012b). Currency momentum strategies. \emph{Journal of Financial Economics, 106}(3), 660--684.
\bibitem[Newey and West(1987)]{nw1987} Newey, W. K., \& West, K. D. (1987). A simple, positive semi-definite, heteroskedasticity and autocorrelation consistent covariance matrix. \emph{Econometrica, 55}(3), 703--708.
\end{thebibliography}
\noindent{\small Data: Bloomberg L.P. (2026), GP, FRD, WIRP and FXIP functions, accessed August 2026. Event dates: official releases of
the Federal Reserve, ECB, Bank of Japan, Bank of England, Swiss National Bank, Norges Bank, RBA, RBNZ, Bank of Canada and
Japan's Ministry of Finance.}
""")

# ------------------------------------------------------------------ annex
an = T("05_annual_returns")
arows = [[str(i), *[f(r[c], sign=True) for c in ["Carry (net)", "Carry + momentum (net)", "Static carry", "DOL"]],
          str(int(r["Months"]))] for i, r in an.iterrows()]
dd = pd.read_excel(XL, "15_drawdown_episodes", index_col=0)
ddrows = [[str(r.iloc[0]), str(r.iloc[1]), str(r.iloc[2]), f(r.iloc[3])] for _, r in dd.iterrows()]
pdl = T("03_performance_daily")
dn = ["Carry (net)", "Carry + momentum (net)", "Dollar basket", "S\\&P 500"]
dlrows = [[n, f(r["Mean ann. (%)"]), f(r["Vol ann. (%)"]), f(r["Sharpe"]), f(r["Max drawdown (%)"]), f(r["Skewness"]),
           f(r["Excess kurtosis"]), f(r["Worst period (%)"])] for n, (_, r) in zip(dn, pdl.iterrows())]
w = T("22_wirp_forward_looking_carry")
wrows = [[i, f(r["Current implied O/N rate (%)"]), f(r["Implied rate at last priced meeting (%)"]), f(r["Expected change (bp)"], 0),
          f(r["Forward-implied differential, 17-Aug-2026 (% p.a.)"]), str(int(r["Rank: WIRP expected differential"])),
          str(int(r["Rank: current forward carry"]))] for i, r in w.iterrows()]
EVT = [("2016-11-08", "USD, JPY", "US election: dollar and US yields rise, yen falls"),
       ("2016-12-14", "USD", "Fed hikes to 0.50--0.75\\%; start of the 2017--18 hiking cycle"),
       ("2018-02-05", "All", "VIX spike (``Volmageddon''); carry $-$2.8\\% in February 2018"),
       ("2018-07-06", "AUD, NZD", "First US tariffs on China; trade war hits AUD and NZD"),
       ("2018-12-19", "USD", "Fed hikes to 2.25--2.50\\%; late-2018 sell-off"),
       ("2019-01-03", "JPY, AUD", "Yen flash crash: AUD/JPY falls about 7\\% in minutes"),
       ("2019-08-05", "JPY, AUD", "Chinese yuan breaks 7 per dollar; US calls China a currency manipulator"),
       ("2020-03-09", "NOK, CAD", "Saudi--Russia oil price war; stock crash"),
       ("2020-03-15", "All", "Fed cuts to zero; dollar swap lines to other central banks"),
       ("2020-11-09", "All", "Vaccine news; risk rally (carry $+$4.2\\% in November 2020)"),
       ("2021-11-26", "NOK, CAD", "Omicron variant; oil sell-off"),
       ("2022-02-24", "EUR, NOK", "Russia invades Ukraine; energy shock"),
       ("2022-09-21/23", "USD, GBP, JPY", "Fed $+$75 bp; UK mini-budget; Japan buys yen (22 Sep)"),
       ("2022-11-10", "USD", "Soft US inflation data: largest one-day dollar fall since 2009"),
       ("2022-12-20", "JPY", "Bank of Japan widens its bond-yield band; yen jumps"),
       ("2023-03-10/19", "CHF, JPY", "Silicon Valley Bank fails; UBS takes over Credit Suisse"),
       ("2024-03-19", "JPY", "Bank of Japan ends negative rates"),
       ("2024-07-11/31", "JPY", "Japan buys yen; BoJ hikes to 0.25\\%; yen-carry unwind starts"),
       ("2024-08-05", "JPY, all", "Global carry crash: Nikkei $-$12.4\\%"),
       ("2025-04-02", "All", "US ``Liberation Day'' tariffs; 90-day pause on 9 April"),
       ("2025-12-19", "JPY", "Bank of Japan hikes to 0.75\\%"),
       ("2026-02-28", "NOK, CAD, JPY", "US--Israel strikes on Iran; Strait of Hormuz closed; oil above \\$100"),
       ("2026-02 to 05", "AUD", "RBA hikes three times, 3.60\\% to 4.35\\%"),
       ("2026-04-28", "JPY", "Japan starts record yen buying (\\textyen 11.7tn, to 27 May)"),
       ("2026-06-11/16", "EUR, JPY", "ECB hikes to 2.25\\%; Bank of Japan hikes to 1.00\\%")]
A(r"""\clearpage
\appendix
\section*{Annexures}
\addcontentsline{toc}{section}{Annexures}
\setcounter{table}{0}\renewcommand{\thetable}{A\arabic{table}}
\setcounter{figure}{0}\renewcommand{\thefigure}{A\arabic{figure}}
\subsection*{Annex A. Additional results}
""")
A(table("Yearly returns (\\%)", "tab:annual", ["Year", "Carry (net)", "Carry + momentum", "Static carry", "Dollar basket", "Months"],
        arows, "lCCCCC", "2016 covers September--December; 2026 covers January--July."))
for _x in ANX:
    A(_x)
A(table("Five largest drawdowns (net, monthly)", "tab:dd", ["Start", "Lowest point", "Recovered", "Depth (\\%)"], ddrows, "CCCC"))
A(table("Daily statistics", "tab:daily", ["Series", "Return (\\% p.a.)", "Volatility (\\% p.a.)", "Sharpe", "Max drawdown (\\%)",
                                          "Skewness", "Excess kurtosis", "Worst day (\\%)"], dlrows, "lCCCCCCC"))
A(fig("F10_differential_heatmap.png", "Carry signal over time: forward-implied rate gap of each currency against USD (\\% p.a.).",
      "fig:heat", 0.95))
A(table("Bloomberg WIRP snapshot (17 August 2026) as a forward-looking check", "tab:wirp",
        ["Currency", "Current rate (\\%)", "Implied rate in about one year (\\%)", "Expected change (bp)", "Forward rate gap now (\\% p.a.)",
         "Rank (WIRP)", "Rank (forward)"], wrows, "lCCCCCC",
        "USD: current implied rate 3.63\\%, about 38 bp of hikes priced to July 2027. Rank correlation between the two rankings: 0.98."))
A(r"""\subsection*{Annex B. Python program}
The whole analysis is run by one script, \texttt{src/carry\_project.py}. It reads the Bloomberg files in \texttt{data/} and writes
every table to \texttt{outputs/final/tables/} (also collected in \texttt{carry\_results.xlsx}) and every chart to
\texttt{outputs/final/figures/}. The steps are: (1) load spot and one-month forward rates and quote them as USD per currency;
(2) take month-end values and compute the forward-discount signal; (3) build the carry, momentum, static and dollar-basket
portfolios; (4) compute forward-based returns, the spot and carry parts, turnover and costs, and daily returns; (5) performance
statistics, sub-periods and VIX regimes; (6) UIP regressions; (7) worst months and days, drawdowns and the tail ratio;
(8) correlations, risk regressions and the Fama--MacBeth test; (9) the WIRP check and robustness tests. This paper is built by
\texttt{src/build\_latex.py}, which reads the same results file.
\subsection*{Annex C. Key events}
""")
A(table("Key market and policy events used in this paper", "tab:events", ["Date", "Currencies", "Event"],
        [list(e) for e in EVT], "llY", "Full list of about 370 events: \\texttt{data/macro\\_event\\_log.xlsx}.", size=r"\small", pos="H"))
A(r"""\subsection*{Annex D. Bloomberg functions}""")
A(table("Bloomberg functions used", "tab:bbg", ["Function", "What it gives", "How it is used"],
        [["GP", "Daily spot rates for the 8 pairs; S\\&P 500 and VIX", "All returns, regimes and correlations"],
         ["FRD", "One-month forward points", "Carry signal and forward-based returns"],
         ["WIRP", "Market-implied central-bank rate paths (17 Aug 2026)", "Forward-looking check (Table~\\ref{tab:wirp})"],
         ["FXIP", "Forward points, overnight to six months (bid/ask)", "Roll-cost estimate; positioning data not available"],
         ["CORR", "Rolling correlation of carry with SPX and VIX", "Check Figure~\\ref{fig:roll} on the terminal (252-day window)"],
         ["REGR", "Regression of carry on SPX and VIX change", "Check Table~\\ref{tab:risk} on the terminal"],
         ["BTST", "Strategy backtest", "Optional check of Table~\\ref{tab:perf}"]], "lYY", pos="H"))
A(r"\end{document}")

tex = "\n".join(L)
(LTX / "main.tex").write_text(tex)
for _ in range(2):
    res = subprocess.run(["pdflatex", "-interaction=nonstopmode", "main.tex"], cwd=LTX, capture_output=True, text=True)
print("pdflatex exit", res.returncode)
for ext in ("aux", "log", "out", "toc"):
    pass
print("written", LTX / "main.tex")
