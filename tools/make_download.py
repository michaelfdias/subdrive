"""Make one download ZIP: the SubDrive program for one system + the player package + LEIA-ME.txt.

    python tools/make_download.py --program dist/SubDrive --package pacotes/panasonic-ub450-150-154-uhd.zip \
        --system macOS-AppleSilicon --output out

The ZIP holds a single folder, e.g. SubDrive-1.0.0-Panasonic-UB450-150-154-UHD-Windows/, with the program,
the folder "pacote" and LEIA-ME.txt. The program keeps its "can be run" permission on macOS and Linux.
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import zipfile
from pathlib import Path, PurePosixPath

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from subdrive import VERSION  # noqa: E402

OPEN = {
    "Windows": ("Abra o SubDrive.exe com dois cliques.\n"
                "   Se o Windows mostrar \"O Windows protegeu o computador\", clique em\n"
                "   \"Mais informações\" e depois em \"Executar assim mesmo\" (só na primeira vez)."),
    "macOS": ("Abra o SubDrive com dois cliques (ele abre no Terminal).\n"
              "   Se o macOS disser que não pode abrir porque o desenvolvedor não pode ser verificado,\n"
              "   abra Ajustes do Sistema > Privacidade e Segurança e clique em \"Abrir Mesmo Assim\"\n"
              "   (só na primeira vez)."),
    "Linux": "Abra um terminal nesta pasta e rode: ./SubDrive",
}

README = """SubDrive {version} - Panasonic DP-UB450 / UB150 / UB154 ({platform}) - {system}
{beta}
Para aparelhos vendidos nos EUA, com firmware 1.13
(no player: Configurações > Sistema > Informações do Firmware).

1. Extraia este ZIP (se ainda não extraiu) e deixe o programa ao lado da pasta "pacote".
2. {open}
3. No menu, escolha "Preparar pendrive".
   Na primeira vez, ele baixa o firmware oficial da Panasonic (91 MB),
   monta o programa do player e grava tudo no pendrive.
   Suas legendas, sincronia, preferências e relatórios são mantidos.
4. Ejete o pendrive, coloque no player e aperte a tecla VERMELHA durante o filme.
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--program", type=Path, required=True)
    ap.add_argument("--package", type=Path, required=True, help="ZIP with a folder pacote/ inside")
    ap.add_argument("--system", required=True, help="Windows, macOS-AppleSilicon, macOS-Intel or Linux")
    ap.add_argument("--output", type=Path, required=True)
    a = ap.parse_args()

    with zipfile.ZipFile(a.package) as src:
        names = [n for n in src.namelist() if "/pacote/" in "/" + n and not n.endswith("/")]
        if not names:
            raise SystemExit("No pacote/ folder in %s" % a.package)
        cut = names[0].index("pacote/")
        files = {n[cut:]: src.read(n) for n in names}
    manifest = json.loads(files["pacote/manifest.json"])
    if manifest["version"] != VERSION:
        raise SystemExit("Package %s, program %s: versions differ" % (manifest["version"], VERSION))
    for n in files:
        p = PurePosixPath(n)
        if p.is_absolute() or ".." in p.parts:
            raise SystemExit("Unsafe name in the package: %s" % n)

    platform = manifest["platform"]
    folder = "SubDrive-%s-Panasonic-UB450-150-154-%s-%s" % (VERSION, platform, a.system)
    family = a.system.split("-")[0]
    readme = README.format(version=VERSION, platform=platform, system=a.system.replace("-AppleSilicon", " Apple Silicon").replace("-", " "),
                           beta="Versão de teste.\n" if "-" in VERSION else "", open=OPEN[family])
    program = a.program.read_bytes()
    program_name = "SubDrive.exe" if family == "Windows" else "SubDrive"

    a.output.mkdir(parents=True, exist_ok=True)
    target = a.output / (folder + ".zip")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        def put(name, data, mode):
            info = zipfile.ZipInfo(folder + "/" + name, (2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3  # Unix permissions, read by Finder, unzip and Windows alike
            info.external_attr = (0o100000 | mode) << 16
            z.writestr(info, data)
        put(program_name, program, 0o755)
        put("LEIA-ME.txt", readme.replace("\n", "\r\n" if family == "Windows" else "\n").encode("utf-8"), 0o644)
        for n in sorted(files):
            put(n, files[n], 0o644)
    target.write_bytes(buf.getvalue())
    with zipfile.ZipFile(target) as z:
        if z.testzip() is not None:
            raise SystemExit("The ZIP did not read back")
    print(target, len(buf.getvalue()))


if __name__ == "__main__":
    main()
