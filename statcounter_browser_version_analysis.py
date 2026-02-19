"""
StatCounter Browser Version Analysis
=====================================
Analyzes US monthly browser-version market share data (StatCounter exports)
to evaluate whether blocking "old browser versions" is a safe anti-bot heuristic.

Usage:
    python3 statcounter_browser_version_analysis.py

Outputs (all written to ./output/):
    cleaned_browser_data.csv        - Tidy long-format data
    summary_family_share.csv        - Average family share by period
    bucket_shares_*.csv             - Lag-bucket shares per browser family
    outlier_months.csv              - Detected outlier months
    concentration_metrics.csv       - HHI/top-N concentration per month/family
    *.png                           - Charts
    report_tables.txt               - Human-readable tables for report.md
"""

import os
import re
import sys
import warnings
import textwrap
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

warnings.filterwarnings("ignore", category=FutureWarning)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DATA_DIR = Path("statcounter-csv")
OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)

CSV_FILES = {
    "2022":    DATA_DIR / "browser_version-US-monthly-202201-202212.csv",
    "2023":    DATA_DIR / "browser_version-US-monthly-202301-202312.csv",
    "2024":    DATA_DIR / "browser_version-US-monthly-202401-202412.csv",
    "2025-26": DATA_DIR / "browser_version-US-monthly-202501-202601.csv",
}

# Families to include in "major family" analyses
MAJOR_FAMILIES = ["Chrome", "Edge", "Firefox", "Safari", "Chrome for Android"]
# Families used for lag analysis (needs version numbers)
LAG_FAMILIES = ["Chrome", "Edge", "Firefox", "Safari"]
# Primary comparison periods
PERIOD_A = "2022"
PERIOD_B = "2025-26"

# Lag buckets: (label, min_lag, max_lag_inclusive)
LAG_BUCKETS = [
    ("0-2",   0,   2),
    ("3-5",   3,   5),
    ("6-11",  6,  11),
    ("12-17", 12, 17),
    ("18+",   18, 9999),
]


# ---------------------------------------------------------------------------
# 1. Column parsing
# ---------------------------------------------------------------------------

# Safari versions that are actually WebKit/Blink engine build numbers,
# not real Safari major versions.  Values >= 200 are flagged.
SAFARI_FAKE_VERSION_THRESHOLD = 200

# Regex: captures "FamilyName" and optional "version_string"
# E.g.: "Chrome 103.0", "Edge 108", "Firefox 91.0", "Safari 15.6",
#        "Chrome for Android", "Mozilla 0", "Other", "IE 11.0",
#        "Opera 89.0", "360 Safe Browser 0", "Brave 0", "SeaMonkey 2.53"
COL_RE = re.compile(
    r"^(?P<family>Chrome for Android|Samsung Internet|"
    r"360 Safe Browser|SeaMonkey|BlackBerry|Opera Mini|"
    r"UC Browser|Yandex Browser|Coc Coc|Brave|Mozilla|"
    r"Chrome|Firefox|Safari|Edge|Opera|IE|Other)"
    r"(?:\s+(?P<version>\S+))?$"
)


def parse_column(col: str):
    """
    Parse a StatCounter column header into (family, version_raw, major).

    Returns:
        family      : str  - browser family name (e.g. "Chrome")
        version_raw : str|None
        major       : int|None
        is_other    : bool - True if this should be lumped into "Other"
    """
    col = col.strip().strip('"')

    if col == "Date":
        return None, None, None, False

    if col == "Other":
        return "Other", None, None, True

    m = COL_RE.match(col)
    if not m:
        # Unknown column – treat as Other
        return "Other", None, None, True

    family = m.group("family")
    version_raw = m.group("version")

    # Normalise family names
    if family == "Mozilla":
        family = "Mozilla (generic)"
    if family == "360 Safe Browser":
        family = "360 Safe Browser"

    major = None
    is_other = False

    if version_raw is not None:
        try:
            major = int(version_raw.split(".")[0])
        except ValueError:
            major = None

    # Safari versions >= SAFARI_FAKE_VERSION_THRESHOLD are WebKit build numbers
    if family == "Safari" and major is not None and major >= SAFARI_FAKE_VERSION_THRESHOLD:
        # Relabel so they don't pollute Safari lag analysis
        family = "Safari (WebKit UA)"
        is_other = False  # keep as separate family, not "Other"

    # "version 0" is essentially unversioned / unknown
    if major == 0:
        version_raw = None
        major = None

    return family, version_raw, major, is_other


# ---------------------------------------------------------------------------
# 2. Load & normalise CSVs
# ---------------------------------------------------------------------------

def load_and_tidy(filepath: Path, period: str) -> pd.DataFrame:
    """Load one StatCounter CSV, return long/tidy DataFrame."""
    df = pd.read_csv(filepath)

    # Normalise Date column
    df.rename(columns={df.columns[0]: "Date"}, inplace=True)
    df["date"] = pd.to_datetime(df["Date"], format="%Y-%m")
    df.drop(columns=["Date"], inplace=True)

    # Melt wide → long
    value_vars = [c for c in df.columns if c != "date"]
    long = df.melt(id_vars="date", value_vars=value_vars,
                   var_name="column", value_name="share")

    # Parse each column name
    parsed = long["column"].apply(lambda c: pd.Series(parse_column(c),
                                  index=["browser_family", "version_raw",
                                         "major", "is_other"]))
    long = pd.concat([long, parsed], axis=1)
    long.drop(columns=["column"], inplace=True)

    long["period"] = period
    long["share"] = pd.to_numeric(long["share"], errors="coerce").fillna(0.0)
    long["major"] = pd.to_numeric(long["major"], errors="coerce")

    return long


def load_all() -> pd.DataFrame:
    frames = []
    for period, path in CSV_FILES.items():
        if not path.exists():
            print(f"  WARNING: {path} not found – skipping.")
            continue
        print(f"  Loading {path.name} …")
        frames.append(load_and_tidy(path, period))
    df = pd.concat(frames, ignore_index=True)
    return df


# ---------------------------------------------------------------------------
# 3. Validate monthly totals
# ---------------------------------------------------------------------------

def validate_totals(df: pd.DataFrame) -> pd.DataFrame:
    """Return per-month total and flag if outside [98, 102]."""
    totals = (df.groupby(["period", "date"])["share"]
                .sum()
                .reset_index()
                .rename(columns={"share": "total_share"}))
    totals["ok"] = totals["total_share"].between(98, 102)
    return totals


# ---------------------------------------------------------------------------
# 4. Family aggregation
# ---------------------------------------------------------------------------

def family_avg_share(df: pd.DataFrame) -> pd.DataFrame:
    """Average browser-family share across each period."""
    # For "Chrome" include Chrome for Android separately
    fam = (df.groupby(["period", "date", "browser_family"])["share"]
             .sum()
             .reset_index())
    avg = (fam.groupby(["period", "browser_family"])["share"]
              .mean()
              .reset_index()
              .rename(columns={"share": "avg_share_pct"}))
    avg = avg.sort_values(["period", "avg_share_pct"], ascending=[True, False])
    return avg


# ---------------------------------------------------------------------------
# 5. Mainstream reference version (Options A and B)
# ---------------------------------------------------------------------------

def weighted_quantile(values, weights, q):
    """Weighted quantile (ascending order)."""
    values = np.array(values, dtype=float)
    weights = np.array(weights, dtype=float)
    mask = ~np.isnan(values) & ~np.isnan(weights) & (weights > 0)
    if mask.sum() == 0:
        return np.nan
    v = values[mask]
    w = weights[mask]
    sorter = np.argsort(v)
    v = v[sorter]
    w = w[sorter]
    cumw = np.cumsum(w)
    cutoff = q * cumw[-1]
    idx = np.searchsorted(cumw, cutoff)
    return v[min(idx, len(v) - 1)]


def compute_reference_versions(df: pd.DataFrame) -> pd.DataFrame:
    """
    For each (browser_family, period, date), compute:
      ref_major_A  : 99.5th-percentile major version (weighted by share)
      ref_major_B  : mode major version (largest-share version)
    """
    records = []
    versioned = df[df["major"].notna() & ~df["browser_family"].isin(
        ["Other", "Mozilla (generic)", "Chrome for Android",
         "Safari (WebKit UA)", "360 Safe Browser"])]

    for (family, period, date), grp in versioned.groupby(
            ["browser_family", "period", "date"]):
        grp = grp[grp["share"] > 0]
        if grp.empty:
            continue
        ref_a = weighted_quantile(grp["major"].values,
                                  grp["share"].values, 0.995)
        ref_b_idx = grp["share"].idxmax()
        ref_b = grp.loc[ref_b_idx, "major"]

        records.append({
            "browser_family": family,
            "period": period,
            "date": date,
            "ref_major_A": int(np.floor(ref_a)) if not np.isnan(ref_a) else np.nan,
            "ref_major_B": int(ref_b),
        })

    return pd.DataFrame(records)


# ---------------------------------------------------------------------------
# 6. Lag and bucket computation
# ---------------------------------------------------------------------------

def compute_lag_buckets(df: pd.DataFrame,
                        refs: pd.DataFrame) -> pd.DataFrame:
    """
    Join reference versions onto versioned rows, compute lag,
    assign bucket, and aggregate bucket shares.
    """
    versioned = df[df["major"].notna() & df["browser_family"].isin(
        LAG_FAMILIES)].copy()

    merged = versioned.merge(
        refs[["browser_family", "period", "date", "ref_major_A", "ref_major_B"]],
        on=["browser_family", "period", "date"],
        how="left"
    )

    merged["lag_A"] = merged["ref_major_A"] - merged["major"]
    merged["lag_B"] = merged["ref_major_B"] - merged["major"]

    def assign_bucket(lag):
        if pd.isna(lag):
            return "unknown"
        lag = int(lag)
        if lag < 0:
            return "ahead"
        for label, lo, hi in LAG_BUCKETS:
            if lo <= lag <= hi:
                return label
        return "18+"  # fallback

    merged["bucket_A"] = merged["lag_A"].apply(assign_bucket)
    merged["bucket_B"] = merged["lag_B"].apply(assign_bucket)

    return merged


def bucket_shares_table(lag_df: pd.DataFrame,
                        ref_col: str = "A") -> pd.DataFrame:
    """
    Return a table: (browser_family, period, bucket) ->
        avg_pct_all_traffic, avg_pct_within_family
    """
    bucket_col = f"bucket_{ref_col}"
    records = []

    for (family, period, date), grp in lag_df.groupby(
            ["browser_family", "period", "date"]):
        total_all = lag_df[
            (lag_df["period"] == period) & (lag_df["date"] == date)
        ]["share"].sum()
        family_total = grp["share"].sum()
        for bucket in [b[0] for b in LAG_BUCKETS] + ["ahead"]:
            sub = grp[grp[bucket_col] == bucket]
            bucket_share = sub["share"].sum()
            records.append({
                "browser_family": family,
                "period": period,
                "date": date,
                "bucket": bucket,
                "share_all_traffic": bucket_share,
                "share_within_family": (bucket_share / family_total * 100
                                        if family_total > 0 else 0),
                "total_all_traffic": total_all,
                "family_total": family_total,
            })

    result = pd.DataFrame(records)
    # Average over months within each period
    avg = (result.groupby(["browser_family", "period", "bucket"])
                 [["share_all_traffic", "share_within_family"]]
                 .mean()
                 .reset_index())
    return avg


# ---------------------------------------------------------------------------
# 7. Outlier detection
# ---------------------------------------------------------------------------

def detect_outliers(lag_df: pd.DataFrame,
                    ref_col: str = "A") -> pd.DataFrame:
    """
    For each (browser_family, period), find months where lag>=12 share
    is > median + 3*MAD or > 2x previous month.
    """
    bucket_col = f"bucket_{ref_col}"
    old_tail = lag_df[lag_df[bucket_col].isin(["12-17", "18+"])]

    monthly = (old_tail.groupby(["browser_family", "period", "date"])["share"]
                       .sum()
                       .reset_index()
                       .rename(columns={"share": "old_tail_share"}))
    monthly = monthly.sort_values(["browser_family", "period", "date"])

    records = []
    for (family, period), grp in monthly.groupby(["browser_family", "period"]):
        grp = grp.sort_values("date").reset_index(drop=True)
        vals = grp["old_tail_share"].values
        median = np.median(vals)
        mad = np.median(np.abs(vals - median))
        threshold_mad = median + 3 * mad

        for i, row in grp.iterrows():
            v = row["old_tail_share"]
            prev = vals[i - 1] if i > 0 else np.nan
            is_outlier_mad = (v > threshold_mad) and (v > 0.05)
            is_outlier_2x = (not np.isnan(prev)) and (prev > 0.05) and (v > 2 * prev)
            if is_outlier_mad or is_outlier_2x:
                records.append({
                    "browser_family": family,
                    "period": period,
                    "date": row["date"],
                    "old_tail_share": v,
                    "median": median,
                    "mad": mad,
                    "threshold_mad": threshold_mad,
                    "prev_month": prev,
                    "flag_3mad": is_outlier_mad,
                    "flag_2x": is_outlier_2x,
                })

    return pd.DataFrame(records) if records else pd.DataFrame(
        columns=["browser_family", "period", "date",
                 "old_tail_share", "flag_3mad", "flag_2x"])


def top_contributing_versions(lag_df, family, date, ref_col="A", n=10):
    """Top-N old-tail versions for a given family/month."""
    bucket_col = f"bucket_{ref_col}"
    sub = lag_df[
        (lag_df["browser_family"] == family) &
        (lag_df["date"] == date) &
        (lag_df[bucket_col].isin(["12-17", "18+"]))
    ].copy()
    if sub.empty:
        return sub
    sub = sub.sort_values("share", ascending=False).head(n)
    total = sub["share"].sum()
    sub["pct_of_tail"] = sub["share"] / total * 100 if total > 0 else 0
    return sub[["major", "version_raw", "share", "pct_of_tail"]]


# ---------------------------------------------------------------------------
# 8. Concentration metrics (HHI, top-N)
# ---------------------------------------------------------------------------

def compute_concentration(lag_df: pd.DataFrame,
                          ref_col: str = "A") -> pd.DataFrame:
    """
    For old tail (lag>=12) in each month/family, compute:
      - HHI (normalised to 0-10000 scale, within-tail shares)
      - top1_pct, top3_pct, top5_pct of tail traffic
    """
    bucket_col = f"bucket_{ref_col}"
    old_tail = lag_df[lag_df[bucket_col].isin(["12-17", "18+"])]
    records = []

    for (family, period, date), grp in old_tail.groupby(
            ["browser_family", "period", "date"]):
        total = grp["share"].sum()
        if total < 0.01:
            continue
        major_shares = grp.groupby("major")["share"].sum().sort_values(ascending=False)
        within_pct = (major_shares / total * 100).values

        hhi = np.sum(within_pct ** 2)  # 0–10000
        top1 = within_pct[:1].sum() if len(within_pct) >= 1 else 0
        top3 = within_pct[:3].sum() if len(within_pct) >= 3 else within_pct.sum()
        top5 = within_pct[:5].sum() if len(within_pct) >= 5 else within_pct.sum()

        n_versions = len(major_shares)
        records.append({
            "browser_family": family,
            "period": period,
            "date": date,
            "old_tail_share_pct": total,
            "n_distinct_majors_in_tail": n_versions,
            "HHI": round(hhi, 1),
            "top1_pct_of_tail": round(top1, 1),
            "top3_pct_of_tail": round(top3, 1),
            "top5_pct_of_tail": round(top5, 1),
        })

    return pd.DataFrame(records)


# ---------------------------------------------------------------------------
# 9. Threshold tables for policy recommendations
# ---------------------------------------------------------------------------

def compute_thresholds(lag_df: pd.DataFrame, ref_col: str = "A") -> pd.DataFrame:
    """
    For Chrome, Edge, Firefox: cumulative share by lag threshold per period.
    Answers: "blocking lag>=N affects what % of browser family traffic?"
    """
    bucket_col = f"bucket_{ref_col}"
    records = []
    periods = [PERIOD_A, PERIOD_B]
    thresholds = list(range(3, 25))

    for family in ["Chrome", "Edge", "Firefox"]:
        for period in periods:
            sub = lag_df[
                (lag_df["browser_family"] == family) &
                (lag_df["period"] == period)
            ]
            if sub.empty:
                continue

            # Per month, family total and per-lag-value shares
            for date, grp in sub.groupby("date"):
                family_total = grp["share"].sum()
                if family_total == 0:
                    continue
                lag_col = f"lag_{ref_col}"
                for thresh in thresholds:
                    blocked = grp[grp[lag_col] >= thresh]["share"].sum()
                    records.append({
                        "browser_family": family,
                        "period": period,
                        "date": date,
                        "lag_threshold": thresh,
                        "pct_family_blocked": blocked / family_total * 100,
                    })

    df = pd.DataFrame(records)
    if df.empty:
        return df
    avg = (df.groupby(["browser_family", "period", "lag_threshold"])
             ["pct_family_blocked"]
             .mean()
             .reset_index())
    return avg


# ---------------------------------------------------------------------------
# 10. Plotting helpers
# ---------------------------------------------------------------------------

FAMILY_COLORS = {
    "Chrome":             "#4285F4",
    "Chrome for Android": "#669DF6",
    "Safari":             "#999999",
    "Firefox":            "#FF7139",
    "Edge":               "#0078D7",
    "IE":                 "#0054A6",
    "Opera":              "#CC0F16",
    "Other":              "#AAAAAA",
}

# Okabe-Ito colorblind-safe palette + distinct line styles for period lines.
# Double-encoding (color + dash) ensures distinguishability without relying on color alone.
PERIOD_STYLES = {
    "2022":    {"color": "#0072B2", "linestyle": "-",    "linewidth": 1.8, "label": "2022"},
    "2023":    {"color": "#E69F00", "linestyle": "--",   "linewidth": 1.8, "label": "2023"},
    "2024":    {"color": "#009E73", "linestyle": ":",    "linewidth": 2.0, "label": "2024"},
    "2025-26": {"color": "#D55E00", "linestyle": "-",    "linewidth": 2.5, "label": "2025-26"},
}


def get_color(family):
    return FAMILY_COLORS.get(family, "#888888")


def plot_family_time_series(df: pd.DataFrame, period: str, outpath: Path):
    """Monthly time-series of top families for one period."""
    sub = df[df["period"] == period].copy()
    family_total = (sub.groupby(["date", "browser_family"])["share"]
                       .sum()
                       .reset_index())

    # Pick top 5 by overall average + Other
    avg = family_total.groupby("browser_family")["share"].mean().sort_values(ascending=False)
    top5 = list(avg.index[:5])
    families_to_plot = top5 + (["Other"] if "Other" not in top5 else [])

    pivot = family_total[family_total["browser_family"].isin(families_to_plot)].pivot(
        index="date", columns="browser_family", values="share"
    ).fillna(0)

    fig, ax = plt.subplots(figsize=(12, 6))
    for fam in families_to_plot:
        if fam in pivot.columns:
            ax.plot(pivot.index, pivot[fam], label=fam,
                    color=get_color(fam), linewidth=2)

    ax.set_title(f"Browser Family Monthly Share – {period} (US, StatCounter)")
    ax.set_ylabel("Market Share (%)")
    ax.set_xlabel("")
    ax.legend(loc="upper right", fontsize=9)
    ax.yaxis.set_major_formatter(mticker.PercentFormatter(xmax=100))
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    fig.tight_layout()
    fig.savefig(outpath, dpi=150)
    plt.close(fig)
    print(f"  Chart saved: {outpath.name}")


def plot_bucket_comparison(bucket_avg: pd.DataFrame, ref_label: str, outpath: Path):
    """
    For Chrome, Edge, Firefox: grouped bar chart comparing bucket shares
    (% within family) between 2022 and 2025-26.
    """
    families = ["Chrome", "Edge", "Firefox"]
    bucket_order = ["0-2", "3-5", "6-11", "12-17", "18+"]
    periods = [PERIOD_A, PERIOD_B]

    fig, axes = plt.subplots(1, 3, figsize=(15, 5), sharey=False)
    bar_width = 0.35
    x = np.arange(len(bucket_order))

    for ax, family in zip(axes, families):
        for i, period in enumerate(periods):
            sub = bucket_avg[
                (bucket_avg["browser_family"] == family) &
                (bucket_avg["period"] == period) &
                (bucket_avg["bucket"].isin(bucket_order))
            ]
            shares = []
            for b in bucket_order:
                row = sub[sub["bucket"] == b]
                shares.append(row["share_within_family"].values[0] if not row.empty else 0)
            offset = (i - 0.5) * bar_width
            ax.bar(x + offset, shares, bar_width, label=period,
                   color=["#4285F4", "#FF7139"][i], alpha=0.85)

        ax.set_title(family, fontsize=13, fontweight="bold")
        ax.set_xticks(x)
        ax.set_xticklabels(bucket_order, rotation=30)
        ax.set_ylabel("% Within Family Traffic" if family == "Chrome" else "")
        ax.legend(fontsize=9)
        ax.grid(axis="y", linestyle="--", alpha=0.4)

    fig.suptitle(
        f"Version-Lag Bucket Distribution by Browser Family\n"
        f"(Ref method {ref_label}, % of family traffic)",
        fontsize=12
    )
    fig.tight_layout()
    fig.savefig(outpath, dpi=150)
    plt.close(fig)
    print(f"  Chart saved: {outpath.name}")


def plot_chrome_old_tail(lag_df: pd.DataFrame, ref_col: str, outpath: Path):
    """Monthly time-series of Chrome lag>=12 share across all periods."""
    bucket_col = f"bucket_{ref_col}"
    old_tail = lag_df[
        (lag_df["browser_family"] == "Chrome") &
        (lag_df[bucket_col].isin(["12-17", "18+"]))
    ]
    monthly = (old_tail.groupby(["period", "date"])["share"]
                       .sum()
                       .reset_index())
    monthly = monthly.sort_values("date")

    fig, ax = plt.subplots(figsize=(12, 4))
    for period, grp in monthly.groupby("period"):
        grp = grp.sort_values("date")
        s = PERIOD_STYLES.get(period, {"color": "#999", "linestyle": "-", "linewidth": 1.8, "label": period})
        ax.plot(grp["date"], grp["share"],
                label=s["label"], color=s["color"],
                linestyle=s["linestyle"], linewidth=s["linewidth"],
                marker="o", markersize=4)

    ax.set_title(f"Chrome: Share of Traffic from Versions 12+ Majors Behind\n"
                 f"(Ref method {ref_col}, % of all US traffic)")
    ax.set_ylabel("Share (%)")
    ax.legend()
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    fig.tight_layout()
    fig.savefig(outpath, dpi=150)
    plt.close(fig)
    print(f"  Chart saved: {outpath.name}")


def plot_concentration_hhi(conc: pd.DataFrame, ref_col: str, outpath: Path):
    """Monthly HHI for old tail across Chrome, Edge, Firefox."""
    families = ["Chrome", "Edge", "Firefox"]
    fig, axes = plt.subplots(1, 3, figsize=(22, 5))
    for ax, family in zip(axes, families):
        sub = conc[conc["browser_family"] == family].sort_values("date")
        for period, grp in sub.groupby("period"):
            grp = grp.sort_values("date")
            s = PERIOD_STYLES.get(period, {"color": "#999", "linestyle": "-", "linewidth": 1.8, "label": period})
            ax.plot(grp["date"], grp["HHI"],
                    label=s["label"],
                    color=s["color"],
                    linestyle=s["linestyle"],
                    linewidth=s["linewidth"],
                    marker="o", markersize=4)
        ax.axhline(2500, color="red", linestyle="--", linewidth=1.2,
                   label="2500 = concentrated")
        ax.set_title(family, fontsize=14, fontweight="bold", pad=10)
        ax.set_ylabel("Concentration Score (0–10,000)" if family == "Chrome" else "")
        ax.legend(fontsize=9, loc="upper left")
        ax.grid(axis="y", linestyle="--", alpha=0.4)
        ax.set_ylim(0, 10500)
        ax.tick_params(axis="x", labelsize=9, rotation=35)
        ax.tick_params(axis="y", labelsize=9)
        # Add readable y-axis annotations
        ax.axhspan(2500, 10500, alpha=0.04, color="red")
        ax.text(0.98, 2600/10500, "concentrated →", transform=ax.transAxes,
                ha="right", va="bottom", fontsize=8, color="red", alpha=0.7)

    fig.suptitle(
        "How Concentrated Is Old-Browser Traffic? (Higher = fewer versions dominate the old-browser tail)",
        fontsize=12, y=1.02
    )
    fig.tight_layout()
    fig.savefig(outpath, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Chart saved: {outpath.name}")


# ---------------------------------------------------------------------------
# 11. Threshold finder for policy recommendations
# ---------------------------------------------------------------------------

def find_lag_thresholds(thresh_df: pd.DataFrame,
                        targets_pct=(1.0, 2.0, 5.0)) -> pd.DataFrame:
    """
    For each browser family / period, find the minimum lag threshold
    that keeps false-positive rate <= target_pct.
    Returns a pivot-like table.
    """
    records = []
    for (family, period), grp in thresh_df.groupby(["browser_family", "period"]):
        row = {"browser_family": family, "period": period}
        for target in targets_pct:
            # Find smallest lag where avg blocked pct <= target
            matches = grp[grp["pct_family_blocked"] <= target].sort_values("lag_threshold")
            if matches.empty:
                row[f"lag_for_{target}pct"] = ">24"
            else:
                row[f"lag_for_{target}pct"] = int(matches.iloc[0]["lag_threshold"])
        records.append(row)
    return pd.DataFrame(records)


# ---------------------------------------------------------------------------
# 12. Report table builder
# ---------------------------------------------------------------------------

def fmt_table(df: pd.DataFrame, title: str, fmt: str = "%.2f") -> str:
    lines = [f"\n{'='*70}", f"  {title}", f"{'='*70}"]
    lines.append(df.to_string(index=False, float_format=fmt))
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    print("\n=== StatCounter Browser Version Analysis ===\n")

    # --- Load ---
    print("[1/8] Loading CSV files …")
    df = load_all()
    print(f"  Loaded {len(df):,} rows, {df['date'].nunique()} months, "
          f"{df['period'].nunique()} periods.")

    # --- Validate ---
    print("[2/8] Validating monthly totals …")
    totals = validate_totals(df)
    bad = totals[~totals["ok"]]
    if bad.empty:
        print("  All monthly totals within [98, 102]%  ✓")
    else:
        print(f"  WARNING: {len(bad)} months outside [98,102]%:")
        print(bad.to_string(index=False))

    # Save cleaned data
    df.to_csv(OUTPUT_DIR / "cleaned_browser_data.csv", index=False)
    print(f"  Saved: cleaned_browser_data.csv ({len(df):,} rows)")

    # --- Family averages ---
    print("[3/8] Computing family averages …")
    fam_avg = family_avg_share(df)
    fam_avg.to_csv(OUTPUT_DIR / "summary_family_share.csv", index=False)
    print("  Saved: summary_family_share.csv")

    # --- Time series plots ---
    print("[4/8] Generating time series plots …")
    for period in df["period"].unique():
        plot_family_time_series(
            df, period, OUTPUT_DIR / f"timeseries_{period}.png")

    # --- Reference versions and lag ---
    print("[5/8] Computing reference versions and lag buckets …")
    refs = compute_reference_versions(df)
    lag_df = compute_lag_buckets(df, refs)

    for ref_col, ref_label in [("A", "99.5th-pct"), ("B", "mode/peak")]:
        bucket_avg = bucket_shares_table(lag_df, ref_col)
        bucket_avg.to_csv(
            OUTPUT_DIR / f"bucket_shares_ref{ref_col}.csv", index=False)
        print(f"  Saved: bucket_shares_ref{ref_col}.csv")

        plot_bucket_comparison(
            bucket_avg, ref_label,
            OUTPUT_DIR / f"bucket_comparison_ref{ref_col}.png")

        plot_chrome_old_tail(
            lag_df, ref_col,
            OUTPUT_DIR / f"chrome_old_tail_ref{ref_col}.png")

    # --- Concentration metrics ---
    print("[6/8] Computing concentration metrics (HHI, top-N) …")
    conc_A = compute_concentration(lag_df, "A")
    conc_A.to_csv(OUTPUT_DIR / "concentration_metrics_refA.csv", index=False)
    print("  Saved: concentration_metrics_refA.csv")
    plot_concentration_hhi(conc_A, "A", OUTPUT_DIR / "concentration_hhi_refA.png")

    # --- Outlier detection ---
    print("[7/8] Detecting outlier months …")
    outliers_A = detect_outliers(lag_df, "A")
    if not outliers_A.empty:
        outliers_A.to_csv(OUTPUT_DIR / "outlier_months.csv", index=False)
        print(f"  {len(outliers_A)} outlier months detected. Saved: outlier_months.csv")
    else:
        print("  No outlier months detected (>median+3*MAD or >2x previous).")

    # --- Threshold tables ---
    print("[8/8] Computing policy thresholds …")
    thresh_df = compute_thresholds(lag_df, "A")
    if not thresh_df.empty:
        thresh_df.to_csv(OUTPUT_DIR / "threshold_pct_blocked.csv", index=False)
        policy_table = find_lag_thresholds(thresh_df)
        policy_table.to_csv(OUTPUT_DIR / "policy_thresholds.csv", index=False)
        print("  Saved: threshold_pct_blocked.csv, policy_thresholds.csv")

    # ==================================================================
    # Build report tables text file
    # ==================================================================
    print("\nBuilding report tables …")
    report_lines = ["StatCounter Browser Analysis – Key Tables", "=" * 70, ""]

    # Table 1: Family averages for 2022 and 2025-26
    t1 = fam_avg[fam_avg["period"].isin([PERIOD_A, PERIOD_B])].pivot(
        index="browser_family", columns="period", values="avg_share_pct"
    ).fillna(0).round(2)
    t1 = t1.sort_values(PERIOD_B, ascending=False)
    report_lines.append(fmt_table(t1.reset_index(),
        f"Table 1: Average Monthly Browser-Family Share (%) — {PERIOD_A} vs {PERIOD_B}"))

    # Table 2: Bucket shares (ref A) for 2022 vs 2025-26
    for family in LAG_FAMILIES:
        sub = bucket_shares_table(lag_df, "A")
        t2 = sub[
            (sub["browser_family"] == family) &
            (sub["period"].isin([PERIOD_A, PERIOD_B])) &
            (sub["bucket"].isin([b[0] for b in LAG_BUCKETS]))
        ].pivot_table(
            index="bucket", columns="period",
            values=["share_all_traffic", "share_within_family"],
            aggfunc="mean"
        ).round(3)
        report_lines.append(fmt_table(
            t2.reset_index(),
            f"Table 2 ({family}): Lag-Bucket Shares — Ref A (99.5th-pct)"))

    # Table 3: Outliers summary
    if not outliers_A.empty:
        report_lines.append(fmt_table(
            outliers_A[["browser_family", "period", "date",
                        "old_tail_share", "flag_3mad", "flag_2x"]].round(3),
            "Table 3: Outlier Months (lag≥12 share unusually high)"))
    else:
        report_lines.append("\nTable 3: No outlier months detected.\n")

    # Table 4: Concentration summary (avg by family/period)
    if not conc_A.empty:
        t4 = (conc_A.groupby(["browser_family", "period"])
                    [["HHI", "top1_pct_of_tail",
                       "top3_pct_of_tail", "top5_pct_of_tail"]]
                    .mean()
                    .round(1)
                    .reset_index())
        report_lines.append(fmt_table(t4, "Table 4: Avg HHI & Top-N Concentration of Old-Tail Versions"))

    # Table 5: Policy thresholds
    if not thresh_df.empty:
        report_lines.append(fmt_table(
            policy_table.round(1),
            "Table 5: Minimum Lag Threshold to Keep False-Positive Rate ≤ Target (Ref A)"))

    # Table 6: Absurdly old versions (e.g., lag >= 30)
    very_old = lag_df[
        (lag_df["lag_A"] >= 30) &
        (lag_df["share"] >= 0.05) &
        (lag_df["browser_family"].isin(LAG_FAMILIES))
    ].copy()
    if not very_old.empty:
        v6 = (very_old.groupby(["browser_family", "period", "major"])["share"]
                      .mean()
                      .reset_index()
                      .sort_values("share", ascending=False)
                      .head(30)
                      .round(3))
        report_lines.append(fmt_table(v6, "Table 6: Persistent Very-Old Versions (lag≥30, avg share≥0.05%)"))

    with open(OUTPUT_DIR / "report_tables.txt", "w") as f:
        f.write("\n".join(report_lines))
    print("  Saved: report_tables.txt")

    # ==================================================================
    # Print key summary to stdout
    # ==================================================================
    print("\n--- KEY FINDINGS SUMMARY ---")
    print("\nTop browser families by average share:")
    for period in [PERIOD_A, PERIOD_B]:
        top = fam_avg[fam_avg["period"] == period].head(6)
        print(f"\n  Period {period}:")
        for _, r in top.iterrows():
            print(f"    {r['browser_family']:30s} {r['avg_share_pct']:6.2f}%")

    if not outliers_A.empty:
        print(f"\nOutlier months detected: {len(outliers_A)}")
        print(outliers_A[["browser_family", "period", "date",
                           "old_tail_share"]].to_string(index=False))

    if not conc_A.empty:
        print("\nAvg HHI of old-tail (lag>=12) by family/period:")
        t4_sub = (conc_A[conc_A["period"].isin([PERIOD_A, PERIOD_B])]
                        .groupby(["browser_family", "period"])["HHI"]
                        .mean()
                        .reset_index()
                        .round(0))
        print(t4_sub.to_string(index=False))

    if not thresh_df.empty:
        print("\nPolicy thresholds (min lag to keep FP <= target):")
        print(policy_table.to_string(index=False))

    print(f"\nAll outputs written to: {OUTPUT_DIR.resolve()}")
    print("Done.\n")


if __name__ == "__main__":
    main()
