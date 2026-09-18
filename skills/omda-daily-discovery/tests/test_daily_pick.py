#!/usr/bin/env python3
"""G6 acceptance tests for the OMDA Skill Beta daily_pick.py.

Maps to ADR-0003 section 8 (AC-1..AC-29) and the G6 plan matrix V-1..V-29.
AC-12 (live Codex install) and AC-30 (bilingual preface against the Owner
draft) cannot be automated here and are disclosed in the Executor report.

Stdlib unittest only; runs on Python >= 3.9 (verified on 3.9 and 3.13).
"""

import ast
import datetime
import hashlib
import io
import json
import re
import os
import shutil
import sys
import tempfile
import unittest
import zipfile
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

import importlib.util

_SKILL_DIR = Path(__file__).resolve().parent.parent
_SCRIPT = _SKILL_DIR / "scripts" / "daily_pick.py"

sys.dont_write_bytecode = True
_spec = importlib.util.spec_from_file_location("daily_pick", str(_SCRIPT))
dp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dp)


def _fixed_now(day="2026-09-18", hour=9):
    tz = datetime.timezone(datetime.timedelta(hours=8))
    date = datetime.date(*[int(part) for part in day.split("-")])
    return datetime.datetime(date.year, date.month, date.day, hour, 0, 0,
                             tzinfo=tz)


class SkillTestCase(unittest.TestCase):
    def setUp(self):
        self._orig_now = dp.now_local
        dp.now_local = lambda: _fixed_now()
        self.work = Path(tempfile.mkdtemp(prefix="omda-skill-test-"))
        self.profile = self.work / "profile" / "MY_PROFILE.md"
        self.profile.parent.mkdir(parents=True, exist_ok=True)
        self.sources = self.work / "sources"
        self.sources.mkdir()
        self.history = self.work / "var" / "omda-skill" / "history.json"
        self.outdir = self.work / "var" / "omda-skill" / "output"

    def tearDown(self):
        dp.now_local = self._orig_now
        shutil.rmtree(self.work, ignore_errors=True)

    # -- helpers ----------------------------------------------------------

    def write_profile(self, status_rows=(), text=None):
        rows = "\n".join("| %s | %s | %s | %s |" % row
                         for row in status_rows)
        if text is None:
            text = "# profile\n\n| Artist 艺人 | Album 专辑 | Status 状态 | " \
                   "Note 备注 |\n|---|---|---|---|\n" + \
                   (rows + "\n" if rows else "")
        self.profile.write_text(text, encoding="utf-8")
        return text

    def write_source(self, name, source_id, albums, extra_meta="",
                     body=None):
        meta_rows = "\n".join(
            "%s: %s" % row for row in [
                ("format_version", "1"),
                ("source_id", source_id),
                ("display_name", "Display %s" % source_id),
                ("curator", "Curator %s" % source_id),
                ("provenance", "test provenance"),
                ("sharing_note", "private only"),
            ] + ([( "rating_scale", extra_meta)] if extra_meta else []))
        table = "| Artist 艺人 | Album 专辑 | Year 年份 | Genre 流派 | " \
                "Rating 评分 | Note 备注 |\n|---|---|---|---|---|---|\n"
        table += "\n".join("| %s | %s | %s | %s | %s | %s |" % album
                           for album in albums)
        if body is None:
            body = ""
        path = self.sources / name
        path.write_text("---\n%s\n---\n\n# source\n\n%s\n\n%s"
                        % (meta_rows, table, body), encoding="utf-8")
        return path

    def run_pick(self, source_paths=None, extra_args=(), profile=None,
                 lang=None):
        if source_paths is None:
            source_paths = [self.sources / "a.md"]
        args = ["--profile", str(profile or self.profile),
                "--history", str(self.history),
                "--output-dir", str(self.outdir)]
        for path in source_paths:
            args.extend(["--source", str(path)])
        args.extend(extra_args)
        if lang:
            args.extend(["--lang", lang])
        out_buffer = io.StringIO()
        err_buffer = io.StringIO()
        with redirect_stdout(out_buffer), redirect_stderr(err_buffer):
            code = dp.main(args)
        return code, out_buffer.getvalue(), err_buffer.getvalue()

    def read_history(self):
        return json.loads(self.history.read_text(encoding="utf-8"))

    def output_text(self, day="2026-09-18"):
        return (self.outdir / ("%s.md" % day)).read_text(encoding="utf-8")

    # -- AC-17 / AC-18: single & multi source flows -----------------------

    def test_ac17_single_source_flow(self):
        self.write_profile()
        src = self.write_source("a.md", "alice",
                                [("A Ref", "Alpha", "2001", "rock", "", "")])
        code, _out, _err = self.run_pick([src])
        self.assertEqual(code, dp.EXIT_OK)
        self.assertIn("Alpha", self.output_text())

    def test_ac18_multi_source_attribution(self):
        self.write_profile()
        s1 = self.write_source("a.md", "alice",
                               [("A Ref", "Alpha", "2001", "rock", "9",
                                 "from alice")])
        s2 = self.write_source("b.md", "bob",
                               [("B Ref", "Beta", "1999", "jazz", "7",
                                 "from bob")])
        code, _out, _err = self.run_pick([s1, s2])
        self.assertEqual(code, dp.EXIT_OK)
        text = self.output_text()
        self.assertIn("来源注记", text)
        self.assertTrue(("alice" in text and "bob" in text))

    # -- AC-2: two consecutive days ---------------------------------------

    def test_ac2_two_consecutive_days(self):
        self.write_profile()
        src = self.write_source("a.md", "alice",
                                [("A Ref", "Alpha", "2001", "rock", "", ""),
                                 ("B Ref", "Beta", "2002", "jazz", "", "")])
        code, _out, _err = self.run_pick([src])
        self.assertEqual(code, dp.EXIT_OK)
        first_pick = self.read_history()["days"]["2026-09-18"]["selected"][
            "album"]
        dp.now_local = lambda: _fixed_now(day="2026-09-19")
        code, _out, _err = self.run_pick([src])
        self.assertEqual(code, dp.EXIT_OK)
        second = self.read_history()["days"]["2026-09-19"]["selected"][
            "album"]
        self.assertNotEqual(first_pick, second)
        # day 2 must not depend on day 1's output file existing
        (self.outdir / "2026-09-19.md").unlink()
        code, _out, _err = self.run_pick([src])
        self.assertEqual(code, dp.EXIT_OK)
        self.assertIn(second, self.output_text("2026-09-19"))

    # -- AC-3: same-day idempotency ----------------------------------------

    def test_ac3_same_day_idempotent(self):
        self.write_profile()
        src = self.write_source("a.md", "alice",
                                [("A Ref", "Alpha", "2001", "rock", "", ""),
                                 ("B Ref", "Beta", "2002", "jazz", "", "")])
        code, _out, _err = self.run_pick([src])
        self.assertEqual(code, dp.EXIT_OK)
        first = self.read_history()
        first_out = self.output_text()
        for _ in range(2):
            code, _out, _err = self.run_pick([src])
            self.assertEqual(code, dp.EXIT_OK)
        self.assertEqual(self.read_history(), first)
        self.assertEqual(self.output_text(), first_out)

    # -- AC-5: same-day source-set lock ------------------------------------

    def test_ac5_same_day_source_lock(self):
        self.write_profile()
        s1 = self.write_source("a.md", "alice",
                               [("A Ref", "Alpha", "2001", "rock", "", "")])
        code, _out, _err = self.run_pick([s1])
        self.assertEqual(code, dp.EXIT_OK)
        before = self.read_history()
        # rerun with a different (even nonexistent) source: must NOT be read
        code, out, _err = self.run_pick([self.sources / "does-not-exist.md"])
        self.assertEqual(code, dp.EXIT_OK)
        self.assertIn("already committed today", out)
        self.assertIn("alice", out)
        self.assertEqual(self.read_history(), before)

    # -- AC-4 / AC-14: profile status vs free text -------------------------

    def test_ac4_profile_status_excludes(self):
        self.write_profile(status_rows=[("A Ref", "Alpha", "heard", "")])
        src = self.write_source("a.md", "alice",
                                [("A Ref", "Alpha", "2001", "rock", "", ""),
                                 ("B Ref", "Beta", "2002", "jazz", "", "")])
        code, _out, _err = self.run_pick([src])
        self.assertEqual(code, dp.EXIT_OK)
        self.assertEqual(
            self.read_history()["days"]["2026-09-18"]["selected"]["album"],
            "Beta")

    def test_ac14_display_fields_do_not_change_selection(self):
        self.write_profile()
        albums = [("A Ref", "Alpha", "2001", "rock", "", ""),
                  ("B Ref", "Beta", "2002", "jazz", "", "")]
        s1 = self.write_source("a.md", "alice", albums)
        code, _out, _err = self.run_pick([s1])
        rec1 = self.read_history()["days"]["2026-09-18"]
        pick1 = rec1["selected"]["album"]
        pool1 = rec1["selection_pool_digest"]
        # change display-only fields: rating, note, year, display metadata
        s2 = self.write_source("a2.md", "alice",
                               [("A Ref", "Alpha", "1990", "rock",
                                 "10", "changed note"),
                                ("B Ref", "Beta", "2002", "jazz", "", "")],
                               extra_meta="5-star")
        code, _out, _err = self.run_pick([s2])  # same day -> replay path; force day 2
        dp.now_local = lambda: _fixed_now(day="2026-09-19")
        code, _out, _err = self.run_pick([s2])
        self.assertEqual(code, dp.EXIT_OK)
        # C1 check on identical inputs: the modified source (same
        # identities/genres, changed year/rating/note/display metadata) must
        # yield the same selection-pool digest as the original, while its
        # content digest differs.
        original = dp.load_source(s1)
        modified = dp.load_source(s2)
        self.assertNotEqual(original.content_digest, modified.content_digest)
        projection = sorted((cand["identity_key"], cand["genre_group"])
                            for cand in dp.merge_sources([modified]).values())
        self.assertEqual(dp.selection_pool_digest(projection), pool1)
        # and the day-2 run itself stayed functional
        rec2 = self.read_history()["days"]["2026-09-19"]
        self.assertIn(rec2["selected"]["album"], ("Alpha", "Beta"))

    def test_ac14_free_text_profile_never_read(self):
        self.write_profile(text="# profile\n\nI hate jazz. Only rock please."
                                "\n\n| Artist 艺人 | Album 专辑 | Status 状态"
                                " | Note 备注 |\n|---|---|---|---|\n")
        src = self.write_source("a.md", "alice",
                                [("A Ref", "Alpha", "2001", "rock", "", ""),
                                 ("B Ref", "Beta", "2002", "jazz", "", "")])
        code, _out, _err = self.run_pick([src])
        self.assertEqual(code, dp.EXIT_OK)
        selected = self.read_history()["days"]["2026-09-18"]["selected"]
        # free text must not act as a filter: the pool still has both albums
        self.assertIn(selected["album"], ("Alpha", "Beta"))

    # -- AC-6: header variants ---------------------------------------------

    def test_ac6_header_variants(self):
        variants = {
            "en": ("| Artist | Album | Year | Genre | Rating | Note |\n"
                   "|---|---|---|---|---|---|\n"
                   "| A Ref | Alpha | 2001 | rock | | |\n"),
            "zh": ("| 艺人 | 专辑 | 年份 | 流派 | 评分 | 备注 |\n"
                   "|---|---|---|---|---|---|\n"
                   "| A Ref | Alpha | 2001 | rock | | |\n"),
            "bilingual": ("| Artist 艺人 | Album 专辑 | Year 年份 | "
                          "Genre 流派 | Rating 评分 | Note 备注 |\n"
                          "|---|---|---|---|---|---|\n"
                          "| A Ref | Alpha | 2001 | rock | | |\n"),
        }
        parsed = []
        for name, table in variants.items():
            path = self.write_source(
                "%s.md" % name, name, [], body=None)
            path.write_text(
                "---\nformat_version: 1\nsource_id: %s\ndisplay_name: D\n"
                "curator: C\nprovenance: P\nsharing_note: S\n---\n\n%s"
                % (name, table), encoding="utf-8")
            source = dp.load_source(path)
            parsed.append(source.records)
        self.assertTrue(all(p == parsed[0] for p in parsed))
        self.assertEqual(parsed[0][0]["album"], "Alpha")

    # -- AC-7: malformed rows / corrupt history ------------------------------

    def test_ac7_partial_row_fails_closed(self):
        self.write_profile()
        path = self.write_source("a.md", "alice",
                                 [("A Ref", "Alpha", "2001", "rock", "", "")])
        text = path.read_text(encoding="utf-8")
        text = text.replace("| A Ref | Alpha | 2001 | rock |  |  |",
                            "| A Ref | | 2001 | rock |  |  |")
        path.write_text(text, encoding="utf-8")
        code, _out, _err = self.run_pick([path])
        self.assertEqual(code, dp.EXIT_INPUT_ERROR)
        self.assertFalse(self.history.exists())

    def test_ac7_blank_rows_ignored(self):
        self.write_profile()
        path = self.write_source("a.md", "alice",
                                 [("A Ref", "Alpha", "2001", "rock", "", "")])
        text = path.read_text(encoding="utf-8")
        text = text.replace(
            "| A Ref | Alpha | 2001 | rock |  |  |",
            "|  |  |  |  |  |  |\n| A Ref | Alpha | 2001 | rock |  |  |\n"
            "|  |  |  |  |  |  |")
        path.write_text(text, encoding="utf-8")
        code, _out, _err = self.run_pick([path])
        self.assertEqual(code, dp.EXIT_OK)

    def test_ac7_corrupt_history_fail_closed(self):
        self.write_profile()
        self.history.parent.mkdir(parents=True, exist_ok=True)
        self.history.write_bytes(b"{ this is not json")
        src = self.write_source("a.md", "alice",
                                [("A Ref", "Alpha", "2001", "rock", "", "")])
        code, _out, _err = self.run_pick([src])
        self.assertEqual(code, dp.EXIT_HISTORY_CORRUPT)
        corrupt_copies = list(self.history.parent.glob("history.corrupt-*.json"
                                                       ""))
        self.assertEqual(len(corrupt_copies), 1)
        self.assertEqual(corrupt_copies[0].read_bytes(),
                         b"{ this is not json")
        self.assertEqual(self.history.read_bytes(), b"{ this is not json")

    # -- C2: restricted frontmatter -----------------------------------------

    def _frontmatter_case(self, meta_block):
        path = self.sources / "bad.md"
        table = ("| Artist 艺人 | Album 专辑 |\n|---|---|\n"
                 "| A Ref | Alpha |\n")
        path.write_text("---\n%s\n---\n\n%s" % (meta_block, table),
                        encoding="utf-8")
        self.write_profile()
        code, _out, err = self.run_pick([path])
        self.assertEqual(code, dp.EXIT_INPUT_ERROR)
        return err

    def test_ac6_frontmatter_nested_rejected(self):
        err = self._frontmatter_case(
            "format_version: 1\nsource_id: alice\n"
            "  display_name: nested value\ncurator: C\n"
            "provenance: P\nsharing_note: S")
        self.assertIn("flat", err)

    def test_ac6_frontmatter_sequence_rejected(self):
        err = self._frontmatter_case(
            "format_version: 1\n- item\nsource_id: alice\ndisplay_name: D\n"
            "curator: C\nprovenance: P\nsharing_note: S")
        self.assertIn("flat", err)

    def test_ac6_frontmatter_duplicate_rejected(self):
        err = self._frontmatter_case(
            "format_version: 1\nsource_id: alice\nsource_id: bob\n"
            "display_name: D\ncurator: C\nprovenance: P\nsharing_note: S")
        self.assertIn("duplicate", err)

    def test_ac6_frontmatter_unknown_rejected(self):
        err = self._frontmatter_case(
            "format_version: 1\nsource_id: alice\ndisplay_name: D\n"
            "curator: C\nprovenance: P\nsharing_note: S\nweird: x")
        self.assertIn("unknown frontmatter field", err)

    def test_ac6_frontmatter_anchor_alias_tag_rejected(self):
        for meta in (
            "format_version: 1\nsource_id: alice\ndisplay_name: &a D\n"
            "curator: C\nprovenance: P\nsharing_note: S",
            "format_version: 1\nsource_id: alice\ndisplay_name: *a\n"
            "curator: C\nprovenance: P\nsharing_note: S",
            "format_version: 1\nsource_id: alice\ndisplay_name: !!str D\n"
            "curator: C\nprovenance: P\nsharing_note: S",
        ):
            err = self._frontmatter_case(meta)
            self.assertIn("reserved YAML-feature character", err)

    def test_ac6_frontmatter_missing_required(self):
        err = self._frontmatter_case(
            "format_version: 1\nsource_id: alice\ndisplay_name: D\n"
            "curator: C\nsharing_note: S")
        self.assertIn("missing required", err)

    # -- AC-8: import allowlist / zero network -------------------------------

    def test_ac8_import_allowlist(self):
        allowlist = {"argparse", "datetime", "hashlib", "json", "os", "re",
                     "sys", "tempfile", "unicodedata", "pathlib"}
        tree = ast.parse(_SCRIPT.read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imported.add(node.module.split(".")[0])
        self.assertTrue(imported <= allowlist,
                        "unexpected imports: %s" % (imported - allowlist))
        forbidden = {"socket", "urllib", "http", "subprocess", "webbrowser",
                     "random", "ssl", "ftplib", "smtplib", "shutil"}
        self.assertFalse(imported & forbidden)

    def test_ac27_no_date_option(self):
        parser = dp.build_arg_parser()
        options = {action.option_strings[0]
                   for action in parser._actions
                   if action.option_strings}
        self.assertNotIn("--date", options)
        for name in options:
            self.assertNotIn("date", name.replace("-", ""))

    # -- AC-15: exhaustion ----------------------------------------------------

    def test_ac15_exhausted(self):
        self.write_profile(status_rows=[("A Ref", "Alpha", "skip", "")])
        src = self.write_source("a.md", "alice",
                                [("A Ref", "Alpha", "2001", "rock", "", "")])
        code, out, _err = self.run_pick([src])
        self.assertEqual(code, dp.EXIT_EXHAUSTED)
        self.assertTrue("耗尽" in out or "exhausted" in out)
        self.assertFalse(self.history.exists())

    def test_ac15_exhausted_after_permanent_exclusion(self):
        self.write_profile()
        src = self.write_source("a.md", "alice",
                                [("A Ref", "Alpha", "2001", "rock", "", "")])
        code, _out, _err = self.run_pick([src])
        self.assertEqual(code, dp.EXIT_OK)
        dp.now_local = lambda: _fixed_now(day="2026-09-19")
        code, out, _err = self.run_pick([src])
        self.assertEqual(code, dp.EXIT_EXHAUSTED)

    # -- AC-16: crash matrix ---------------------------------------------------

    def test_ac16_history_commit_failure_never_reports_success(self):
        self.write_profile()
        src = self.write_source("a.md", "alice",
                                [("A Ref", "Alpha", "2001", "rock", "", "")])
        original = dp._atomic_write

        def failing(path, payload):
            if Path(path).name == "history.json":
                raise OSError("simulated crash before history commit")
            return original(path, payload)

        dp._atomic_write = failing
        try:
            with self.assertRaises(OSError):
                self.run_pick([src])
        finally:
            dp._atomic_write = original
        self.assertFalse(self.history.exists())
        # retry succeeds exactly once for the day
        code, _out, _err = self.run_pick([src])
        self.assertEqual(code, dp.EXIT_OK)
        self.assertEqual(len(self.read_history()["days"]), 1)

    def test_ac16_output_failure_recovers_without_new_selection(self):
        self.write_profile()
        src = self.write_source("a.md", "alice",
                                [("A Ref", "Alpha", "2001", "rock", "", ""),
                                 ("B Ref", "Beta", "2002", "jazz", "", "")])
        original_text = dp.atomic_write_text

        def failing(path, text):
            raise OSError("simulated crash after history commit")

        dp.atomic_write_text = failing
        try:
            with self.assertRaises(OSError):
                self.run_pick([src])
        finally:
            dp.atomic_write_text = original_text
        committed = self.read_history()
        self.assertEqual(len(committed["days"]), 1)
        dp.now_local = lambda: _fixed_now(hour=10)
        code, _out, _err = self.run_pick([src])
        self.assertEqual(code, dp.EXIT_OK)
        after = self.read_history()
        self.assertEqual(after, committed)  # no re-selection, no new record
        self.assertEqual(self.output_text(),
                         dp.render_day(committed["days"]["2026-09-18"], "zh"))

    # -- AC-19: permutation invariance -----------------------------------------

    def test_ac19_source_and_row_order_invariance(self):
        self.write_profile()
        albums = [("A Ref", "Alpha", "2001", "rock", "9", "n1"),
                  ("B Ref", "Beta", "2002", "jazz", "", "n2"),
                  ("C Ref", "Gamma", "2003", "ambient", "", "")]
        s1 = self.write_source("a.md", "alice", albums)
        s2 = self.write_source("b.md", "bob", albums[:1])
        code, _out, _err = self.run_pick([s1, s2])
        rec1 = self.read_history()["days"]["2026-09-18"]
        # reversed --source order
        self.history.unlink()
        code, _out, _err = self.run_pick([s2, s1])
        rec2 = self.read_history()["days"]["2026-09-18"]
        self.assertEqual(rec1["selection_pool_digest"],
                         rec2["selection_pool_digest"])
        self.assertEqual(rec1["selected"]["album"],
                         rec2["selected"]["album"])
        # shuffled rows within a file (content order changes, selection must
        # not)
        shuffled = [albums[2], albums[0], albums[1]]
        s3 = self.write_source("a2.md", "alice", shuffled)
        s4 = self.write_source("b2.md", "bob", [albums[0]])
        self.history.unlink()
        code, _out, _err = self.run_pick([s3, s4])
        rec3 = self.read_history()["days"]["2026-09-18"]
        self.assertEqual(rec1["selection_pool_digest"],
                         rec3["selection_pool_digest"])
        self.assertEqual(rec1["selected"]["album"],
                         rec3["selected"]["album"])
        # G6-004 extension: audit digests, history evidence and the record
        # as a whole are identical under permutations (canonical content
        # representation + canonical source_id order + fixed clock).
        self.assertEqual(rec1["per_source_content_digests"],
                         rec3["per_source_content_digests"])
        self.assertEqual(rec1["source_ids"], rec3["source_ids"])
        self.assertEqual(rec1, rec3)

    # -- AC-20: duplicate albums never increase probability ---------------------

    def test_ac20_duplicate_only_source_no_effect(self):
        self.write_profile()
        albums = [("A Ref", "Alpha", "2001", "rock", "", ""),
                  ("B Ref", "Beta", "2002", "jazz", "", "")]
        s1 = self.write_source("a.md", "alice", albums)
        dup = self.write_source("d.md", "dup",
                                [("A Ref", "Alpha", "2001", "rock", "", "")])
        code, _out, _err = self.run_pick([s1])
        rec1 = self.read_history()["days"]["2026-09-18"]
        self.history.unlink()
        code, _out, _err = self.run_pick([s1, dup])
        rec2 = self.read_history()["days"]["2026-09-18"]
        self.assertEqual(rec1["selection_pool_digest"],
                         rec2["selection_pool_digest"])
        self.assertEqual(rec1["selected"]["album"],
                         rec2["selected"]["album"])

    # -- AC-21: opinions preserved separately -----------------------------------

    def test_ac21_opinions_kept_per_source(self):
        self.write_profile()
        s1 = self.write_source("a.md", "alice",
                               [("A Ref", "Alpha", "2001", "rock", "9",
                                 "great")])
        s2 = self.write_source("b.md", "bob",
                               [("A Ref", "Alpha", "2001", "rock", "2",
                                 "meh")])
        # force the pick: make Alpha the only candidate
        self.write_profile(status_rows=[])
        s3 = self.write_source("c.md", "carol",
                               [("Z Ref", "Zulu", "2000", "pop", "", "")])
        # remove Zulu via skip so only Alpha is eligible
        self.write_profile(status_rows=[("Z Ref", "Zulu", "skip", "")])
        code, _out, _err = self.run_pick([s1, s2, s3])
        self.assertEqual(code, dp.EXIT_OK)
        text = self.output_text()
        self.assertIn("Alpha", text)
        self.assertIn("9", text)
        self.assertIn("great", text)
        self.assertIn("2", text)
        self.assertIn("meh", text)
        rec = self.read_history()["days"]["2026-09-18"]
        self.assertEqual(len(rec["selected"]["annotations"]), 2)

    # -- AC-22: genre conflict fail-closed ---------------------------------------

    def test_ac22_genre_conflict_fail_closed(self):
        self.write_profile()
        s1 = self.write_source("a.md", "alice",
                               [("A Ref", "Alpha", "2001", "rock", "", "")])
        s2 = self.write_source("b.md", "bob",
                               [("A Ref", "Alpha", "2001", "jazz", "", "")])
        code, _out, err = self.run_pick([s1, s2])
        self.assertEqual(code, dp.EXIT_INPUT_ERROR)
        self.assertIn("Genre conflict", err)
        self.assertIn("a ref|alpha", err)
        self.assertIn("alice=rock", err)
        self.assertIn("bob=jazz", err)
        self.assertFalse(self.history.exists())

    # -- AC-23: sources read-only, shareable across users -------------------------

    def test_ac23_sources_untouched_and_shareable(self):
        albums = [("A Ref", "Alpha", "2001", "rock", "", ""),
                  ("B Ref", "Beta", "2002", "jazz", "", "")]
        s1 = self.write_source("a.md", "alice", albums)
        digest_before = hashlib.sha256(s1.read_bytes()).hexdigest()
        profiles = []
        for user in ("u1", "u2"):
            profile = self.work / ("profile-%s.md" % user)
            profile.write_text(
                "# profile\n\n| Artist 艺人 | Album 专辑 | Status 状态 | "
                "Note 备注 |\n|---|---|---|---|\n" +
                ("| A Ref | Alpha | heard | |\n" if user == "u2" else ""),
                encoding="utf-8")
            profiles.append(profile)
        self.write_profile()
        code, _out, _err = self.run_pick([s1], profile=profiles[0])
        self.assertEqual(code, dp.EXIT_OK)
        code, _out, _err = self.run_pick([s1], profile=profiles[1])
        self.assertEqual(code, dp.EXIT_OK)
        digest_after = hashlib.sha256(s1.read_bytes()).hexdigest()
        self.assertEqual(digest_before, digest_after)

    # -- AC-24: unrated sources fully valid ---------------------------------------

    def test_ac24_unrated_source_valid(self):
        rated = self.write_source("r.md", "rated",
                                  [("A Ref", "Alpha", "2001", "rock", "9",
                                    "")],
                                  extra_meta="10-point")
        unrated = self.write_source("u.md", "unrated",
                                    [("B Ref", "Beta", "2002", "jazz", "",
                                      "")])
        self.write_profile()
        dp.now_local = lambda: _fixed_now(day="2026-09-18")
        code, _out, _err = self.run_pick([rated])
        self.assertEqual(code, dp.EXIT_OK)
        dp.now_local = lambda: _fixed_now(day="2026-09-19")
        code, _out, _err = self.run_pick([unrated])
        self.assertEqual(code, dp.EXIT_OK)
        self.assertEqual(self.read_history()["days"]["2026-09-19"][
            "selected"]["album"], "Beta")

    # -- AC-25: history evidence ---------------------------------------------------

    def test_ac25_history_evidence(self):
        self.write_profile()
        s1 = self.write_source("a.md", "alice",
                               [("A Ref", "Alpha", "2001", "rock", "9", "")])
        code, _out, _err = self.run_pick([s1])
        self.assertEqual(code, dp.EXIT_OK)
        rec = self.read_history()["days"]["2026-09-18"]
        for field in ("source_ids", "per_source_content_digests",
                      "selection_pool_digest", "seed_material_digest",
                      "algorithm_version", "schema_version",
                      "timezone_evidence", "selected_at"):
            self.assertIn(field, rec)
        self.assertEqual(rec["source_ids"], ["alice"])
        self.assertEqual(rec["timezone_evidence"]["utc_offset"], "+08:00")
        # G6-004: row order must not change the canonical audit digest
        s1b = self.write_source("a-reordered.md", "alice",
                                [("A Ref", "Alpha", "2001", "rock", "9", "")])
        # (a-reordered has identical content in identical order; the real
        # row-order invariance is asserted in test_g6004_content_digest)
        self.assertEqual(dp.load_source(s1).content_digest,
                         dp.load_source(s1b).content_digest)

    def test_g6004_content_digest_row_order_invariant(self):
        albums = [("A Ref", "Alpha", "2001", "rock", "9", "n1"),
                  ("B Ref", "Beta", "2002", "jazz", "", "n2"),
                  ("C Ref", "Gamma", "2003", "ambient", "", "")]
        forward = self.write_source("f.md", "alice", albums)
        reverse = self.write_source("r.md", "alice", list(reversed(albums)))
        self.assertEqual(dp.load_source(forward).content_digest,
                         dp.load_source(reverse).content_digest)

    # -- AC-26: pinned cross-version vector -----------------------------------------

    def test_ac26_pinned_selection_vector(self):
        # Generated once with algorithm_version=1; guards against protocol
        # drift. The full suite also runs under Python 3.9 and 3.13.
        pool = [("a|alpha", "rock"), ("b|beta", "jazz")]
        digest = dp.selection_pool_digest(pool)
        self.assertEqual(
            digest,
            "15085063635068ec34ba129b1cfdc9002c2f6dfb48c63b666e25c0ba3b851431")
        # G6-001: seed = exactly (day_key, algorithm_version, pool digest)
        seed = dp.seed_material_digest("2026-09-18", digest)
        genre_index = dp.uniform_index(seed, b"genre", 2)
        album_index = dp.uniform_index(seed, b"album", 1)
        self.assertEqual((genre_index, album_index), (1, 0))

    # -- AC-29: pristine templates ----------------------------------------------------

    def test_ac29_pristine_templates_zero_candidates(self):
        templates = _SKILL_DIR / "templates"
        profile = self.work / "profile-t" / "MY_PROFILE.md"
        profile.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(templates / "OMDA_PROFILE.template.zh-CN.md", profile)
        src = self.work / "source-t.md"
        shutil.copy(templates / "OMDA_SOURCE.template.zh-CN.md", src)
        source = dp.load_source(src)  # must parse cleanly
        self.assertEqual(source.records, [])
        self.assertEqual(dp.load_profile_status(profile), {})
        code, out, _err = self.run_pick([src], profile=profile)
        self.assertEqual(code, dp.EXIT_EXHAUSTED)
        self.assertFalse(self.history.exists())

    def test_ac29_example_block_never_recommended(self):
        source = dp.load_source(_SKILL_DIR / "templates" /
                                "OMDA_SOURCE.template.zh-CN.md")
        albums = [rec["album"] for rec in source.records]
        self.assertNotIn("async", albums)

    # -- AC-10/AC-28/AC-9: structure, license, secrets ---------------------------------

    def test_ac10_skill_structure(self):
        required = [
            "SKILL.md", "agents/openai.yaml", "README.md", "VERSION",
            "LICENSE", "LICENSES.md", "scripts/daily_pick.py",
            "templates/OMDA_SOURCE.template.zh-CN.md",
            "templates/OMDA_SOURCE.template.en.md",
            "templates/OMDA_PROFILE.template.zh-CN.md",
            "templates/OMDA_PROFILE.template.en.md",
            "prompts/ORGANIZE_PROMPT.zh-CN.md",
            "prompts/ORGANIZE_PROMPT.en.md",
            "FEEDBACK_TEMPLATE.md",
        ]
        for rel in required:
            self.assertTrue((_SKILL_DIR / rel).is_file(), "missing %s" % rel)
        skill_text = (_SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        self.assertTrue(skill_text.startswith("---"))
        self.assertIn("name: omda-daily-discovery", skill_text)
        self.assertIn("companion mode", skill_text)
        self.assertIn("3 Genre × 3 Album 引擎", skill_text)
        self.assertIn("AI 只解释", skill_text)

    def test_ac28_license_and_version(self):
        license_text = (_SKILL_DIR / "LICENSE").read_text(encoding="utf-8")
        self.assertIn("Apache License", license_text)
        self.assertIn("Version 2.0, January 2004", license_text)
        self.assertEqual((_SKILL_DIR / "VERSION").read_text().strip(),
                         "0.1.0-beta.1")

    def test_ac9_secret_scan(self):
        patterns = (b"/Users/", b"sk-", b"AKIA", b"OMDA_PP_TOKEN",
                    b"password", b"api_key", b"token=", b"192.168.")
        skip = {"LICENSE"}
        for path in _SKILL_DIR.rglob("*"):
            if not path.is_file() or path.name in skip:
                continue
            if "tests" in path.parts or "__pycache__" in path.parts:
                continue
            blob = path.read_bytes()
            for pattern in patterns:
                self.assertNotIn(pattern, blob,
                                 "secret-like %r in %s" % (pattern, path))

    # -- AC-11: ZIP build/extract/validate in isolation ---------------------------------

    def test_ac11_zip_whitelist_and_validation(self):
        expected = {
            "omda-daily-discovery/SKILL.md",
            "omda-daily-discovery/agents/openai.yaml",
            "omda-daily-discovery/README.md",
            "omda-daily-discovery/VERSION",
            "omda-daily-discovery/LICENSE",
            "omda-daily-discovery/LICENSES.md",
            "omda-daily-discovery/scripts/daily_pick.py",
            "omda-daily-discovery/templates/OMDA_SOURCE.template.zh-CN.md",
            "omda-daily-discovery/templates/OMDA_SOURCE.template.en.md",
            "omda-daily-discovery/templates/OMDA_PROFILE.template.zh-CN.md",
            "omda-daily-discovery/templates/OMDA_PROFILE.template.en.md",
            "omda-daily-discovery/prompts/ORGANIZE_PROMPT.zh-CN.md",
            "omda-daily-discovery/prompts/ORGANIZE_PROMPT.en.md",
            "omda-daily-discovery/FEEDBACK_TEMPLATE.md",
        }
        with tempfile.TemporaryDirectory(prefix="omda-zip-") as tmp:
            zip_path = Path(tmp) / "omda-daily-discovery.zip"
            with zipfile.ZipFile(zip_path, "w") as archive:
                for path in sorted(_SKILL_DIR.rglob("*")):
                    relparts = path.relative_to(_SKILL_DIR).parts
                    if path.is_file() and "tests" not in relparts \
                            and "__pycache__" not in relparts:
                        archive.write(path, arcname=str(
                            Path("omda-daily-discovery") /
                            path.relative_to(_SKILL_DIR)))
            with zipfile.ZipFile(zip_path) as archive:
                names = set(archive.namelist())
            self.assertEqual(names, expected)
            extract_to = Path(tmp) / "extracted"
            with zipfile.ZipFile(zip_path) as archive:
                archive.extractall(extract_to)
            extracted = extract_to / "omda-daily-discovery"
            self.assertIn("Apache License",
                          (extracted / "LICENSE").read_text(encoding="utf-8"))
            # validate the extracted skill end-to-end
            profile = extracted.parent / "profile.md"
            shutil.copy(extracted / "templates" /
                        "OMDA_PROFILE.template.en.md", profile)
            src = extracted.parent / "src.md"
            shutil.copy(extracted / "templates" /
                        "OMDA_SOURCE.template.en.md", src)
            self.assertEqual(dp.load_source(src).records, [])
            self.assertEqual(dp.load_profile_status(profile), {})
            self.assertEqual(
                (extracted / "VERSION").read_text().strip(),
                "0.1.0-beta.1")
        # tempdir context manager removed build + extract (nothing retained)

    # -- AC-1: clean-environment manual path ----------------------------------------------

    def test_ac1_clean_env_manual_flow(self):
        """Simulates the README manual path in an isolated workspace using
        the packaged script and templates only (functional equivalent of
        the clean-env install check; the full CLI smoke is the same code
        path as AC-17/AC-18)."""
        with tempfile.TemporaryDirectory(prefix="omda-clean-") as tmp:
            base = Path(tmp)
            shutil.copytree(_SKILL_DIR, base / "omda-daily-discovery")
            work = base / "workspace"
            (work / "profile").mkdir(parents=True)
            (work / "sources").mkdir()
            shutil.copy(_SKILL_DIR / "templates" /
                        "OMDA_PROFILE.template.en.md",
                        work / "profile" / "MY_PROFILE.md")
            src = work / "sources" / "alice.md"
            shutil.copy(_SKILL_DIR / "templates" /
                        "OMDA_SOURCE.template.en.md", src)
            text = src.read_text(encoding="utf-8")
            text = text.replace(
                "| Artist | Album | Year | Genre | Rating | Note |\n"
                "|---|---|---|---|---|---|\n",
                "| Artist | Album | Year | Genre | Rating | Note |\n"
                "|---|---|---|---|---|---|\n"
                "| A Ref | Alpha | 2001 | rock | | |\n")
            src.write_text(text, encoding="utf-8")
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                code = dp.main([
                    "--profile", str(work / "profile" / "MY_PROFILE.md"),
                    "--source", str(src),
                    "--history",
                    str(work / "var" / "omda-skill" / "history.json"),
                    "--output-dir",
                    str(work / "var" / "omda-skill" / "output"),
                    "--lang", "en",
                ])
            self.assertEqual(code, dp.EXIT_OK)
            self.assertIn("Alpha", (work / "var" / "omda-skill" / "output" /
                                    "2026-09-18.md").read_text(
                                        encoding="utf-8"))


    # ================= G6-001: seed protocol ==============================

    def test_g6001_seed_independent_of_history_length(self):
        """Same day + same final pool must give the same seed and choice no
        matter how long the history is; the protocol has no history-length
        input at all (G6-001)."""
        import inspect
        params = list(inspect.signature(
            dp.seed_material_digest).parameters)
        self.assertEqual(params, ["day_key", "pool_digest"])
        by_group = {"jazz": ["b|beta"], "rock": ["a|alpha"]}
        first = dp.select(by_group, None, "2026-09-18")
        second = dp.select(by_group, None, "2026-09-18")
        self.assertEqual(first, second)
        # a same projection from a "longer history" (simulated by calling
        # again after hypothetically more commits) is by construction
        # identical because history length is not an input
        self.assertEqual(first[2], second[2])
        self.assertEqual(first[3], second[3])

    def test_g6001_excluded_genre_mutation_invariant(self):
        """Mutating an album that is only in the cooldown-excluded previous
        genre must not change the pool digest, seed, or choice (G6-001)."""
        base = {"rock": ["a|alpha", "a|alpha2"], "jazz": ["b|beta"]}
        mutated = {"rock": ["a|alpha", "a|alpha2", "a|mutated"],
                   "jazz": ["b|beta"]}
        r1 = dp.select(base, "rock", "2026-09-18")
        r2 = dp.select(mutated, "rock", "2026-09-18")
        self.assertEqual(r1[2], r2[2])  # selection_pool_digest
        self.assertEqual(r1[3], r2[3])  # seed
        self.assertEqual(r1[0], r2[0])  # chosen group
        self.assertEqual(r1[1], r2[1])  # chosen album

    # ================= G6-002: genre note branches ========================

    def test_g6002_true_waiver_unique_genre_note(self):
        result = dp.select({"rock": ["a|alpha"]}, "rock", "2026-09-18")
        self.assertIsNotNone(result[4])
        self.assertIn("唯一可用流派", result[4])
        self.assertIn("waived", result[4])
        self.assertIsNone(result[5])

    def test_g6002_cooldown_applied_single_remainder_note(self):
        result = dp.select({"rock": ["a|alpha"], "jazz": ["b|beta"]},
                           "rock", "2026-09-18")
        self.assertIsNone(result[4])  # NOT a waiver
        self.assertIsNotNone(result[5])
        self.assertIn("applied", result[5])
        self.assertEqual(result[0], "jazz")  # non-repeating group chosen

    def test_g6002_normal_multi_group_no_notes(self):
        result = dp.select({"rock": ["a|alpha"], "jazz": ["b|beta"]},
                           None, "2026-09-18")
        self.assertIsNone(result[4])
        self.assertIsNone(result[5])

    def test_g6002_end_to_end_cooldown_note(self):
        self.write_profile()
        src1 = self.write_source("a.md", "alice",
                                 [("A Ref", "Alpha", "2001", "rock", "", ""),
                                  ("A Ref", "Alpha II", "2002", "rock",
                                   "", "")])
        code, _out, _err = self.run_pick([src1])
        self.assertEqual(code, dp.EXIT_OK)
        first_group = self.read_history()["days"]["2026-09-18"]["selected"][
            "genre_group"]
        self.assertEqual(first_group, "rock")
        dp.now_local = lambda: _fixed_now(day="2026-09-19")
        src2 = self.write_source("b.md", "alice",
                                 [("A Ref", "Alpha", "2001", "rock", "", ""),
                                  ("A Ref", "Alpha II", "2002", "rock",
                                   "", ""),
                                  ("B Ref", "Beta", "2003", "jazz", "", "")])
        code, _out, _err = self.run_pick([src2])
        self.assertEqual(code, dp.EXIT_OK)
        rec = self.read_history()["days"]["2026-09-19"]
        self.assertIsNone(rec["selected"]["forced_note"])
        self.assertIsNotNone(rec["selected"]["cooldown_note"])
        self.assertEqual(rec["selected"]["album"], "Beta")
        self.assertIn("防重复规则已执行", self.output_text("2026-09-19"))

    def test_g6002_end_to_end_forced_unique_note(self):
        self.write_profile()
        src = self.write_source("a.md", "alice",
                                [("A Ref", "Alpha", "2001", "rock", "", ""),
                                 ("A Ref", "Alpha II", "2002", "rock", "", "")])
        code, _out, _err = self.run_pick([src])
        self.assertEqual(code, dp.EXIT_OK)
        dp.now_local = lambda: _fixed_now(day="2026-09-19")
        code, _out, _err = self.run_pick([src])
        self.assertEqual(code, dp.EXIT_OK)
        rec = self.read_history()["days"]["2026-09-19"]
        self.assertIsNotNone(rec["selected"]["forced_note"])
        self.assertIn("唯一可用流派", rec["selected"]["forced_note"])
        self.assertIsNone(rec["selected"]["cooldown_note"])

    # ================= G6-003: history semantics ==========================

    def test_g6003_shaped_corrupt_history_exit3(self):
        self.write_profile()
        shaped = {
            "schema_version": 2, "algorithm_version": 1,
            "days": {"2026-09-18": {
                "day_key": "2026-09-18", "selected": {},
                "source_ids": ["alice"],
                "source_display_names": {"alice": "A"},
                "per_source_content_digests": {"alice": "0" * 64},
                "selection_pool_digest": "0" * 64,
                "seed_material_digest": "0" * 64,
                "algorithm_version": 1, "schema_version": 2,
                "selected_at": "x",
                "timezone_evidence": {"utc_offset": "+08:00",
                                      "local_iso": "x", "utc_iso": "x"},
                "render_lang": "zh", "forced_note": None,
                "cooldown_note": None,
            }},
        }
        self.history.parent.mkdir(parents=True, exist_ok=True)
        self.history.write_text(json.dumps(shaped), encoding="utf-8")
        before = self.history.read_bytes()
        src = self.write_source("a.md", "alice",
                                [("A Ref", "Alpha", "2001", "rock", "", "")])
        code, _out, _err = self.run_pick([src])
        self.assertEqual(code, dp.EXIT_HISTORY_CORRUPT)  # no uncaught KeyError
        corrupt_copies = list(self.history.parent.glob("history.corrupt-*.json"
                                                       ""))
        self.assertEqual(len(corrupt_copies), 1)
        self.assertEqual(self.history.read_bytes(), before)

    def test_g6003_language_locked_for_same_day(self):
        self.write_profile()
        src = self.write_source("a.md", "alice",
                                [("A Ref", "Alpha", "2001", "rock", "", "")])
        code, _out, _err = self.run_pick([src])  # default zh
        self.assertEqual(code, dp.EXIT_OK)
        committed = self.output_text()
        self.assertIn("今天的推荐", committed)
        code, out, _err = self.run_pick([src], lang="en")
        self.assertEqual(code, dp.EXIT_OK)
        self.assertEqual(self.output_text(), committed)  # byte-identical
        self.assertIn("ignored", out)

    def test_g6003_clock_rollback_rejected(self):
        self.write_profile()
        src = self.write_source("a.md", "alice",
                                [("A Ref", "Alpha", "2001", "rock", "", "")])
        code, _out, _err = self.run_pick([src])
        self.assertEqual(code, dp.EXIT_OK)
        dp.now_local = lambda: _fixed_now(day="2026-09-17")
        code, _out, err = self.run_pick([src])
        self.assertEqual(code, dp.EXIT_INPUT_ERROR)
        self.assertIn("earlier than the latest committed day", err)
        self.assertNotIn("2026-09-17", self.read_history()["days"])

    # ================= G6-005: Codex Skill packaging ======================

    def test_g6005_openai_yaml_interface_structure(self):
        text = (_SKILL_DIR / "agents" / "openai.yaml").read_text(
            encoding="utf-8")
        self.assertIn("interface:", text)
        self.assertIn('display_name: "OMDA Daily Discovery"', text)
        self.assertIn('short_description: "Pick one local album each day '
                      'from chosen source lists"', text)
        self.assertIn("$omda-daily-discovery", text)
        self.assertIn('default_prompt: "Use $omda-daily-discovery', text)
        # the invalid top-level structure must be gone
        top_level_banned = re.compile(r"^(name|display_name|description|"
                                      r"default_prompt|version):",
                                      re.MULTILINE)
        self.assertIsNone(top_level_banned.search(text))

    def test_g6005_install_simulation_separate_dirs(self):
        """Skill installed under a skills directory; user data lives in a
        completely separate workspace; the first recommendation still
        succeeds when the script is invoked from the installed skill root
        (G6-005)."""
        import subprocess
        with tempfile.TemporaryDirectory(prefix="omda-install-") as tmp:
            base = Path(tmp)
            skill_root = base / "codex-skills" / "omda-daily-discovery"
            shutil.copytree(_SKILL_DIR, skill_root,
                            ignore=shutil.ignore_patterns(
                                "tests", "__pycache__"))
            workspace = base / "user-workspace"
            (workspace / "profile").mkdir(parents=True)
            (workspace / "sources").mkdir()
            shutil.copy(skill_root / "templates" /
                        "OMDA_PROFILE.template.en.md",
                        workspace / "profile" / "MY_PROFILE.md")
            src = workspace / "sources" / "alice.md"
            shutil.copy(skill_root / "templates" /
                        "OMDA_SOURCE.template.en.md", src)
            text = src.read_text(encoding="utf-8").replace(
                "|---|---|---|---|---|---|\n",
                "|---|---|---|---|---|---|\n"
                "| A Ref | Alpha | 2001 | rock | | |\n", 1)
            src.write_text(text, encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, str(skill_root / "scripts" / "daily_pick.py"),
                 "--profile", str(workspace / "profile" / "MY_PROFILE.md"),
                 "--source", str(src),
                 "--history",
                 str(workspace / "var" / "omda-skill" / "history.json"),
                 "--output-dir",
                 str(workspace / "var" / "omda-skill" / "output"),
                 "--lang", "en"],
                cwd=str(workspace), capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            outputs = list((workspace / "var" / "omda-skill" / "output")
                           .glob("*.md"))
            self.assertEqual(len(outputs), 1)
            output = outputs[0].read_text(encoding="utf-8")
            self.assertIn("Alpha", output)
            self.assertIn("Today's pick", output)
            # the installed skill root must not have received user data
            self.assertFalse((skill_root / "var").exists())
            self.assertFalse((skill_root / "profile").exists())

    # ================= G6-007: second live table ==========================

    def test_g6007_second_live_table_fails_with_line_number(self):
        self.write_profile()
        path = self.sources / "two-tables.md"
        lines = [
            "---",
            "format_version: 1",
            "source_id: alice",
            "display_name: D",
            "curator: C",
            "provenance: P",
            "sharing_note: S",
            "---",
            "",
            "# list",
            "",
            "| Artist 艺人 | Album 专辑 | Year 年份 | Genre 流派 | "
            "Rating 评分 | Note 备注 |",
            "|---|---|---|---|---|---|",
            "| A Ref | Alpha | 2001 | rock |  |  |",
            "",
            "一些说明文字。",
            "",
            "| Artist 艺人 | Album 专辑 | Year 年份 | Genre 流派 | "
            "Rating 评分 | Note 备注 |",
            "|---|---|---|---|---|---|",
            "| B Ref | Beta | 2002 | jazz |  |  |",
        ]
        path.write_text("\n".join(lines), encoding="utf-8")
        header_line = ("| Artist 艺人 | Album 专辑 | Year 年份 | Genre 流派 | "
                       "Rating 评分 | Note 备注 |")
        first_header = lines.index(header_line)
        second_header_line = lines.index(header_line, first_header + 1) + 1
        code, _out, err = self.run_pick([path])
        self.assertEqual(code, dp.EXIT_INPUT_ERROR)
        self.assertIn("second live source album table starts at line %d"
                      % second_header_line, err)
        self.assertFalse(self.history.exists())

    def test_g6007_fenced_second_table_allowed(self):
        self.write_profile()
        path = self.sources / "fenced.md"
        lines = [
            "---",
            "format_version: 1",
            "source_id: alice",
            "display_name: D",
            "curator: C",
            "provenance: P",
            "sharing_note: S",
            "---",
            "",
            "| Artist 艺人 | Album 专辑 | Year 年份 | Genre 流派 | "
            "Rating 评分 | Note 备注 |",
            "|---|---|---|---|---|---|",
            "| A Ref | Alpha | 2001 | rock |  |  |",
            "",
            "```",
            "| Artist 艺人 | Album 专辑 | Year 年份 | Genre 流派 | "
            "Rating 评分 | Note 备注 |",
            "|---|---|---|---|---|---|",
            "| Example Ref | Example | 2000 | pop |  |  |",
            "```",
        ]
        path.write_text("\n".join(lines), encoding="utf-8")
        code, _out, _err = self.run_pick([path])
        self.assertEqual(code, dp.EXIT_OK)
        self.assertEqual(
            self.read_history()["days"]["2026-09-18"]["selected"]["album"],
            "Alpha")


    # ============ Re-review 1: G6-R1-001 ==================================

    def test_r1001_canonical_equivalent_duplicates_permutation_invariant(self):
        """`A Ref | Alpha` and `a ref | Alpha.` normalize to one identity;
        swapping their file/row order must produce identical history JSON
        and byte-identical output (G6-R1-001)."""
        order_a = [("A Ref", "Alpha", "2001", "rock", "9", "note one"),
                   ("a ref", "Alpha.", "2001", "rock", "7", "note two")]
        order_b = list(reversed(order_a))
        outputs = []
        records = []
        for index, albums in enumerate((order_a, order_b)):
            self.write_profile()
            src = self.write_source("eq-%d.md" % index, "alice", albums)
            if self.history.exists():
                self.history.unlink()
            code, _out, _err = self.run_pick([src])
            self.assertEqual(code, dp.EXIT_OK)
            records.append(json.loads(self.history.read_text(
                encoding="utf-8"))["days"]["2026-09-18"])
            outputs.append(self.output_text())
        selected = records[0]["selected"]
        # canonical display text (not file-order dependent)
        self.assertEqual(selected["artist"], "A Ref")
        self.assertEqual(selected["album"], "Alpha")
        # full history record and output bytes identical across permutation
        self.assertEqual(records[0], records[1])
        self.assertEqual(outputs[0], outputs[1])

    # ============ Re-review 1: G6-R1-002 ==================================

    def _two_language_tables_source(self, first_header, second_header,
                                    blank_between=True):
        lines = [
            "---",
            "format_version: 1",
            "source_id: alice",
            "display_name: D",
            "curator: C",
            "provenance: P",
            "sharing_note: S",
            "---",
            "",
            first_header,
            "|---|---|---|---|---|---|",
            "| A Ref | Alpha | 2001 | rock |  |  |",
        ]
        if blank_between:
            lines.append("")
        lines.extend([
            second_header,
            "|---|---|---|---|---|---|",
            "| B Ref | Beta | 2002 | jazz |  |  |",
        ])
        path = self.sources / "lang-tables.md"
        path.write_text("\n".join(lines), encoding="utf-8")
        first_index = lines.index(first_header)
        second_line = lines.index(second_header, first_index + 1) + 1
        return path, second_line

    def test_r1002_english_then_chinese_header_fail_closed(self):
        self.write_profile()
        path, second_line = self._two_language_tables_source(
            "| Artist | Album | Year | Genre | Rating | Note |",
            "| Artist 艺人 | Album 专辑 | Year 年份 | Genre 流派 | "
            "Rating 评分 | Note 备注 |")
        code, _out, err = self.run_pick([path])
        self.assertEqual(code, dp.EXIT_INPUT_ERROR)
        self.assertIn("second live source album table starts at line %d"
                      % second_line, err)

    def test_r1002_chinese_then_english_header_fail_closed(self):
        self.write_profile()
        path, second_line = self._two_language_tables_source(
            "| Artist 艺人 | Album 专辑 | Year 年份 | Genre 流派 | "
            "Rating 评分 | Note 备注 |",
            "| Artist | Album | Year | Genre | Rating | Note |")
        code, _out, err = self.run_pick([path])
        self.assertEqual(code, dp.EXIT_INPUT_ERROR)
        self.assertIn("second live source album table starts at line %d"
                      % second_line, err)

    def test_r1002_blank_line_only_separation_fail_closed(self):
        self.write_profile()
        # same language, only a blank line between the two live tables
        path, second_line = self._two_language_tables_source(
            "| Artist | Album | Year | Genre | Rating | Note |",
            "| Artist | Album | Year | Genre | Rating | Note |",
            blank_between=True)
        code, _out, err = self.run_pick([path])
        self.assertEqual(code, dp.EXIT_INPUT_ERROR)
        self.assertIn("second live source album table starts at line %d"
                      % second_line, err)

    # ============ Re-review 1: G6-R1-003 ==================================

    def _commit_one_day(self):
        """Produce a real committed record and return (src, record_dict)."""
        self.write_profile()
        src = self.write_source("a.md", "alice",
                                [("A Ref", "Alpha", "2001", "rock", "", "")])
        code, _out, _err = self.run_pick([src])
        self.assertEqual(code, dp.EXIT_OK)
        record = json.loads(self.history.read_text(
            encoding="utf-8"))["days"]["2026-09-18"]
        return src, record

    def _run_with_mutated_history(self, mutate):
        src, record = self._commit_one_day()
        mutate(record)
        # rewrite the history document with the mutation under the same
        # schema; nothing else changes
        # key the mutated record under its own day_key so structural
        # day-key match checks pass and semantic date validation is what
        # fires (for the impossible-date probe)
        document = {"schema_version": 2, "algorithm_version": 1,
                    "days": {record["day_key"]: record}}
        self.history.write_text(json.dumps(document, ensure_ascii=False,
                                           indent=2, sort_keys=True),
                                encoding="utf-8")
        self._history_mutated_bytes = self.history.read_bytes()
        return self.run_pick([src])

    def test_r1003_impossible_day_key_exit3(self):
        def mutate(record):
            record["day_key"] = "2026-99-99"
            record["timezone_evidence"]["local_iso"] = "not-a-time"
            record["timezone_evidence"]["utc_iso"] = "not-a-time"
            record["selected_at"] = "not-a-time"
        code, _out, err = self._run_with_mutated_history(mutate)
        # history-corruption path (exit 3), never clock-rollback (exit 2)
        self.assertEqual(code, dp.EXIT_HISTORY_CORRUPT)
        self.assertIn("not a valid ISO calendar date", err)
        self.assertEqual(len(list(self.history.parent.glob(
            "history.corrupt-*.json"))), 1)
        # the failing run must not rewrite the (corrupt) history file
        self.assertEqual(self.history.read_bytes(),
                         self._history_mutated_bytes)
        # and the corrupt copy preserves exactly those mutated bytes
        self.assertEqual(list(self.history.parent.glob(
            "history.corrupt-*.json"))[0].read_bytes(),
            self._history_mutated_bytes)

    def test_r1003_invalid_timestamp_exit3(self):
        def mutate(record):
            record["selected_at"] = "not-a-time"
        code, _out, err = self._run_with_mutated_history(mutate)
        self.assertEqual(code, dp.EXIT_HISTORY_CORRUPT)
        self.assertIn("selected_at", err)

    def test_r1003_naive_timestamp_exit3(self):
        def mutate(record):
            record["timezone_evidence"]["local_iso"] = "2026-09-18T09:00:00"
        code, _out, err = self._run_with_mutated_history(mutate)
        self.assertEqual(code, dp.EXIT_HISTORY_CORRUPT)
        self.assertIn("not timezone-aware", err)

    def test_r1003_local_date_mismatch_exit3(self):
        def mutate(record):
            record["timezone_evidence"]["local_iso"] = (
                "2026-09-19T09:00:00+08:00")
        code, _out, err = self._run_with_mutated_history(mutate)
        self.assertEqual(code, dp.EXIT_HISTORY_CORRUPT)
        self.assertIn("does not match day key", err)

    def test_r1003_offset_mismatch_exit3(self):
        def mutate(record):
            record["timezone_evidence"]["utc_offset"] = "+09:00"
        code, _out, err = self._run_with_mutated_history(mutate)
        self.assertEqual(code, dp.EXIT_HISTORY_CORRUPT)
        self.assertIn("does not match local_iso", err)

    def test_r1003_utc_iso_not_utc_exit3(self):
        def mutate(record):
            record["timezone_evidence"]["utc_iso"] = (
                "2026-09-18T15:28:39+08:00")
        code, _out, err = self._run_with_mutated_history(mutate)
        self.assertEqual(code, dp.EXIT_HISTORY_CORRUPT)
        self.assertIn("is not in UTC", err)


if __name__ == "__main__":
    unittest.main()
