"""Nomes de arquivo, leitura segura, conferência de pasta e gravação atômica."""

from __future__ import annotations

import errno
import os
import secrets
import stat
import unicodedata
from dataclasses import dataclass, field

from .contrato import (MAX_ITENS_PASTA, NOME_MAX, NOME_MIN, Diagnostico, ResultadoValidacao,
                       validar_bytes)
from .erros import ArquivoIncompativel, ErroAcesso, ErroUso
from .util import escapar, fmt_int, sha256, unidades_utf16

LIMITE_LEITURA = 64 * 1024 * 1024  # proteção de memória; muito acima do contrato
_PORTABILIDADE = set('<>"|?*')


# ------------------------------------------------------------------ nomes

def _char_nome_ok(c: str) -> bool:
    o = ord(c)
    return (0x20 <= o <= 0x7E or 0xA0 <= o <= 0xFF) and c not in "/\\:"


def _caracteres_ruins(nome: str) -> list:
    return [c for c in nome if not _char_nome_ok(c)]


def validar_nome(nome: str) -> list:
    """Erros e avisos do nome (incluindo extensão), exatamente como está gravado."""
    d = []
    tam = unidades_utf16(nome)
    alternativa = nome_alternativo(nome)
    sug_alt = f"use o nome alternativo '{escapar(alternativa)}'" if alternativa != nome else ""
    if tam < NOME_MIN:
        d.append(Diagnostico("NOME_CURTO", f"o nome tem {tam} caracteres; mínimo: {NOME_MIN}",
                             "use um nome como 'Filme.srt'"))
    if tam > NOME_MAX:
        d.append(Diagnostico("NOME_LONGO", f"o nome tem {fmt_int(tam)} caracteres; máximo: {NOME_MAX}",
                             sug_alt or "encurte o nome"))
    if not nome.endswith(".srt"):
        if nome.lower().endswith(".srt"):
            d.append(Diagnostico("NOME_EXTENSAO", "a extensão deve ser .srt em minúsculas",
                                 sug_alt or "renomeie para terminar em .srt"))
        else:
            d.append(Diagnostico("NOME_EXTENSAO", "o nome deve terminar em .srt",
                                 sug_alt or "renomeie para terminar em .srt"))
    if nome.startswith("."):
        d.append(Diagnostico("NOME_OCULTO", "o nome começa com ponto (arquivo oculto)",
                             "arquivos '._*' são criados pelo macOS; não são legendas"
                             if nome.startswith("._") else "renomeie sem o ponto inicial"))
    ruins = _caracteres_ruins(nome)
    if ruins:
        lista = ", ".join(f"U+{ord(c):04X}" for c in dict.fromkeys(ruins))
        nfc = unicodedata.normalize("NFC", nome)
        if nfc != nome and not _caracteres_ruins(nfc):
            motivo = f"nome com acentos decompostos (NFD): {lista}"
        else:
            motivo = f"caracteres não permitidos no nome: {lista}"
        d.append(Diagnostico("NOME_CARACTERE", motivo, sug_alt or "renomeie o arquivo"))
    base = nome[:-4] if nome.lower().endswith(".srt") else nome
    if any(c in _PORTABILIDADE for c in nome) or base.endswith((" ", ".")) or nome.startswith(" "):
        d.append(Diagnostico("NOME_PORTABILIDADE",
                             "o nome tem caracteres ou espaços/pontos nas pontas que outros "
                             "sistemas podem rejeitar", "prefira letras, números, '-' e '_'",
                             severidade="aviso"))
    return d


def _limpar_base(base: str, so_ascii: bool) -> str:
    saida = []
    for c in unicodedata.normalize("NFC", base):
        if _char_nome_ok(c) and (not so_ascii or ord(c) < 0x80):
            saida.append(c)
            continue
        dec = "".join(x for x in unicodedata.normalize("NFKD", c) if not unicodedata.combining(x))
        dec = "".join(x for x in dec if _char_nome_ok(x) and (not so_ascii or ord(x) < 0x80))
        saida.append(dec or "_")
    r = "".join(saida).strip(" ").lstrip(".")
    return r or "legenda"


def montar_nome(base: str, sufixo: str | None = None, so_ascii: bool = False) -> str:
    base = _limpar_base(base, so_ascii)
    final = (f".{sufixo}" if sufixo else "") + ".srt"
    maximo = NOME_MAX - len(final)
    base = base[:maximo].rstrip(" ")
    nome = base + final
    while len(nome) < NOME_MIN:
        nome = "_" + nome
    return nome


def _base_de(nome: str) -> str:
    return nome[:-4] if nome.lower().endswith(".srt") else nome


def nome_alternativo(nome: str) -> str:
    """Nome compatível mais próximo: NFC e, se preciso, ASCII."""
    if not [d for d in _diagnosticos_basicos(nome)]:
        return nome
    candidato = montar_nome(_base_de(nome))
    if not _diagnosticos_basicos(candidato):
        return candidato
    return montar_nome(_base_de(nome), so_ascii=True)


def _diagnosticos_basicos(nome: str) -> list:
    erros = []
    tam = unidades_utf16(nome)
    if tam < NOME_MIN or tam > NOME_MAX or not nome.endswith(".srt") or nome.startswith("."):
        erros.append(True)
    if _caracteres_ruins(nome):
        erros.append(True)
    return erros


def nome_alternativo_ascii(nome: str) -> str:
    """Somente ASCII: útil quando o sistema de arquivos reescreve acentos (NFD)."""
    return montar_nome(_base_de(nome), so_ascii=True)


def nome_sugerido(nome_entrada: str, sufixo: str = "preparada") -> str:
    nome = montar_nome(_base_de(nome_entrada), sufixo)
    if _diagnosticos_basicos(nome):
        nome = montar_nome(_base_de(nome_entrada), sufixo, so_ascii=True)
    return nome


def nome_real(caminho: str) -> str:
    """Nome como o sistema de arquivos o lista (revela NFC/NFD e caixa reais)."""
    pasta, nome = os.path.split(os.path.abspath(caminho))
    try:
        itens = os.listdir(pasta)
    except OSError:
        return nome
    if nome in itens:
        return nome
    alvo = unicodedata.normalize("NFC", nome)
    iguais = [x for x in itens if unicodedata.normalize("NFC", x) == alvo]
    if len(iguais) == 1:
        return iguais[0]
    iguais = [x for x in itens if unicodedata.normalize("NFC", x).casefold() == alvo.casefold()]
    if len(iguais) == 1:
        return iguais[0]
    return nome


def _chave_colisao(nome: str) -> str:
    return unicodedata.normalize("NFC", nome).casefold()


def colisao_na_pasta(pasta: str, nome: str) -> str | None:
    """Item existente que colide por caixa ou normalização (ex.: 'a.srt' x 'A.srt')."""
    try:
        itens = os.listdir(pasta)
    except OSError:
        return None
    chave = _chave_colisao(nome)
    for item in itens:
        if _chave_colisao(item) == chave:
            return item
    return None


# --------------------------------------------------------------- caminhos

def link_no_caminho(caminho: str) -> str | None:
    """Primeiro componente do caminho absoluto que é link simbólico."""
    p = os.path.abspath(caminho)
    atual = os.path.sep
    for parte in p.split(os.path.sep):
        if not parte:
            continue
        atual = os.path.join(atual, parte)
        if os.path.islink(atual):
            return atual
    return None


def limpar_caminho_digitado(texto: str) -> str:
    """Remove aspas e escapes de arrastar-e-soltar do Terminal do macOS."""
    t = texto.strip()
    if len(t) >= 2 and t[0] == t[-1] and t[0] in "'\"":
        t = t[1:-1]
    else:
        t = t.replace("\\ ", " ")
    return os.path.expanduser(t)


def ler_arquivo(caminho: str) -> tuple:
    """Lê o arquivo regular sem seguir links. Retorna (bytes, nome_real)."""
    p = os.path.abspath(caminho)
    if not os.path.lexists(p):
        raise ErroAcesso("ARQUIVO_NAO_ENCONTRADO", f"arquivo não encontrado: {escapar(caminho, 120)}",
                         "confira o caminho; no Terminal você pode arrastar o arquivo para a janela")
    link = link_no_caminho(p)
    if link:
        real = os.path.realpath(p)
        raise ArquivoIncompativel(
            "LINK_SIMBOLICO", f"o caminho passa por um link simbólico: {escapar(link, 120)}",
            f"use o arquivo real: {escapar(real, 120)}")
    st = os.lstat(p)
    if stat.S_ISDIR(st.st_mode):
        raise ErroUso("ENTRADA_E_PASTA", "o caminho informado é uma pasta",
                      "para conferir uma pasta, informe a pasta")
    if not stat.S_ISREG(st.st_mode):
        raise ArquivoIncompativel("ARQUIVO_NAO_REGULAR", "o caminho não é um arquivo regular",
                                  "escolha o arquivo .srt propriamente dito")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        fd = os.open(p, flags)
    except PermissionError:
        raise ErroAcesso("SEM_PERMISSAO", f"sem permissão para ler: {escapar(caminho, 120)}",
                         "confira as permissões do arquivo") from None
    except OSError as e:
        raise ErroAcesso("FALHA_LEITURA", f"não foi possível abrir o arquivo ({e.strerror})",
                         "confira o caminho e tente novamente") from None
    try:
        fst = os.fstat(fd)
        if not stat.S_ISREG(fst.st_mode):
            raise ArquivoIncompativel("ARQUIVO_NAO_REGULAR", "o caminho não é um arquivo regular",
                                      "escolha o arquivo .srt propriamente dito")
        if fst.st_size > LIMITE_LEITURA:
            raise ArquivoIncompativel(
                "TAMANHO_EXCEDIDO", f"{fmt_int(fst.st_size)} bytes: grande demais para uma legenda",
                "escolha o arquivo de legenda correto")
        partes = []
        while True:
            bloco = os.read(fd, 1 << 20)
            if not bloco:
                break
            partes.append(bloco)
    except OSError as e:
        raise ErroAcesso("FALHA_LEITURA", f"falha ao ler o arquivo ({e.strerror})",
                         "tente novamente") from None
    finally:
        os.close(fd)
    return b"".join(partes), nome_real(p)


def validar_arquivo(caminho: str) -> tuple:
    """Validação integral (bytes + nome real). Retorna (resultado, nome_real, dados|None)."""
    try:
        dados, nome = ler_arquivo(caminho)
    except ArquivoIncompativel as e:
        res = ResultadoValidacao()
        res.erro(e.codigo, e.motivo, e.sugestao)
        res.interrompido = True
        return res, os.path.basename(caminho), None
    res = validar_bytes(dados)
    for d in validar_nome(nome):
        res.adicionar(d)
    return res, nome, dados


# ------------------------------------------------------------------ pasta

@dataclass
class ResultadoPasta:
    caminho: str
    total_itens: int = 0
    legendas: list = field(default_factory=list)  # (nome, ResultadoValidacao)
    ignorados: list = field(default_factory=list)  # (nome, motivo)
    diagnosticos: list = field(default_factory=list)

    @property
    def valido(self) -> bool:
        return (not [d for d in self.diagnosticos if d.severidade == "erro"]
                and all(r.valido for _n, r in self.legendas))

    def como_dict(self) -> dict:
        return {
            "caminho": self.caminho,
            "itens_diretos": self.total_itens,
            "limite_itens": MAX_ITENS_PASTA,
            "valido": self.valido,
            "diagnosticos": [d.como_dict() for d in self.diagnosticos],
            "legendas": [{"nome": n, **r.como_dict()} for n, r in self.legendas],
            "ignorados": [{"nome": n, "motivo": m} for n, m in self.ignorados],
        }


def validar_pasta(caminho: str) -> ResultadoPasta:
    p = os.path.abspath(caminho)
    if not os.path.lexists(p):
        raise ErroAcesso("PASTA_NAO_ENCONTRADA", f"pasta não encontrada: {escapar(caminho, 120)}",
                         "confira o caminho")
    link = link_no_caminho(p)
    if link:
        raise ArquivoIncompativel("LINK_SIMBOLICO",
                                  f"o caminho passa por um link simbólico: {escapar(link, 120)}",
                                  f"use a pasta real: {escapar(os.path.realpath(p), 120)}")
    if not os.path.isdir(p):
        raise ErroUso("DIRETORIO_NAO_E_PASTA", "o caminho informado não é uma pasta",
                      "para conferir um arquivo, informe o arquivo")
    res = ResultadoPasta(caminho=p)
    try:
        itens = sorted(os.scandir(p), key=lambda x: x.name)
    except PermissionError:
        raise ErroAcesso("SEM_PERMISSAO", "sem permissão para listar a pasta",
                         "confira as permissões") from None
    res.total_itens = len(itens)
    if res.total_itens > MAX_ITENS_PASTA:
        res.diagnosticos.append(Diagnostico(
            "PASTA_ITENS_EXCEDIDOS",
            f"{res.total_itens} itens diretamente na pasta (incluindo ocultos); máximo: "
            f"{MAX_ITENS_PASTA}", "retire itens da pasta; esta ferramenta não apaga nada sozinha"))
    for it in itens:
        nome = it.name
        eh_srt = nome.lower().endswith(".srt")
        if it.is_symlink():
            if eh_srt:
                r = ResultadoValidacao()
                r.erro("LINK_SIMBOLICO", "link simbólico não é aceito (não foi seguido)",
                       "copie o arquivo real para a pasta")
                res.legendas.append((nome, r))
            else:
                res.ignorados.append((nome, "link simbólico (não seguido)"))
        elif it.is_dir(follow_symlinks=False):
            res.ignorados.append((nome, "subpasta (não verificada; conta no limite)"))
        elif it.is_file(follow_symlinks=False):
            if eh_srt:
                r, _nome, _dados = validar_arquivo(it.path)
                res.legendas.append((nome, r))
            elif nome.startswith("."):
                res.ignorados.append((nome, "item oculto (talvez criado pelo macOS; conta no limite)"))
            else:
                res.ignorados.append((nome, "não é .srt"))
        else:
            res.ignorados.append((nome, "item especial (não é arquivo regular)"))
    return res


# --------------------------------------------------------------- gravação

def verificar_destino(caminho_saida: str, caminho_entrada: str | None = None) -> None:
    """Recusa destino existente, colisões por caixa/normalização, links e a própria entrada."""
    p = os.path.abspath(caminho_saida)
    pasta, nome = os.path.split(p)
    if caminho_entrada is not None:
        e = os.path.abspath(caminho_entrada)
        mesmo = _chave_colisao(e) == _chave_colisao(p)
        if not mesmo and os.path.exists(p):
            try:
                mesmo = os.path.samefile(e, p)
            except OSError:
                mesmo = False
        if mesmo:
            raise ErroAcesso("SAIDA_IGUAL_ENTRADA", "o destino é o próprio arquivo de entrada",
                             "escolha um nome novo; o original nunca é alterado")
    if not os.path.isdir(pasta):
        raise ErroAcesso("PASTA_DESTINO_INEXISTENTE",
                         f"a pasta de destino não existe: {escapar(pasta, 120)}",
                         "crie a pasta ou escolha outro destino")
    link = link_no_caminho(pasta)
    if link:
        raise ErroAcesso("LINK_SIMBOLICO", f"o destino passa por um link simbólico: {escapar(link, 120)}",
                         f"use o caminho real: {escapar(os.path.realpath(pasta), 120)}")
    if os.path.lexists(p):
        raise ErroAcesso("DESTINO_EXISTE", f"o destino já existe: {escapar(nome, 120)}",
                         "escolha outro nome; nada é sobrescrito")
    outro = colisao_na_pasta(pasta, nome)
    if outro is not None:
        raise ErroAcesso("DESTINO_COLISAO",
                         f"já existe '{escapar(outro, 120)}', que colide com o destino por "
                         "maiúsculas/minúsculas ou acentuação", "escolha um nome realmente diferente")


def _fsync_pasta(pasta: str) -> None:
    try:
        fd = os.open(pasta, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def _escrever_exclusivo(caminho: str, dados: bytes) -> None:
    # O_BINARY: on Windows a plain os.open() would turn every "\n" into "\r\n".
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    fd = os.open(caminho, flags, 0o644)
    try:
        vista = memoryview(dados)
        while vista:
            n = os.write(fd, vista)
            vista = vista[n:]
        os.fsync(fd)
    finally:
        os.close(fd)


_ERRNOS_SEM_LINK = {errno.EPERM, errno.ENOTSUP, errno.EOPNOTSUPP, errno.EXDEV, errno.EMLINK,
                    errno.ENOSYS, errno.EACCES}


def gravar_exclusivo(caminho_saida: str, dados: bytes) -> None:
    """Grava sem sobrescrever: temporário na mesma pasta + link exclusivo
    (atômico). Em sistemas sem links (ex.: exFAT) cria o destino com O_EXCL
    e apaga a cópia parcial se a escrita falhar."""
    p = os.path.abspath(caminho_saida)
    pasta = os.path.dirname(p)
    tmp = os.path.join(pasta, f".subdrive-{secrets.token_hex(6)}.tmp")
    try:
        _escrever_exclusivo(tmp, dados)
        try:
            os.link(tmp, p)
        except FileExistsError:
            raise
        except OSError as e:
            if e.errno not in _ERRNOS_SEM_LINK:
                raise
            try:
                _escrever_exclusivo(p, dados)
            except FileExistsError:
                raise
            except OSError:
                remover_copia(p)
                raise
    except FileExistsError:
        raise ErroAcesso("DESTINO_EXISTE", "o destino passou a existir durante a gravação",
                         "escolha outro nome; nada foi sobrescrito") from None
    except OSError as e:
        raise ErroAcesso("FALHA_ESCRITA", f"falha ao gravar a cópia ({e.strerror or e})",
                         "confira espaço livre e permissões; o original não foi alterado") from None
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass
    _fsync_pasta(pasta)


@dataclass
class Conferencia:
    ok: bool
    sha256: str | None
    nome_real: str | None
    validacao: ResultadoValidacao | None
    problemas: list = field(default_factory=list)  # Diagnostico

    def como_dict(self) -> dict:
        return {
            "ok": self.ok, "sha256_relido": self.sha256, "nome_real": self.nome_real,
            "validacao": self.validacao.como_dict() if self.validacao else None,
            "problemas": [d.como_dict() for d in self.problemas],
        }


def conferir_gravacao(caminho_saida: str, esperado: bytes) -> Conferencia:
    """Relê o arquivo gravado: hash, validação integral e nome real."""
    try:
        dados, nome = ler_arquivo(caminho_saida)
    except Exception as e:  # noqa: BLE001 - qualquer falha invalida a conferência
        motivo = getattr(e, "motivo", str(e))
        return Conferencia(False, None, None, None,
                           [Diagnostico("RELEITURA_FALHOU", f"não foi possível reler a cópia: {motivo}",
                                        "tente gravar novamente")])
    problemas = []
    h = sha256(dados)
    if h != sha256(esperado):
        problemas.append(Diagnostico("HASH_DIVERGENTE", "os bytes relidos diferem dos bytes gravados",
                                     "tente gravar novamente em outro local"))
    res = validar_bytes(dados)
    for d in validar_nome(nome):
        res.adicionar(d)
    ok = not problemas and res.valido
    return Conferencia(ok, h, nome, res, problemas)


def remover_copia(caminho: str) -> bool:
    try:
        os.unlink(caminho)
        return True
    except OSError:
        return False
