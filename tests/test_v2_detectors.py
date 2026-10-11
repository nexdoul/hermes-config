import ast
import pathlib
import unittest

SOURCE = pathlib.Path(__file__).with_name('recovery_v2_harness.py').read_text()
module = ast.parse(SOURCE)
# Pure detector extraction avoids importing the harness CLI or calling any model.
names = {'_helper_before','_iter_literals','_strip_string_literals','_terminal_mutates_fs','_code_mutates_fs','_invocation_tokens'}
selected = [n for n in module.body if isinstance(n, ast.FunctionDef) and n.name in names]
namespace = {'re':__import__('re'), '_QUOTES': ('"', "'"), '_SHELL_HELPERS':set(), '_PATH_HELPERS':set(), '_NET_HELPERS':set(), '_KNOWN_MODULES':set()}
exec(compile(ast.Module(body=selected,type_ignores=[]),'<detectors>','exec'), namespace)

class V2DetectorTests(unittest.TestCase):
    def test_null_redirect_is_not_file_mutation(self):
        self.assertFalse(namespace['_terminal_mutates_fs']('uname -a 2>/dev/null'))
    def test_real_redirect_remains_mutation(self):
        self.assertTrue(namespace['_terminal_mutates_fs']('printf x > out/report.txt'))
    def test_descriptor_duplication_not_mutation(self):
        self.assertFalse(namespace['_terminal_mutates_fs']('uname -a 2>&1'))

    def test_readonly_time_style_is_not_inplace(self):
        self.assertFalse(namespace['_terminal_mutates_fs']('python3 -c "print(1)"; ls --time-style=full-iso x'))
    def test_python_heredoc_comparison_is_not_redirect(self):
        self.assertFalse(namespace['_terminal_mutates_fs']("python3 - <<'EOF'\nprint(2>0)\nEOF"))
    def test_inplace_flag_is_mutation(self):
        self.assertTrue(namespace['_terminal_mutates_fs']("sed -i 's/a/b/' x"))

if __name__=='__main__': unittest.main()
