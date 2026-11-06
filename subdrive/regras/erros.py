"""Exceções com código estável, motivo e sugestão em português."""

from __future__ import annotations


class ErroSubDrive(Exception):
    """Base. `codigo_saida` segue a convenção: 1 incompatível, 2 argumentos/acesso/escrita."""

    codigo_saida = 2

    def __init__(self, codigo: str, motivo: str, sugestao: str = ""):
        super().__init__(motivo)
        self.codigo = codigo
        self.motivo = motivo
        self.sugestao = sugestao

    def como_dict(self) -> dict:
        return {"codigo": self.codigo, "motivo": self.motivo, "sugestao": self.sugestao}


class ErroUso(ErroSubDrive):
    """Argumento ausente, inválido ou combinação proibida (código 2)."""


class ErroAcesso(ErroSubDrive):
    """Arquivo inexistente, sem permissão, destino em conflito ou falha de escrita (código 2)."""


class ArquivoIncompativel(ErroSubDrive):
    """O alvo existe, mas viola o contrato antes mesmo da leitura (ex.: link simbólico)."""

    codigo_saida = 1
