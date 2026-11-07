import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import tempfile
import time
import unittest
from pathlib import Path
import importlib.util
if importlib.util.find_spec("PySide6"):
    from PySide6.QtWidgets import QApplication
    from subdrive.desktop import Window
else:
    QApplication = None


@unittest.skipIf(QApplication is None, "Desktop dependencies not installed")
class DesktopUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.window = Window()
        self.window.show()

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def test_sup_disables_srt_actions(self):
        p = Path(self.tmp.name) / "Film.sup"; p.touch()
        self.window.set_paths([p])
        self.window.action.setCurrentIndex(1)
        self.assertFalse(self.window.run_button.isEnabled())
        self.assertIn("SRT", self.window.explanation.text())
        self.window.action.setCurrentIndex(3)
        self.assertTrue(self.window.run_button.isEnabled())

    def test_check_runs_on_worker_and_displays_result(self):
        p = Path(self.tmp.name) / "Film.srt"
        p.write_text("1\n00:00:01,000 --> 00:00:03,000\nOlá!\n", encoding="utf-8")
        self.window.set_paths([p])
        self.window.run_button.click()
        self.assertFalse(self.window.tabs.isEnabled())
        limit = time.monotonic() + 10
        while self.window.worker and time.monotonic() < limit:
            self.app.processEvents()
            time.sleep(.01)
        self.assertIsNone(self.window.worker)
        self.assertIn("Film.srt", self.window.log.toPlainText())
        self.assertIn("Concluído", self.window.status.text())
        self.assertTrue(self.window.tabs.isEnabled())

    def test_options_hidden_until_requested(self):
        self.assertFalse(self.window.advanced.isVisible())
        self.window.advanced_toggle.setChecked(True)
        self.assertTrue(self.window.advanced.isVisible())
        self.assertFalse(self.window.pgs_box.isVisible())
        self.window.action.setCurrentIndex(2)
        self.assertTrue(self.window.pgs_box.isVisible())
