# Browser Version Anti-Bot Heuristic Analysis

**Can old browser versions reliably signal bot traffic?**

This project analyzes 49 months of US browser market share data (StatCounter, January 2022 – January 2026) to assess whether version lag — how far behind the current stable release a browser is — can serve as a practical anti-bot signal.

**Directed by:** [John Brandenburg](https://github.com/johnbburg)
**Analysis generated with:** [Claude Code](https://claude.ai/claude-code) (Anthropic)

**Published report:** [`docs/report.html`](docs/report.html)

---

## Key Findings

- **Edge 87** surged from under 0.1% to 3.6% of all US web traffic in November 2023–February 2024, then collapsed — a characteristic bot-campaign signature.
- **Firefox 11** (released 2012, lag ~129 versions) accounts for ~0.8% of US traffic and is still growing. This is consistent with an automated scraper fleet.
- **Firefox 118** maintained ~1% of all US traffic for two years, then dropped to exactly 0% in January 2026 — strongly indicative of automated traffic being shut down or migrating.
- **Safari lag rules backfire:** ~39% of Safari traffic appears "old" under version-lag analysis, but most of those are legitimate iOS 18 users on current iPhones.
- **No lag threshold alone achieves a <1% false positive rate for Chrome or Firefox** within the range studied. Lag-based rules must be combined with behavioral signals.

---

## Repository Structure

```
.
├── statcounter-csv/              # Raw StatCounter US monthly browser version exports
│   ├── browser_version-US-monthly-202201-202212.csv
│   ├── browser_version-US-monthly-202301-202312.csv
│   ├── browser_version-US-monthly-202401-202412.csv
│   └── browser_version-US-monthly-202501-202601.csv
│
├── statcounter_browser_version_analysis.py   # Data pipeline and analysis
├── generate_html_report.py                   # HTML report generator
│
├── output/                       # Generated data tables and charts (git-ignored)
│   ├── cleaned_browser_data.csv
│   ├── summary_family_share.csv
│   ├── bucket_shares_refA.csv
│   ├── concentration_metrics_refA.csv
│   ├── outlier_months.csv
│   ├── policy_thresholds.csv
│   ├── threshold_pct_blocked.csv
│   └── *.png                     # Charts
│
├── docs/
│   └── report.html               # Self-contained published report (embedded charts)
│
└── report.md                     # Markdown version of the report
```

---

## Running the Analysis

### Requirements

```
pip install pandas numpy matplotlib
```

Python 3.9+ recommended.

### Step 1 — Run the data pipeline

```bash
python statcounter_browser_version_analysis.py
```

This reads the four CSV files from `statcounter-csv/`, tidies the data, computes version lags, concentration metrics, and outlier flags, and writes all outputs to `output/`.

### Step 2 — Generate the HTML report

```bash
python generate_html_report.py
```

This reads the CSVs and PNGs from `output/`, embeds all charts as base64 data URIs, and writes a self-contained HTML file to `docs/report.html`. The file can be opened directly in any browser or served as a static page.

---

## Methodology Summary

**Data:** StatCounter "US monthly browser-version" exports in wide format. Columns represent specific browser + version combinations (e.g., `Chrome 103.0`, `Edge 107`, `Firefox 96.0`); values are percentage of all measured US web traffic for that month.

**Version lag:** For each observation, `lag = reference_version − this_version`. The reference version is computed using the **99.5th-percentile method** — the major version at or below which 99.5% of that browser family's traffic falls in a given month. This is more robust than using the simple mode, as it handles small fractions of pre-release (Beta/Canary) traffic.

**Old-version tail:** Defined as `lag ≥ 12` — approximately one year or more behind current stable release.

**Concentration metric:** The [Herfindahl-Hirschman Index (HHI)](https://en.wikipedia.org/wiki/Herfindahl%E2%80%93Hirschman_index) is applied to version shares within the lag ≥ 12 tail. A higher HHI indicates traffic is concentrated on fewer specific versions — a pattern more consistent with automated fleets using hard-coded user-agent strings than with organic slow-updating users. Values above 2,500 are conventionally considered "concentrated."

**Outlier detection:** A month is flagged as an outlier if the lag ≥ 12 share exceeds the period's median + 3 × the median absolute deviation (MAD), or if it is more than 2× the previous month's value.

**Limitations:** StatCounter measures JavaScript-rendered page views, not raw HTTP requests, and includes both human and automated traffic. All conclusions are probabilistic inferences; confirmed bot detection requires server-side signals (request rate, TLS fingerprint, header completeness, IP reputation).

---

## Reference Documents

The `docs/` directory also contains reference material consulted during the research:

- *Akamai Blog: Evading Link Scanning Security Services with Passive Fingerprinting*
- *Akamai: Scrapers and Bot Series — Managing Professional Bots*

---

## Data Attribution

**Data source:** [Statcounter Global Stats](https://gs.statcounter.com/browser-version-market-share)
© Statcounter 1999–2026. Licensed under a
[Creative Commons Attribution-Share Alike 3.0 Unported License](https://creativecommons.org/licenses/by-sa/3.0/).
Use of this data is credited to Statcounter as required by their terms.

StatCounter measures JavaScript-rendered page views from a network of over 1.5 million
websites (~5 billion page views/month). Statistics are subject to quality assurance
revision for 45 days from initial publication.

## Code License

Analysis code: MIT License.
