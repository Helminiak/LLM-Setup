#!/usr/bin/env python3
"""Acceptance tests for redact.redact(). Run: python3 test_redact.py"""

import copy
import json
import unittest

from redact import redact


class TestRedact(unittest.TestCase):
    def test_sensitive_keys_case_insensitive(self):
        for key in ("api_key", "API_KEY", "Api_Key", "authorization",
                    "Authorization", "AUTHORIZATION", "password", "PASSWORD",
                    "token", "TOKEN", "secret", "Secret"):
            with self.subTest(key=key):
                self.assertEqual(redact({key: "hunter2"}), {key: "[REDACTED]"})

    def test_sensitive_key_redacts_any_value_type(self):
        for value in (123, 4.5, True, None, ["a", {"b": 1}], {"nested": [1]}):
            with self.subTest(value=value):
                self.assertEqual(redact({"Secret": value}), {"Secret": "[REDACTED]"})

    def test_keys_not_redacted_unless_exact_sensitive(self):
        for key in ("my_token_count", "secretive", "tokens", "api_key_meta",
                    "password2", "auth", "bearer"):
            with self.subTest(key=key):
                self.assertEqual(redact({key: "keepme"}), {key: "keepme"})

    def test_non_string_keys(self):
        self.assertEqual(redact({1: "keep", (2, 3): "keep", True: "keep"}),
                         {1: "keep", (2, 3): "keep", True: "keep"})

    def test_bearer_in_strings(self):
        # Each match of case-insensitive "Bearer" (as a standalone word) +
        # whitespace + a maximal non-whitespace credential becomes exactly
        # "Bearer [REDACTED]"; adjacent unmatched text is untouched. Neither
        # the original casing nor the original whitespace survives.
        cases = [
            ("Authorization: bearer   ***", "Authorization: Bearer [REDACTED]"),
            ("Authorization: bearer   *** def", "Authorization: Bearer [REDACTED] def"),
            ("BEARER\txyz", "Bearer [REDACTED]"),
            ("Bearer abc123", "Bearer [REDACTED]"),
            ("Bearer\n\r  q w", "Bearer [REDACTED] w"),
            ("aBearer bBearer c", "aBearer [REDACTED] c"),
            ("bearerxyz123", "bearerxyz123"),
            ("Bearer", "Bearer"),
            ("Bearer ", "Bearer "),
            ("Bearer\tBearer two", "Bearer [REDACTED] two"),
            ("Bearer  aaa \nBearer\tbbb", "Bearer [REDACTED] \nBearer [REDACTED]"),
            ("Bearer abc123xyz", "Bearer [REDACTED]"),
            ("nothing sensitive here", "nothing sensitive here"),
            ("", ""),
        ]
        for src, want in cases:
            with self.subTest(src=src):
                self.assertEqual(redact(src), want)

    def test_recursive(self):
        value = {
            "api_key": "SECRET",
            "meta": ["Bearer tok", {"token": {"x": 1}, "keep": "plain text"}],
            "count": 3,
            "flag": False,
            "nothing": None,
        }
        want = {
            "api_key": "[REDACTED]",
            "meta": ["Bearer [REDACTED]", {"token": "[REDACTED]", "keep": "plain text"}],
            "count": 3,
            "flag": False,
            "nothing": None,
        }
        self.assertEqual(redact(value), want)

    def test_no_mutation_and_deep_copy(self):
        original = {
            "api_key": "SECRET",
            "headers": {"Authorization": "Bearer abc"},
            "list": ["Bearer xyz", {"secret": 99}],
        }
        frozen = copy.deepcopy(original)
        result = redact(original)
        self.assertEqual(original, frozen)
        self.assertNotEqual(result, original)
        self.assertIsNot(result["headers"], original["headers"])
        self.assertIsNot(result["list"], original["list"])

    def test_scalars_preserved(self):
        for value in (None, True, False, 0, 1, -5, 3.25):
            with self.subTest(value=value):
                self.assertIs(redact(value), value)
        self.assertEqual(redact(""), "")

    def test_empty_structures(self):
        self.assertEqual(redact({}), {})
        self.assertEqual(redact([]), [])

    def test_json_roundtrip_output(self):
        value = {"Authorization": "Bearer s3cr3t", "note": "Bearer x and plain"}
        out = redact(value)
        self.assertEqual(out, {"Authorization": "[REDACTED]",
                               "note": "Bearer [REDACTED] and plain"})
        text = json.dumps(out)
        self.assertNotIn("s3cr3t", text)
        self.assertIn("[REDACTED]", text)

    def test_tuple_and_opaque_objects_preserved(self):
        t = ("Bearer abc", 1)
        self.assertIs(redact(t), t)
        self.assertEqual(redact([t]), [t])
        sentinel = object()
        returned = redact({"obj": sentinel})
        self.assertIsInstance(returned, dict)
        self.assertIsNot(returned, {"obj": sentinel})
        self.assertIs(returned["obj"], sentinel)
        self.assertIs(redact(sentinel), sentinel)


if __name__ == "__main__":
    unittest.main()
