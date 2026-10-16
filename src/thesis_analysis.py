"""
Analysis script 
"""

import re
import sys
import platform
import datetime
import matplotlib as _mpl, scipy as _sp, statsmodels as _sm
import numpy as np
import pandas as pd
import scipy.stats as stats
import statsmodels.api as sm
import statsmodels.formula.api as smf
from statsmodels.stats.outliers_influence import variance_inflation_factor
from statsmodels.stats.diagnostic import het_breuschpagan
from statsmodels.stats.stattools import durbin_watson
from statsmodels.stats.multitest import multipletests
from statsmodels.stats.anova import anova_lm
import pingouin as pg
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# =====================================================================
# SETTINGS
# =====================================================================
DATA_FILE = "responses.csv"       
MANUAL_COLUMNS = {}               
DROP_STRAIGHTLINERS = False       
ALPHA = 0.05
REQUIRE_CONSENT_COLUMN = True      # True = stop if no consent column is found (safe default)
AI_EXP_SOURCE = "Q1.4"           
# No category merging anywhere in this script: every answer category (including very small ones, e.g. age 60+ or education "Other") is analysed as it is.


def g(row, *names):
    """Read a pingouin result column whatever the installed version calls it
    (older versions: 'p-unc', newer: 'p_unc')."""
    for n in names:
        if n in row.index:
            return row[n]
    raise KeyError(f"none of {names} found in {list(row.index)}")


class Tee:
    """Print to console and to results.txt at the same time."""
    def __init__(self, path):
        self.f = open(path, "w", encoding="utf-8")
        self.o = sys.stdout
    def write(self, s):
        self.o.write(s); self.f.write(s)
    def flush(self):
        self.o.flush(); self.f.flush()
    def __getattr__(self, name):          
        return getattr(self.o, name)


import argparse, os
_ap = argparse.ArgumentParser(description="Thesis analysis script")
_ap.add_argument("--data", help="path to the survey export (.csv or .xlsx); default = DATA_FILE above")
_ap.add_argument("--out", help="folder for all outputs (created if needed); default = current folder")
_args, _ = _ap.parse_known_args()
DATA_FILE = os.path.abspath(_args.data or DATA_FILE)
if _args.out:
    os.makedirs(_args.out, exist_ok=True)
    os.chdir(_args.out)
sys.stdout = Tee("results.txt")
pd.set_option("display.width", 140)
pd.set_option("display.max_columns", 60)


def head(title):
    print("\n" + "=" * 78 + f"\n{title}\n" + "=" * 78)


tables = {}  
warnings_log = []   

def shapiro_safe(x, label):
    """Shapiro-Wilk that never fails silently: too few values or no variation -> NaN plus a logged warning."""
    x = pd.Series(x).dropna()
    if len(x) < 3 or x.nunique() < 2:
        warnings_log.append(f"Shapiro-Wilk not computed for {label} (n = {len(x)}, distinct values = {x.nunique()})")
        print(f"  WARNING: Shapiro-Wilk not computed for {label} (n = {len(x)}, distinct values = {x.nunique()})")
        return np.nan, np.nan
    return stats.shapiro(x)


def require_variance(df_, cols, label):
    """Stop (and say why) if a variable has no variation or too few valid values for correlations / regression."""
    bad = [c for c in cols if df_[c].notna().sum() < 5 or df_[c].nunique() < 2]
    if bad:
        raise SystemExit(f"STOP ({label}): too few valid values or no variation in {bad}.")
tables["Run_info"] = pd.DataFrame({"Item": ["Analysis date", "Data file", "Python", "pandas", "numpy", "scipy", "statsmodels", "pingouin", "matplotlib"],
    "Value": [datetime.date.today().isoformat(), os.path.basename(DATA_FILE), platform.python_version(), pd.__version__, np.__version__,
              _sp.__version__, _sm.__version__, pg.__version__, _mpl.__version__]})
print("Run info:", "; ".join(f"{a} {b}" for a, b in tables["Run_info"].values))

# =====================================================================
# 1. LOAD AND LOCATE COLUMNS
# =====================================================================
raw = pd.read_excel(DATA_FILE) if DATA_FILE.lower().endswith((".xlsx", ".xls")) else pd.read_csv(DATA_FILE)
n_loaded = raw.shape[0]
print(f"Loaded {raw.shape[0]} rows, {raw.shape[1]} columns from {os.path.basename(DATA_FILE)}  (the file itself is never modified)")

# consent question: keep only respondents who agreed to participate
consent_cols = [c for c in raw.columns if "agree to participate" in str(c).lower()]
consent_idx = None
if not consent_cols and REQUIRE_CONSENT_COLUMN:
    raise SystemExit("STOP: consent column not found (no header contains 'agree to participate'). "
                     "Check the export header, or set REQUIRE_CONSENT_COLUMN = False if consent was not collected in the file.")
if consent_cols:
    consent_idx = list(raw.columns).index(consent_cols[0])
    print("Consent answers found in the file (value: count):")
    print(raw[consent_cols[0]].value_counts(dropna=False).to_string())
    _cs = raw[consent_cols[0]].astype(str).str.strip().str.lower()
    agreed = _cs.str.startswith("yes")
    _unknown = sorted(set(_cs[~agreed]) - {v for v in _cs[~agreed] if v.startswith("no") or v in ("nan", "")})
    if _unknown:
        raise SystemExit(f"STOP: unexpected consent answers {_unknown}. Only values starting with 'Yes' count as consent "
                         "and values starting with 'No' as refusal; check the export.")
    print("  -> 'Yes ...' = consent (kept); 'No ...' or empty = no consent (removed)")
    print(f"Consent question found: {int((~agreed).sum())} respondent(s) did not consent -> removed")
    n_nonconsent = int((~agreed).sum())
    raw = raw.loc[agreed].reset_index(drop=True)

CODES = ([f"Q1.{i}" for i in range(1, 6)] + [f"Q2.{i}" for i in range(1, 12)]
         + [f"Q3.{i}" for i in range(1, 9)] + [f"Q4.{i}" for i in range(1, 5)]
         + ["Q5.1", "Q5.2", "Q5.3"])


def find_col(df, code):
    if code in MANUAL_COLUMNS:
        return MANUAL_COLUMNS[code]
    pat = re.compile(rf"^\s*{re.escape(code)}(?!\d)")
    hits = [c for c in df.columns if pat.match(str(c))]
    return hits[0] if len(hits) == 1 else None


colmap = {code: find_col(raw, code) for code in CODES}
missing = [c for c, v in colmap.items() if v is None]
POSITIONAL = False
if missing and len(missing) == len(CODES) and consent_idx is not None:
 
    after = list(raw.columns)[consent_idx + 1:]
    if len(after) == len(CODES):
        colmap = dict(zip(CODES, after))
        missing = []
        POSITIONAL = True
        print("\nHeaders have no question codes -> mapped by position. CHECK this mapping:")
        for code, col in colmap.items():
            print(f"  {code:5s} <- {str(col).replace(chr(10), ' ')[:85]}")
if missing:
    print("\nCould not find columns for:", missing)
    print("Rename those headers so they START with the question code (e.g. 'Q2.7 ...'),")
    print("or list them in MANUAL_COLUMNS at the top of this script.")
    print("\nColumns in your file:")
    for c in raw.columns:
        print("  -", c)
    sys.exit(1)

EXPECT = {
    "Q1.1": (["age group"], []), "Q1.2": (["gender"], []), "Q1.3": (["educational"], []),
    "Q1.4": (["general experience with ai tools"], []), "Q1.5": (["used any ai-based health tools"], []),
    "Q2.1": (["provide accurate information"], []), "Q2.2": (["as accurate as a healthcare professional"], []),
    "Q2.3": (["incorrect information"], []),
    "Q2.4": (["clearly explain the reasoning"], []), "Q2.5": (["i understand how"], []), "Q2.6": (["black box"], []),
    "Q2.7": (["reliable information"], []), "Q2.8": (["trust the advice"], []), "Q2.9": (["sceptical"], []),
    "Q2.10": (["willing to receive healthcare"], []), "Q2.11": (["would accept a healthcare professional"], []),
    "Q3.1": (["physician", "acceptable"], []), "Q3.2": (["physician", "receiving care"], []),
    "Q3.3": (["nurse", "acceptable"], []), "Q3.4": (["nurse", "receiving care"], []),
    "Q3.5": (["dentist", "acceptable"], []), "Q3.6": (["dentist", "receiving care"], []),
    "Q3.7": (["pharmacist", "acceptable"], []), "Q3.8": (["pharmacist", "receiving care"], []),
    "Q4.1": (["accurate diagnoses"], ["knowing this"]), "Q4.2": (["appropriate decisions"], ["knowing this"]),
    "Q4.3": (["knowing this", "accurate diagnoses"], []), "Q4.4": (["knowing this", "appropriate decisions"], []),
    "Q5.1": (["less trustworthy"], []), "Q5.2": (["prefer"], []), "Q5.3": (["open text"], []),
}
assert set(EXPECT) == set(CODES), "EXPECT must cover all 31 question codes"
print("\nColumn mapping (question code <- start of the header; all 31 are checked against the expected wording):")
wrong = []
for code in CODES:
    h = str(colmap[code]).lower()
    must, mustnot = EXPECT[code]
    ok = all(k in h for k in must) and not any(k in h for k in mustnot)
    print(f"  {'OK ' if ok else 'BAD'} {code:5s} <- {str(colmap[code]).replace(chr(10), ' ')[-70:]}")
    if not ok:
        wrong.append(code)
if wrong:
    print("\nSTOP: these columns do not look like the expected questions:", wrong)
    print("The column order or the mapping is wrong; fix MANUAL_COLUMNS or the file before continuing.")
    sys.exit(1)
print("All 31 columns match the expected questions.")

df = pd.DataFrame({code: raw[col] for code, col in colmap.items()})
n_consented = len(df)
dups = int(df.duplicated().sum())
print(f"CHECK: duplicated answer rows (identical in every question): {dups}")
if dups:
    warnings_log.append(f"{dups} duplicated answer row(s) - inspect them; they are NOT removed automatically")

# =====================================================================
# 2. RECODE
# =====================================================================
TEXT_LIKERT = {"strongly disagree": 1, "disagree": 2, "neither agree or disagree": 3,
               "neither agree nor disagree": 3, "neutral": 3, "agree": 4, "strongly agree": 5}


def to_likert(s):
    if pd.api.types.is_numeric_dtype(s):
        return pd.to_numeric(s, errors="coerce")
    t = s.astype(str).str.strip()
    num = pd.to_numeric(t.str.extract(r"^\s*([1-5])\b")[0], errors="coerce")
    txt = t.str.lower().map(TEXT_LIKERT)
    return num.fillna(txt)


LIKERT_CODES = ([f"Q2.{i}" for i in range(1, 12)] + [f"Q3.{i}" for i in range(1, 9)]
                + [f"Q4.{i}" for i in range(1, 5)] + ["Q5.1"])
for c in LIKERT_CODES:
    df[c] = to_likert(df[c])


def clean(x):
    return str(x).lower().replace("\u2013", "-").replace("\u2014", "-").replace(" ", "")


def recode_age(x):
    x = clean(x)
    if x.startswith("under"): return "Under 25"
    if "25-40" in x: return "25-40"
    if "41-59" in x: return "41-59"
    if x.startswith("60"): return "60+"
    return np.nan


def recode_gender(x):
    x = clean(x)
    if x == "male": return "Male"
    if x == "female": return "Female"
    if x.startswith("prefer"): return "Prefer not to say"
    return np.nan


def recode_edu(x):
    x = clean(x)
    if x.startswith("high"): return "High school or below"
    if x.startswith("bachelor"): return "Bachelor's degree"
    if x.startswith("master"): return "Master's degree or above"
    if x.startswith("other"): return "Other"
    return np.nan


def recode_ai_exp(x):
    x = clean(x)
    if x.startswith("regular"): return "Regular"
    if x.startswith("occasional"): return "Occasional"
    if x.startswith("rare") or "never" in x: return "Rare/never"
    return np.nan


def recode_health_ai(x):
    x = clean(x)
    if "regularly" in x: return "Regular"
    if "occasionally" in x: return "Occasional"
    if x.startswith("no"): return "Rare/never"
    return np.nan


AGE_ORDER = ["Under 25", "25-40", "41-59", "60+"]
EDU_ORDER = ["High school or below", "Bachelor's degree", "Master's degree or above", "Other"]
EXP_ORDER = ["Rare/never", "Occasional", "Regular"]

df["Age_group"] = df["Q1.1"].map(recode_age)
df["Gender"] = df["Q1.2"].map(recode_gender)
df["Education"] = df["Q1.3"].map(recode_edu)
df["AI_general"] = df["Q1.4"].map(recode_ai_exp)
df["AI_health"] = df["Q1.5"].map(recode_health_ai)
assert AI_EXP_SOURCE in ("Q1.4", "Q1.5"), "AI_EXP_SOURCE must be 'Q1.4' or 'Q1.5'"
df["AI_exp"] = df["AI_general"] if AI_EXP_SOURCE == "Q1.4" else df["AI_health"]
for col, src in [("Age_group", "Q1.1"), ("Gender", "Q1.2"), ("Education", "Q1.3"),
                 ("AI_general", "Q1.4"), ("AI_health", "Q1.5")]:
    bad = df[col].isna() & df[src].notna()
    if bad.any():
        print(f"WARNING: {bad.sum()} unrecognised value(s) in {src}: {df.loc[bad, src].unique()[:5]}")


AI_ORDER = EXP_ORDER      # Rare/never, Occasional, Regular (no merging)
print(f"Prior-AI-experience variable for RQ4 = {AI_EXP_SOURCE}")

# =====================================================================
# 3. EXCLUSIONS, REVERSE SCORING, COMPOSITES
# =====================================================================
core = [c for c in LIKERT_CODES if c != "Q5.1"]
n0 = len(df)
df_all = df.copy()          # consent-filtered
open_text_all = df["Q5.3"].dropna().astype(str).str.strip()  
open_text_all = open_text_all[open_text_all != ""]

print("\nCHECK: missing or unreadable Likert answers per item (should be 0 for the core items):")
miss = df[LIKERT_CODES].isna().sum()
print(miss[miss > 0].to_string() if (miss > 0).any() else "  none")
print("CHECK: respondents missing at least one core item:", int(df[core].isna().any(axis=1).sum()))
bad = [c for c in LIKERT_CODES if not df[c].dropna().isin([1, 2, 3, 4, 5]).all()]
if bad:
    raise SystemExit(f"STOP: invalid Likert values (not 1-5) in {bad}. Check the export and recoding before continuing.")
print("CHECK: all non-missing Likert values are within 1-5.")
df = df.dropna(subset=core).reset_index(drop=True)
print(f"\nDropped {n0 - len(df)} rows with missing/unreadable Likert answers -> N = {len(df)}")
if n0 - len(df):
    warnings_log.append(f"{n0 - len(df)} respondent(s) dropped for missing/unreadable core Likert answers")
n_after_core = len(df)

q2 = [f"Q2.{i}" for i in range(1, 10)]
straight = df[q2].nunique(axis=1) == 1
print(f"Rows with the identical raw answer to all of Q2.1-Q2.9 (includes reverse items): {int(straight.sum())}")
if DROP_STRAIGHTLINERS and straight.any():
    df = df.loc[~straight].reset_index(drop=True)
    print(f"  dropped -> N = {len(df)}")
if straight.any():
    warnings_log.append(f"{int(straight.sum())} respondent(s) gave the identical raw answer to Q2.1-Q2.9 (DROP_STRAIGHTLINERS = {DROP_STRAIGHTLINERS})")
tables["Sample_flow"] = pd.DataFrame({"Step": ["Rows in file", "Did not consent (removed)", "Consented",
                                              "Dropped: missing core Likert answers", "Dropped: straightliners (only if DROP_STRAIGHTLINERS)", "Final N"],
                                      "n": [n_loaded, n_nonconsent if consent_cols else 0, n_consented, n0 - n_after_core,
                                            n_after_core - len(df), len(df)]})
print(tables["Sample_flow"].to_string(index=False))
df["id"] = df.index

REVERSED = ["Q2.3", "Q2.6", "Q2.9"]           # reverse-worded items 
for c in REVERSED:
    assert pd.api.types.is_numeric_dtype(df[c]), f"{c} is not numeric before reverse scoring"
_before = df[REVERSED].mean()
for c in REVERSED:
    df[c] = 6 - df[c]
print("Reverse scoring (6 - x) applied to", REVERSED, "| means before:", _before.round(2).to_dict(),
      "| after:", df[REVERSED].mean().round(2).to_dict())
assert df[REVERSED].isin([1, 2, 3, 4, 5]).all().all(), "reverse scoring produced values outside 1-5"

SCALES = {
    "Accuracy":     ["Q2.1", "Q2.2", "Q2.3"],
    "Transparency": ["Q2.4", "Q2.5", "Q2.6"],
    "Trust":        ["Q2.7", "Q2.8", "Q2.9"],
    "Acceptance":   ["Q2.10", "Q2.11"],
    "Acc_Physician":  ["Q3.1", "Q3.2"],
    "Acc_Nurse":      ["Q3.3", "Q3.4"],
    "Acc_Dentist":    ["Q3.5", "Q3.6"],
    "Acc_Pharmacist": ["Q3.7", "Q3.8"],
    "Trust_Baseline":   ["Q4.1", "Q4.2"],
    "Trust_Disclosure": ["Q4.3", "Q4.4"],
}
for name, items in SCALES.items():
    df[name] = df[items].mean(axis=1, skipna=False)   

# =====================================================================
# 4. SAMPLE DESCRIPTION
# =====================================================================
head("SAMPLE DESCRIPTION")
print(f"Final N = {len(df)}")
sample_rows = []
for label, col, order in [("Age group", "Age_group", AGE_ORDER), ("Gender", "Gender", None),
                          ("Education", "Education", EDU_ORDER), ("General AI tool experience (Q1.4)", "AI_general", EXP_ORDER),
                          ("AI health tool use (Q1.5)", "AI_health", EXP_ORDER)]:
    vc = df[col].value_counts()
    if order:
        vc = vc.reindex(order).fillna(0).astype(int)
    for level, n in vc.items():
        sample_rows.append({"Variable": label, "Level": level, "n": int(n), "%": round(100 * n / len(df), 1)})
sample_table = pd.DataFrame(sample_rows)
print(sample_table.to_string(index=False))
tables["Sample"] = sample_table
small = sample_table[(sample_table["n"] < 10) & (sample_table["Variable"].isin(
    ["Age group", "Education", "General AI tool experience (Q1.4)", "AI health tool use (Q1.5)"]))]
if len(small):
        print(small.to_string(index=False))

# =====================================================================
# 5. RELIABILITY
# =====================================================================
head("RELIABILITY (after reverse-scoring Q2.3, Q2.6, Q2.9)")
rel_rows = []
for name, items in SCALES.items():
    sub = df[items]
    a, ci = pg.cronbach_alpha(data=sub)
    corr = sub.corr().values
    mean_r = corr[np.triu_indices_from(corr, k=1)].mean()
    rel_rows.append({"Scale": name, "Items": len(items), "Cronbach_alpha": round(a, 3),
                     "CI_low": round(ci[0], 3), "CI_high": round(ci[1], 3),
                     "Mean_inter_item_r": round(mean_r, 3),
                     "Spearman_Brown": round(2 * mean_r / (1 + mean_r), 3) if len(items) == 2 else np.nan})
rel_table = pd.DataFrame(rel_rows)
print(rel_table.to_string(index=False))
print("\nFor 2-item scales report the inter-item r (and Spearman-Brown) rather than alpha.")
print("\nAlpha if item deleted (3-item scales; a reverse-worded item that lowers alpha is a typical cause of low alpha):")
for name in ["Accuracy", "Transparency", "Trust"]:
    its = SCALES[name]
    print(f"  {name}: " + ", ".join(f"-{i}: {pg.cronbach_alpha(data=df[[j for j in its if j != i]])[0]:.3f}" for i in its))
tables["Reliability"] = rel_table

# =====================================================================
# 6. RQ2 -- DESCRIPTIVES
# =====================================================================
head("RQ2 -- Descriptive statistics")
core_scales = ["Accuracy", "Transparency", "Trust", "Acceptance"]
rq2 = df[core_scales].agg(["count", "mean", "std", "min", "max", "skew", "kurt"]).T.round(3)
print(rq2)
tables["RQ2_Descriptives"] = rq2.reset_index().rename(columns={"index": "Construct"})

item_desc = df[[c for c in LIKERT_CODES if c.startswith("Q2")]].agg(["mean", "std"]).T.round(2)
print("\nItem-level means (Q2.3, Q2.6, Q2.9 already reverse-scored):")
print(item_desc)
tables["Item_descriptives"] = item_desc.reset_index().rename(columns={"index": "Item"})

fig, axes = plt.subplots(1, 3, figsize=(12, 3.6), sharey=True)
for ax, c in zip(axes, ["Accuracy", "Transparency", "Trust"]):
    ax.hist(df[c], bins=np.arange(0.75, 5.5, 0.5), edgecolor="black")
    ax.set_title(c); ax.set_xlabel("Composite score (1-5)")
axes[0].set_ylabel("Respondents")
plt.tight_layout(); plt.savefig("fig_rq2_distributions.png", dpi=200); plt.close()

# =====================================================================
# 7. RQ1 -- CORRELATIONS AND MULTIPLE REGRESSION
# =====================================================================
head("RQ1 -- Pearson correlations with Acceptance")
cor_rows = []
for p in ["Accuracy", "Transparency", "Trust"]:
    r = pg.corr(df[p], df["Acceptance"], method="pearson").iloc[0]
    ci = [c for c in r.index if str(c).startswith("CI95")][0]
    cor_rows.append({"Predictor": p, "n": int(r["n"]), "r": round(r["r"], 3),
                     "CI95": r[ci], "p": g(r, "p-val", "p_val")})
cor_table = pd.DataFrame(cor_rows)
print(cor_table.to_string(index=False))
tables["RQ1_Correlations"] = cor_table
print("\nFull correlation matrix:")
print(df[core_scales].corr().round(3))

head("RQ1 -- Multiple regression: Acceptance ~ Accuracy + Transparency + Trust")
X = sm.add_constant(df[["Accuracy", "Transparency", "Trust"]])
m1 = sm.OLS(df["Acceptance"], X).fit()
print(m1.summary())
beta = {p: m1.params[p] * df[p].std() / df["Acceptance"].std() for p in ["Accuracy", "Transparency", "Trust"]}
ci = m1.conf_int()
coef = pd.DataFrame({"B": m1.params, "SE": m1.bse, "Beta": pd.Series(beta), "t": m1.tvalues,
                     "p": m1.pvalues, "CI_low": ci[0], "CI_high": ci[1]}).round(4)
print(f"\nR2 = {m1.rsquared:.3f}, adj. R2 = {m1.rsquared_adj:.3f}, "
      f"F({int(m1.df_model)}, {int(m1.df_resid)}) = {m1.fvalue:.2f}, p = {m1.f_pvalue:.4g}, N = {int(m1.nobs)}")
tables["RQ1_Regression"] = coef.reset_index().rename(columns={"index": "Term"})

vif = pd.DataFrame({"Predictor": X.columns[1:],
                    "VIF": [variance_inflation_factor(X.values, i) for i in range(1, X.shape[1])]}).round(3)
print("\nVIF (concern if > 5):")
print(vif.to_string(index=False))
sh = shapiro_safe(m1.resid, "RQ1 residuals")
bp = het_breuschpagan(m1.resid, X)
print(f"Shapiro-Wilk on residuals: W = {sh[0]:.3f}, p = {sh[1]:.3f}")
print(f"Breusch-Pagan (homoscedasticity): LM = {bp[0]:.3f}, p = {bp[1]:.3f}")
print(f"Durbin-Watson: {durbin_watson(m1.resid):.3f}  (little informative for a cross-sectional survey with one row per respondent; the rows have no meaningful order)")
# influence check and residual plot
infl = m1.get_influence()
cook = infl.cooks_distance[0]
thr = 4 / len(df)
print(f"Cook's distance: max = {cook.max():.3f}; cases above 4/N ({thr:.3f}): {int((cook > thr).sum())}; cases above 1: {int((cook > 1).sum())}")
tables["RQ1_Influence"] = pd.DataFrame({"id": df["id"], "CooksD": np.round(cook, 4), "Studentized_resid": np.round(infl.resid_studentized_external, 3)}).sort_values("CooksD", ascending=False).head(10)
fig, axs = plt.subplots(1, 2, figsize=(9, 3.8))
axs[0].scatter(m1.fittedvalues, m1.resid, s=14); axs[0].axhline(0, color="black", lw=1)
axs[0].set_xlabel("Fitted acceptance"); axs[0].set_ylabel("Residual"); axs[0].set_title("Residuals vs fitted")
axs[1].stem(np.arange(len(cook)), cook, markerfmt=" "); axs[1].axhline(thr, color="red", ls="--", lw=1)
axs[1].set_xlabel("Respondent"); axs[1].set_ylabel("Cook's distance"); axs[1].set_title("Influence (dashed = 4/N)")
plt.tight_layout(); plt.savefig("fig_rq1_diagnostics.png", dpi=200); plt.close()
tables["RQ1_VIF"] = vif
m1_hc3 = sm.OLS(df["Acceptance"], X).fit(cov_type="HC3")
_ci_hc3 = m1_hc3.conf_int()
tables["RQ1_Regression_HC3"] = pd.DataFrame({"B": m1_hc3.params, "SE_HC3": m1_hc3.bse, "t": m1_hc3.tvalues,
                                             "p_HC3": m1_hc3.pvalues, "CI_low": _ci_hc3[0], "CI_high": _ci_hc3[1]}).round(4).reset_index().rename(columns={"index": "Term"})
print("\nSensitivity: heteroscedasticity-robust (HC3) p-values: " +
      ", ".join(f"{k} p = {v:.4f}" for k, v in m1_hc3.pvalues.items() if k != "const"))

# --- extended regression with background variables (RQ4) ---
head("RQ4 -- Extended regression: background factors added to the RQ1 model")
d_ext = df.dropna(subset=["Age_group", "Education", "AI_exp"]).copy()
formula_base = "Acceptance ~ Accuracy + Transparency + Trust"
formula_ext = (formula_base + f' + C(Age_group, Treatment(reference="{AGE_ORDER[0]}"))'
               f' + C(Education, Treatment(reference="{EDU_ORDER[0]}"))'
               f' + C(AI_exp, Treatment(reference="{AI_ORDER[0]}"))')
print(f"Reference categories: age = {AGE_ORDER[0]}, education = {EDU_ORDER[0]}, AI experience = {AI_ORDER[0]}")
try:
    m_base = smf.ols(formula_base, data=d_ext).fit()
    m_ext = smf.ols(formula_ext, data=d_ext).fit()
    print(m_ext.summary())
    cmp_ = anova_lm(m_base, m_ext)
    print(f"\nBase R2 = {m_base.rsquared:.3f}; extended R2 = {m_ext.rsquared:.3f}; "
          f"change = {m_ext.rsquared - m_base.rsquared:.3f}")
    print("Nested-model F test (do the background factors add anything?):")
    print(cmp_)
    ci2 = m_ext.conf_int()
    ext_table = pd.DataFrame({"B": m_ext.params, "SE": m_ext.bse, "t": m_ext.tvalues,
                              "p": m_ext.pvalues, "CI_low": ci2[0], "CI_high": ci2[1]}).round(4)
    tables["RQ4_ExtendedRegression"] = ext_table.reset_index().rename(columns={"index": "Term"})
    tables["RQ4_ModelComparison"] = cmp_.reset_index()
    # supplementary: same model with the other experience question instead of the primary one
    other_col, other_label = ("AI_health", "Q1.5 (AI health tool use)") if AI_EXP_SOURCE == "Q1.4" else ("AI_general", "Q1.4 (general AI tool experience)")
    d2 = df.dropna(subset=["Age_group", "Education", other_col]).copy()   # independent of the primary variable's missingness
    m_b2 = smf.ols(formula_base, data=d2).fit()
    m_e2 = smf.ols(formula_base + f' + C(Age_group, Treatment(reference="{AGE_ORDER[0]}"))'
                   f' + C(Education, Treatment(reference="{EDU_ORDER[0]}"))'
                   f' + C({other_col}, Treatment(reference="{AI_ORDER[0]}"))', data=d2).fit()
    c2 = anova_lm(m_b2, m_e2)
    print(f"\nSUPPLEMENTARY extended model using {other_label} instead of the primary experience variable (N = {len(d2)}):")
    print(m_e2.summary().tables[1])
    print(f"Base R2 = {m_b2.rsquared:.3f}; extended R2 = {m_e2.rsquared:.3f}; change = {m_e2.rsquared - m_b2.rsquared:.3f}; "
          f"F p = {c2['Pr(>F)'].iloc[1]:.4f}")
    ci3 = m_e2.conf_int()
    tables["RQ4_ExtReg_Supplementary"] = pd.DataFrame({"B": m_e2.params, "SE": m_e2.bse, "t": m_e2.tvalues, "p": m_e2.pvalues,
                                             "CI_low": ci3[0], "CI_high": ci3[1]}).round(4).reset_index().rename(columns={"index": "Term"})
except Exception as e:
    print("Extended regression failed (usually an empty or very sparse category):", e)

# =====================================================================
# 8. RQ3 -- ACCEPTANCE ACROSS PROFESSIONS
# =====================================================================
head("RQ3 -- Acceptance across professions (within-subjects)")
prof_cols = ["Acc_Physician", "Acc_Nurse", "Acc_Dentist", "Acc_Pharmacist"]
prof_desc = df[prof_cols].agg(["count", "mean", "std", "min", "max", "skew"]).T.round(3)
print(prof_desc)
tables["RQ3_Descriptives"] = prof_desc.reset_index().rename(columns={"index": "Profession"})
print("\nShapiro-Wilk per profession (informational; RM-ANOVA is fairly robust at this N):")
for c in prof_cols:
    w, p = shapiro_safe(df[c], c)
    print(f"  {c:16s} W = {w:.3f}, p = {p:.3f}")

long = df[["id"] + prof_cols].melt(id_vars="id", var_name="Profession", value_name="Acceptance")
long["Profession"] = long["Profession"].str.replace("Acc_", "", regex=False)

aov = pg.rm_anova(data=long, dv="Acceptance", within="Profession", subject="id",
                  correction=True, detailed=True, effsize="np2")
print("\nRepeated-measures ANOVA (sphericity test and Greenhouse-Geisser correction included):")
print(aov.to_string(index=False))
tables["RQ3_RM_ANOVA"] = aov
row = aov.iloc[0]
spher = pg.sphericity(df[prof_cols])           
violated = not bool(spher[0])
print(f"Mauchly's test of sphericity: W = {spher[1]:.3f}, chi2 = {spher[2]:.2f}, df = {spher[3]}, p = {spher[4]:.4f} "
      f"-> {'violated' if violated else 'not violated'}")
p_omni = g(row, "p-GG-corr", "p_GG_corr") if violated else g(row, "p-unc", "p_unc")
if "eps" in aov.columns:
    print(f"Greenhouse-Geisser epsilon = {row['eps']:.3f}")
print(f"\nOmnibus p used for the decision: {p_omni:.4g} "
      f"({'Greenhouse-Geisser corrected, sphericity violated' if violated else 'uncorrected, sphericity not violated'})")

if p_omni < ALPHA:
    post = pg.pairwise_tests(data=long, dv="Acceptance", within="Profession", subject="id",
                             padjust="bonf", effsize="cohen")
    print("\nPost-hoc paired t-tests, Bonferroni-corrected:")
    print(post.to_string(index=False))
    tables["RQ3_PostHoc"] = post
else:
    print("\nOmnibus test not significant -> no post-hoc comparisons (as per methodology).")

fr = pg.friedman(data=long, dv="Acceptance", within="Profession", subject="id")
print("\nROBUSTNESS CHECK ONLY -- Friedman test:")
print(fr.to_string())
tables["RQ3_Friedman_robustness"] = fr

fig, ax = plt.subplots(figsize=(6, 4))
means = df[prof_cols].mean(); sem = df[prof_cols].sem()
ax.bar([c.replace("Acc_", "") for c in prof_cols], means, yerr=stats.t.ppf(0.975, len(df) - 1) * sem, capsize=4, edgecolor="black")
ax.set_ylim(1, 5); ax.set_ylabel("Mean acceptance (1-5), 95% CI")
plt.tight_layout(); plt.savefig("fig_rq3_professions.png", dpi=200); plt.close()

# =====================================================================
# 9. RQ4 -- BACKGROUND FACTORS (one-way ANOVA with Holm adjustment)
# =====================================================================
head("RQ4")
rq4_rows, group_desc, posthocs = [], [], []
for out in core_scales:
    for fac, label in [("Age_group", "Age group"), ("Education", "Education"),
                       ("AI_general", "AI tool experience (Q1.4)"), ("AI_health", "AI health tool use (Q1.5)")]:
        sub = df[[out, fac]].dropna()
        gd = sub.groupby(fac)[out].agg(["count", "mean", "std"]).round(3).reset_index()
        gd.insert(0, "Outcome", out); gd.insert(1, "Factor", label); gd = gd.rename(columns={fac: "Group"})
        group_desc.append(gd)
        # 1) the omnibus ANOVA
        try:
            a = pg.anova(data=sub, dv=out, between=fac).iloc[0]
        except Exception as e:
            print(f"  ANOVA failed for {out} ~ {fac}: {e}")
            warnings_log.append(f"RQ4 ANOVA failed for {out} ~ {fac}: {e}")
            rq4_rows.append({"Outcome": out, "Factor": label, "Test": "One-way ANOVA",
                             "Statistic": np.nan, "df": "", "p": np.nan, "Effect_size": np.nan, "Effect_size_type": "partial eta-squared"})
            continue
        rq4_rows.append({"Outcome": out, "Factor": label, "Test": "One-way ANOVA",
                         "Statistic": round(a["F"], 3), "df": f"{int(a['ddof1'])}, {int(a['ddof2'])}",
                         "p": g(a, "p-unc", "p_unc"), "Effect_size": round(a["np2"], 3), "Effect_size_type": "partial eta-squared"})
        # 2) the exploratory Tukey follow-up
        if g(a, "p-unc", "p_unc") < ALPHA:
            try:
                ph = pg.pairwise_tukey(data=sub, dv=out, between=fac)
                ph.insert(0, "Outcome", out); ph.insert(1, "Factor", label)
                posthocs.append(ph)
            except Exception as e:
                print(f"  Tukey test failed for {out} ~ {fac}: {e}")
                warnings_log.append(f"RQ4 Tukey follow-up failed for {out} ~ {fac}: {e}")


rq4 = pd.DataFrame(rq4_rows)
rq4["p_Holm_adjusted"] = np.nan
ok = rq4["p"].notna()
rq4.loc[ok, "p_Holm_adjusted"] = multipletests(rq4.loc[ok, "p"], method="holm")[1]
print("\n(All RQ4 tests are one-way ANOVAs on the unmerged groups; the effect size is partial eta-squared.)")
print(rq4.to_string(index=False))
print("\nHolm-adjusted p-values are shown because many exploratory tests were run; "
      "report them alongside the raw p-values.")
tables["RQ4_Tests"] = rq4

head("RQ4 -- Robustness check: Levene and Welch ANOVA (all four factors)")
rob_rows = []
for out in core_scales:
    for fac, label in [("Age_group", "Age group"), ("Education", "Education"),
                       ("AI_general", "AI tool experience (Q1.4)"), ("AI_health", "AI health tool use (Q1.5)")]:
        sub = df[[out, fac]].dropna()
        if sub.groupby(fac)[out].count().min() < 2:
            print(f"  Welch ANOVA not computable for {out} ~ {label}: a group has n = 1 (its variance is undefined)")
            rob_rows.append({"Outcome": out, "Factor": label, "Levene_p": np.nan, "Welch_F": np.nan, "df1": np.nan,
                             "df2": np.nan, "p": np.nan, "partial_eta2": np.nan})
            continue
        groups = [v[out].values for _, v in sub.groupby(fac)]
        try:
            lev = stats.levene(*groups)
            w = pg.welch_anova(data=sub, dv=out, between=fac).iloc[0]
            pw = g(w, "p-unc", "p_unc")
            rob_rows.append({"Outcome": out, "Factor": label, "Levene_p": round(lev.pvalue, 3),
                             "Welch_F": round(w["F"], 3), "df1": int(w["ddof1"]), "df2": round(w["ddof2"], 1),
                             "p": round(pw, 4), "partial_eta2": round(w["np2"], 3) if "np2" in w.index else np.nan})
            if pw < ALPHA:
                gh = pg.pairwise_gameshowell(data=sub, dv=out, between=fac)
                print(f"\nGames-Howell for {out} by {label}:"); print(gh.to_string(index=False))
        except Exception as e:
            print(f"  Welch ANOVA failed for {out} ~ {fac}: {e}")
rob = pd.DataFrame(rob_rows)
print(rob.to_string(index=False))
tables["RQ4_Robust_WelchANOVA"] = rob
tables["RQ4_GroupDescriptives"] = pd.concat(group_desc, ignore_index=True)
if posthocs:
    _ph = pd.concat(posthocs, ignore_index=True)
    _om = rq4[["Outcome", "Factor", "p", "p_Holm_adjusted"]].rename(
        columns={"p": "Omnibus_p_unadjusted", "p_Holm_adjusted": "Omnibus_p_Holm"})
    _ph = _ph.merge(_om, on=["Outcome", "Factor"], how="left")
    _ph["Omnibus_survives_Holm"] = np.where(_ph["Omnibus_p_Holm"] < ALPHA, "yes", "NO - exploratory only")
    tables["RQ4_PostHoc_Tukey"] = _ph
    print("\nTukey post-hoc, run for every ANOVA with unadjusted p < .05 (decision rule fixed in advance; ALL of these are EXPLORATORY).")
    print("Only comparisons whose omnibus test also survives the Holm adjustment (column Omnibus_survives_Holm = yes) may be")
    print("interpreted beyond hypothesis generation; Tukey controls the error rate within one ANOVA, not across the 16 tests.")
    print(tables["RQ4_PostHoc_Tukey"].to_string(index=False))

# =====================================================================
# 10. RQ5 -- TRUST BEFORE VS AFTER DISCLOSURE
# =====================================================================
head("RQ5 -- Provider trust: baseline vs after AI disclosure (paired-samples t-test)")
b, d_ = df["Trust_Baseline"], df["Trust_Disclosure"]
diff = d_ - b
n = len(diff)
md, sd = diff.mean(), diff.std(ddof=1)
se = sd / np.sqrt(n)
tcrit = stats.t.ppf(0.975, n - 1)
tt = pg.ttest(b, d_, paired=True).iloc[0]
print(f"Baseline:   M = {b.mean():.3f}, SD = {b.std():.3f}")
print(f"Disclosure: M = {d_.mean():.3f}, SD = {d_.std():.3f}")
print(f"Mean difference (disclosure - baseline) = {md:.3f}, 95% CI [{md - tcrit * se:.3f}, {md + tcrit * se:.3f}]")
t5 = md / se   
p5 = 2 * stats.t.sf(abs(t5), n - 1)
print(f"t({n - 1}) = {t5:.3f}, p = {p5:.4g}, Cohen's dz = {md / sd:.3f}")
_, p_diff = shapiro_safe(diff, "RQ5 difference scores")
print(f"Shapiro-Wilk on difference scores: p = {p_diff:.3f}")
rq5 = pd.DataFrame([{"N": n, "M_baseline": b.mean(), "SD_baseline": b.std(), "M_disclosure": d_.mean(),
                     "SD_disclosure": d_.std(), "Mean_diff": md, "CI_low": md - tcrit * se,
                     "CI_high": md + tcrit * se, "t": t5, "df": n - 1, "p": p5,
                     "Cohens_dz": md / sd}]).round(4)
tables["RQ5_PairedT"] = rq5

wil = pg.wilcoxon(b, d_)
print("\nROBUSTNESS CHECK ONLY -- Wilcoxon signed-rank:")
print(wil.to_string())
tables["RQ5_Wilcoxon_robustness"] = wil

print("\nItem-level paired tests (supplementary):")
for lab, a_, b_ in [("Accurate diagnoses (Q4.1 vs Q4.3)", "Q4.1", "Q4.3"),
                    ("Appropriate decisions (Q4.2 vs Q4.4)", "Q4.2", "Q4.4")]:
    r = pg.ttest(df[b_], df[a_], paired=True).iloc[0]     # disclosure - baseline, same sign as the main test
    print(f"  {lab}: M {df[a_].mean():.2f} -> {df[b_].mean():.2f}, t = {r['T']:.2f}, p = {g(r, 'p-val', 'p_val'):.4g}")

fig, ax = plt.subplots(figsize=(4.5, 4))
ax.bar(["Baseline", "After disclosure"], [b.mean(), d_.mean()], yerr=[stats.t.ppf(0.975, len(b) - 1) * b.sem(), stats.t.ppf(0.975, len(d_) - 1) * d_.sem()],
       capsize=4, edgecolor="black")
ax.set_ylim(1, 5); ax.set_ylabel("Mean provider trust (1-5), 95% CI")
plt.tight_layout(); plt.savefig("fig_rq5_disclosure.png", dpi=200); plt.close()

# =====================================================================
# 11. SECTION 5 -- SUPPLEMENTARY (not part of the five RQs)
# =====================================================================
head("SECTION 5 -- Overall reflection (descriptive, supplementary)")
print(f"Sample for the Section 5 items: all {len(df_all)} consented respondents with a valid answer (core items use N = {len(df)}).")
q51 = df_all["Q5.1"].dropna()
print(f"Q5.1 'AI-using provider is LESS trustworthy' (higher = more agreement): "
      f"n = {len(q51)}, M = {q51.mean():.2f}, SD = {q51.std():.2f}")
print(q51.value_counts().sort_index().to_string())
q52 = df_all["Q5.2"].value_counts()
print("\nQ5.2 preference:")
print(pd.DataFrame({"n": q52, "%": (100 * q52 / q52.sum()).round(1)}))
tables["Q5.2_Preference"] = pd.DataFrame({"n": q52, "%": (100 * q52 / q52.sum()).round(1)}).reset_index()
open_text = open_text_all
print(f"\nQ5.3 open-text answers: {len(open_text)} (saved to open_text_responses.csv for thematic coding)")
open_text.to_frame("response").to_csv("open_text_responses.csv", index=False)

# =====================================================================
# 12. SUPPLEMENTARY DESCRIPTIVES AND FIGURES
# =====================================================================
head("SUPPLEMENTARY DESCRIPTIVES AND FIGURES")
from matplotlib.colors import LinearSegmentedColormap

C_BLUE, C_ORANGE, C_GREY = "#2a78d6", "#eb6834", "#c9c8c3"      # one hue for magnitude; orange/blue pair for polarity
C_TEXT, C_MUTED, C_GRID = "#0b0b0b", "#52514e", "#e6e5e0"
plt.rcParams.update({"font.size": 9, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.edgecolor": C_MUTED, "axes.labelcolor": C_TEXT, "text.color": C_TEXT,
                     "xtick.color": C_MUTED, "ytick.color": C_MUTED})


profile = [("Age group", "Age_group", AGE_ORDER), ("Gender", "Gender", ["Female", "Male", "Prefer not to say"]),
           ("Highest educational level", "Education", EDU_ORDER),
           ("General experience with AI tools (Q1.4)", "AI_general", EXP_ORDER),
           ("Use of AI-based health tools (Q1.5)", "AI_health", EXP_ORDER)]
fig, axes = plt.subplots(2, 3, figsize=(12, 6.4))
for ax, (title, col, order) in zip(axes.ravel(), profile):
    vc = df[col].value_counts()
    levels = [l for l in order if l in vc.index] + [l for l in vc.index if l not in order]
    vals = [int(vc.get(l, 0)) for l in levels]
    ypos = np.arange(len(levels))[::-1]
    for y, v in zip(ypos, vals):
        small = v < 10
        ax.barh(y, v, color=C_BLUE if not small else "white", edgecolor=C_BLUE, hatch="///" if small else None,
                linewidth=1.2, height=0.6)
        ax.text(v + max(vals) * 0.02, y, f"{v} ({100 * v / len(df):.1f}%)", va="center", fontsize=8.5, color=C_TEXT)
    ax.set_yticks(ypos); ax.set_yticklabels(levels, fontsize=8.5)
    ax.set_xlim(0, max(vals) * 1.35); ax.set_title(title, loc="left", fontsize=10, fontweight="bold")
    ax.set_xlabel("Respondents"); ax.grid(axis="x", color=C_GRID, linewidth=0.7); ax.set_axisbelow(True)
axes.ravel()[-1].axis("off")
axes.ravel()[-1].text(0, 0.6, f"N = {len(df)}\nHatched bars: groups with fewer than\n10 respondents (interpret with caution)",
                      fontsize=9, color=C_MUTED, va="center")
plt.tight_layout(); plt.savefig("fig_demographics.png", dpi=200); plt.close()

# ---- B. Item-level agreement percentages -------------------------------------
ITEM_LABELS = {
    "Q2.1": "Q2.1 Tools give accurate information", "Q2.2": "Q2.2 As accurate as a professional",
    "Q2.3": "Q2.3 Tools often give incorrect info (R)", "Q2.4": "Q2.4 Tools explain their reasoning",
    "Q2.5": "Q2.5 I understand how they conclude", "Q2.6": "Q2.6 Feels like a black box (R)",
    "Q2.7": "Q2.7 Trust them for reliable info", "Q2.8": "Q2.8 Trust their advice",
    "Q2.9": "Q2.9 Sceptical to rely on them (R)", "Q2.10": "Q2.10 Willing to receive care from user",
    "Q2.11": "Q2.11 Accept professional using them",
    "Q3.1": "Q3.1 Physician: acceptable", "Q3.2": "Q3.2 Physician: accept care",
    "Q3.3": "Q3.3 Nurse: acceptable", "Q3.4": "Q3.4 Nurse: accept care",
    "Q3.5": "Q3.5 Dentist: acceptable", "Q3.6": "Q3.6 Dentist: accept care",
    "Q3.7": "Q3.7 Pharmacist: acceptable", "Q3.8": "Q3.8 Pharmacist: accept care",
    "Q4.1": "Q4.1 Trust accurate diagnoses (before)", "Q4.2": "Q4.2 Trust appropriate decisions (before)",
    "Q4.3": "Q4.3 Trust accurate diagnoses (after)", "Q4.4": "Q4.4 Trust appropriate decisions (after)",
    "Q5.1": "Q5.1 AI-using provider less trustworthy"}
rows = []
for code, lab in ITEM_LABELS.items():
    # Q5.1 is a stand-alone Section 5 item: it uses every consented respondent with a valid answer 
    s = (df_all if code == "Q5.1" else df)[code].dropna()
    rows.append({"Item": code, "Label": lab, "n": len(s), "Mean": round(s.mean(), 2),
                 "% Disagree (1-2)": round(100 * (s <= 2).mean(), 1), "% Neutral (3)": round(100 * (s == 3).mean(), 1),
                 "% Agree (4-5)": round(100 * (s >= 4).mean(), 1)})
agree = pd.DataFrame(rows)
print("Item-level agreement (Q2.3, Q2.6, Q2.9 after reverse scoring; (R) = reverse-worded; Q5.1 is not reversed):")
print(agree.drop(columns="Label").to_string(index=False))
tables["Item_agreement_pct"] = agree

fig, ax = plt.subplots(figsize=(10, 9))
y = 0; yticks, ylabels = [], []
for i, r in agree.iterrows():
    if r["Item"] in ("Q3.1", "Q4.1", "Q5.1"):
        y += 0.8                                   
    d, n_, a = r["% Disagree (1-2)"], r["% Neutral (3)"], r["% Agree (4-5)"]
    ax.barh(y, d, left=-n_ / 2 - d, color=C_ORANGE, edgecolor="white", linewidth=1.5, height=0.7)
    ax.barh(y, n_, left=-n_ / 2, color=C_GREY, edgecolor="white", linewidth=1.5, height=0.7)
    ax.barh(y, a, left=n_ / 2, color=C_BLUE, edgecolor="white", linewidth=1.5, height=0.7)
    for val, x0, col in [(d, -n_ / 2 - d / 2, "white"), (n_, 0, C_TEXT), (a, n_ / 2 + a / 2, "white")]:
        if val >= 7:
            ax.text(x0, y, f"{val:.0f}%", ha="center", va="center", fontsize=7.5, color=col, fontweight="bold")
    yticks.append(y); ylabels.append(r["Label"]); y += 1
ax.set_yticks(yticks); ax.set_yticklabels(ylabels, fontsize=8); ax.invert_yaxis()
ax.axvline(0, color=C_MUTED, linewidth=0.8)
ax.set_xlim(-92, 92); ax.set_xlabel("Percentage of respondents (neutral centred; disagree to the left, agree to the right)")
ax.set_xticks([-80, -60, -40, -20, 0, 20, 40, 60, 80]); ax.set_xticklabels(["80", "60", "40", "20", "0", "20", "40", "60", "80"])
ax.grid(axis="x", color=C_GRID, linewidth=0.7); ax.set_axisbelow(True)
from matplotlib.patches import Patch
ax.legend(handles=[Patch(color=C_ORANGE, label="Disagree / strongly disagree"), Patch(color=C_GREY, label="Neutral"),
                   Patch(color=C_BLUE, label="Agree / strongly agree")], loc="lower center",
          bbox_to_anchor=(0.5, 1.0), ncol=3, frameon=False, fontsize=8.5)
plt.tight_layout(); plt.savefig("fig_items_agreement.png", dpi=200, bbox_inches="tight"); plt.close()

# ---- C. Section 5 charts -------------------------------------------------------
q51 = df_all["Q5.1"].dropna().astype(int).value_counts().reindex([1, 2, 3, 4, 5]).fillna(0).astype(int)
def _short_pref(x):
    t = str(x).lower()
    if "only as a diagnosis tool" in t or "diagnosis tool" in t: return "AI only as a diagnosis tool,\nfinal judgement with provider"
    if "no ai at all" in t: return "No AI at all"
    return "No preference"
q52 = df_all["Q5.2"].dropna().map(_short_pref).value_counts()
fig, (a1, a2) = plt.subplots(1, 2, figsize=(11, 3.8), gridspec_kw={"width_ratios": [1, 1.1]})
lab51 = ["Strongly\ndisagree", "Disagree", "Neither", "Agree", "Strongly\nagree"]
a1.bar(range(5), q51.values, color=C_BLUE, width=0.6)
for i, v in enumerate(q51.values):
    a1.text(i, v + 0.5, f"{v} ({100 * v / q51.sum():.1f}%)", ha="center", fontsize=8.5)
a1.set_xticks(range(5)); a1.set_xticklabels(lab51, fontsize=8.5); a1.set_ylabel("Respondents")
a1.set_ylim(0, q51.max() * 1.18)
a1.set_title(f"Q5.1 A provider who uses AI is less trustworthy (n = {q51.sum()})", loc="left", fontsize=10, fontweight="bold")
yy = np.arange(len(q52))[::-1]
a2.barh(yy, q52.values, color=C_BLUE, height=0.55)
for yv, v in zip(yy, q52.values):
    a2.text(v + 0.8, yv, f"{v} ({100 * v / q52.sum():.1f}%)", va="center", fontsize=8.5)
a2.set_yticks(yy); a2.set_yticklabels(q52.index, fontsize=8.5); a2.set_xlim(0, q52.max() * 1.3)
a2.set_xlabel("Respondents"); a2.set_title(f"Q5.2 Preferred situation (n = {q52.sum()})", loc="left", fontsize=10, fontweight="bold")
for a in (a1, a2):
    a.grid(color=C_GRID, linewidth=0.7, axis="y" if a is a1 else "x"); a.set_axisbelow(True)
plt.tight_layout(); plt.savefig("fig_section5.png", dpi=200); plt.close()

# ---- D. Correlation matrix of the composite scores ------------------------------
corr_vars = ["Accuracy", "Transparency", "Trust", "Acceptance", "Trust_Baseline", "Trust_Disclosure"]
require_variance(df, corr_vars, "correlation matrix")
cmat = df[corr_vars].corr(method="pearson")
pmat = pd.DataFrame(np.ones_like(cmat.values), index=corr_vars, columns=corr_vars)
for a_ in corr_vars:
    for b_ in corr_vars:
        if a_ != b_:
            pmat.loc[a_, b_] = stats.pearsonr(df[a_], df[b_])[1]
print("Pearson correlations between the composite scores:")
print(cmat.round(2).to_string())
tables["Construct_correlations_r"] = cmat.round(3).reset_index().rename(columns={"index": "Variable"})
tables["Construct_correlations_p"] = pmat.round(4).reset_index().rename(columns={"index": "Variable"})
cmap = LinearSegmentedColormap.from_list("div", [C_ORANGE, "#f2f1ed", C_BLUE])
fig, ax = plt.subplots(figsize=(6.4, 5.4))
im = ax.imshow(cmat.values, cmap=cmap, vmin=-1, vmax=1)
nice = ["Accuracy", "Transparency", "Trust (AI)", "Acceptance", "Provider trust\n(before)", "Provider trust\n(after)"]
ax.set_xticks(range(6)); ax.set_xticklabels(nice, rotation=30, ha="right", fontsize=8.5)
ax.set_yticks(range(6)); ax.set_yticklabels(nice, fontsize=8.5)
for i in range(6):
    for j in range(6):
        star = "" if i == j else ("**" if pmat.iloc[i, j] < .01 else "*" if pmat.iloc[i, j] < .05 else "")
        ax.text(j, i, f"{cmat.iloc[i, j]:.2f}{star}", ha="center", va="center", fontsize=8.5,
                color="white" if abs(cmat.iloc[i, j]) > 0.6 else C_TEXT)
for s in ax.spines.values(): s.set_visible(False)
ax.set_title("Pearson r between composite scores\n(* p < .05, ** p < .01; uncorrected, descriptive)", loc="left", fontsize=9.5)
fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
plt.tight_layout(); plt.savefig("fig_correlation_matrix.png", dpi=200); plt.close()

# ---- E. RQ4: group means with 95% CI -------------------------------------------
facs = [("Age group", "Age_group", AGE_ORDER), ("Education", "Education", EDU_ORDER),
        ("AI tools (Q1.4)", "AI_general", EXP_ORDER), ("AI health tools (Q1.5)", "AI_health", EXP_ORDER)]
outs = ["Accuracy", "Transparency", "Trust", "Acceptance"]
fig, axes = plt.subplots(4, 4, figsize=(13, 10), sharey=True)
for r_i, outc in enumerate(outs):
    for c_i, (ftitle, fcol, order) in enumerate(facs):
        ax = axes[r_i, c_i]
        for k, lvl in enumerate(order):
            s = df.loc[df[fcol] == lvl, outc].dropna()
            if len(s) == 0: continue
            m = s.mean(); hw = stats.t.ppf(0.975, len(s) - 1) * s.std(ddof=1) / np.sqrt(len(s)) if len(s) > 1 else np.nan
            small = len(s) < 10
            if not np.isnan(hw): ax.errorbar(k, m, yerr=hw, color=C_BLUE, capsize=3, linewidth=1.2, zorder=2)
            ax.plot(k, m, "o", markersize=7, markerfacecolor="white" if small else C_BLUE, markeredgecolor=C_BLUE,
                    markeredgewidth=1.5, zorder=3)
        ax.axhline(3, color=C_MUTED, linewidth=0.7, linestyle=":")
        ax.set_xticks(range(len(order)))
        ax.set_xticklabels([f"{l.replace('High school or below', 'HS or less').replace(' degree', '').replace(' or above', '+')}\n(n={int((df[fcol] == l).sum())})"
                            for l in order], fontsize=7)
        ax.set_xlim(-0.5, len(order) - 0.5); ax.set_ylim(0.5, 5.5); ax.set_yticks([1, 2, 3, 4, 5])
        ax.grid(axis="y", color=C_GRID, linewidth=0.7); ax.set_axisbelow(True)
        if r_i == 0: ax.set_title(ftitle, fontsize=10, fontweight="bold")
        if c_i == 0: ax.set_ylabel(outc + "\n(mean, 1-5)")
fig.suptitle("RQ4 (exploratory): mean scores by background group with 95% CI. Hollow points: groups with n < 10 "
             "(no CI for n = 1). Dotted line = scale midpoint.", fontsize=9.5, x=0.01, ha="left")
plt.tight_layout(rect=[0, 0, 1, 0.97]); plt.savefig("fig_rq4_group_means.png", dpi=200); plt.close()
plt.rcdefaults(); matplotlib.use("Agg")

# =====================================================================
# 13. EXPORT
# =====================================================================
with pd.ExcelWriter("tables.xlsx") as w:
    for name, t in tables.items():
        if t is not None and len(t):
            t.to_excel(w, sheet_name=name[:31], index=False)
print("\n" + "=" * 70 + "\nVALIDATION SUMMARY")
_s = tables["Sample"]
for _, r in _s[(_s["n"] < 10) & (_s["Variable"] != "Gender")].iterrows():
    warnings_log.append(f"small group kept as is (no merging): {r['Variable']} / {r['Level']} n = {r['n']} - interpret with great caution")
print("\n".join("  - " + w for w in warnings_log) if warnings_log else "  no warnings")
print("\nDone. Saved: results.txt, tables.xlsx, fig_*.png (incl. demographics, item agreement, Section 5, correlation matrix, RQ4 group means), open_text_responses.csv")
