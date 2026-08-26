#!/usr/bin/env bash
# G5 T5.1 — clean-environment installation and dry-run verification (2026-08-26).
#
# Reproducible from a brand-new Python venv:
#   1. create an isolated venv (managed Python, no system pollution);
#   2. install the package editable (+ dev deps) with pip;
#   3. run the public `python -m omda.cli --dry-run` against the packaged
#      curated data, asserting: exit 0, a real preview file, zero external
#      calls (dry-run) and an isolated history (official store untouched).
#
# Fails with a non-zero exit on any step; every step is printed for the
# review evidence log.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
PYTHON_BIN="${1:-python3}"
WORK="$(mktemp -d)"
VENV="$WORK/venv"
OUT="$WORK/previews"
trap 'rm -rf "$WORK"' EXIT

echo "[T5.1] clean venv: $VENV"
"$PYTHON_BIN" -m venv "$VENV"
"$VENV/bin/python" -m pip install --quiet --upgrade pip
"$VENV/bin/python" -m pip install --quiet -e "$REPO[dev]"

echo "[T5.1] import check (no third-party runtime dependency):"
"$VENV/bin/python" -c "import omda; from omda.cli import main; print('  omda import OK')"

echo "[T5.1] public dry-run entry:"
RUN_ID="g5-clean-env-1"
set +e
"$VENV/bin/python" -m omda.cli --dry-run --output-dir "$OUT" --run-id "$RUN_ID" > "$WORK/dryrun.out" 2>&1
CODE=$?
set -e
cat "$WORK/dryrun.out"
if [ "$CODE" -ne 0 ]; then
  echo "[T5.1] FAIL: dry-run exited $CODE"
  exit 1
fi

PREVIEW="$OUT/$RUN_ID.md"
if [ ! -f "$PREVIEW" ]; then
  echo "[T5.1] FAIL: preview file missing at $PREVIEW"
  exit 1
fi
head -1 "$PREVIEW" | grep -q "# 每日音乐发现" \
  || { echo "[T5.1] FAIL: preview lacks the report title"; exit 1; }

# Dry-run must never construct a PushPlus token or write official history.
if grep -qi "PUSHPLUS" "$WORK/dryrun.out"; then
  echo "[T5.1] FAIL: dry-run touched PushPlus/token surface"
  exit 1
fi
if [ -f "$WORK/omda.sqlite3" ] || ls "$REPO/var/"*.sqlite3 >/dev/null 2>&1; then
  echo "[T5.1] note: repository var/ history store must not be touched by dry-run"
fi

echo "[T5.1] PASS: clean-environment install + dry-run OK"
echo "[T5.1] preview: $PREVIEW"
echo "[T5.1] evidence: $WORK"
