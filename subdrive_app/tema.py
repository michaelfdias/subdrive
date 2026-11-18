"""Cores, letras e estilo da janela: as mesmas cores do site do SubDrive, em claro e escuro (segue o sistema)."""
from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QGuiApplication, QPalette

LIGHT = dict(
    bg="#f7f7f5", side="#efeeea", surface="#ffffff", raised="#fbfbfa", text="#18191b", muted="#4b4f55", faint="#686c72",
    line="#e4e4e0", strong="#cfcfca", accent="#b45309", accent_hover="#93440a", accent_bg="#fbf1e3", on_accent="#ffffff",
    ok="#15803d", ok_bg="#e9f6ee", warn="#8a5a00", warn_bg="#fdf5df", warn_line="#f0d48a", fail="#b91c1c", fail_bg="#fdeeee",
    info="#1d4ed8", info_bg="#eef3fd", sel="#f3e6d3", hover="#e6e5e0", tv="#0d0e10", focus="#b45309",
)
DARK = dict(
    bg="#111214", side="#0c0d0f", surface="#18191c", raised="#1d1f22", text="#ecebe7", muted="#b8bbc0", faint="#9a9ea4",
    line="#26282c", strong="#36393e", accent="#f0a43a", accent_hover="#f6bb66", accent_bg="#2a2216", on_accent="#16181c",
    ok="#4ade80", ok_bg="#13261a", warn="#f7c948", warn_bg="#2a2410", warn_line="#5a4a1a", fail="#fb8a8a", fail_bg="#2c1517",
    info="#93b4f8", info_bg="#141c2c", sel="#2a2216", hover="#202226", tv="#000000", focus="#f0a43a",
)

FAMILY = "Source Sans 3"
C = dict(LIGHT)  # as cores em uso agora


def dark_wanted() -> bool:
    forced = os.environ.get("SUBDRIVE_TEMA", "").lower()
    if forced in ("escuro", "dark"):
        return True
    if forced in ("claro", "light"):
        return False
    try:
        return QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark
    except Exception:
        return False


UI_FAMILY = "SubDrive Sans"


def load_fonts(folder: Path):
    """A fonte do site (Source Sans 3), que já vem com o SubDrive para desenhar PGS.

    Os arquivos trazem nomes internos iguais para o normal e o negrito; o Windows então troca um pelo outro.
    Aqui cada um ganha o nome certo (só na memória, os arquivos não mudam)."""
    global FAMILY
    import io
    try:
        from fontTools.ttLib import TTFont
    except ImportError:
        TTFont = None
    loaded = False
    for name, bold, italic in (("sourcesans3-400.ttf", False, False), ("sourcesans3-700.ttf", True, False),
                               ("sourcesans3-italic-400.ttf", False, True), ("sourcesans3-italic-700.ttf", True, True)):
        path = folder / name
        try:
            if TTFont is None:
                raise ValueError
            font = TTFont(str(path))
            style = ("Bold " if bold else "") + ("Italic" if italic else "")
            style = style.strip() or "Regular"
            table = font["name"]
            for rec in list(table.names):
                if rec.nameID in (1, 2, 3, 4, 6, 16, 17):
                    table.removeNames(nameID=rec.nameID)
            ps = "SubDriveSans-" + style.replace(" ", "")
            for nid, text in ((1, UI_FAMILY), (2, style), (3, ps), (4, UI_FAMILY + ("" if style == "Regular" else " " + style)), (6, ps)):
                table.setName(text, nid, 3, 1, 0x409)
                table.setName(text, nid, 1, 0, 0)
            os2 = font["OS/2"]
            os2.usWeightClass = 700 if bold else 400
            os2.fsSelection = (os2.fsSelection & ~0b1100001) | (0b100000 if bold else 0) | (0b1 if italic else 0) | (0 if bold or italic else 0b1000000)
            font["head"].macStyle = (1 if bold else 0) | (2 if italic else 0)
            buf = io.BytesIO(); font.save(buf)
            fid = QFontDatabase.addApplicationFontFromData(buf.getvalue())
        except Exception:
            fid = QFontDatabase.addApplicationFont(str(path))
            if fid >= 0 and not loaded:
                fams = QFontDatabase.applicationFontFamilies(fid)
                FAMILY = fams[0] if fams else FAMILY
                loaded = True
            continue
        if fid >= 0 and not loaded:
            FAMILY = UI_FAMILY
            loaded = True


def apply(app):
    C.clear()
    C.update(DARK if dark_wanted() else LIGHT)
    font = QFont(FAMILY)
    font.setPixelSize(14)
    font.setHintingPreference(QFont.PreferNoHinting)
    app.setFont(font)
    pal = QPalette()
    role = QPalette.ColorRole
    for r, key in ((role.Window, "bg"), (role.WindowText, "text"), (role.Base, "surface"), (role.AlternateBase, "raised"),
                   (role.Text, "text"), (role.Button, "surface"), (role.ButtonText, "text"), (role.ToolTipBase, "surface"),
                   (role.ToolTipText, "text"), (role.Highlight, "accent"), (role.HighlightedText, "on_accent"),
                   (role.PlaceholderText, "faint"), (role.Link, "accent"), (role.Mid, "strong"), (role.Midlight, "line"),
                   (role.Dark, "strong"), (role.Light, "surface"), (role.Shadow, "strong")):
        pal.setColor(r, QColor(C[key]))
    for r in (role.Text, role.WindowText, role.ButtonText):
        pal.setColor(QPalette.Disabled, r, QColor(C["faint"]))
    app.setPalette(pal)
    app.setStyleSheet(qss())


def qss() -> str:
    c = C
    return """
* { font-family: "%(family)s"; }
QWidget { color: %(text)s; }
QMainWindow, QDialog, #page, #content { background: %(bg)s; }
QToolTip { background: %(surface)s; color: %(text)s; border: 1px solid %(strong)s; padding: 6px 8px; border-radius: 6px; }

#sidebar { background: %(side)s; border-right: 1px solid %(line)s; }
#brand { font-size: 19px; font-weight: 700; }
#navButton { text-align: left; padding: 10px 14px; border: none; border-radius: 8px; font-size: 15px; color: %(muted)s; background: transparent; }
#navButton:hover { background: %(hover)s; color: %(text)s; }
#navButton:checked { background: %(surface)s; color: %(text)s; font-weight: 700; border: 1px solid %(line)s; }
#navButton:focus { border: 2px solid %(focus)s; }
QPushButton[kind="ghost"]:focus, QPushButton[kind="icon"]:focus { border: 2px solid %(focus)s; }
#sideFoot { color: %(faint)s; font-size: 13px; }
#driveBox { text-align: left; border: 1px solid transparent; border-radius: 8px; background: transparent; padding: 0; }
#driveBox:hover { background: %(hover)s; border-color: %(line)s; }

QLabel[role="title"] { font-size: 28px; font-weight: 700; }
QLabel[role="lead"] { font-size: 15px; color: %(muted)s; }
QLabel[role="h2"] { font-size: 17px; font-weight: 700; }
QLabel[role="group"] { font-size: 12px; font-weight: 700; color: %(faint)s; letter-spacing: 0.6px; }
QLabel[role="muted"] { color: %(muted)s; }
QLabel[role="faint"] { color: %(faint)s; font-size: 13px; }
QLabel[role="big"] { font-size: 20px; font-weight: 700; }
QLabel[tone="ok"] { color: %(ok)s; }
QLabel[tone="fail"] { color: %(fail)s; }
QLabel[tone="warn"] { color: %(warn)s; }
QLabel[role="mono"] { font-family: "Menlo", "Consolas", "DejaVu Sans Mono", monospace; font-size: 13px; color: %(muted)s; }
QLabel a { color: %(accent)s; }

#card { background: %(surface)s; border: 1px solid %(line)s; border-radius: 12px; }
#card[tone="ok"] { background: %(ok_bg)s; border-color: transparent; }
#card[tone="fail"] { background: %(fail_bg)s; border-color: transparent; }
#card[tone="warn"] { background: %(warn_bg)s; border-color: transparent; }
#card[tone="info"] { background: %(info_bg)s; border-color: transparent; }
#card[tone="accent"] { background: %(accent_bg)s; border-color: transparent; }
#row { background: %(surface)s; border: 1px solid %(line)s; border-radius: 10px; }
#row:hover { border-color: %(strong)s; background: %(raised)s; }
#sep { background: %(line)s; max-height: 1px; min-height: 1px; border: none; }

QPushButton { font-size: 14px; padding: 8px 16px; border-radius: 8px; border: 1px solid %(strong)s; background: %(surface)s; color: %(text)s; }
QPushButton:hover { background: %(hover)s; }
QPushButton:pressed { background: %(line)s; }
QPushButton:disabled { color: %(faint)s; background: %(bg)s; border-color: %(line)s; }
QPushButton:focus { border-color: %(focus)s; }
QPushButton[kind="primary"] { background: %(accent)s; color: %(on_accent)s; border: 1px solid %(accent)s; font-weight: 700; }
QPushButton[kind="primary"]:hover { background: %(accent_hover)s; border-color: %(accent_hover)s; }
QPushButton[kind="primary"]:disabled { background: %(line)s; border-color: %(strong)s; color: %(muted)s; }
QPushButton[kind="primary"]:focus { border: 2px solid %(text)s; padding: 7px 15px; }
QPushButton[kind="ghost"] { border: none; background: transparent; color: %(accent)s; padding: 6px 8px; font-weight: 700; }
QPushButton[kind="ghost"]:hover { background: %(accent_bg)s; }
QPushButton[kind="ghost"]:disabled { color: %(faint)s; background: transparent; }
QPushButton[kind="icon"] { border: none; background: transparent; padding: 6px; border-radius: 8px; }
QPushButton[kind="icon"]:hover { background: %(hover)s; }
QPushButton[kind="big"] { font-size: 16px; padding: 12px 22px; }

QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox { background: %(surface)s; border: 1px solid %(strong)s; border-radius: 8px; padding: 7px 10px; font-size: 14px; selection-background-color: %(accent)s; selection-color: %(on_accent)s; }
QLineEdit:focus, QComboBox:focus { border: 1px solid %(focus)s; }
QComboBox::drop-down { border: none; width: 30px; }
QComboBox::down-arrow { image: url(%(chevron)s); width: 14px; height: 14px; }
QComboBox QAbstractItemView { background: %(surface)s; border: 1px solid %(strong)s; selection-background-color: %(sel)s; selection-color: %(text)s; padding: 4px; outline: none; }
QCheckBox { spacing: 10px; font-size: 14px; }
QCheckBox::indicator { width: 18px; height: 18px; border-radius: 5px; border: 1px solid %(strong)s; background: %(surface)s; }
QCheckBox::indicator:hover { border-color: %(accent)s; }
QCheckBox::indicator:checked { background: %(accent)s; border-color: %(accent)s; image: url(%(check)s); }

QSlider::groove:horizontal { height: 6px; background: %(line)s; border-radius: 3px; }
QSlider::sub-page:horizontal { background: %(accent)s; border-radius: 3px; }
QSlider { min-height: 24px; }
QSlider::handle:horizontal { background: %(surface)s; border: 3px solid %(accent)s; width: 12px; height: 12px; margin: -6px 0; border-radius: 9px; }
QSlider::handle:horizontal:hover { background: %(accent_bg)s; }
QSlider::sub-page:horizontal:disabled { background: %(strong)s; }
QSlider::handle:horizontal:disabled { border-color: %(strong)s; background: %(bg)s; }
QComboBox:disabled, QLineEdit:disabled { color: %(faint)s; background: %(bg)s; border-color: %(line)s; }
QCheckBox:disabled { color: %(faint)s; }
QCheckBox::indicator:checked:disabled { background: %(strong)s; border-color: %(strong)s; }

QProgressBar { background: %(line)s; border: none; border-radius: 4px; height: 8px; max-height: 8px; text-align: center; color: transparent; }
QProgressBar::chunk { background: %(accent)s; border-radius: 4px; }

QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; border: none; }
QScrollBar:vertical { background: transparent; width: 12px; margin: 2px; }
QScrollBar::handle:vertical { background: %(strong)s; border-radius: 4px; min-height: 30px; margin: 0 2px; }
QScrollBar::handle:vertical:hover { background: %(faint)s; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
QScrollBar:horizontal { height: 0; }

QMenu { background: %(surface)s; border: 1px solid %(strong)s; border-radius: 8px; padding: 6px; }
QMenu::item { padding: 8px 18px 8px 12px; border-radius: 6px; }
QMenu::item:selected { background: %(sel)s; color: %(text)s; }
QMessageBox QLabel { font-size: 14px; }
""" % dict(c, family=FAMILY, check=_png("check", C["on_accent"], 2.4), chevron=_png("down", C["muted"], 2))


_CHECK = {}


def _png(name, color, width) -> str:
    """Um ícone salvo num arquivo temporário, porque o QSS só aceita imagens de arquivo."""
    key = (name, color)
    if key in _CHECK:
        return _CHECK[key]
    import tempfile
    from . import icones
    pix = icones.pixmap(name, color, 18, width)
    path = Path(tempfile.gettempdir()) / ("subdrive-%s-%s.png" % (name, color.strip("#")))
    try:
        pix.save(str(path), "PNG")
    except Exception:
        return ""
    _CHECK[key] = path.as_posix()
    return _CHECK[key]
