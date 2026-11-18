"""Um download do SubDrive com janelas, no formato dos downloads do SubDrive CLI.

    python tools/make_app_download.py --program dist/SubDrive.app --package pacote-uhd.zip --system macOS-AppleSilicon --output out

O ZIP tem uma pasta só: SubDrive-App-<versão>-Panasonic-UB450-150-154-<BD|UHD>-<sistema>/ com o programa
(SubDrive.exe, SubDrive ou SubDrive.app), a pasta "pacote", LEIA-ME.txt e LICENCAS/. Permissões de executar
e links simbólicos (dentro do .app) são mantidos.
Com --update-asset, grava também o arquivo que a atualização pelo programa usa (chave app-<sistema>-<arquitetura>).
"""
from __future__ import annotations

import argparse
import json
import os
import stat
import sys
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from subdrive import VERSION  # noqa: E402

OPEN = {
    "Windows": ("Abra o SubDrive.exe com dois cliques.\n"
                "   Se o Windows mostrar \"O Windows protegeu o computador\", clique em\n"
                "   \"Mais informações\" e depois em \"Executar assim mesmo\" (só na primeira vez)."),
    "macOS": ("Abra o SubDrive com dois cliques.\n"
              "   Se o macOS disser que não pode abrir o SubDrive, abra Ajustes do Sistema >\n"
              "   Privacidade e Segurança e clique em \"Abrir Mesmo Assim\" (só na primeira vez)."),
    "Linux": ("Abra o SubDrive com dois cliques. Se o gerenciador de arquivos não abrir,\n"
              "   rode num terminal nesta pasta: ./SubDrive"),
}
README = """SubDrive {version} - Panasonic DP-UB450 / UB150 / UB154 ({platform}) - {system}
{beta}
Para aparelhos vendidos nos EUA (como o DP-UB450-K), com firmware 1.13
(no player: HOME > Setup > Player Settings > System > System Information).
Este ZIP serve para discos {disc}.

O que tem aqui:
  {program}o SubDrive, programa com janelas que prepara o pendrive e cuida das legendas
  pacote/            o pacote SubDrive, que o programa grava no pendrive
  LICENCAS/          as licenças do SubDrive e das bibliotecas que ele usa
  LEIA-ME.txt        este arquivo

Não precisa instalar nada, nem Java.

1. Extraia este ZIP (se ainda não extraiu) e deixe tudo junto na mesma pasta.
2. Conecte um pendrive.
3. {open}
4. Na tela Pendrive, clique em "Preparar pendrive".
   Na primeira vez, ele baixa o firmware oficial da Panasonic (91 MB),
   monta o programa do player e grava tudo no pendrive, já com as pastas
   legendas, sincronia e relatorios criadas.
   Suas legendas, sincronia, preferências e relatórios são mantidos.
5. Na tela Legendas, arraste suas legendas (.srt ou .sup) para a janela:
   o SubDrive diz se vão funcionar e corrige o que precisar.
   Depois coloque as legendas prontas na pasta "legendas" do pendrive.
6. Ejete o pendrive. No player, na primeira vez: ligue sem disco e espere a
   tela inicial carregar; coloque o pendrive e feche a janela que o player abre;
   espere de 10 a 15 segundos, coloque o disco e, durante o filme, aperte a
   tecla VERMELHA. Nas próximas vezes o pendrive pode ficar no aparelho.
7. Se a legenda sumir depois de um menu do disco, aperte VERMELHA de novo
   (ou PAUSE, espere 3 segundos e PLAY).

Guia completo: https://michaelfdias.github.io/subdrive/
"""


def entry(z, name, data=b"", mode=0o644, link=None):
    info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
    info.create_system = 3  # permissões Unix, lidas pelo Finder, unzip e Windows
    if link is not None:
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        z.writestr(info, link)
        return
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = (stat.S_IFREG | mode) << 16
    z.writestr(info, data)


def add_tree(z, src: Path, prefix: str):
    if src.is_file():
        entry(z, prefix, src.read_bytes(), 0o755)
        return
    for f in sorted(src.rglob("*")):
        name = prefix + "/" + f.relative_to(src).as_posix()
        if f.is_symlink():
            entry(z, name, link=os.readlink(f))
        elif f.is_file():
            entry(z, name, f.read_bytes(), 0o755 if os.access(f, os.X_OK) else 0o644)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--program", type=Path, required=True)
    ap.add_argument("--package", type=Path, required=True, help="ZIP com uma pasta pacote/ dentro")
    ap.add_argument("--system", required=True, help="Windows, macOS-AppleSilicon, macOS-Intel ou Linux")
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--update-asset", type=Path, help="grava também o programa sozinho (o .app vai num ZIP) para a atualização")
    a = ap.parse_args()

    with zipfile.ZipFile(a.package) as src:
        names = [n for n in src.namelist() if "/pacote/" in "/" + n and not n.endswith("/")]
        if not names:
            raise SystemExit("Sem pasta pacote/ em %s" % a.package)
        cut = names[0].index("pacote/")
        files = {n[cut:]: src.read(n) for n in names}
    for n in files:
        p = PurePosixPath(n)
        if p.is_absolute() or ".." in p.parts:
            raise SystemExit("Nome inseguro no pacote: %s" % n)
    manifest = json.loads(files["pacote/manifest.json"])
    if manifest["version"] != VERSION:
        raise SystemExit("Pacote %s, programa %s: versões diferentes" % (manifest["version"], VERSION))
    platform = manifest["platform"]
    family = a.system.split("-")[0]
    prog_name = {"Windows": "SubDrive.exe", "macOS": "SubDrive.app", "Linux": "SubDrive"}[family]
    folder = "SubDrive-App-%s-Panasonic-UB450-150-154-%s-%s" % (VERSION, platform, a.system)
    readme = README.format(version=VERSION, platform=platform, system=a.system.replace("-AppleSilicon", " Apple Silicon").replace("-", " "),
                           beta="Versão de teste.\n" if "-" in VERSION else "", open=OPEN[family],
                           disc="Blu-ray (BD)" if platform == "BD" else "4K UHD", program=prog_name.ljust(19))
    a.output.mkdir(parents=True, exist_ok=True)
    target = a.output / (folder + ".zip")
    licences = ROOT / "packaging" / "app" / "licencas"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        add_tree(z, a.program, folder + "/" + prog_name)
        entry(z, folder + "/LEIA-ME.txt", readme.replace("\n", "\r\n" if family == "Windows" else "\n").encode("utf-8"))
        entry(z, folder + "/LICENCAS/SubDrive-MIT.txt", (ROOT / "LICENSE").read_bytes())
        for lic in sorted(licences.iterdir()):
            entry(z, folder + "/LICENCAS/" + lic.name, lic.read_bytes())
        for n in sorted(files):
            entry(z, folder + "/" + n, files[n])
    with zipfile.ZipFile(target) as z:
        if z.testzip() is not None:
            raise SystemExit("O ZIP não abriu de volta")
    print(target, target.stat().st_size)
    if a.update_asset:
        a.update_asset.parent.mkdir(parents=True, exist_ok=True)
        if a.program.is_dir():
            with zipfile.ZipFile(a.update_asset, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
                add_tree(z, a.program, "SubDrive.app")
        else:
            a.update_asset.write_bytes(a.program.read_bytes())
        print(a.update_asset, a.update_asset.stat().st_size)


if __name__ == "__main__":
    main()
