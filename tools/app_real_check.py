"""Teste de ponta a ponta com o que é real (usado no build): firmware oficial da Panasonic, pacote publicado e versões assinadas.

    python tools/app_real_check.py <pacote.zip>

Faz o que o botão "Preparar pendrive" faz: baixa o firmware (91 MB) do site da Panasonic, confere, monta o
BDJ.jar conferindo cada parte com o manifesto, grava numa pasta que faz o papel do pendrive e confere de novo.
Depois procura atualização nas versões publicadas no GitHub (com a assinatura do projeto).
"""
from __future__ import annotations

import io
import sys
import tempfile
import zipfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from subdrive import VERSION, drives, update  # noqa: E402
from subdrive_app import acoes, lugares  # noqa: E402


def main():
    work = Path(tempfile.mkdtemp(prefix="subdrive-real-"))
    with zipfile.ZipFile(sys.argv[1]) as z:
        z.extractall(work / "download")
    pkg_dir = next((work / "download").glob("*/pacote"))
    with mock.patch.object(lugares, "program_dir", return_value=pkg_dir.parent):
        pkg = acoes.carregar_pacote(pkg_dir)
        print("pacote:", pkg.version, pkg.platform, "precisa montar o BDJ.jar:", pkg.needs_jar)
        print(acoes.confirmar_firmware(pkg))
        assert acoes.firmware_guardado(pkg) is None
        steps = []
        blob = acoes.baixar_firmware(pkg, progress=lambda d, t: steps.append(d))
        print("firmware baixado e conferido: %d bytes (%d avisos de progresso)" % (len(blob), len(steps)))
        assert acoes.firmware_guardado(pkg) == blob, "o firmware não ficou guardado para a próxima vez"
        acoes.montar_programa(pkg, blob)
        print("BDJ.jar montado e conferido com o manifesto: %d bytes" % len(pkg.files["BDJ.jar"]))
        usb = work / "PENDRIVE"; usb.mkdir()
        d = drives.Drive(path=usb, label="PENDRIVE", size=16_000_000_000, free=15_000_000_000, filesystem="FAT32",
                         scheme="MBR", partitions=1).judge()
        plano = acoes.planejar(d, pkg)
        print(plano.title); [print("  •", x) for x in plano.lines]
        acoes.gravar(d, pkg)
        again = acoes.planejar(d, pkg)
        assert again.nothing, again.lines
        with zipfile.ZipFile(usb / "BDJ.jar") as jar:
            assert jar.testzip() is None
        print("pendrive gravado e conferido:", sorted(p.name for p in usb.iterdir()))
    with mock.patch.object(lugares, "program_dir", return_value=work):
        try:
            rel = acoes.procurar_atualizacao()
            print("versões publicadas e assinadas conferidas; mais nova que %s: %s" % (VERSION, rel.version if rel else "nenhuma"))
        except acoes.Falha as e:
            print("atualização:", e.message)
            raise
    print("OK")


if __name__ == "__main__":
    main()
