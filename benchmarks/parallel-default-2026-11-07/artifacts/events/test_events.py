#!/usr/bin/env python3
"""Tests for events.summarize. Standard library only; run with unittest."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import events


def rec(**kw):
    return json.dumps(kw)


class SummarizeTests(unittest.TestCase):
    def summary(self, lines):
        got = events.summarize(lines)
        self.assertEqual(set(got), {"tools", "invalid"})
        return got

    def test_empty_input(self):
        self.assertEqual(self.summary([]), {"tools": {}, "invalid": 0})

    def test_counts_calls_and_results_per_name(self):
        lines = [
            rec(type="tool_use", name="terminal", tool_call_id="a"),
            rec(type="tool_result", name="terminal", tool_call_id="a"),
            rec(type="tool_use", name="terminal", tool_call_id="b"),
        ]
        self.assertEqual(
            self.summary(lines),
            {"tools": {"terminal": {"calls": 2, "results": 1}}, "invalid": 0},
        )

    def test_unrelated_events_ignored_not_invalid(self):
        lines = [
            rec(type="system", subtype="init", model="gyro"),
            rec(type="text", text="hello"),
            rec(type="result", session_id="s", exit_code=0),
            rec(type="assistant", name="whatever"),
            rec(type="", name="x"),
        ]
        self.assertEqual(self.summary(lines), {"tools": {}, "invalid": 0})

    def test_tool_event_without_type_is_ignored(self):
        # No "type" key at all: unrelated valid object, not invalid.
        self.assertEqual(self.summary([rec(name="terminal")]),
                         {"tools": {}, "invalid": 0})

    def test_invalid_json_counts(self):
        lines = [
            "{not json",
            "",
            "   ",
            "\n",
            "[1, 2, 3]",
            '"just a string"',
            "42",
            "null",
            "true",
            "{}{}",
        ]
        # Every record counts as invalid: blanks/whitespace-only are invalid
        # JSON, and non-object JSON values count toward invalid as well.
        self.assertEqual(self.summary(lines), {"tools": {}, "invalid": 10})

    def test_blank_record_counts_invalid(self):
        # Reproducer from acceptance: summarize(['\n']) must be invalid:1.
        self.assertEqual(self.summary(["\n"]), {"tools": {}, "invalid": 1})
        self.assertEqual(self.summary([""]), {"tools": {}, "invalid": 1})
        self.assertEqual(self.summary(["\r\n"]), {"tools": {}, "invalid": 1})

    def test_whitespace_only_records_count_invalid(self):
        for payload in [" ", "   ", "\t", "\n\n", "  \t \n ", "\f", "\v"]:
            with self.subTest(payload=payload):
                self.assertEqual(self.summary([payload]),
                                 {"tools": {}, "invalid": 1})

    def test_blank_records_mixed_with_tool_events(self):
        lines = [
            "\n",
            rec(type="tool_use", name="t"),
            "   ",
            rec(type="tool_result", name="t"),
            "",
        ]
        self.assertEqual(self.summary(lines),
                         {"tools": {"t": {"calls": 1, "results": 1}},
                          "invalid": 3})

    def test_json_scalars_and_containers_are_invalid(self):
        for payload in ['[]', '123', '"s"', 'null', 'true', 'false', '[{"a":1}]']:
            with self.subTest(payload=payload):
                self.assertEqual(self.summary([payload]),
                                 {"tools": {}, "invalid": 1})

    def test_missing_name_is_empty_string_key(self):
        self.assertEqual(
            self.summary([rec(type="tool_use")]),
            {"tools": {"": {"calls": 1, "results": 0}}, "invalid": 0},
        )

    def test_null_name_is_coherent_key(self):
        self.assertEqual(
            self.summary([rec(type="tool_result", name=None)]),
            {"tools": {"None": {"calls": 0, "results": 1}}, "invalid": 0},
        )

    def test_names_sorted_deterministically(self):
        lines = [
            rec(type="tool_use", name="search_files"),
            rec(type="tool_use", name="terminal"),
            rec(type="tool_use", name="read_file"),
            rec(type="tool_result", name="read_file"),
            rec(type="tool_use", name="Patch"),
            rec(type="tool_result", name="Patch"),
        ]
        got = self.summary(lines)
        self.assertEqual(list(got["tools"]), sorted(got["tools"]))
        self.assertEqual(list(got["tools"]),
                         ["Patch", "read_file", "search_files", "terminal"])
        # read_file has both; Patch has both; search_files calls-only;
        # terminal results-only never appears here -> check zero fills.
        self.assertEqual(got["tools"]["search_files"], {"calls": 1, "results": 0})
        self.assertEqual(got["tools"]["Patch"], {"calls": 1, "results": 1})

    def test_sorting_is_stable_for_non_str_names(self):
        # JSON object keys are always strings, so the emitted mapping is
        # JSON-serializable even when a record smuggles a numeric name.
        got = self.summary([rec(type="tool_use", name=7),
                            rec(type="tool_use", name="7"),
                            rec(type="tool_result", name=7)])
        self.assertEqual(got["tools"]["7"], {"calls": 2, "results": 1})
        json.dumps(got)

    def test_input_is_generator_ok(self):
        def gen():
            yield rec(type="tool_use", name="t")
            yield rec(type="tool_result", name="t")
        self.assertEqual(self.summary(gen()),
                         {"tools": {"t": {"calls": 1, "results": 1}}, "invalid": 0})

    def test_result_without_matching_call_is_counted(self):
        got = self.summary([rec(type="tool_result", name="t")])
        self.assertEqual(got["tools"]["t"], {"calls": 0, "results": 1})

    def test_bytes_lines_accepted(self):
        got = self.summary([b'{"type": "tool_use", "name": "t"}'])
        self.assertEqual(got["tools"], {"t": {"calls": 1, "results": 0}})

    def test_invalid_utf8_bytes_counted_invalid_not_crash(self):
        got = self.summary([b'{"type": "tool_use", "name": "\xff"}'])
        self.assertEqual(got["invalid"], 0)
        self.assertEqual(list(got["tools"]), ["\ufffd"])

    def test_real_evidence_file(self):
        path = Path(__file__).resolve().parent / "slice-1-stdout.jsonl"
        if not path.is_file():
            self.skipTest(f"no captured evidence at {path}")
        with path.open("r", errors="replace") as fh:
            lines = fh.readlines()
        got = self.summary(lines)
        # Structural invariants plus an exact recount, computed independently
        # of the summarizer (raw json parse per line) so the assertion holds
        # regardless of how many events the captured feed contains.
        expected_tools = {}
        expected_invalid = 0
        for text in lines:
            try:
                ev = json.loads(text)
            except json.JSONDecodeError:
                expected_invalid += 1
                continue
            if not isinstance(ev, dict):
                expected_invalid += 1
                continue
            field = {"tool_use": "calls", "tool_result": "results"}.get(
                ev.get("type"))
            if field is None:
                continue
            key = str(ev.get("name", ""))
            entry = expected_tools.setdefault(key, {"calls": 0, "results": 0})
            entry[field] += 1
        self.assertEqual(got["invalid"], expected_invalid)
        self.assertEqual(got["tools"], dict(sorted(expected_tools.items())))
        self.assertEqual(list(got["tools"]), sorted(got["tools"]))
        # The slice-1 feed is expected to carry tool events; assert presence
        # without hard-coding counts that drift when the capture is regenerated.
        self.assertGreater(
            sum(t["calls"] + t["results"] for t in got["tools"].values()), 0)

    def test_deterministic_across_runs_and_input_order(self):
        lines = [
            rec(type="tool_use", name="z"),
            rec(type="tool_result", name="z"),
            rec(type="tool_use", name="a"),
        ]
        self.assertEqual(events.summarize(lines),
                         events.summarize(list(reversed(lines))))
        self.assertEqual(list(self.summary(lines)["tools"]), ["a", "z"])

    def test_returned_counts_are_plain_ints(self):
        got = self.summary([rec(type="tool_use", name="t")] * 3)
        self.assertIs(type(got["tools"]["t"]["calls"]), int)
        self.assertIs(type(got["invalid"]), int)

    def test_output_is_json_serializable(self):
        got = self.summary([rec(type="tool_use", name="t"), "nope"])
        self.assertEqual(json.loads(json.dumps(got)), got)

    def test_no_third_party_imports(self):
        src = Path(events.__file__).read_text()
        for bad in ("import pandas", "import numpy", "import requests",
                    "from collections.abc import"):
            self.assertNotIn(bad, src)

    def test_stdin_cli_path(self):
        here = Path(__file__).resolve().parent
        payload = "\n".join(
            [rec(type="tool_use", name="t"), rec(type="tool_result", name="t"), "{x"]
        )
        proc = subprocess.run(
            [sys.executable, str(here / "events.py")],
            input=payload, capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout),
                         {"tools": {"t": {"calls": 1, "results": 1}}, "invalid": 1})

    def test_cli_file_args(self):
        here = Path(__file__).resolve().parent
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as fh:
            fh.write(rec(type="tool_use", name="t") + "\n")
            name = fh.name
        try:
            proc = subprocess.run(
                [sys.executable, str(here / "events.py"), name],
                capture_output=True, text=True, timeout=60,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(json.loads(proc.stdout)["tools"],
                             {"t": {"calls": 1, "results": 0}})
        finally:
            Path(name).unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
