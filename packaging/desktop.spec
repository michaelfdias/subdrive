# One-file desktop executable; macOS additionally gets a Finder application bundle.
import os
import sys
import glob

root = os.path.abspath(os.path.join(SPECPATH, ".."))
graphics = []
if sys.platform.startswith("linux"):
    # QtGui links EGL even for a QWidget-only app. PyInstaller normally regards
    # these as system libraries; include dispatch libraries so minimal desktops
    # do not need a separate runtime installation. GPU drivers remain OS-owned.
    for name in ("libEGL.so.1", "libOpenGL.so.0", "libGL.so.1", "libGLX.so.0", "libGLdispatch.so.0"):
        matches = glob.glob("/usr/lib/*-linux-gnu/" + name) + glob.glob("/lib/*-linux-gnu/" + name)
        if matches:
            graphics.append((matches[0], "."))
a = Analysis([os.path.join(SPECPATH, "desktop_launcher.py")], pathex=[root],
    binaries=graphics,
    datas=[(os.path.join(root, "subdrive", "fonts"), "subdrive/fonts"),
           (os.path.join(root, "LICENSE"), "licenses"),
           (os.path.join(root, "docs", "img", "icone.svg"), "subdrive/assets"),
           (os.path.join(root, "packaging", "desktop-licenses"), "licenses/desktop")],
    hiddenimports=[], excludes=["tkinter", "unittest", "numpy", "PySide6.QtWebEngineCore",
                                "PySide6.QtWebEngineWidgets", "PySide6.QtQml", "PySide6.QtQuick"])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name="SubDrive-Desktop",
          console=False, upx=False, strip=False)
if sys.platform == "darwin":
    app = BUNDLE(exe, name="SubDrive Desktop.app", bundle_identifier="io.github.michaelfdias.subdrive.desktop",
        info_plist={"NSHighResolutionCapable": True,
                    "NSHumanReadableCopyright": "SubDrive © Michael Dias; MIT. Qt/PySide6 LGPLv3.",
                    "CFBundleShortVersionString": "1.0.0",
                    "CFBundleDocumentTypes": [{"CFBundleTypeName": "Subtitle",
                        "CFBundleTypeExtensions": ["srt", "sup"], "CFBundleTypeRole": "Editor"}]})
