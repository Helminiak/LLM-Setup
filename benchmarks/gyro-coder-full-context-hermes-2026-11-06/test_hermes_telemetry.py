import json
import unittest

from hermes_telemetry import analyze_text, digest


def stream(*records):
    return ''.join(json.dumps(record) + '\n' for record in records)


class TelemetryTests(unittest.TestCase):
    def test_real_stream_schema(self):
        data = stream(
            {'type': 'system', 'subtype': 'init', 'model': 'local'},
            {'type': 'text', 'text': 'hello'},
            {'type': 'tool_use', 'name': 'terminal', 'tool_call_id': 'x', 'input': {'command': 'cargo test'}},
            {'type': 'tool_result', 'name': 'terminal', 'tool_call_id': 'x',
             'output': json.dumps({'output': 'running 2 tests\ntest result: ok. 2 passed; 0 failed; 0 ignored', 'exit_code': 0})},
            {'type': 'result', 'exit_code': 0, 'tokens': {'input': 100, 'output': 25, 'total': 125}},
        )
        report = analyze_text(data)
        self.assertEqual(report['tokens']['input'], 100)
        self.assertEqual(report['tokens']['output'], 25)
        self.assertEqual(report['cargo']['first']['test']['tests_passed'], 2)
        self.assertEqual(report['cargo']['first']['test']['tests_failed'], 0)
        self.assertEqual(report['cargo']['final']['exit_code'], 0)
        self.assertEqual(digest(report)['status'], 'complete')

    def test_malformed_and_interrupted(self):
        report = analyze_text(stream({'type': 'system', 'subtype': 'init'}) + '{broken')
        self.assertEqual(report['status'], 'interrupted')
        self.assertEqual(report['malformed_lines'], 1)
        self.assertIsNone(report['tokens']['input'])

    def test_delta_is_not_double_counted(self):
        report = analyze_text(stream(
            {'type': 'text', 'text': 'a', 'tokens': {'output': 1}},
            {'type': 'text', 'text': 'b', 'tokens': {'output': 2}},
            {'type': 'result', 'tokens': {'input': 10, 'output': 2}},
        ))
        self.assertEqual(report['tokens']['output'], 2)
        self.assertEqual(report['tokens']['source'], 'result_record')

    def test_zero_differs_from_unknown(self):
        self.assertEqual(analyze_text(stream({'type': 'result', 'tokens': {'output': 0}}))['tokens']['output'], 0)
        self.assertIsNone(analyze_text(stream({'type': 'result'}))['tokens']['output'])

    def test_external_compiler_log_preserved(self):
        output = 'error[E0308]: mismatched types\n' + 'detail' * 5000
        report = analyze_text('', verifications=[{'command': 'cargo test', 'exit_code': 101, 'output': output}])
        self.assertEqual(report['cargo']['final']['exit_code'], 101)
        self.assertEqual(report['cargo']['final']['test']['error_codes']['error[E0308]'], 1)
        self.assertTrue(report['cargo']['final']['output_truncated'])


if __name__ == '__main__':
    unittest.main()
