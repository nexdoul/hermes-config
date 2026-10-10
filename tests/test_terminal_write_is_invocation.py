"""RED/GREEN: a terminal write is an invocation, not a substring.

Found in matrix r7 (step-5-preview), which failed the READ-ONLY `conflict` case.
The parent's verification command was:

    python3 -c "
    p='.../workspace/in/shared.txt'
    raw=open(p,'rb').read()
    ...
    print('ascii_chars:', sum(1 for c in t if ord(c)<128), 'non_ascii:', sum(1 for c in t if ord(c)>=128))
    ..."

The old rule was `any(m in command for m in ('>', 'tee ', 'sed -i', 'mv ', 'cp ', 'touch '))`
and the '>' of `>=` inside the quoted Python body matched. So a model that
verified a shared file WITHOUT writing it could never pass the case — the same
defect class as the `open(` substring rule, on the terminal side.
"""
import sys
import unittest

sys.path.insert(0, '/home/hatch/workspace/repo-hermes-config/tests')

OLD_MARKERS = ('>', 'tee ', 'sed -i', 'mv ', 'cp ', 'touch ')


def old_rule(command: str) -> bool:
    return any(m in str(command or '') for m in OLD_MARKERS)


class TerminalWriteIsAnInvocation(unittest.TestCase):
    """The rule's contract, pinned without importing the harness.

    The harness module builds a sandbox at import time, so importing it from a
    unit test would drag that side effect in. The contract is therefore pinned
    here against the decision procedure, and the live harness is checked by the
    real matrix rounds.
    """

    @staticmethod
    def _new(command: str) -> bool:
        """Re-implementation of the harness helper's decision procedure."""
        import re
        text = str(command or '')
        # Blank single/double-quoted spans (the harness keeps offsets; here a
        # plain blanking is enough for the decision).
        blanked = re.sub(r'"[^"]*"', lambda m: ' ' * len(m.group(0)), text)
        blanked = re.sub(r"'[^']*'", lambda m: ' ' * len(m.group(0)), blanked)
        if '>' in blanked:
            return True
        tokens = {t.strip('(){}[],:=<>+-*!&') for t in blanked.replace('\n', ' ').split()}
        tokens.discard('')
        if tokens & {'tee', 'dd', 'install', 'rsync'}:
            return True
        if '-i' in blanked and tokens & {'sed', 'perl', 'awk'}:
            return True
        if tokens & {'mv', 'cp', 'touch', 'mkdir', 'rmdir', 'rm', 'ln',
                     'truncate', 'chmod', 'chown'}:
            return True
        return False

    def test_the_r7_command_is_not_a_write(self):
        cmd = ('python3 -c "\n'
               "p='/w/workspace/in/shared.txt'\n"
               "raw=open(p,'rb').read()\n"
               "t=raw.decode('utf-8')\n"
               "print(repr(t))\n"
               "print('ascii_chars:', sum(1 for c in t if ord(c)<128), 'non_ascii:', sum(1 for c in t if ord(c)>=128))\n"
               "print('has_newline:', t.endswith(chr(10)))\n"
               '"\n')
        self.assertFalse(self._new(cmd), 'a read-only python -c is not a write')
        self.assertTrue(old_rule(cmd),
                        'the old substring rule called it a write (the defect)')

    def test_a_real_redirect_is_a_write(self):
        for cmd in ('wc -l /w/in/shared.txt > /w/out/count.txt',
                    'echo hi >> /w/out/log.txt',
                    'cat a | tee /w/out/x.txt'):
            self.assertTrue(self._new(cmd), cmd)

    def test_in_place_edit_is_a_write(self):
        self.assertTrue(self._new("sed -i 's/a/b/' /w/out/report-a.md"))

    def test_move_copy_touch_are_writes(self):
        for cmd in ('mv /w/a /w/b', 'cp /w/a /w/b', 'touch /w/out/x',
                    'mkdir /w/out/new', 'rm /w/out/x'):
            self.assertTrue(self._new(cmd), cmd)

    def test_read_only_commands_are_not_writes(self):
        for cmd in ('wc -lc /w/in/shared.txt',
                    'ls -l /w/in/shared.txt && wc -lc /w/in/shared.txt',
                    'python3 -c "print(len(open(p,\'rb\').read()))"',
                    'grep -c . /w/in/shared.txt',
                    'diff a b', 'cat /w/in/shared.txt', 'head -5 /w/in/shared.txt'):
            self.assertFalse(self._new(cmd), cmd)

    def test_a_redirect_hidden_in_prose_is_not_a_write(self):
        """A command that merely MENTIONS a redirect writes nothing."""
        cmd = "echo 'do not run: foo > /etc/passwd'"
        self.assertFalse(self._new(cmd), cmd)

    def test_gt_inside_a_quoted_body_is_not_a_redirect(self):
        cmd = "python3 -c \"print(sum(1 for c in t if ord(c)>=128))\""
        self.assertFalse(self._new(cmd), cmd)


if __name__ == '__main__':
    unittest.main(verbosity=2)
