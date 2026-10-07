"""
Unit tests for PhantomSuite Embedded Python Scripting & Plugin Engine.
"""

import os
import shutil
import subprocess
import tempfile
import time
import unittest
from phantom_suite.core.script_engine import ScriptEngine
from phantom_suite.core.elf_explorer import ElfExplorer


class TestScriptEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        target_src = os.path.join(os.path.dirname(__file__), "test_target.c")
        target_bin = os.path.join(os.path.dirname(__file__), "test_target")
        if not os.path.exists(target_bin):
            subprocess.run(["gcc", "-O0", "-g", target_src, "-o", target_bin, "-lpthread"], check=True)

        cls.proc = subprocess.Popen([target_bin], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        time.sleep(0.2)
        cls.pid = cls.proc.pid

        # Find health address
        mods = ElfExplorer.get_loaded_modules(cls.pid)
        target_mod = next(m for m in mods if "test_target" in m.name)
        syms = ElfExplorer.parse_symbols(target_mod.path, base_address=target_mod.base_address)
        cls.health_sym = next(s for s in syms if s.name == "target_health")
        cls.health_addr = cls.health_sym.runtime_address

    @classmethod
    def tearDownClass(cls):
        if cls.proc and cls.proc.poll() is None:
            cls.proc.terminate()
            cls.proc.wait()

    def test_expression_evaluation(self):
        engine = ScriptEngine()
        success, out = engine.execute("21 * 2")
        self.assertTrue(success)
        self.assertIn("42", out)

    def test_multiline_execution(self):
        engine = ScriptEngine()
        code = (
            "res = []\n"
            "for i in range(3):\n"
            "    res.append(i * 10)\n"
            "print('Result:', res)\n"
        )
        success, out = engine.execute(code)
        self.assertTrue(success)
        self.assertIn("Result: [0, 10, 20]", out)

    def test_syntax_or_runtime_error(self):
        engine = ScriptEngine()
        success, out = engine.execute("1 / 0")
        self.assertFalse(success)
        self.assertIn("ZeroDivisionError", out)

    def test_memory_helpers_with_pid(self):
        engine = ScriptEngine(target_pid=self.pid)
        
        # Test read_i32
        success, out = engine.execute(f"read_i32({self.health_addr})")
        self.assertTrue(success)
        self.assertIn("100", out)

        # Test write_i32
        success, out = engine.execute(f"write_i32({self.health_addr}, 888)")
        self.assertTrue(success)

        # Verify new value
        success, out = engine.execute(f"read_i32({self.health_addr})")
        self.assertTrue(success)
        self.assertIn("888", out)

        # Reset value
        engine.execute(f"write_i32({self.health_addr}, 100)")

    def test_repl_hybrid_statement_and_expression(self):
        engine = ScriptEngine()
        code = "val_a = 50\nval_b = 25\nval_a + val_b"
        success, out = engine.execute(code)
        self.assertTrue(success)
        self.assertIn("75", out)

    def test_variable_persistence_across_executions(self):
        engine = ScriptEngine()
        s1, _ = engine.execute("custom_counter = 100")
        self.assertTrue(s1)
        s2, out = engine.execute("custom_counter + 25")
        self.assertTrue(s2)
        self.assertIn("125", out)

    def test_variable_preservation_on_set_target(self):
        engine = ScriptEngine()
        engine.execute("stored_var = 999")
        engine.set_target(self.pid)
        success, out = engine.execute("stored_var")
        self.assertTrue(success)
        self.assertIn("999", out)

    def test_syntax_error_handling(self):
        engine = ScriptEngine()
        success, out = engine.execute("def invalid_fn(")
        self.assertFalse(success)
        self.assertIn("SyntaxError", out)

    def test_empty_execution(self):
        engine = ScriptEngine()
        success, out = engine.execute("   \n  ")
        self.assertTrue(success)
        self.assertEqual(out, "")

    def test_system_exit_trapping(self):
        engine = ScriptEngine()
        # Ensure sys.exit(0) does NOT kill process and reports failure
        success, out = engine.execute("import sys; sys.exit(0)")
        self.assertFalse(success)
        self.assertIn("SystemExit", out)

    def test_reset_environment(self):
        engine = ScriptEngine()
        engine.execute("kernel_val = 555")
        self.assertIn("kernel_val", engine.custom_globals)
        engine.reset_environment()
        self.assertNotIn("kernel_val", engine.custom_globals)
        self.assertIn("read", engine.custom_globals)


if __name__ == "__main__":
    unittest.main()
