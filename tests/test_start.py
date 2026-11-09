"""The real program entry: builds the window and enters the event loop."""
import os
import pathlib
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent

CODE = """
import os, sys, tempfile
from psytags import config
folder = tempfile.mkdtemp()
os.makedirs(os.path.join(folder, "data"))
config.config_dir = lambda: folder
from PySide6.QtWidgets import QApplication
QApplication.exec = lambda self=None: 0
from psytags import app
sys.exit(app.main(["psytags", "--new-instance"]))
"""


class StartTests(unittest.TestCase):
    def test_main_starts(self):
        env = dict(os.environ, QT_QPA_PLATFORM="offscreen", PYTHONPATH=str(ROOT))
        done = subprocess.run([sys.executable, "-c", CODE], cwd=ROOT, env=env, capture_output=True,
                              text=True, encoding="utf-8", errors="replace", timeout=60)
        self.assertEqual(done.returncode, 0, done.stderr[-1500:])


if __name__ == "__main__":
    unittest.main()
