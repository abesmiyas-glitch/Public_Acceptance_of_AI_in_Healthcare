# thesis-ai-healthcare-acceptance

Supporting materials for the bachelor thesis **"Public Acceptance of AI-Supported Healthcare"** ([Yasmin Seba], IU International University, 2026): the survey instrument, the analysis script and the results behind Chapter 4.

## Abstract

This study examines publics’ acceptance of AI use by healthcare providers as a support tool. A cross-sectional online survey has been completed by 103 participants recruited through convenience sampling. This study contributes evidence on the associations between perceived accuracy, transparency, trust and acceptance of AI-supported healthcare by examining the three perceptions simultaneously in one model. The results revealed strong relationships between both perceived accuracy and perceived trust, and acceptance (β,= .32, and β = .31, respectively) while they couldn’t confirm the same with perceived transparency. Together with transparency, the three perceptions were associated with about a third of the variance in acceptance (R² = .34). The research examines wether acceptance of AI-supported healthcare differs from a healthcare profession to another, it compares acceptance across four healthcare professions and concludes that acceptance tends to be uniform across physicians, nurses, dentists and pharmacists, with a modest difference between acceptance of dentists and physicians. The study provides a description of how trust in healthcare providers differs after disclosure of AI use, which revealed that trust in provider was much lower once the information regarding AI use was disclosed. Additionally, the study investigates how background charachteristics relate to the acceptance of AI-use by healthcare providers by conducting 16 exploratory analysis, where only one remained significant after Holm adjustment : respondents who reported more regular use of AI-based healthcare tools, reported higher trust. The analysis script, the questionnaire and the collected data are all documented in the project Github repository and the study can be reproduced and extended.

The study is a quantitative, cross-sectional online survey (convenience sample, N = 103). It examines how respondents' perceived accuracy, transparency and trust are associated with their acceptance of AI-supported healthcare (RQ1), describes these perceptions (RQ2), compares acceptance across four professions (RQ3), explores background factors (RQ4) and compares reported trust before and after disclosure of AI use (RQ5). Acceptance is measured as acceptance of healthcare professionals using AI-based tools as a support tool. All findings describe what respondents reported and are not generalised to the population.

## Research questions

| | Question |
| --- | --- |
| RQ1 | How do perceived accuracy, transparency and trust relate to individuals’ acceptance of AI-supported healthcare ? |
| RQ2 | How do individuals perceive the use of artificial intelligence in healthcare in terms of accuracy, transparency and trust ? |
| RQ3 | Does acceptance differ from a healthcare profession to another or is it uniform accross the field ? |
| RQ4 | Are respondent’s reported background factors such as age/generation, prior experience with AI tools or educational level associated with perceived accuracy, transparency, trust and acceptance of AI supported healthcare ?  |
| RQ5 | Does respondents’ reported trust in healthcare providers diff fer before and after disclosure of AI use ?|

## Folder overview

```
thesis-ai-healthcare-acceptance/
├── README.md
├── LICENSE
├── CITATION.cff
├── requirements.txt
├── src/
│   └── thesis_analysis.py      # the complete analysis (RQ1 to RQ5)
├── questionnaire/
│   └── README.md               # add the questionnaire here (e.g. questionnaire.pdf)
├── data/
│   ├── responses_anonymised.csv  # the anonymised survey export (N = 104 rows, 103 consented)
│   └── README.md               # what was anonymised
├── results/
│   ├── results.txt             # full output of the script
│   ├── tables.xlsx             
│   ├── open_text_responses*.csv, open_text_themes.csv   # Q5.3 answers, their coding and the themes
│   └── fig_*.png               # 9 figures: profile, distributions, item agreement, diagnostics,
│                               # correlation matrix, professions, group means, disclosure, Section 5
└── docs/
    └── codebook.md             # coding, reverse-scored items, composites, categories

```

## What the script does

| RQ | Analysis |
| --- | --- |
| Reliability | Cronbach's alpha (with 95% CI); inter-item r and Spearman-Brown for two-item scales |
| RQ1 | Pearson correlations; multiple linear regression (OLS) with VIF, Shapiro-Wilk, Breusch-Pagan, Durbin-Watson, Cook's distance and HC3 robust errors |
| RQ2 | Descriptive statistics, histograms and item-level percentages (disagree / neutral / agree) |
| RQ3 | Repeated-measures ANOVA (Mauchly's test, Greenhouse-Geisser if needed), Bonferroni-corrected paired t-tests; Friedman test as a robustness check |
| RQ4 | One-way ANOVA by age, education, Q1.4 and Q1.5 for each outcome (16 tests, Holm-adjusted), exploratory Tukey follow-up (reported with the Holm-adjusted omnibus p); Levene and Welch ANOVA robustness check; extended regression with a supplementary Q1.5 model. No categories are merged |
| RQ5 | Paired t-test (Cohen's dz); Wilcoxon signed-rank as a robustness check |

The script also checks that all 31 columns match the questionnaire wording, lists the consent answers and stops on inconsistencies. Non-parametric tests appear only as labelled robustness checks. Likert items are scored 1 to 5; Q2.3, Q2.6 and Q2.9 are reverse-coded (6 - x); composite scores are item means (see `docs/codebook.md`).

## How to run

1. Install Python 3.10 or later, then the packages:
   ```bash
   pip install -r requirements.txt
   ```
2. The anonymised data are in `data/responses_anonymised.csv` (see `data/README.md`).
3. From the repository root, run:
   ```bash
   python src/thesis_analysis.py --data src/Responses.csv --out results
   ```
   The script prints and saves everything to `results/`. Settings (for example `DROP_STRAIGHTLINERS`) are at the top of `src/thesis_analysis.py`.

The exact package versions used for the thesis are listed in the `Run_info` sheet of `results/tables.xlsx`.

## Data and ethics

Respondents were adults who gave consent; the survey was anonymous and the data were collected for academic purposes only. An anonymised copy of the data is included (`data/responses_anonymised.csv`): the timestamp was removed and two open-text answers containing personal health informations were redacted. No names, contact details or IDs were collected. Data handling followed the principles of the General Data Protection Regulation (GDPR), in particular data minimisation, purpose and storage limitation (Regulation (EU) 2016/679 art.5). 

## Citation

If you use this material, please cite it as given in `CITATION.cff`.

## License

The code is released under the MIT License (see `LICENSE`). The thesis text is not covered by this license.
