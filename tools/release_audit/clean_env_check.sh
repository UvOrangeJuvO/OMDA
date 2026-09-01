#!/usr/bin/env bash
# G5 T5.1 — clean-environment artifact install + dry-run verification (G5-001).
#
# Reproducible release check that installs the BUILT ARTIFACT (not an editable
# checkout), from OUTSIDE the repository:
#   1. build wheel + sdist from the exact candidate (python -m build);
#   2. install the wheel into a brand-new Python 3.12 venv;
#   3. from a directory OUTSIDE the checkout run: import, config validation,
#      and the public `python -m omda.cli --dry-run`;
#   4. record resolved tool/dependency versions.
#
# Fails with a non-zero exit on any step. Run from the repository root:
#     bash tools/release_audit/clean_env_check.sh [python3.12-binary]
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
PYTHON_BIN="${1:-python3.12}"
WORK="$(mktemp -d)"
BUILD_VENV="$WORK/build-venv"
CLEAN_VENV="$WORK/clean-venv"
OUT="$WORK/previews"
DIST="$WORK/dist"
trap 'rm -rf "$WORK"' EXIT

echo "[T5.1] candidate checkout: $REPO"
echo "[T5.1] python: $("$PYTHON_BIN" --version)"

# 1) Build wheel + sdist with an isolated build environment.
"$PYTHON_BIN" -m venv "$BUILD_VENV"
"$BUILD_VENV/bin/python" -m pip install --quiet --upgrade pip build setuptools wheel
(
  cd "$REPO"
  "$BUILD_VENV/bin/python" -m build --outdir "$DIST" . >/dev/null
)
WHEEL="$(ls "$DIST"/*.whl)"
SDIST="$(ls "$DIST"/*.tar.gz)"
echo "[T5.1] built: $WHEEL"
echo "[T5.1] built: $SDIST"

# 2) Install the WHEEL into a brand-new venv (no editable checkout).
"$PYTHON_BIN" -m venv "$CLEAN_VENV"
"$CLEAN_VENV/bin/python" -m pip install --quiet --no-input "$WHEEL"

# 3) Run from OUTSIDE the checkout: import, config, public dry-run.
cd "$WORK"
"$CLEAN_VENV/bin/python" - <<'PY'
import omda
from omda.config import load_config
from omda.production import DEFAULT_DATA_DIR
assert (DEFAULT_DATA_DIR / "schemas" / "config.schema.json").is_file()
assert (DEFAULT_DATA_DIR / "genres" / "demo-omda" / "source.yaml").is_file()
assert (DEFAULT_DATA_DIR / "genres" / "curated-omda" / "genres.jsonl").is_file()
cfg = load_config()
assert cfg.llm.mode == "deterministic", cfg.llm.mode
print("  import + config validation OK (data:", DEFAULT_DATA_DIR, ")")
PY

echo "[T5.1] public dry-run from outside the checkout:"
RUN_ID="g5-clean-env-1"
set +e
"$CLEAN_VENV/bin/python" -m omda.cli --dry-run --output-dir "$OUT" --run-id "$RUN_ID" > "$WORK/dryrun.out" 2>&1
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

# 4) Record resolved tool/dependency versions.
echo "[T5.1] resolved versions:"
"$BUILD_VENV/bin/python" - <<'PY'
import importlib.metadata as m
for pkg in ("setuptools", "wheel", "build", "pip"):
    try:
        print(f"  build-env {pkg}: {m.version(pkg)}")
    except m.PackageNotFoundError:
        print(f"  build-env {pkg}: (not installed)")
PY
"$CLEAN_VENV/bin/python" - <<'PY'
import importlib.metadata as m
print(f"  clean-env omda: {m.version('omda')}")
for pkg in ("pytest", "ruff", "pip"):
    try:
        print(f"  clean-env {pkg}: {m.version(pkg)}")
    except m.PackageNotFoundError:
        print(f"  clean-env {pkg}: (not installed)")
PY

echo "[T5.1] PASS: built-artifact install + outside-checkout dry-run OK"
echo "[T5.1] preview: $PREVIEW"
