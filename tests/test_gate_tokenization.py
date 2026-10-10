"""Gate unit tests: deny real escapes, allow prose that merely names a path.

These run WITHOUT the Hermes runtime (pure string logic), so they are fast and
can be run by the mission cron on every iteration. The harness imports the gate
functions by exec'ing the module header up to the gate definition, because the
full file requires the runtime on PYTHONPATH.

RED/GREEN record:
  RED   - before the tokenizer refactor, `_absolute_path_tokens` did not exist
          and the gate used raw substring matching; test_prose_path_is_not_an_access
          FAILED (a Chinese explanation of cron's spool path was blocked).
  GREEN - after the refactor, all cases pass.
"""
import pathlib
import re
import unittest

HARNESS = pathlib.Path(__file__).with_name('full_schema_delegation_harness.py')


def _load_gate_functions():
    """Extract the pure string helpers from the harness without importing the runtime."""
    src = HARNESS.read_text(encoding='utf-8')
    start = src.index('_QUOTES =')
    end = src.index('def _resolve_inside')
    ns = {'pathlib': pathlib, 'os': __import__('os'), 're': __import__('re')}
    exec(compile(src[start:end], 'gate-helpers', 'exec'), ns)
    return ns


G = _load_gate_functions()
_strip = G['_strip_string_literals']
_abs = G['_absolute_path_tokens']
_lead = G['_leading_identifiers']
_shell = G['_shell_invocation_tokens']
_nested = G['_nested_shell_commands']


class StringLiteralTests(unittest.TestCase):
    def test_literal_contents_blanked_but_offsets_preserved(self):
        code = 'd = {"a": "/etc/crontab"}\nprint(d)'
        stripped = _strip(code)
        self.assertNotIn('/etc/crontab', stripped)
        self.assertEqual(len(stripped), len(code))
        self.assertIn('print', stripped)

    def test_triple_quoted_block_consumed(self):
        code = 'x = """\nrm -rf /\n"""\ny = 1'
        self.assertNotIn('rm -rf', _strip(code))
        self.assertIn('y', _strip(code))

    def test_escaped_quote_does_not_end_literal(self):
        code = 's = "a \\" b /etc/passwd c"\nprint(s)'
        self.assertNotIn('/etc/passwd', _strip(code))


class AbsolutePathTests(unittest.TestCase):
    def test_prose_path_is_not_an_access(self):
        """The exact false positive from the real 17:08 run."""
        code = ('import json\n\nd = {\n "scheme": "cron 是单守护进程、分钟粒度、无作业状态的触发机制：'
                'cron 每分钟醒来一次，比对 crontab（用户 spool /var/spool/cron/crontabs、'
                '/etc/crontab、/etc/cron.d、/etc/cron.{hourly,daily,weekly,monthly}）'
                '中的时间表达式，命中就 fork/e"\n}')
        self.assertEqual(_abs(code), [], 'prose path inside a string literal must not be an access')

    def test_real_code_path_is_an_access(self):
        code = 'p = pathlib.Path("/etc/passwd")\nprint(p.read_text())'
        self.assertIn('/etc/passwd', _abs(code))

    def test_unquoted_argument_path_is_an_access(self):
        self.assertIn('/etc/shadow', _abs('open(/etc/shadow)'))


class EgressTests(unittest.TestCase):
    def test_prose_mentioning_nc_is_not_a_call(self):
        """The exact false positive from the real 17:20 run ('nc ' matched inside prose)."""
        code = ('import json\nout = {\n "scheme": "独立常驻脚本（self-hosted resident daemon）：'
                '由一个自写长驻进程承担采集/调度/执行职责...\n}')
        self.assertNotIn('nc', {t.rsplit('.', 1)[-1] for t in _lead(code)})

    def test_real_curl_call_is_detected(self):
        self.assertIn('curl', {t.rsplit('.', 1)[-1] for t in _lead('import requests\ncurl("/x")')})
        self.assertIn('curl', {t.rsplit('.', 1)[-1] for t in _lead('curl(url)')})

    def test_shell_invocation_detected(self):
        self.assertIn('curl', {t.rsplit('/', 1)[-1] for t in _shell('curl -s http://x | head')})
        self.assertIn('systemctl', {t.rsplit('/', 1)[-1] for t in _shell('/bin/systemctl show x')})

    def test_quoted_binary_name_is_not_an_invocation(self):
        self.assertEqual([t for t in _shell('echo "do not run curl here"') if t == 'curl'], [])

    def test_rsync_is_not_matched_as_sync(self):
        inv = {t.rsplit('/', 1)[-1] for t in _shell('rsync -a /a /b')}
        self.assertIn('rsync', inv)
        self.assertNotIn('sync', inv)


class NestedShellTests(unittest.TestCase):
    def test_nested_terminal_command_extracted(self):
        """The real 17:20 escape attempt: execute_code wrapping terminal("systemctl ...")."""
        code = ('from hermes_tools import terminal\n'
                'r = terminal("systemctl show --no-pager -p DefaultStartLimitIntervalSec '
                '2>&1 | head -5; ls /proc/1/comm && cat /proc/1/comm")\nprint(r["output"])\n')
        nested = _nested(code)
        self.assertEqual(len(nested), 1)
        self.assertIn('systemctl', nested[0])
        self.assertIn('/proc/1/comm', _abs(nested[0]))

    def test_prose_literal_is_not_a_nested_command(self):
        code = 'd = {"note": "run systemctl stop foo"}\nprint(d)'
        self.assertEqual(_nested(code), [])

    def test_method_named_run_is_not_treated_as_helper(self):
        code = 'x = runner.run("systemctl stop")\n'
        self.assertEqual(_nested(code), [], 'runner.run is a method, not the shell helper')

    def test_nested_curl_is_extracted(self):
        self.assertIn('curl', _nested('from hermes_tools import terminal\nterminal("curl http://x")\n')[0])


if __name__ == '__main__':
    unittest.main(verbosity=2)
