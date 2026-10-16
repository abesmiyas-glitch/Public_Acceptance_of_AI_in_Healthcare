# Codebook

## Likert coding
All attitude items use a 5-point scale: 1 = strongly disagree, 2 = disagree, 3 = neither agree nor disagree, 4 = agree, 5 = strongly agree. Text answers such as "4 : Agree" are converted to numbers by the script, which stops if a value outside 1 to 5 appears.

## Reverse-worded items
Q2.3, Q2.6 and Q2.9 are recoded as 6 - x before the composite scores are calculated.

## Composite scores (mean of the items; a composite needs all its items)
| Composite | Items | Used in |
| --- | --- | --- |
| Accuracy | Q2.1, Q2.2, Q2.3 (reversed) | RQ1, RQ2, RQ4 |
| Transparency | Q2.4, Q2.5, Q2.6 (reversed) | RQ1, RQ2, RQ4 |
| Trust | Q2.7, Q2.8, Q2.9 (reversed) | RQ1, RQ2, RQ4 |
| Acceptance (general) | Q2.10, Q2.11 | RQ1, RQ4 |
| Acceptance: physician / nurse / dentist / pharmacist | Q3.1-Q3.2 / Q3.3-Q3.4 / Q3.5-Q3.6 / Q3.7-Q3.8 | RQ3 |
| Provider trust, baseline | Q4.1, Q4.2 | RQ5 |
| Provider trust, after disclosure | Q4.3, Q4.4 | RQ5 |

## Background variables (no categories are merged or excluded)
| Variable | Item | Categories |
| --- | --- | --- |
| Age group | Q1.1 | Under 25; 25-40; 41-59; 60+ |
| Gender | Q1.2 | Male; Female; Prefer not to say |
| Education | Q1.3 | High school or below; Bachelor's degree; Master's degree or above; Other |
| AI tool experience | Q1.4 | Rare/never; Occasional; Regular |
| AI health tool use | Q1.5 | rarely or never; occasionally; regularly |

Small groups (for example age 60+ n = 1, education "Other" n = 1) are analysed as they are; the script lists them in its validation summary and results for them should be interpreted with great caution.

## Section 5 (supplementary, not part of RQ1 to RQ5)
Q5.1 (single item; higher = more agreement that an AI-using provider is less trustworthy, not reverse-scored), Q5.2 (preference, frequencies), Q5.3 (open text, thematic analysis done manually).

## Output files (`results/`)
- `results.txt` - full console output of the script
- `tables.xlsx` - one sheet per table (sample, reliability, RQ1 to RQ5, run information)
- `fig_*.png` - figures
