"""O SubDrive aceita exatamente o que o player aceita.

`paridade/player.json` traz arquivos de teste e o veredito do leitor de SRT do próprio player
(aceito ou recusado) para cada um.
"""
import base64, json, unittest
from pathlib import Path

from subdrive import core
from subdrive.regras.contrato import validar_bytes

PLAYER = json.loads((Path(__file__).parent / "paridade/player.json").read_text(encoding="utf-8"))


class ParidadeTests(unittest.TestCase):
    def test_mesmo_veredito_do_player(self):
        diferentes = []
        for f in PLAYER["files"]:
            data = base64.b64decode(f["data"])
            if validar_bytes(data).valido != (f["player"] == "ACCEPT"):
                diferentes.append("%s player=%s" % (f["name"], f["player"]))
        self.assertGreater(len(PLAYER["files"]), 600)
        self.assertEqual(diferentes, [])

    def test_fix_sempre_gera_arquivo_aceito(self):
        for f in PLAYER["files"]:
            data = base64.b64decode(f["data"])
            if f["player"] == "ACCEPT":
                continue
            fx = core.fix_srt(Path(f["name"]), data=data)
            if fx.ok:
                self.assertTrue(validar_bytes(fx.data).valido, f["name"])


if __name__ == "__main__":
    unittest.main()
