# Data

`responses_anonymised.csv` is the survey export used for all results in the thesis, in anonymised form:

- the timestamp column was removed (no names, e-mail addresses or IP addresses were ever collected);
- two open-text answers (Q5.3) that described a respondent's personal medical history were replaced by "[removed before publication: personal health details]"; the other answers are unchanged;
- all closed answers are as exported (one row per respondent, 104 rows including the one respondent who did not give consent; the script removes that row).

Please note that a few categories are very small (for example one respondent aged 60 or above), so that the combination of age group, gender and education may be distinctive in a small circle of acquaintances. Do not try to identify individual respondents.

Column order: consent item, then the 31 questions Q1.1 to Q5.3 in the order of the questionnaire (see `questionnaire/`).

To use another export, save it here as `responses.csv` (ignored by Git) and pass it with `--data`.
