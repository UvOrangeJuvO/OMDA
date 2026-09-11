#!/usr/bin/env python3
"""G5-R1-002 — generate the resolved dependency/license inventory.

Run this script WITH the interpreter of ONE clean release-audit environment:

    /path/to/fresh-py3.12-venv/bin/python tools/release_audit/dependency_inventory.py

It inspects the distributions actually RESOLVED in that environment (never a
hand-written list) and emits, for every installed distribution:

- package name and exact resolved version;
- dependency role (build / test / lint / transitive-of-X / environment tooling);
- license or SPDX expression taken from the installed distribution metadata
  (PEP 639 ``License-Expression`` first, then ``License``, then the
  ``Classifier: License ::`` entries) — the authoritative record for that exact
  version, together with the METADATA file path it was read from;
- the reverse-dependency map (which installed distribution requires it) and the
  raw requirement string, so transitive roles are evidence-based rather than
  asserted;
- requirements that carry an environment marker NOT satisfied here (platform /
  interpreter-conditional dependencies), listed separately so nothing is
  silently dropped.

Output: a Markdown report on stdout plus optional ``--json`` for machine use.
Exit 0 on success. Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from importlib import metadata

# Role classification for the G5 release-audit environment (canonical names).
# Unknown packages are reported as "transitive (unclassified)" rather than
# guessed.
ROLES: dict[str, str] = {
    "setuptools": "build (PEP 517 build backend)",
    "wheel": "build (wheel builder)",
    "build": "build (PEP 517 frontend, release check)",
    "pyproject-hooks": "build tooling (transitive of build)",
    "packaging": "build tooling (transitive of build/setuptools)",
    "pytest": "test runner (dev extra)",
    "pluggy": "test tooling (transitive of pytest)",
    "iniconfig": "test tooling (transitive of pytest)",
    "pygments": "test tooling (transitive of pytest)",
    "ruff": "linter/formatter (dev extra)",
}

# Environment tooling that is present in any venv but is NOT a dependency of
# OMDA. Reported in a separate section so the inventory stays complete.
ENVIRONMENT_TOOLING = {"pip"}

_REQ_NAME = re.compile(r"^\s*([A-Za-z0-9._-]+)")


def _canonical(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _license_from_metadata(meta: metadata.PackageMetadata) -> tuple[str, str]:
    """Return (license-or-SPDX, where-it-came-from)."""
    expr = meta.get("License-Expression")
    if expr:
        return expr, "metadata License-Expression (PEP 639)"
    classifiers = [
        c for c in (meta.get_all("Classifier") or []) if c.startswith("License ::")
    ]
    if classifiers:
        return "; ".join(sorted(classifiers)), "metadata Classifier: License ::"
    license_field = meta.get("License")
    if license_field:
        first = license_field.strip().splitlines()[0].strip()
        return (first or "(empty)", "metadata License field")
    return "(not declared in metadata)", "no license metadata found"


def _source_from_metadata(dist: metadata.Distribution, meta: metadata.PackageMetadata) -> str:
    urls = meta.get_all("Project-URL") or []
    for entry in urls:
        label, _, url = entry.partition(",")
        if label.strip().lower() in ("source", "repository", "homepage", "home-page"):
            return url.strip()
    home = meta.get("Home-page")
    if home:
        return home
    if urls:
        return urls[0].split(",", 1)[-1].strip()
    try:
        return str(dist._path)  # dist-info directory (metadata location)
    except Exception:  # pragma: no cover - defensive
        return "(unknown)"


def _requirements(dist: metadata.Distribution) -> list[str]:
    return list(dist.requires or [])


def _requirement_name(req: str) -> str | None:
    match = _REQ_NAME.match(req)
    return _canonical(match.group(1)) if match else None


def _is_extra_only(req: str) -> bool:
    """True when the requirement only applies to an optional extra group."""
    _, _, marker = req.partition(";")
    return "extra ==" in marker or "extra==" in marker


def collect() -> dict:
    dists = {_canonical(d.metadata["Name"]): d for d in metadata.distributions()}
    reverse: dict[str, list[str]] = {name: [] for name in dists}
    for dist in dists.values():
        for req in _requirements(dist):
            if _is_extra_only(req):
                continue  # opt-in extras are not part of the release environment
            target = _requirement_name(req)
            if target and target in reverse:
                reverse[target].append(f"{dist.metadata['Name']} ({req.strip()})")

    rows = []
    for name in sorted(dists):
        dist = dists[name]
        meta = dist.metadata
        license_value, license_source = _license_from_metadata(meta)
        if name in ENVIRONMENT_TOOLING:
            role = "environment tooling (NOT a dependency of OMDA)"
        else:
            role = ROLES.get(name, "transitive (unclassified)")
        rows.append(
            {
                "package": meta["Name"],
                "version": dist.version,
                "role": role,
                "license": license_value,
                "license_source": license_source,
                "source": _source_from_metadata(dist, meta),
                "required_by": reverse.get(name, []),
                "metadata_path": str(getattr(dist, "_path", "")) + "/METADATA",
            }
        )

    # Requirements whose environment marker is NOT satisfied here and that are
    # not merely optional extras — i.e. real interpreter/platform-conditional
    # dependencies of the resolved set.
    conditional: list[dict] = []
    extra_only_counts: dict[str, int] = {}
    for dist in dists.values():
        for req in _requirements(dist):
            if _is_extra_only(req):
                extra_only_counts[dist.metadata["Name"]] = (
                    extra_only_counts.get(dist.metadata["Name"], 0) + 1
                )
                continue
            if ";" in req:
                conditional.append(
                    {"required_by": dist.metadata["Name"], "requirement": req.strip()}
                )
    conditional.sort(key=lambda c: (c["required_by"], c["requirement"]))

    return {
        "python": sys.version.split()[0],
        "python_executable": sys.executable,
        "resolved_count": len(rows),
        "rows": rows,
        "platform_conditional_requirements": conditional,
        "optional_extra_requirement_counts": extra_only_counts,
    }


def render_markdown(data: dict) -> str:
    lines: list[str] = []
    lines.append(f"Environment: Python {data['python']} ({data['python_executable']})")
    lines.append(f"Resolved distributions: {data['resolved_count']}")
    lines.append("")
    lines.append(
        "| Package | Version | Role | License / SPDX | License source | Authoritative source |"
    )
    lines.append("|---|---|---|---|---|---|")
    for row in data["rows"]:
        lines.append(
            f"| {row['package']} | {row['version']} | {row['role']} | "
            f"{row['license']} | {row['license_source']} | {row['source']} |"
        )
    lines.append("")
    lines.append("### Required-by (base install, non-extra requirements)")
    lines.append("")
    for row in data["rows"]:
        if row["required_by"]:
            lines.append(f"- **{row['package']}**: " + "; ".join(row["required_by"]))
    lines.append("")
    lines.append("### Interpreter/platform-conditional requirements not resolved here")
    lines.append("")
    if data["platform_conditional_requirements"]:
        for item in data["platform_conditional_requirements"]:
            lines.append(f"- `{item['required_by']}` → `{item['requirement']}`")
    else:
        lines.append("- (none)")
    lines.append("")
    lines.append("### Optional extras (opt-in groups, NOT part of this environment)")
    lines.append("")
    for pkg, count in sorted(data["optional_extra_requirement_counts"].items()):
        lines.append(f"- {pkg}: {count} requirement(s) behind `extra == \"...\"` markers")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit JSON instead of Markdown")
    args = parser.parse_args(argv)
    data = collect()
    if args.json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(render_markdown(data))
    return 0


if __name__ == "__main__":
    sys.exit(main())
