# PyInstaller: o SubDrive com janelas. Windows e Linux: um arquivo só; macOS: SubDrive.app.
# Build: pyinstaller packaging/app/subdrive_app.spec  (da raiz do repositório)
import os, re, sys

here = os.path.abspath(SPECPATH)
root = os.path.abspath(os.path.join(here, "..", ".."))
windows, mac = sys.platform == "win32", sys.platform == "darwin"
sys.path.insert(0, root)
from subdrive import VERSION

a = Analysis([os.path.join(here, "SubDrive.py")], pathex=[root],
             datas=[(os.path.join(root, "subdrive", "fonts"), os.path.join("subdrive", "fonts"))],
             hiddenimports=["subdrive_app.janela", "PySide6.QtSvg"],
             excludes=["tkinter", "unittest", "pydoc", "numpy", "PySide6.QtNetwork", "PySide6.QtQml", "PySide6.QtQuick",
                       "PySide6.QtOpenGL", "PySide6.QtPdf", "PySide6.QtDBus"])

if not windows and not mac:
    # Linux: o que todo sistema com tela já tem (driver de vídeo, fontes, X11/Wayland, C++) fica de fora;
    # vão junto as bibliotecas xcb que algumas distribuições não instalam (o Qt 6 precisa delas).
    system = re.compile(r"^(libGL|libEGL|libGLX|libGLdispatch|libOpenGL|libfontconfig|libfreetype|libdbus-1|libglib-2|libgobject-2|"
                        r"libgthread-2|libgmodule-2|libX11|libXau|libXdmcp|libXext|libXrender|libxcb\.so|libwayland-|libstdc\+\+|"
                        r"libgcc_s|libpng16|libuuid|libpcre|libbsd|libmd\.so|libexpat|libz\.so|libbrotli|libharfbuzz|libgraphite)")
    # (as cópias que vêm dentro dos pacotes, como pillow.libs/, ficam: têm nome próprio e são as testadas)
    a.binaries = [b for b in a.binaries if ".libs" in b[1] or not system.match(os.path.basename(b[0]))]
a.binaries = [b for b in a.binaries if not re.search(r"(qtwebengine|Qt6?(Pdf|Quick|Qml|Network|OpenGL|VirtualKeyboard|Wayland(Egl|Compositor)))", b[0])]
a.datas = [d for d in a.datas if not re.search(r"PySide6[/\\]Qt[/\\]translations", d[0])]

pyz = PYZ(a.pure)
if mac:
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="SubDrive", console=False, upx=False, strip=False)
    coll = COLLECT(exe, a.binaries, a.datas, name="SubDrive", upx=False, strip=False)
    app = BUNDLE(coll, name="SubDrive.app", icon=os.path.join(here, "icons", "subdrive.icns"),
                 bundle_identifier="io.github.michaelfdias.subdrive", version=VERSION,
                 info_plist={"CFBundleDisplayName": "SubDrive", "CFBundleShortVersionString": VERSION, "CFBundleVersion": VERSION,
                             "LSMinimumSystemVersion": "12.0", "NSHighResolutionCapable": True,
                             "NSRequiresAquaSystemAppearance": False, "LSApplicationCategoryType": "public.app-category.utilities",
                             "CFBundleDevelopmentRegion": "pt-BR",
                             "CFBundleDocumentTypes": [{"CFBundleTypeName": "Legenda", "CFBundleTypeRole": "Editor",
                                                        "LSHandlerRank": "Alternate", "CFBundleTypeExtensions": ["srt", "sup"],
                                                        "LSItemContentTypes": ["public.data"]}]})
else:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name="SubDrive", console=False, upx=False, strip=False,
              icon=os.path.join(here, "icons", "subdrive.ico") if windows else None,
              version=os.path.join(here, "version.txt") if windows else None)
