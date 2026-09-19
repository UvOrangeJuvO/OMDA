# G6 Owner Content Integration Report

## Scope

Owner confirmed the complete bilingual README and requested that the supplied
`一天一专辑.xlsx` be included as a small personal source bundled with OMDA Skill Beta.
This checkpoint changes documentation, curated source data, package metadata and tests only;
the deterministic selector and the accepted 3×3 Core are unchanged.

## Source conversion

- Input workbook: Owner-supplied `一天一专辑.xlsx` (not included in the package)
- Worksheet: `Sheet1`; no formulas
- Imported records: **205**
- Required-field audit: 0 missing Artist, 0 missing Album
- Duplicate normalized Artist+Album identities: 0
- Markdown-breaking pipe/newline values: 0
- Transformation: trim outer whitespace, collapse embedded line whitespace, normalize Unicode
  to NFC and preserve the original row order
- No Year, Genre or Rating was invented; all three fields remain blank
- The original list number is preserved in each Note field

Output:
`skills/omda-daily-discovery/assets/sources/OMDA_ONE_ALBUM_A_DAY.md`

The bundled source is optional and read-only. README and SKILL explicitly require a user choice
before it is passed as `--source`; it is never silently mixed into another user's selected set.

## Owner preface confirmation

Owner supplied the final Chinese “为什么我想做 OMDA” text, reviewed the complete README and
confirmed that the version is acceptable. Reviewer checked the corresponding English paragraphs.
`reviews/stage-06/PREFACE_CHECKLIST.md` is therefore closed as **AC-30 PASS**.

## Verification

- Python 3.9.6: **66/66 passed**, 0 failed, 0 skipped
- Python 3.12.14: **66/66 passed**, 0 failed, 0 skipped
- Package whitelist: exact match, now **15 files**; extracted bundled source parses to 205 records
- Independent real CLI run with the bundled source: exit 0, one committed daily output
- `git diff --check`: clean
- Source workbook was read only and remains outside the Git repository

## Status

**G6 / READY_FOR_REVIEW**

No merge, tag, push, public package build or publication was performed.
