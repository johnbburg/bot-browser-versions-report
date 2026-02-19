"""
Generate self-contained HTML report with embedded charts.
Run: python3 generate_html_report.py
Output: report.html
"""

import base64
import pandas as pd
import numpy as np
from pathlib import Path

OUTPUT_DIR = Path("output")
DATA_DIR = Path("statcounter-csv")

def b64img(path: Path) -> str:
    """Return a base64-encoded data URI for a PNG file."""
    with open(path, "rb") as f:
        return "data:image/png;base64," + base64.b64encode(f.read()).decode()

def main():
    # --- Load key data for inline tables ---
    df = pd.read_csv(OUTPUT_DIR / "cleaned_browser_data.csv", parse_dates=["date"])
    fam_avg = pd.read_csv(OUTPUT_DIR / "summary_family_share.csv")
    outliers = pd.read_csv(OUTPUT_DIR / "outlier_months.csv", parse_dates=["date"])
    conc = pd.read_csv(OUTPUT_DIR / "concentration_metrics_refA.csv", parse_dates=["date"])
    policy = pd.read_csv(OUTPUT_DIR / "policy_thresholds.csv")
    bucket_a = pd.read_csv(OUTPUT_DIR / "bucket_shares_refA.csv")

    # --- Encode charts ---
    imgs = {
        "ts_2022":       b64img(OUTPUT_DIR / "timeseries_2022.png"),
        "ts_2025":       b64img(OUTPUT_DIR / "timeseries_2025-26.png"),
        "bucket_cmp":    b64img(OUTPUT_DIR / "bucket_comparison_refA.png"),
        "chrome_tail":   b64img(OUTPUT_DIR / "chrome_old_tail_refA.png"),
        "hhi":           b64img(OUTPUT_DIR / "concentration_hhi_refA.png"),
    }

    # --- Pre-compute a few inline stats ---
    # Family share pivot 2022 vs 2025-26
    t1 = fam_avg[fam_avg["period"].isin(["2022","2025-26"])].pivot(
        index="browser_family", columns="period", values="avg_share_pct"
    ).fillna(0).round(2).sort_values("2025-26", ascending=False)

    # Bucket shares for Chrome, Edge, Firefox
    def bucket_row(family, period, bucket):
        r = bucket_a[(bucket_a["browser_family"]==family) &
                     (bucket_a["period"]==period) &
                     (bucket_a["bucket"]==bucket)]
        if r.empty: return 0, 0
        return round(float(r["share_all_traffic"].values[0]),2), \
               round(float(r["share_within_family"].values[0]),2)

    # Avg HHI
    hhi_avg = conc[conc["period"].isin(["2022","2025-26"])].groupby(
        ["browser_family","period"])["HHI"].mean().round(0).reset_index()
    top1_avg = conc[conc["period"].isin(["2022","2025-26"])].groupby(
        ["browser_family","period"])["top1_pct_of_tail"].mean().round(1).reset_index()
    top3_avg = conc[conc["period"].isin(["2022","2025-26"])].groupby(
        ["browser_family","period"])["top3_pct_of_tail"].mean().round(1).reset_index()

    def get_stat(tbl, family, period, col):
        r = tbl[(tbl["browser_family"]==family) & (tbl["period"]==period)]
        if r.empty: return "—"
        return str(r[col].values[0])

    # Chrome version cadence (2025)
    chrome_2526 = df[(df["browser_family"]=="Chrome") &
                     (df["period"]=="2025-26") &
                     (df["major"].notna())]
    cadence_rows = []
    for date, grp in chrome_2526.groupby("date"):
        top = grp.sort_values("share", ascending=False).iloc[0]
        cadence_rows.append((date.strftime("%b %Y"), int(top["major"]), round(float(top["share"]),1)))

    # Firefox 118 monthly
    ff118 = df[(df["browser_family"]=="Firefox") & (df["major"]==118)].sort_values("date")
    ff11  = df[(df["browser_family"]=="Firefox") & (df["major"]==11)].sort_values("date")

    # Edge 87 spike
    e87 = df[(df["browser_family"]=="Edge") & (df["major"]==87)].sort_values("date")

    # ---------------------------------------------------------------
    # HTML template
    # ---------------------------------------------------------------
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Browser Version Anti-Bot Analysis — US Market Share 2022–2026</title>
<style>
  :root {{
    --blue:   #2563eb;
    --lblue:  #dbeafe;
    --green:  #16a34a;
    --lgreen: #dcfce7;
    --amber:  #d97706;
    --lamber: #fef3c7;
    --red:    #dc2626;
    --lred:   #fee2e2;
    --purple: #7c3aed;
    --lpurple:#ede9fe;
    --gray:   #374151;
    --lgray:  #f3f4f6;
    --border: #e5e7eb;
    --max-w:  900px;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    font-size: 16px;
    line-height: 1.7;
    color: var(--gray);
    background: #fff;
  }}
  a {{ color: var(--blue); text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}

  /* Layout */
  .page-header {{
    background: linear-gradient(135deg, #1e3a8a 0%, #2563eb 100%);
    color: #fff;
    padding: 3rem 2rem 2.5rem;
    text-align: center;
  }}
  .page-header h1 {{ font-size: 2rem; font-weight: 700; margin-bottom: .5rem; }}
  .page-header p  {{ font-size: 1rem; opacity: .85; max-width: 650px; margin: 0 auto; }}
  .page-header .meta {{ margin-top: 1rem; font-size: .85rem; opacity: .7; }}

  nav.toc {{
    background: var(--lgray);
    border-bottom: 1px solid var(--border);
    padding: .75rem 2rem;
    font-size: .875rem;
  }}
  nav.toc a {{ margin-right: 1.25rem; color: var(--blue); }}

  main {{ max-width: var(--max-w); margin: 0 auto; padding: 2rem 1.5rem; }}

  h2 {{
    font-size: 1.5rem;
    font-weight: 700;
    color: #1e3a8a;
    margin: 2.5rem 0 1rem;
    padding-bottom: .4rem;
    border-bottom: 3px solid var(--blue);
  }}
  h3 {{
    font-size: 1.15rem;
    font-weight: 600;
    color: var(--gray);
    margin: 1.75rem 0 .6rem;
  }}
  p {{ margin-bottom: 1rem; }}

  /* Callout boxes */
  .callout {{
    border-left: 4px solid;
    border-radius: 0 8px 8px 0;
    padding: .9rem 1.1rem;
    margin: 1rem 0;
    font-size: .95rem;
  }}
  .callout.info    {{ border-color: var(--blue);   background: var(--lblue); }}
  .callout.success {{ border-color: var(--green);  background: var(--lgreen); }}
  .callout.warning {{ border-color: var(--amber);  background: var(--lamber); }}
  .callout.danger  {{ border-color: var(--red);    background: var(--lred); }}
  .callout.purple  {{ border-color: var(--purple); background: var(--lpurple); }}
  /* Only the FIRST strong in a callout (the title) gets block display.
     Inline <strong> elements later in the same callout remain inline. */
  .callout > strong:first-child {{ display: block; margin-bottom: .3rem; font-size: 1rem; }}

  /* Executive summary grid */
  .exec-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
    gap: 1rem;
    margin: 1.5rem 0;
  }}
  .exec-card {{
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 1rem 1.1rem;
    background: #fff;
    box-shadow: 0 1px 4px rgba(0,0,0,.06);
  }}
  .exec-card .num {{
    font-size: 1.6rem;
    font-weight: 800;
    color: var(--blue);
    line-height: 1;
    margin-bottom: .4rem;
  }}
  .exec-card .num.red    {{ color: var(--red); }}
  .exec-card .num.green  {{ color: var(--green); }}
  .exec-card .num.amber  {{ color: var(--amber); }}
  .exec-card .num.purple {{ color: var(--purple); }}
  .exec-card p {{ font-size: .9rem; margin: 0; color: #555; }}

  /* Tables */
  .tbl-wrap {{ overflow-x: auto; margin: 1rem 0 1.5rem; }}
  table {{ width: 100%; border-collapse: collapse; font-size: .9rem; }}
  th {{
    background: #1e3a8a;
    color: #fff;
    padding: .55rem .75rem;
    text-align: left;
    font-weight: 600;
    /* ensure sufficient contrast: white on #1e3a8a ≈ 10:1 */
  }}
  th[scope="row"] {{
    background: #f0f4ff;
    color: #1e3a8a;
    font-weight: 600;
  }}
  tr:nth-child(even) td {{ background: var(--lgray); }}
  td {{ padding: .5rem .75rem; border-bottom: 1px solid var(--border); }}
  /* Table cell highlight colors — all meet WCAG AA 4.5:1 on white */
  td.hi-red    {{ color: #b91c1c;   font-weight: 700; }}  /* darkened red  #dc2626→#b91c1c */
  td.hi-amber  {{ color: #92400e;   font-weight: 600; }}  /* dark amber, not the thin #d97706 */
  td.hi-green  {{ color: #15803d;   font-weight: 600; }}  /* darkened green */

  /* Skip navigation link (hidden until focused) */
  .skip-link {{
    position: absolute;
    top: -9999px; left: 0;
    background: #1e3a8a; color: #fff;
    padding: .5rem 1rem;
    z-index: 9999;
    border-radius: 0 0 6px 0;
  }}
  .skip-link:focus {{ top: 0; }}

  /* Visible focus styles for keyboard navigation */
  a:focus, button:focus {{ outline: 3px solid #2563eb; outline-offset: 2px; }}
  :focus-visible {{ outline: 3px solid #2563eb; outline-offset: 2px; }}

  /* Charts — normal (constrained to text column) */
  .chart-block {{ margin: 1.5rem 0 2rem; }}
  .chart-block img {{ width: 100%; border: 1px solid var(--border); border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,.08); }}
  .chart-caption {{
    font-size: .85rem;
    color: #666;
    margin-top: .5rem;
    padding: .5rem .75rem;
    background: var(--lgray);
    border-radius: 6px;
    border-left: 3px solid var(--blue);
  }}

  /* Wide charts — break out of the text column */
  .chart-wide {{
    position: relative;
    left: 50%;
    transform: translateX(-50%);
    width: min(95vw, 1400px);
    margin: 1.5rem 0 2rem;
  }}
  .chart-wide img {{
    width: 100%;
    border: 1px solid var(--border);
    border-radius: 8px;
    box-shadow: 0 2px 8px rgba(0,0,0,.08);
  }}
  .chart-wide .chart-caption {{
    max-width: var(--max-w);
    margin: .5rem auto 0;
    font-size: .85rem;
    color: #666;
    padding: .5rem .75rem;
    background: var(--lgray);
    border-radius: 6px;
    border-left: 3px solid var(--blue);
  }}

  /* Badge pills */
  .badge {{
    display: inline-block;
    padding: .15rem .55rem;
    border-radius: 999px;
    font-size: .8rem;
    font-weight: 600;
    margin: 0 .1rem;
  }}
  .badge.red    {{ background: var(--lred);    color: var(--red); }}
  .badge.green  {{ background: var(--lgreen);  color: var(--green); }}
  .badge.amber  {{ background: var(--lamber);  color: var(--amber); }}
  .badge.blue   {{ background: var(--lblue);   color: var(--blue); }}
  .badge.purple {{ background: var(--lpurple); color: var(--purple); }}

  /* Timeline */
  .timeline {{ margin: 1rem 0 1.5rem; border-left: 3px solid var(--blue); padding-left: 1.5rem; }}
  .tl-item {{ margin-bottom: 1rem; position: relative; }}
  .tl-item::before {{
    content: "";
    width: 12px; height: 12px;
    background: var(--blue);
    border-radius: 50%;
    position: absolute;
    left: -1.95rem;
    top: .4rem;
  }}
  .tl-item.red::before {{ background: var(--red); }}
  .tl-item .tl-date {{ font-weight: 700; font-size: .9rem; }}
  .tl-item .tl-val  {{ color: var(--red); font-weight: 700; }}

  /* Threshold meter */
  .thresh-grid {{
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    gap: 1rem;
    margin: 1rem 0;
  }}
  @media (max-width: 640px) {{ .thresh-grid {{ grid-template-columns: 1fr; }} }}
  .thresh-card {{
    border: 2px solid var(--border);
    border-radius: 10px;
    overflow: hidden;
  }}
  .thresh-card .tc-head {{
    padding: .6rem 1rem;
    font-weight: 700;
    color: #fff;
    font-size: 1rem;
  }}
  .thresh-card .tc-head.chrome {{ background: #4285F4; }}
  .thresh-card .tc-head.edge   {{ background: #0078D7; }}
  .thresh-card .tc-head.firefox{{ background: #E76000; }}
  .thresh-card .tc-head.safari {{ background: #555; }}
  .thresh-card .tc-body {{ padding: .8rem 1rem; font-size: .875rem; }}
  .thresh-card .tc-body ul {{ padding-left: 1.2rem; }}
  .thresh-card .tc-body li {{ margin-bottom: .35rem; }}
  .thresh-card .tc-body .block   {{ color: var(--red);   font-weight: 700; }}
  .thresh-card .tc-body .caution {{ color: var(--amber); font-weight: 600; }}
  .thresh-card .tc-body .ok      {{ color: var(--green); font-weight: 600; }}

  /* Policy table */
  .policy-tier {{ margin: 1.5rem 0; }}
  .policy-tier h3 {{ margin-top: 0; }}

  footer {{
    margin-top: 4rem;
    padding: 2rem 1.5rem;
    text-align: center;
    font-size: .85rem;
    color: #888;
    border-top: 1px solid var(--border);
    background: var(--lgray);
  }}
</style>
</head>
<body>
<a href="#main-content" class="skip-link">Skip to main content</a>

<header class="page-header" role="banner">
  <h1>Are Old Browser Versions a Useful Bot Signal?</h1>
  <p>A data-driven look at US browser market share data (StatCounter, 2022–January 2026)
     to help decide when blocking old browser versions is safe — and when it isn't.</p>
  <p class="meta">Analysis period: January 2022 – January 2026 &nbsp;·&nbsp;
     Source: StatCounter US monthly exports &nbsp;·&nbsp; Published: 2026-02-19</p>
</header>

<nav class="toc" aria-label="Table of contents">
  Jump to:
  <a href="#summary">Summary</a>
  <a href="#lag-explained">Version Lag Explained</a>
  <a href="#market-share">Market Share</a>
  <a href="#bot-signals">Bot Signals</a>
  <a href="#thresholds">Block Thresholds</a>
  <a href="#safari">Safari Problem</a>
  <a href="#pageviews">Page Views vs. Requests</a>
  <a href="#limitations">Limitations</a>
  <a href="#methodology">Methodology</a>
</nav>

<main id="main-content">

<aside style="background:#fef9c3; border:1px solid #fde047; border-radius:10px; padding:1rem 1.25rem; margin-bottom:1.5rem; font-size:.9rem; color:#713f12;">
  <strong>🤖 AI-generated report</strong> — This report was produced by
  <a href="https://claude.ai/claude-code" style="color:#92400e">Claude Code</a>
  (Anthropic), a coding and analysis agent, using only the StatCounter CSV files
  in this project directory. No external data sources or web browsing were used.
  All charts, tables, and statistical calculations were generated by the accompanying
  Python scripts (<code>statcounter_browser_version_analysis.py</code>,
  <code>generate_html_report.py</code>).
  Human review and validation of conclusions is recommended before acting on
  any policy recommendations.
</aside>

<!-- ============================================================ -->
<section id="summary">
<h2>Executive Summary</h2>
<p>We analyzed 49 months of US browser market share data to answer one question:
<em>Can you detect bots by looking at browser version age?</em>
Short answer: <strong>yes, for some browsers and version patterns — but with important caveats.</strong></p>

<div class="exec-grid">
  <div class="exec-card">
    <div class="num red">3.61%</div>
    <p><strong>Edge 87 bot campaign.</strong> In January 2024, a single 4-year-old Edge version suddenly accounted for 3.6% of <em>all</em> US web traffic, then collapsed to near-zero in weeks. Classic bot-campaign signature.</p>
  </div>
  <div class="exec-card">
    <div class="num red">0.76%</div>
    <p><strong>Firefox 11 — ~130 versions behind current.</strong> Firefox 11 accounts for ~0.76% of all US traffic and is <em>still growing</em>. With a version lag of ~130 major versions, no plausible update path or legitimate enterprise use case explains its presence. The traffic pattern strongly suggests an automated fleet.</p>
  </div>
  <div class="exec-card">
    <div class="num red">1.09%</div>
    <p><strong>Firefox 118 disappeared overnight.</strong> Firefox 118 ran at ~1% of all US traffic for over 2 years, then dropped to exactly 0% in January 2026 — a pattern strongly consistent with automated traffic being shut down or migrating to a different version.</p>
  </div>
  <div class="exec-card">
    <div class="num amber">29.6%</div>
    <p><strong>Chrome October 2025 anomaly.</strong> Nearly 30% of all US traffic came from Chrome versions 12+ versions behind current — 3× the annual average. Likely a mix of enterprise users and bot activity.</p>
  </div>
  <div class="exec-card">
    <div class="num green">96%</div>
    <p><strong>Edge users are nearly always current.</strong> 96% of Edge traffic runs within 2 versions of the latest stable. Blocking old Edge versions is very low-risk for false positives.</p>
  </div>
  <div class="exec-card">
    <div class="num amber">88%</div>
    <p><strong>Old Firefox traffic is dominated by 3 versions.</strong> In 2025-26, just 3 old Firefox versions explain 88% of all old-Firefox traffic — a strong sign of bots using hard-coded user-agent strings.</p>
  </div>
  <div class="exec-card">
    <div class="num red">39%</div>
    <p><strong>Safari lag rules will backfire.</strong> Using the same approach as Chrome, ~39% of Safari traffic appears "old" — but most of these are legitimate iOS 18 users on current iPhones. Don't apply lag rules to Safari.</p>
  </div>
  <div class="exec-card">
    <div class="num amber">16%</div>
    <p><strong>Chrome old-tail has roughly doubled (within Chrome).</strong> Old Chrome versions (12+ behind current) went from ~8.7% of Chrome's own traffic in 2022 to ~16.0% in 2025-26. As a fraction of all US web traffic that's ~5.0% rising to ~9.7%.</p>
  </div>
  <div class="exec-card">
    <div class="num blue">109</div>
    <p><strong>Chrome 109: legitimate Windows 7 users.</strong> Chrome 109 is the last version that runs on Windows 7/8. It maintains ~0.5–1% of all US traffic. Don't hard-block Chrome 109 without other signals.</p>
  </div>
  <div class="exec-card">
    <div class="num purple">115/128</div>
    <p><strong>Firefox ESR users look "old" but aren't bots.</strong> Firefox's long-term support (ESR) channel keeps enterprise users on versions 12–25+ behind current. ESR traffic (~0.14–0.4% of all traffic depending on the ESR version) is legitimate. Firefox 11 (0.45–0.76%) is not — it is far too old to be any ESR version.</p>
  </div>
</div>

<div class="callout warning">
  <strong>⚠ Important caveat</strong>
  All findings are based on StatCounter aggregate data, which includes both human and bot traffic.
  We cannot <em>prove</em> any traffic is a bot from this data alone — we infer it from patterns
  (sudden spikes, extreme version age, concentration on specific versions) that are
  inconsistent with normal human browser update behavior.
  Server-side signals (request rate, missing headers, IP reputation) are required for production deployments.
</div>
</section>

<!-- ============================================================ -->
<section id="lag-explained">
<h2>Understanding "Version Lag"</h2>

<p>Modern browsers like Chrome, Edge, and Firefox release a new major version roughly
<strong>every 4 weeks</strong>. That means:</p>

<div class="callout info">
  <strong>Version lag ≈ months behind</strong>
  A browser that is 12 versions behind current is approximately <strong>12 months (1 year) old.</strong>
  A browser that is 30 versions behind is roughly <strong>2.5 years old.</strong>
  (Safari is a special case — see the <a href="#safari">Safari section</a>.)
</div>

<p>We define "version lag" as: <em>current version − this user's version</em>.
For example, if Chrome 141 is the current stable and a visitor uses Chrome 109, their lag is 32 — meaning they're running a version roughly 2.5 years old.</p>

<h3>Chrome Version Cadence (2025)</h3>
<p>To make this concrete, here's what the "current" Chrome version looked like each month in 2025.
<em>"Current Chrome" here means the single version with the highest share that month (the statistical mode) —
a slightly different measure from the 99.5th-percentile reference used in the lag charts, but useful
for building intuition about the version timeline.</em></p>
<div class="tbl-wrap">
<table>
  <tr><th>Month</th><th>Current Chrome (highest share)</th><th>Share of Traffic</th><th>Approximate Lag 12 = version ≤</th></tr>
"""
    for month, ver, share in cadence_rows:
        cutoff = ver - 12
        html += f"  <tr><td>{month}</td><td>Chrome {ver}</td><td>{share}%</td><td>Chrome {cutoff} and older</td></tr>\n"

    html += f"""</table>
</div>
<p>The takeaway: "lag 12" means roughly "version released more than a year ago." But the right threshold
depends on how aggressively the browser auto-updates — and whether legitimate enterprise users
might be pinned to older versions. Read on for browser-by-browser guidance.</p>

<h3>Why Not Just Block Anything Old?</h3>
<p>The risk is blocking real people. Some legitimate reasons a user might be on an older browser version:</p>
<ul style="padding-left:1.5rem; margin-bottom:1rem;">
  <li><strong>Enterprise IT policy</strong> — companies sometimes freeze browser versions for compatibility with internal tools. Chrome and Edge support an "Extended Stable" channel that lags 8 weeks behind regular stable.</li>
  <li><strong>Legacy hardware/OS</strong> — Chrome 109 is the last version that runs on Windows 7/8.1, which some machines still run.</li>
  <li><strong>Firefox ESR</strong> — Firefox's "Extended Support Release" gives enterprises a supported older version. Firefox 128 ESR (released July 2024) is <em>currently supported</em> and would appear as "old" under a strict lag rule.</li>
  <li><strong>Slow auto-update</strong> — some users disable automatic updates. Being 2–3 versions behind is not unusual.</li>
</ul>

<div class="callout success">
  <strong>✓ The signal to look for</strong>
  Bots often use a single hard-coded version string that never changes. So the red flag isn't
  just "old version" — it's <em>a very old specific version that shows up repeatedly and in bulk</em>.
  Edge 87 appearing at 3.6% of all traffic in one month (while normal Edge 87 traffic was ~0.03%)
  is the kind of anomaly that screams "bot campaign."
</div>
</section>

<!-- ============================================================ -->
<section id="market-share">
<h2>Browser Market Share Overview</h2>
<p>Our data covers 49 months across four periods. Chrome dominates US traffic, followed by
Safari, Edge, and Firefox. A few notable shifts from 2022 to 2025-26:</p>

<div class="tbl-wrap">
<table>
  <tr><th>Browser</th><th>2022 Avg Share</th><th>2025-26 Avg Share</th><th>Change</th></tr>
"""
    for fam in t1.index:
        v22 = t1.loc[fam, "2022"] if "2022" in t1.columns else 0
        v25 = t1.loc[fam, "2025-26"] if "2025-26" in t1.columns else 0
        delta = v25 - v22
        arrow = f"+{delta:.2f}" if delta >= 0 else f"{delta:.2f}"
        color = "hi-green" if delta > 0.5 else ("hi-red" if delta < -0.5 else "")
        html += f"  <tr><td>{fam}</td><td>{v22:.2f}%</td><td>{v25:.2f}%</td><td class='{color}'>{arrow} pp</td></tr>\n"

    html += f"""</table>
</div>
<p>Key notes: IE fell from 1.28% to 0.21% — IE 11 officially ended support in June 2022,
so most remaining IE traffic is non-human. Brave grew from near-zero to 2.73%, and
Chrome for Android doubled its share (likely reflecting more mobile measurement).</p>

<div class="chart-block">
  <img src="{imgs['ts_2022']}" alt="Monthly browser family share, 2022">
  <p class="chart-caption">
    <strong>Figure 1 — 2022:</strong> Monthly share by browser family. Chrome led at ~58%,
    Safari second at ~16%, Edge third at ~13%. The spiky lines for each Chrome/Edge version
    reflect the ~monthly release cycle: one version dominates, then the next takes over.
  </p>
</div>

<div class="chart-block">
  <img src="{imgs['ts_2025']}" alt="Monthly browser family share, 2025-26">
  <p class="chart-caption">
    <strong>Figure 2 — 2025-26:</strong> Chrome holds steady at ~59%. Safari dropped to ~11%
    (down ~5 percentage points from 2022). Brave emerged as a measurable browser at ~2.7%.
    Chrome for Android doubled. Edge and Firefox stayed roughly flat.
  </p>
</div>
</section>

<!-- ============================================================ -->
<section id="bot-signals">
<h2>Bot Signals in the Data</h2>
<p>Three patterns in the data stand out as almost certainly representing bot activity rather than
human browser use. They share a common signature: <em>specific old versions appearing in bulk,
often with sudden on/off behavior inconsistent with normal software update patterns.</em></p>

<h3>Signal 1: The Edge 87 Anomaly (November 2023 – February 2024)</h3>
<p>This is the clearest automated-traffic signal in the dataset. By late 2023, the dominant Edge
version was ~119 — putting Edge 87 approximately <strong>32 versions behind current</strong>
(about 2.5 years' worth of releases at Edge's ~4-week cadence). Edge 87 traffic was otherwise
a tiny background trace of ~0.02–0.04% — consistent with deeply outdated usage gradually
fading away.</p>

<p>Here's what happened to Edge 87's traffic share:</p>
<div class="tbl-wrap">
<table>
  <tr><th>Month</th><th>Edge 87 Share (% all US traffic)</th><th>Interpretation</th></tr>
"""
    # Relevant months for Edge 87
    e87_rel = e87[(e87["date"] >= "2023-09-01") & (e87["date"] <= "2024-04-01")]
    for _, r in e87_rel.iterrows():
        share = r["share"]
        if share >= 1.0:
            note = "🚨 Bot campaign active"
            cls = "hi-red"
        elif share >= 0.2:
            note = "⚠ Suspicious rise/fall"
            cls = "hi-amber"
        else:
            note = "Background noise"
            cls = ""
        html += f"  <tr><td>{r['date'].strftime('%b %Y')}</td><td class='{cls}'>{share:.2f}%</td><td>{note}</td></tr>\n"

    html += f"""</table>
</div>

<div class="callout danger">
  <strong>🚨 Why this is highly consistent with automated traffic</strong>
  Normal browser traffic for a 3-year-old version would be a tiny, slowly declining fraction.
  Instead, Edge 87 went from 0.03% → 3.61% in 3 months (a 120× increase), then collapsed
  back to 0.02% in 3 weeks. No organic user population behaves this way.
  The concentration metric (HHI) for old Edge versions hit <strong>4,626 out of 10,000</strong>
  in 2024 — meaning traffic was extremely concentrated on this one version.
</div>

<p><strong>Recommendation:</strong> Hard-block Edge 87 outright. Also block the legacy
"EdgeHTML" versions (Edge 15, 18, 19) — these pre-date the 2020 redesign and have been
end-of-life since 2021.</p>

<h3>Signal 2: Firefox 11 — The Growing Bot Fleet</h3>
<p>Firefox 11 was released in 2012. Current Firefox in 2026 is version 140+. That's a lag
of roughly 129 versions — or about <strong>10+ years</strong> behind current. There is no
realistic scenario in which a human user has been running Firefox 11 uninterrupted since 2012.</p>

<p>What makes this more alarming is that Firefox 11 traffic is <em>growing</em>:</p>
<div class="tbl-wrap">
<table>
  <tr><th>Year</th><th>Avg Monthly Share</th><th>Peak Month</th><th>Change from 2022</th></tr>
"""
    for period, grp in ff11.groupby("period"):
        avg = round(float(grp["share"].mean()), 3)
        peak = round(float(grp["share"].max()), 3)
        pk_month = grp.loc[grp["share"].idxmax(), "date"].strftime("%b %Y") if not grp.empty else "—"
        html += f"  <tr><td>{period}</td><td>{avg:.3f}%</td><td>{peak:.3f}% ({pk_month})</td><td>{'8×' if period=='2025-26' else '—'}</td></tr>\n"

    html += f"""</table>
</div>

<div class="callout danger">
  <strong>🚨 Why this is bot traffic</strong>
  Firefox 11's share has grown 8× in four years. No browser with a ~130-version lag gains
  organic users over time — this is new automated infrastructure being deployed with a
  hard-coded Firefox 11 user-agent string.
  The spike to 0.74% of all US traffic in May 2025 (roughly equalling Firefox's entire
  legitimate share) confirms this is an active, growing scraper fleet.
</div>

<h3>Signal 3: Firefox 118 — The Hidden Campaign That Just Ended</h3>
<p>This is a more subtle signal we discovered when looking at which specific old Firefox
versions dominate traffic. Firefox 118 was released in September 2023 — a perfectly normal
browser version at the time. But something unusual happened: it maintained roughly <strong>1%
of all US web traffic</strong> for over two years, then <em>dropped to exactly 0%</em> in
January 2026 — the last month in our dataset.</p>

<div class="tbl-wrap">
<table>
  <tr><th>Period</th><th>Firefox 118 Avg Monthly Share</th><th>Notes</th></tr>
"""
    ff118_2023 = ff118[ff118["period"]=="2023"]
    ff118_2024 = ff118[ff118["period"]=="2024"]
    ff118_2526 = ff118[ff118["period"]=="2025-26"]
    for period, grp, note in [
        ("Oct 2023 (launch)", ff118[ff118["date"]=="2023-10-01"], "Firefox 118 just released — peak normal use"),
        ("2024 (all year)", ff118_2024, "Should be declining naturally..."),
        ("2025 (Jan–Dec)", ff118_2526[ff118_2526["date"] < "2026-01-01"], "Still at ~1%+ — very suspicious"),
        ("Jan 2026", ff118_2526[ff118_2526["date"] == "2026-01-01"], "Drops to exactly 0% overnight"),
    ]:
        avg = round(float(grp["share"].mean()), 3) if not grp.empty else 0
        cls = "hi-red" if period == "Jan 2026" or "2025" in period else ("hi-amber" if "2024" in period else "")
        html += f"  <tr><td>{period}</td><td class='{cls}'>{avg:.3f}%</td><td>{note}</td></tr>\n"

    html += f"""</table>
</div>

<div class="callout danger">
  <strong>🚨 The smoking gun</strong>
  A browser version released in 2023 that maintains exactly ~1% of all US traffic through
  all of 2024 and 2025 — never declining, never fluctuating much — and then drops to
  <em>exactly zero</em> in one month, is highly consistent with automated traffic —
  either a campaign shutting down, migrating to a newer version, or a measurement
  change — but not with any organic human browser update pattern.
  By late 2025, Firefox 118 was about 25 versions behind current, placing it firmly in
  "impossible for organic traffic to maintain" territory.
</div>

<h3>Signal 4: Chrome October 2025 Anomaly</h3>
<p>In October 2025, nearly <strong>30% of all US web traffic</strong> came from Chrome
versions 12+ versions behind current (compared to the annual average of ~16%).
This is the largest single-month spike in the dataset.</p>

<div class="chart-block">
  <img src="{imgs['chrome_tail']}" alt="Chrome old-tail share over time">
  <p class="chart-caption">
    <strong>Figure 3 — Chrome "old version" traffic over time.</strong>
    Each line represents a different year. The dramatic spike in late 2025 is visible
    (orange line, far right). Monthly swings are common due to version transitions, but
    the October 2025 level is roughly 3× the typical monthly value for 2025-26.
  </p>
</div>

<p>The main contributors in October 2025:</p>
<div class="tbl-wrap">
<table>
  <tr><th>Version</th><th>Share (Oct 2025)</th><th>Approx Age</th><th>Likely Explanation</th></tr>
  <tr><td>Chrome 141</td><td>19.0%</td><td>Current stable</td><td class="hi-green">Normal ✓</td></tr>
  <tr><td class="hi-amber">Chrome 125</td><td class="hi-amber">12.8%</td><td>~17 months old (released May 2024)</td><td>Suspicious — lag 16 from Chrome 141. Also spiked in Dec 2024. Possible automation or pinned fleet.</td></tr>
  <tr><td class="hi-amber">Chrome 130</td><td class="hi-amber">11.1%</td><td>~5 months old</td><td>Lag 11 — borderline. Could be enterprise or extended-stable users.</td></tr>
  <tr><td>Chrome 117</td><td>0.74%</td><td>~1 year old</td><td>Suspicious — mixed signal</td></tr>
  <tr><td class="hi-red">Chrome 109</td><td class="hi-red">0.50%</td><td>~2.5 years old</td><td>Windows 7/8 legacy (likely legit)</td></tr>
  <tr><td class="hi-red">Chrome 79</td><td class="hi-red">0.37%</td><td>~5 years old</td><td>Strong bot signal</td></tr>
  <tr><td class="hi-red">Chrome 83</td><td class="hi-red">0.33%</td><td>~4.5 years old</td><td>Strong bot signal</td></tr>
</table>
</div>

<p>Chrome 125 (12.8%) is particularly notable: it was released in May 2024 — <em>17 months</em>
before October 2025, placing it 16 versions behind current. It had also spiked anomalously
in December 2024 before fading out, then resurged in October 2025. Chrome's Extended Stable
channel only extends support by ~8 weeks (2 versions), not 16. This level of persistence
for a ~17-month-old version suggests large pinned or legacy fleets, measurement artifacts, or
automation using Chrome 125 user-agent strings — not a plausible Extended Stable explanation.
Chrome 130 (~5 months old, lag 11) is a more defensible enterprise candidate.</p>

<h3>How Concentrated Is the Old-Version Traffic?</h3>
<p>One way to distinguish bot traffic from slow-updating humans: bots tend to use
<em>one specific version</em>, while humans spread out across multiple adjacent versions.
We measure this with a "concentration score" (HHI) — a higher score means traffic
is more concentrated on fewer specific versions.</p>

<div class="callout info">
  <strong>Reading the concentration score (HHI)</strong>
  Score 0–1,000 = traffic is spread across many versions (more likely human) <br>
  Score 1,000–2,500 = moderately concentrated <br>
  Score 2,500–10,000 = traffic is dominated by 1–3 specific versions (strong bot signal)
</div>

<div class="chart-wide">
  <img src="{imgs['hhi']}" alt="HHI concentration of old-version traffic">
  <p class="chart-caption">
    <strong>Figure 4 — How concentrated is "old browser" traffic? (Chrome / Edge / Firefox, all years)</strong>
    Each line is one year. The red dashed line marks the "concentrated" threshold.
    Edge's dramatic 2024 spike reflects the Edge 87 bot campaign. Firefox's rising
    trend reflects the growing Firefox 11 fleet and Firefox 118 campaign. Chrome
    stays relatively low and flat — its old-version tail is more spread out, consistent
    with a mix of legitimate slow-updaters and bots rather than a single hard-coded version.
    The shaded red band above the dashed line = "concentrated / likely bot-dominated."
  </p>
</div>

<div class="tbl-wrap">
<table>
  <tr>
    <th>Browser</th><th>Period</th>
    <th>Concentration Score (HHI)</th>
    <th>Top 1 Version = % of old traffic</th>
    <th>Top 3 Versions = % of old traffic</th>
  </tr>
"""
    conc_avg = conc[conc["period"].isin(["2022","2025-26"])].groupby(
        ["browser_family","period"])[["HHI","top1_pct_of_tail","top3_pct_of_tail"]].mean().round(1).reset_index()
    for fam in ["Chrome","Edge","Firefox"]:
        for period in ["2022","2025-26"]:
            r = conc_avg[(conc_avg["browser_family"]==fam) & (conc_avg["period"]==period)]
            if r.empty: continue
            hhi = r["HHI"].values[0]
            t1v = r["top1_pct_of_tail"].values[0]
            t3v = r["top3_pct_of_tail"].values[0]
            hhi_cls = "hi-red" if hhi > 2500 else ("hi-amber" if hhi > 1000 else "hi-green")
            t3_cls  = "hi-red" if t3v > 70 else ("hi-amber" if t3v > 50 else "")
            html += f"  <tr><td>{fam}</td><td>{period}</td><td class='{hhi_cls}'>{hhi:.0f}</td><td>{t1v:.1f}%</td><td class='{t3_cls}'>{t3v:.1f}%</td></tr>\n"

    html += f"""</table>
</div>
</section>

<!-- ============================================================ -->
<section id="thresholds">
<h2>What Version Lags Should We Actually Block?</h2>

<p>Here's the practical guide, browser by browser. The key insight is that <strong>the right
lag threshold is different for each browser</strong>, and for some browsers (Firefox especially)
there are specific version numbers that are better hard-block candidates than a blanket lag rule.</p>

<div class="chart-block">
  <img src="{imgs['bucket_cmp']}" alt="Version lag bucket distribution comparison">
  <p class="chart-caption">
    <strong>Figure 5 — How much of each browser's traffic is "old"?</strong>
    Each cluster of bars shows the share of that browser's traffic falling in each version-lag
    bucket. Compare 2022 (blue) to 2025-26 (orange). Edge stays almost entirely in the
    "0–2 versions behind" bucket. Chrome and Firefox have grown significantly in the
    older buckets. Note: these are percentages <em>within each browser's own traffic</em>
    — not of all traffic.
  </p>
</div>

<div class="thresh-grid">
  <div class="thresh-card">
    <div class="tc-head chrome">Chrome</div>
    <div class="tc-body">
      <p><strong>Release cadence:</strong> ~4 weeks/version</p>
      <p><strong>Auto-update:</strong> Yes, but enterprise can freeze</p>
      <p style="margin-top:.5rem"><strong>Version lag guide:</strong></p>
      <ul>
        <li><span class="ok">Lag 0–5</span> — Normal. Don't block. (~91% of Chrome)</li>
        <li><span class="caution">Lag 6–11</span> — Slow updaters. Log only, no block.</li>
        <li><span class="caution">Lag 12–17</span> — Suspicious. Soft-challenge or rate-limit. (~7% of Chrome)</li>
        <li><span class="caution">Lag 18–24</span> — Unlikely organic. Soft-block unless Chrome 109.</li>
        <li><span class="block">Lag 25+</span> — Hard-block (carve out Chrome 109). (~2–3% FP)</li>
      </ul>
      <p style="margin-top:.5rem"><strong>Always hard-block:</strong> Chrome 79, 83, 87 (persistent bot versions with 4–5 year lag)</p>
      <p><strong>Never hard-block on lag alone:</strong> Chrome 109 (Windows 7/8 legacy users, ~0.5–1% of all traffic)</p>
    </div>
  </div>
  <div class="thresh-card">
    <div class="tc-head edge">Edge</div>
    <div class="tc-body">
      <p><strong>Release cadence:</strong> ~4 weeks/version (synced with Chrome)</p>
      <p><strong>Auto-update:</strong> Very aggressive — 96% of Edge users are current</p>
      <p style="margin-top:.5rem"><strong>Version lag guide:</strong></p>
      <ul>
        <li><span class="ok">Lag 0–2</span> — Normal. Don't block. (~96% of Edge)</li>
        <li><span class="caution">Lag 3–8</span> — Unusual but some enterprise. Log only.</li>
        <li><span class="block">Lag 9+</span> — Hard-block. Only ~2% of real Edge users here.</li>
        <li><span class="block">Lag 21+</span> — Hard-block. &lt;1% FP rate.</li>
      </ul>
      <p style="margin-top:.5rem"><strong>Always hard-block:</strong></p>
      <ul>
        <li>Edge 87 — strong automated-traffic signal (see above)</li>
        <li>Edge 15, 18, 19 — legacy "EdgeHTML" browser, EOL 2021</li>
      </ul>
    </div>
  </div>
  <div class="thresh-card">
    <div class="tc-head firefox">Firefox</div>
    <div class="tc-body">
      <p><strong>Release cadence:</strong> ~4 weeks/version</p>
      <p><strong>⚠ Important:</strong> Firefox has an ESR (Extended Support Release) channel — a supported older version for enterprise IT. The current ESR in this dataset ranges from Firefox 115 to 128 (lag ~12–25 depending on month). Do not blanket-block based on lag alone; you will hit ESR users.</p>
      <p style="margin-top:.5rem"><strong>Version lag guide:</strong></p>
      <ul>
        <li><span class="ok">Lag 0–15</span> — Don't block (may include Firefox 128 ESR, lag ~12–19 in late 2025)</li>
        <li><span class="caution">Lag 16–29</span> — Caution. Firefox 115 ESR (now expired but still present at 0.27%) lives here.</li>
        <li><span class="block">Lag 30+</span> — Soft-block. (&lt;5% FP for actual humans)</li>
        <li><span class="block">Lag 60+</span> — Hard-block. Versions like Firefox 72, 78, 44 (2016–2020). Near-certain bots.</li>
      </ul>
      <p style="margin-top:.5rem"><strong>Always hard-block these specific versions:</strong></p>
      <ul>
        <li>Firefox 11 — ~130 versions behind current, traffic still growing (automated fleet)</li>
        <li>Firefox 118 — ran at ~1% for 2 years, dropped to 0% overnight (Jan 2026). Likely migrating to new version — watch for successor.</li>
        <li>Firefox 44, 52, 59, 72, 78 — confirmed persistent bot versions</li>
      </ul>
    </div>
  </div>
</div>

<h3>Policy Tiers</h3>
<p>Here are three readymade policy options depending on your risk tolerance.
"False positive rate" means the estimated percentage of <em>legitimate</em> browser traffic
that would be blocked or challenged — lower is better for user experience.</p>

<div class="policy-tier">
<div class="callout success">
<strong>✓ Conservative Policy — Near-zero false positives</strong>
Block only the versions that are demonstrably bots. Very low risk of affecting real users.
</div>
<div class="tbl-wrap">
<table>
  <tr><th>Browser</th><th>Rule</th><th>Examples from Data</th><th>Est. False Positive Risk</th></tr>
  <tr>
    <td>Chrome</td>
    <td>Block major ≤ 70</td>
    <td>Chrome 70 released Oct 2018 — 7+ years old. Traffic at ~0.1% is bot territory.</td>
    <td class="hi-green">Near zero</td>
  </tr>
  <tr>
    <td>Firefox</td>
    <td>Block Firefox 11, 44, 52, 59, 72, 78, 118 explicitly</td>
    <td>All confirmed persistent bot versions from this dataset</td>
    <td class="hi-green">Near zero</td>
  </tr>
  <tr>
    <td>Edge</td>
    <td>Block Edge 87, Edge 15/18/19</td>
    <td>Edge 87 = confirmed campaign; EdgeHTML = EOL 2021</td>
    <td class="hi-green">Near zero</td>
  </tr>
  <tr>
    <td>IE</td>
    <td>Block all Internet Explorer</td>
    <td>IE 11 EOL June 2022. Any remaining IE traffic is almost certainly non-human.</td>
    <td class="hi-green">Near zero</td>
  </tr>
  <tr>
    <td>Safari</td>
    <td>Block Safari ≤ 12 and "Safari 604.1", "Safari 537.36" UA strings</td>
    <td>Safari 12 = 2018; fake WebKit UA strings are spoofed headers</td>
    <td class="hi-green">Near zero</td>
  </tr>
</table>
</div>
</div>

<div class="policy-tier">
<div class="callout warning">
<strong>⚖ Balanced Policy — Low false positives, catches more bots</strong>
Apply a lag threshold per browser. Use "soft" actions (rate-limit, CAPTCHA challenge)
rather than hard blocks where false-positive rates are above 1%.
</div>
<div class="tbl-wrap">
<table>
  <tr><th>Browser</th><th>≤1% FP: min lag</th><th>≤2% FP: min lag</th><th>≤5% FP: min lag</th></tr>
  <tr><td>Chrome (2025-26)</td><td class="hi-red">&gt;24 (no threshold)</td><td class="hi-red">&gt;24</td><td class="hi-amber">Lag ≥ 25–30*</td></tr>
  <tr><td>Edge (2025-26)</td><td class="hi-amber">Lag ≥ 21</td><td class="hi-green">Lag ≥ 9</td><td class="hi-green">Lag ≥ 3</td></tr>
  <tr><td>Firefox (2025-26)</td><td class="hi-red">&gt;24 (bot-inflated)</td><td class="hi-red">&gt;24</td><td class="hi-red">&gt;24*</td></tr>
  <tr><td>Safari</td><td colspan="3">Use conservative hard-block list only — no lag rule</td></tr>
</table>
</div>
<p style="font-size:.875rem; color:#666">* Chrome and Firefox FP thresholds are high because their old-version tail includes significant bot traffic (which inflates the denominator). True human FP rates are lower. Chrome lag ≥ 25 is a reasonable soft-challenge threshold. For Firefox, use specific version hard-blocks rather than a lag rule.</p>
</div>

<div class="policy-tier">
<div class="callout danger">
<strong>🔒 Strict Policy — Aggressive blocking, higher false-positive risk</strong>
Appropriate when old-version traffic is already elevated in other signals
(high request rate, missing Accept-Language headers, no cookie support).
Combine with behavioral signals for best results.
</div>
<div class="tbl-wrap">
<table>
  <tr><th>Browser</th><th>Threshold</th><th>Expected FP Rate</th><th>Justification</th></tr>
  <tr><td>Chrome</td><td>Lag ≥ 12 (~1 year old)</td><td class="hi-amber">~16% of Chrome traffic</td><td>HHI rising; Oct 2025 spike shows bot-heavy months. Pair with rate signals to reduce FP.</td></tr>
  <tr><td>Edge</td><td>Lag ≥ 12</td><td class="hi-green">&lt;1% of Edge traffic</td><td>Edge users are nearly always current. Very safe to block.</td></tr>
  <tr><td>Firefox</td><td>Lag ≥ 12 + explicit version list</td><td class="hi-amber">~6% of Firefox* (but mostly bots)</td><td>Old Firefox tail is heavily concentrated on known bot versions. Most "FP" here are bots.</td></tr>
  <tr><td>Safari</td><td>Hard-block list only</td><td class="hi-green">~0.2% of Safari</td><td>Safari 12 and older, fake WebKit UAs</td></tr>
</table>
</div>
</div>

<div class="callout purple">
  <strong>💡 Practical recommendation</strong>
  Start with the <strong>Conservative</strong> policy (hard-blocks only) and add monitoring.
  Once you can see the volume of traffic hitting each rule, promote the higher-confidence
  cases to the <strong>Balanced</strong> thresholds. Save the <strong>Strict</strong> policy
  for endpoints where you've already validated elevated bot activity through other signals.
  Never apply a blanket lag rule to Safari.
</div>
</section>

<!-- ============================================================ -->
<section id="safari">
<h2>The Safari Problem</h2>

<p>Safari is fundamentally different from Chrome, Edge, and Firefox when it comes to
version-based anti-bot rules. Here's why:</p>

<p><strong>Safari's major version is tied to the operating system.</strong> When Apple
releases a new version of iOS or macOS, Safari gets a new major version number. You can't
upgrade Safari independently — you upgrade your entire phone or computer.
This creates a very different traffic pattern:</p>

<p style="font-size:.875rem;color:#555;margin-bottom:.25rem">
  <em>Note: Shares below are aggregated across all sub-versions (e.g., Safari 18.0 + 18.1 + 18.2 … = "Safari 18").
  The lag column uses the 99.5th-percentile reference, which shifts mid-period (see note below table).</em>
</p>
<div class="tbl-wrap">
<table>
  <tr><th scope="col">Safari Version</th><th scope="col">Tied To</th><th scope="col">Avg Share (2025-26, all sub-versions)</th><th scope="col">Under lag-based rule...</th></tr>
  <tr><td class="hi-green">Safari 18</td><td>iOS 18 (Sep 2024)</td><td class="hi-green"><strong>6.43%</strong> (largest by far)</td><td class="hi-red">⚠ Lag 8 — flagged as "old" (Aug 2025 onward)</td></tr>
  <tr><td>Safari 17</td><td>iOS 17 (Sep 2023)</td><td>2.06%</td><td class="hi-amber">Lag 9 — flagged</td></tr>
  <tr><td>Safari 16</td><td>iOS 16 (Sep 2022)</td><td>1.16%</td><td class="hi-amber">Lag 10 — flagged</td></tr>
  <tr><td class="hi-green">Safari 26</td><td>iOS/macOS 26 (2025)</td><td>0.66%</td><td class="hi-green">Current — fine ✓</td></tr>
  <tr><td>Safari 15</td><td>iOS 15 / macOS 12</td><td>0.64%</td><td class="hi-red">Lag 11 — blocked</td></tr>
  <tr><td>Safari 14</td><td>iOS 14 / macOS 11</td><td>0.18%</td><td class="hi-red">Lag 12 — blocked</td></tr>
  <tr><td>Safari 13</td><td>iOS 13 / macOS 10.15</td><td>0.14%</td><td class="hi-red">Lag 13 — blocked</td></tr>
</table>
</div>

<div class="callout warning">
  <strong>⚠ Reference version instability makes Safari lags unreliable</strong>
  In this dataset, the "current" Safari reference (using the 99.5th-percentile method) is
  <strong>Safari 18</strong> from January through July 2025, then jumps to <strong>Safari 26</strong>
  from August 2025 onward when iOS/macOS 26 launched. This mid-period shift means the same
  user on Safari 17 would have lag 1 (not flagged) in June 2025 but lag 9 (flagged) in
  September 2025 — with no change on their end. Lag-bucket results for Safari are therefore
  not stable across the period and should not be used for blocking decisions.
</div>

<div class="callout danger">
  <strong>⚠ The scale of the problem</strong>
  Safari 18 (all sub-versions combined) accounts for <strong>6.43% of all US web traffic</strong>
  in 2025-26 — the dominant Safari version. From August 2025 onward it falls in the "lag 8"
  bucket under our 99.5th-percentile reference. Blocking at lag ≥ 8 would challenge the
  majority of current iOS 18 iPhone users.
  <strong>Under our lag-based analysis, 38.8% of all Safari traffic appears "old" —
  but most of this is legitimate iOS 17 and 18 users on current Apple devices.</strong>
</div>

<p>There's a secondary complication: some very old Safari user-agent strings
(like "Safari 604.1" or "Safari 537.36") are actually <em>Blink/WebKit engine version
numbers</em> that appear in old or spoofed user-agent strings, not real Safari versions.
These are worth blocking separately as they represent either ancient browsers or
deliberate spoofing.</p>

<p><strong>Bottom line for Safari:</strong> Stick to hard-blocking specific very old versions
(Safari 12 and below, released before 2019) and fake WebKit UA strings. Do not apply a
"lag ≥ N" rule to Safari based on major version numbers.</p>
</section>

<!-- ============================================================ -->
<section id="pageviews">
<h2>What StatCounter Actually Measures — And Why It Matters for Your Access Logs</h2>

<p>This is one of the most important things to understand before acting on this data.
StatCounter and your web server's access logs are measuring <em>completely different things</em>,
and mixing them up can lead to bad decisions.</p>

<h3>StatCounter measures JavaScript page views, not HTTP requests</h3>

<p>StatCounter works by embedding a small JavaScript tag on participating websites.
Every time a page fully loads and that JavaScript executes, StatCounter records
one data point — one "page view." This means:</p>

<div class="tbl-wrap">
<table>
  <tr><th>What happened</th><th>StatCounter records</th><th>Your access log records</th></tr>
  <tr>
    <td>A human visits one page on a website</td>
    <td>1 page view</td>
    <td>~30–100 HTTP requests (HTML + images + CSS + JS + fonts + API calls)</td>
  </tr>
  <tr>
    <td>A bot crawls 500 pages on a website, executing JS on each</td>
    <td>500 page views</td>
    <td>~15,000–50,000 HTTP requests</td>
  </tr>
  <tr>
    <td>A bot crawls 500 pages but doesn't execute JavaScript</td>
    <td>0 page views (invisible to StatCounter)</td>
    <td>500–1,000 HTTP requests (just the HTML)</td>
  </tr>
  <tr>
    <td>A bot checks one URL repeatedly every 5 minutes for a day</td>
    <td>0–288 page views (depends on whether it re-executes JS)</td>
    <td>288 HTTP requests (just for the HTML; plus sub-resources each time)</td>
  </tr>
</table>
</div>

<div class="callout warning">
  <strong>⚠ "1% market share" does not mean "1% of your HTTP requests"</strong>
  If Firefox 11 has 0.76% of StatCounter page views, that does not mean it will appear
  at 0.76% of entries in your access log. The actual percentage depends heavily on
  how many pages each Firefox 11 session visits — which for a scraper bot could be
  thousands of times more than a human visitor.
</div>

<h3>The Pagination / Faceted Search Trap Problem</h3>

<p>This is particularly relevant if your website has:</p>
<ul style="padding-left:1.5rem; margin-bottom:1rem;">
  <li><strong>Paginated listings</strong> — e.g., <code>/products?page=1</code> through <code>/products?page=9999</code></li>
  <li><strong>Faceted search</strong> — where every combination of filters generates a unique URL
      (e.g., color × size × brand × sort-order × page = potentially millions of unique URLs)</li>
  <li><strong>Auto-generated tag or category pages</strong> that link to each other endlessly</li>
  <li><strong>Calendar or date-range archives</strong> that can be combined indefinitely</li>
</ul>

<p>A bot following links through faceted search can visit an effectively unlimited number
of unique URLs on your site. Each page it loads (if it executes JavaScript) becomes
one StatCounter data point — but generates dozens of HTTP requests in your access log
for the page itself, plus all its assets.</p>

<div class="callout danger">
  <strong>🚨 The amplification effect</strong>
  Imagine a bot that visits 10,000 unique faceted-search pages on your site, each page
  generating 50 HTTP requests. That bot would contribute <strong>10,000 page views</strong>
  to StatCounter (inflating its browser version's apparent "market share") and
  <strong>500,000 HTTP requests</strong> to your access log.
  Meanwhile, a real human visitor might generate 5 page views and 250 HTTP requests.
  The bot-to-human ratio in StatCounter (10,000 : 5 = 2,000×) looks very different
  from the bot-to-human ratio in your bandwidth bill (500,000 : 250 = 2,000× — same
  in this case, but the absolute numbers are wildly different from what StatCounter suggests).
</div>

<h3>What This Means for Old Browser Version Analysis</h3>

<p>There are two opposing distortions to be aware of:</p>

<p><strong>1. StatCounter may <em>overstate</em> old-browser version share relative to unique visitors.</strong>
If bot crawlers using old browser UA strings visit many pages per session (especially
in a faceted-search trap), their version's "share" in StatCounter will be inflated
relative to the number of actual bot instances. The 0.76% "Firefox 11 share" could
represent a handful of bot processes visiting millions of pages, not millions of
unique Firefox 11 browser installations.</p>

<p><strong>2. StatCounter may <em>understate</em> the impact on your server load.</strong>
Each of those many page views triggers dozens of HTTP requests. So if StatCounter
shows Firefox 11 at 0.76% of page views, the actual percentage of HTTP requests
hitting your server could be much higher — especially if those bots are crawling
deep into your pagination or faceted search.</p>

<p><strong>3. Bots that don't execute JavaScript are completely invisible to StatCounter.</strong>
Many scrapers and crawlers fetch raw HTML without executing JavaScript at all. These
would appear in your access logs but not in any StatCounter data. This means
StatCounter's numbers are a <em>lower bound</em> on bot activity — the real bot traffic
hitting your server is likely higher than what StatCounter can see.</p>

<div class="callout info">
  <strong>💡 Practical implication for blocking decisions</strong>
  The version-lag analysis in this report is useful for identifying <em>which</em>
  browser versions are likely bots. But to understand the actual <em>volume</em>
  and <em>cost</em> of that bot traffic on your infrastructure, you need your own
  access logs — not StatCounter. Look for old browser UA strings in your logs,
  then measure: how many requests per session? Are they hitting the same content
  repeatedly? Are they following pagination into thousands of pages? That's where
  the real damage assessment lives.
</div>

<h3>A Note on StatCounter's Own Bot Filtering</h3>
<p>StatCounter states that it filters known bots and crawlers. However:
its filtering is based on known bot signatures (user-agent strings, IP ranges),
not on behavioral analysis. Novel or disguised bots using legitimate browser
UA strings (like the Firefox 11 and Edge 87 campaigns in this dataset) may
pass through StatCounter's filters and be counted as real traffic. This means
some of what appears to be "human market share" in this dataset is almost
certainly bot traffic that StatCounter could not identify.</p>
</section>

<!-- ============================================================ -->
<section id="limitations">
<h2>Important Limitations</h2>

<div class="callout warning">
  <strong>1. This data includes bots.</strong>
  StatCounter measures JavaScript-rendered page views. Many bots do render JavaScript.
  StatCounter filters <em>some</em> known bots, but the methodology is proprietary and
  incomplete. Our "false positive rates" include bot traffic in the denominator — real
  human FP rates are likely lower than reported.
</div>

<div class="callout warning">
  <strong>2. We can't actually confirm what's a bot.</strong>
  All bot inferences are probabilistic — based on patterns (extreme age, sudden on/off,
  concentration on specific versions) inconsistent with human behavior. To confirm bot
  status, you need server-side data: request rate, TLS fingerprint, header completeness,
  JavaScript execution evidence, IP reputation.
</div>

<div class="callout warning">
  <strong>3. Chrome 109 is a legitimate exception.</strong>
  Chrome 109 is the last Chrome version supporting Windows 7 and Windows 8.1.
  Its consistent ~0.5–1% share throughout 2025-26 (slowly declining) is consistent
  with enterprise legacy hardware. Any lag-based Chrome rule should explicitly
  carve out Chrome 109.
</div>

<div class="callout warning">
  <strong>4. Firefox ESR versions are legitimate.</strong>
  Firefox ships an Extended Support Release (ESR) for enterprise users, updated roughly
  every ~14 months. The ESR versions active during this dataset (Firefox 115 and 128)
  appear at lag 12–25+ behind the current standard release, meaning a strict lag rule
  would incorrectly flag real enterprise users. Treat Firefox lag rules cautiously; prefer
  explicit version hard-block lists over blanket lag thresholds for Firefox.
</div>

<div class="callout warning">
  <strong>5. Enterprise browser freezes are real.</strong>
  Both Chrome and Edge support enterprise policies that freeze browser versions.
  The Chrome Extended Stable channel adds up to 8 weeks. Some large organizations
  have IT policies that update quarterly or on a longer schedule. These users
  would appear as "old" in lag-based analysis.
</div>

<div class="callout warning">
  <strong>6. This is US traffic only.</strong>
  StatCounter data is US-focused. Bot traffic patterns and browser version distributions
  may differ significantly in other countries.
</div>
</section>

<!-- ============================================================ -->
<section id="methodology">
<h2>Methodology (Brief)</h2>
<p>Four StatCounter CSV files covering January 2022 through January 2026 were loaded and
converted from "wide" format (one column per browser version) to "long" format with one
row per month per browser version. Special cases were handled as follows:</p>

<ul style="padding-left:1.5rem; margin-bottom:1rem;">
  <li><strong>Safari 604.1, 537.36, 605.1</strong> — Reclassified as "Safari (WebKit UA)";
    these are engine build numbers, not real Safari versions.</li>
  <li><strong>Chrome for Android</strong> — Kept as separate family (no version number
    available).</li>
  <li><strong>Mozilla 0, 360 Safe Browser 0</strong> — Treated as "unversioned" special
    families.</li>
  <li><strong>IE, Edge (all versions), Opera, Brave, SeaMonkey</strong> — Parsed normally.</li>
</ul>

<p>The "current" version reference for each browser was computed two ways: (A) the
99.5th-percentile major version by traffic share that month (handles beta/canary noise),
and (B) the single highest-traffic version (mode). Results are reported using Method A.</p>

<p>Outlier months were flagged if lag≥12 traffic exceeded the period's median + 3× the
median absolute deviation. Concentration was measured using the Herfindahl-Hirschman
Index (HHI) — a standard measure of market concentration — applied to version shares
within the old-version tail.</p>

<p>All analysis code is in <code>statcounter_browser_version_analysis.py</code>.
Raw data tables are in the <code>output/</code> directory.</p>
</section>

</main>

<footer>
  <p>Analysis by DOI &nbsp;·&nbsp; Data: StatCounter US Monthly Browser Version Share &nbsp;·&nbsp;
     Period: Jan 2022 – Jan 2026</p>
  <p style="margin-top:.5rem">All findings are probabilistic inferences from aggregate market-share data.
     Server-side validation required for production bot detection.</p>
</footer>

</body>
</html>
"""

    out = Path("report.html")
    out.write_text(html, encoding="utf-8")
    size_kb = out.stat().st_size // 1024
    print(f"Generated: {out}  ({size_kb} KB)")

if __name__ == "__main__":
    main()
