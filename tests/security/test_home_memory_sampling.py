import ctypes
import gc
from pathlib import Path
import subprocess
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import home_preparation_resources as resources


@unittest.skipUnless(sys.platform == 'win32', 'Requires native Windows memory APIs')
class WindowsMemorySamplingTests(unittest.TestCase):
    def test_repeated_parent_and_child_samples_do_not_retain_new_types(self):
        with subprocess.Popen([sys.executable, '-c', 'import time;time.sleep(20)'],
                              creationflags=subprocess.CREATE_NO_WINDOW) as child:
            try:
                resources.memory()
                resources.memory(child)
                gc.collect()
                before = len(ctypes._pointer_type_cache)
                for _ in range(2000):
                    for target in (None, child):
                        available, rss = resources.memory(target)
                        self.assertGreater(available, 0)
                        self.assertGreater(rss, 0)
                gc.collect()
                self.assertEqual(len(ctypes._pointer_type_cache), before)
            finally:
                child.terminate()
                child.wait(timeout=5)
