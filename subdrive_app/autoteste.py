"""Autoteste do programa empacotado: `SubDrive --autoteste <pasta>` (usado no build de cada sistema).

Verifica, corrige, cria PGS (em vários processos, como na janela) e aplica a sincronia nas legendas da pasta,
e grava o resultado em <pasta>/autoteste.json. Não abre janela.
"""
from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path


def run(folder: Path) -> int:
    from subdrive import VERSION, core, sync
    from . import acoes
    report = {"version": VERSION, "python": sys.version, "frozen": bool(getattr(sys, "frozen", False)), "files": {}, "ok": True}
    try:
        for path in core.subtitle_files(folder):
            r = report["files"][path.name] = {}
            v = acoes.verificar(path)
            r["check"] = [v.headline] + [p.text for p in v.problems]
            if path.suffix == ".srt" and not v.ok:
                fixed = acoes.corrigir(path)
                r["fix"] = fixed.output.name if fixed.output else None
                path = fixed.output or path
            if path.suffix == ".srt" and acoes.verificar(path).ok:
                res = acoes.criar_pgs(path, acoes.EstiloPGS(color="dark-yellow", font="inter", bold=True))
                r["pgs"] = res.output.name
                r["pgs_check"] = acoes.verificar(res.output).headline
            if sync.sync_file_for(path):
                r["sync"] = acoes.sincronizar(acoes.pontos(path)).output.name
        from subdrive import drives
        report["drives"] = [str(d.path) for d in drives.find()]
    except Exception:
        report["ok"] = False
        report["error"] = traceback.format_exc()
    (folder / "autoteste.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0 if report["ok"] else 1
