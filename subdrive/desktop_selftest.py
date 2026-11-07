"""CI-only, actual GUI worker/PGS/font/process-pool integration in frozen builds."""
import json
import tempfile
from pathlib import Path
from PySide6.QtCore import QTimer
from . import core


def begin(app, window, report):
    workspace = tempfile.TemporaryDirectory()
    path = Path(workspace.name) / "Film.srt"
    path.write_text("1\n00:00:01,000 --> 00:00:03,000\nOlá, João!\n", encoding="utf-8")
    window.set_paths([path])
    window.action.setCurrentIndex(2)
    window.run_subtitle()
    timer = QTimer(window)

    def done():
        if window.worker:
            return
        timer.stop()
        target = path.with_name("Film.soft-white.sup")
        success = target.exists() and core.check_path(target).ok and not window.failed
        report.write_text(json.dumps({"success": success, "log": window.log.toPlainText()}, ensure_ascii=False), encoding="utf-8")
        workspace.cleanup()
        app.exit(0 if success else 1)

    timer.timeout.connect(done)
    timer.start(100)
