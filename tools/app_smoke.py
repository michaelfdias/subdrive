"""Confere o SubDrive com janelas já empacotado, no sistema de verdade (usado no build de cada sistema).

    python tools/app_smoke.py <programa> <pasta de saída>

1. Autoteste sem janela: verificar, corrigir, criar PGS (vários processos) e aplicar a sincronia.
2. Abre a janela, espera, confere que continua aberta e tira uma foto da tela.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

SRT = "1\n00:00:01,000 --> 00:00:03,000\nOlá — tudo bem? ♪\n\n2\n00:00:04,000 --> 00:00:06,000\n<i>Sim, é isso.</i>\n"


def screenshot(target: Path):
    try:
        from PIL import ImageGrab
        img = ImageGrab.grab(xdisplay=os.environ["DISPLAY"]) if sys.platform.startswith("linux") else ImageGrab.grab()
        img.save(target)
        print("foto da tela:", target, img.size)
    except Exception as e:  # a foto ajuda a conferir; não é o teste
        print("sem foto da tela:", type(e).__name__, e)


def stop(p):
    """Fecha o programa e o processo filho (o programa de um arquivo só roda em dois processos)."""
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)], capture_output=True)
    else:
        p.terminate()
    try:
        p.wait(15)
    except subprocess.TimeoutExpired:
        p.kill()


def main():
    program, out = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
    out.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="subdrive-smoke-"))
    (work / "legendas").mkdir(); (work / "sincronia").mkdir()
    (work / "legendas" / "Filme.srt").write_text(SRT, encoding="utf-8")
    (work / "sincronia" / "Filme_2.srt.txt").write_text("versao=1\nponto=0,-500\n", encoding="utf-8")

    t = time.time()
    r = subprocess.run([str(program), "--autoteste", str(work / "legendas")], cwd=work, timeout=900)
    report = json.loads((work / "legendas" / "autoteste.json").read_text(encoding="utf-8"))
    print(json.dumps(report, indent=2, ensure_ascii=False))
    print("autoteste: código %d em %.1f s" % (r.returncode, time.time() - t))
    f = report["files"]["Filme.srt"]
    assert r.returncode == 0 and report["ok"] and report["frozen"], report
    assert f["fix"] == "Filme_2.srt" and f["pgs"] == "Filme.dark-yellow.sup" and f["pgs_check"] == "Pronto para o player", f
    assert f["sync"] == "Filme_3.srt", f
    sup = (work / "legendas" / "Filme.dark-yellow.sup").read_bytes()
    assert sup[:2] == b"PG" and len(sup) > 1000

    env = dict(os.environ)
    p = subprocess.Popen([str(program)], cwd=work, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(25)
    alive = p.poll() is None
    screenshot(out / ("janela-%s.png" % sys.platform))
    if sys.platform == "darwin" and ".app/" in str(program):
        # também como o Finder abre (LaunchServices)
        bundle = str(program).split(".app/")[0] + ".app"
        subprocess.run(["open", "-n", bundle], check=True)
        time.sleep(20)
        running = subprocess.run(["pgrep", "-f", bundle + "/Contents/MacOS/SubDrive"], capture_output=True, text=True).stdout.split()
        print("aberto pelo Finder (open):", running)
        screenshot(out / "janela-darwin-open.png")
        for pid in running:
            subprocess.run(["kill", pid])
        assert len(running) >= 2, "o SubDrive.app não abriu pelo open"
    stop(p)
    print("janela aberta depois de 25 s:", alive)
    assert alive, "a janela fechou sozinha (código %s)" % p.returncode
    print("OK")


if __name__ == "__main__":
    main()
