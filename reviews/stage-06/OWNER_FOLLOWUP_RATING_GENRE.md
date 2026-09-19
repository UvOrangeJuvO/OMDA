# G6 Owner Follow-up — Ten-point ratings and bundled Genre enrichment

Date: 2026-09-19

Scope: OMDA Skill Beta only

Authorization: the Owner explicitly selected a ten-point scale and asked the
Reviewer to make this small update directly before local packaging.

## Decisions implemented

1. New OMDA-native source lists use `rating_scale: 10-point-integer`.
2. A Rating under that scale is either blank or an integer from 1 through 10.
3. The earlier `10-point` spelling remains a compatible alias.
4. Other explicitly named source scales remain display-only and are not
   silently converted.
5. Ratings and notes still never affect Genre or Album selection.
6. The Owner's bundled 205-album source now uses a broad primary Genre before
   the first comma and optional finer styles after it. The script groups only
   by the broad primary Genre.

## Genre research and curation

- The Artist, Album, Year, Rating and Note cells were compared to the accepted
  source and remain unchanged for all 205 rows.
- MusicBrainz release-group search produced 159 Artist+Album exact matches;
  147 of those carried usable positive tags. MusicBrainz and additional public
  artist/catalog pages were used only as research evidence.
- The bundled output is an original broad human classification, not a copied
  external tag table or database export.
- 202 rows have Genre values. Three entries remain deliberately blank because
  reliable evidence was not found: `一天一专辑 167`, `169`, and `198`.
- Broad-group distribution: Electronic 58; Hip Hop 49; Rock 42; Pop 22;
  Metal 9; Jazz 6; Punk 5; Folk and Country 4; R&B and Soul 4; Soundtrack 3;
  uncategorized 3.
- Genre is subjective. These labels support discovery and may be edited in a
  future Owner-curated revision; they are not an official quality judgment.

## Runtime and privacy boundary

The Skill remains local-only and performs zero network calls. The public-data
research happened only while preparing this bundled source; no lookup code,
API client, credential or external database was added to the package.

## Verification

- Skill creator validation: PASS.
- Python 3.9.6: 69/69 tests passed, 0 failed, 0 skipped.
- Python 3.12.14: 69/69 tests passed, 0 failed, 0 skipped.
- Rating regression coverage: blank/1/10 accepted; 0/11/8.5 rejected; legacy
  metadata spelling accepted.
- Bundled source: 205 records, 202 Genre values, exactly three intentional
  blanks, and the expected 11 broad selection groups including uncategorized.
- Accepted-source comparison: all 205 Artist, Album, Year, Rating and Note
  fields unchanged.
- ZIP whitelist/extract validation: covered by the full test suite.
- `git diff --check`: PASS.

## Process disclosure

This is an Owner-authorized exception to the usual Executor/Reviewer role
split: GPT-5.6 Sol made the narrow maintenance update directly. Therefore the
technical checks are complete, but the Genre judgments are not independent
of their implementation. The Owner may revise any subjective label later.
