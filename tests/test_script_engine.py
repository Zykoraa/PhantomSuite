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

    def test_load_plugins(self):
        temp_dir = tempfile.mkdtemp()
        try:
            plugin_file = os.path.join(temp_dir, "my_custom_plugin.py")
            with open(plugin_file, "w") as f:
                f.write("# Sample plugin\nPLUGIN_ACTIVE = True\n")

            loaded = ScriptEngine.load_plugins(temp_dir)
            self.assertIn("my_custom_plugin", loaded)
        finally:
            shutil.rmtree(temp_dir)


if __name__ == "__main__":
    unittest.main()
