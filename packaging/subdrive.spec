# PyInstaller recipe: one file per system, with the fonts used to draw PGS subtitles.
# Build: pyinstaller packaging/subdrive.spec  (from the repository root)
import os

root = os.path.abspath(os.path.join(SPECPATH, ".."))
a = Analysis([os.path.join(SPECPATH, "launcher.py")], pathex=[root],
             datas=[(os.path.join(root, "subdrive", "fonts"), os.path.join("subdrive", "fonts"))],
             hiddenimports=["subdrive.menu"], excludes=["tkinter", "unittest", "pydoc", "numpy"])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name="SubDrive-CLI", console=True, upx=False, strip=False)
