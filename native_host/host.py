"""
Native Messaging Host – Leitor de Certificados Digitais
=======================================================

Este programa roda no Windows e é chamado pelo Chrome (ou Edge) através do
protocolo "Chrome Native Messaging". A extensão envia mensagens JSON pela
entrada padrão e recebe respostas pela saída padrão.

Protocolo (por mensagem):
    [4 bytes little-endian uint32 = tamanho][JSON UTF-8]

Ações suportadas:
    {"action": "ping"}
    {"action": "list", "stores": ["MY"]}
    {"action": "delete", "id": "<hex do DER>", "store": "MY", "confirm_native": true}
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import os
import struct
import sys
import traceback

# Garante que stdin/stdout sejam binários puros no Windows (sem tradução
# de CRLF), caso contrário o protocolo quebra.
if sys.platform == "win32":
    import msvcrt

    msvcrt.setmode(sys.stdin.fileno(), os.O_BINARY)
    msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)

# Permite que este script rode em modo "dev" (python host.py) importando o
# cert_reader.py que fica na pasta pai. Em modo empacotado pelo PyInstaller,
# o cert_reader é embutido no executável.
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PARENT_DIR = os.path.dirname(_THIS_DIR)
if _PARENT_DIR not in sys.path:
    sys.path.insert(0, _PARENT_DIR)

from cert_reader import listar_certificados, remover_certificado  # noqa: E402


__version__ = "1.1.0"

# ---------------------------------------------------------------------------
# Segurança / limites
# ---------------------------------------------------------------------------

# Chrome limita mensagens a 1 MB em cada direção; definimos um teto menor
# para rejeitar rapidamente payloads maliciosos.
MAX_MESSAGE_BYTES = 128 * 1024

# Apenas o repositório pessoal pode ter certificados excluídos pela
# extensão. CA/ROOT envolvem cadeias de confiança do sistema e podem
# quebrar a segurança do navegador se removidos indevidamente.
STORES_PERMITIDOS_LEITURA = {"MY", "CA", "ROOT"}
STORES_PERMITIDOS_EXCLUSAO = {"MY"}

# Limite sanitário no tamanho do DER de um certificado (certificados
# reais giram em torno de 1-3 KB).
MAX_CERT_DER_BYTES = 32 * 1024


# ---------------------------------------------------------------------------
# Logging em arquivo (%LOCALAPPDATA%\LeitorCertificados\logs\)
# ---------------------------------------------------------------------------


def _log_dir() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, "LeitorCertificados", "logs")


def _setup_logging() -> logging.Logger:
    log_dir = _log_dir()
    try:
        os.makedirs(log_dir, exist_ok=True)
    except OSError:
        log_dir = None

    logger = logging.getLogger("cert_host")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    fmt = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    if log_dir:
        try:
            handler = logging.handlers.RotatingFileHandler(
                os.path.join(log_dir, "cert_host.log"),
                maxBytes=1 * 1024 * 1024,
                backupCount=3,
                encoding="utf-8",
            )
            handler.setFormatter(fmt)
            logger.addHandler(handler)
        except OSError:
            pass

    # Silencia log no stdout - ele é usado pelo protocolo; qualquer byte
    # acidental ali corromperia a comunicação com o Chrome.
    return logger


log = _setup_logging()


# ---------------------------------------------------------------------------
# Protocolo de mensagens (Chrome Native Messaging)
# ---------------------------------------------------------------------------


def read_message() -> dict | None:
    raw_length = sys.stdin.buffer.read(4)
    if len(raw_length) < 4:
        return None
    length = struct.unpack("<I", raw_length)[0]
    if length == 0:
        return None
    if length > MAX_MESSAGE_BYTES:
        log.warning("Mensagem recusada por tamanho: %d bytes", length)
        # Descarta os bytes restantes para não travar, e encerra.
        sys.stdin.buffer.read(length)
        raise ValueError(
            f"mensagem excede o tamanho maximo permitido ({MAX_MESSAGE_BYTES} bytes)"
        )
    data = sys.stdin.buffer.read(length)
    if len(data) < length:
        return None
    return json.loads(data.decode("utf-8"))


def send_message(obj: dict) -> None:
    data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    sys.stdout.buffer.write(struct.pack("<I", len(data)))
    sys.stdout.buffer.write(data)
    sys.stdout.buffer.flush()


# ---------------------------------------------------------------------------
# Confirmação nativa de exclusão (MessageBox do Windows)
# ---------------------------------------------------------------------------


def confirmar_exclusao_nativa(titulo: str, detalhe: str) -> bool:
    """Exibe um MessageBox nativo do Windows e retorna True se o usuario
    clicar em ``Sim``.

    Essa confirmação é importante porque uma extensão maliciosa (ou
    comprometida) pode falsificar confirmações em HTML. O prompt do
    Windows só pode ser acionado por um processo rodando como o próprio
    usuário – não tem como a extensão simular esse clique.
    """
    if sys.platform != "win32":
        return True
    try:
        import ctypes

        MB_YESNO = 0x00000004
        MB_ICONWARNING = 0x00000030
        MB_DEFBUTTON2 = 0x00000100
        MB_TOPMOST = 0x00040000
        MB_SETFOREGROUND = 0x00010000

        flags = (
            MB_YESNO
            | MB_ICONWARNING
            | MB_DEFBUTTON2
            | MB_TOPMOST
            | MB_SETFOREGROUND
        )
        IDYES = 6

        mensagem = (
            f"{detalhe}\n\n"
            "Esta operação é IRREVERSÍVEL e remove o certificado do "
            "repositório do Windows.\n\n"
            "Deseja prosseguir?"
        )
        resultado = ctypes.windll.user32.MessageBoxW(
            0, mensagem, titulo, flags
        )
        return resultado == IDYES
    except Exception:
        log.exception("Falha ao exibir MessageBox nativa")
        return False


# ---------------------------------------------------------------------------
# Serialização dos certificados
# ---------------------------------------------------------------------------


def cert_to_dict(c) -> dict:
    return {
        # Id usado pelo front-end para pedir a exclusão. Guardamos o DER em
        # hexadecimal para garantir que sobrevive à serialização JSON.
        "id": c.raw_der.hex() if c.raw_der else "",
        "store": c.store,
        "tipo": c.tipo,
        "titular_nome": c.titular_nome,
        "cpf": c.cpf,
        "cnpj": c.cnpj,
        "empresa": c.empresa,
        "responsavel_nome": c.responsavel_nome,
        "responsavel_cpf": c.responsavel_cpf,
        "data_nascimento": c.data_nascimento,
        "pis": c.pis,
        "rg": c.rg,
        "email": c.email,
        "emissor": c.emissor,
        "numero_serie": c.numero_serie,
        "data_emissao": c.data_emissao.isoformat() if c.data_emissao else None,
        "data_vencimento": (
            c.data_vencimento.isoformat() if c.data_vencimento else None
        ),
        "dias_para_vencer": c.dias_para_vencer,
        "valido": c.valido,
        "warnings": list(c.warnings),
    }


# ---------------------------------------------------------------------------
# Handlers de ação
# ---------------------------------------------------------------------------


def _handle_list(msg: dict) -> dict:
    stores = msg.get("stores") or ["MY"]
    if not isinstance(stores, list):
        return {"ok": False, "error": "campo 'stores' deve ser uma lista"}

    # Whitelist estrita - rejeita qualquer repositorio nao conhecido.
    stores_validos: list[str] = []
    for s in stores:
        if not isinstance(s, str):
            return {"ok": False, "error": "itens de 'stores' devem ser strings"}
        s = s.strip().upper()
        if s not in STORES_PERMITIDOS_LEITURA:
            return {
                "ok": False,
                "error": f"repositorio nao permitido: {s!r}",
            }
        if s not in stores_validos:
            stores_validos.append(s)

    if not stores_validos:
        return {"ok": False, "error": "nenhum repositorio valido informado"}

    log.info("list stores=%s", stores_validos)
    certs = listar_certificados(tuple(stores_validos))
    return {
        "ok": True,
        "certificados": [cert_to_dict(c) for c in certs],
    }


def _handle_delete(msg: dict) -> dict:
    der_hex = msg.get("id") or ""
    store = (msg.get("store") or "MY").strip().upper()

    if store not in STORES_PERMITIDOS_EXCLUSAO:
        log.warning(
            "Tentativa de exclusao bloqueada em store proibido: %s", store
        )
        return {
            "ok": False,
            "error": (
                f"exclusao nao permitida no repositorio {store!r}. "
                "Apenas o repositorio pessoal (MY) permite exclusao via "
                "esta extensao; use certmgr.msc como administrador para "
                "mexer em CA/ROOT."
            ),
        }

    if not isinstance(der_hex, str) or not der_hex:
        return {"ok": False, "error": "id vazio"}
    if len(der_hex) > MAX_CERT_DER_BYTES * 2:
        return {"ok": False, "error": "id excede o tamanho maximo"}

    try:
        der = bytes.fromhex(der_hex)
    except ValueError:
        return {"ok": False, "error": "id invalido (esperado hex)"}

    if len(der) < 16 or len(der) > MAX_CERT_DER_BYTES:
        return {"ok": False, "error": "tamanho do DER invalido"}

    # Inspeciona o DER ANTES de excluir para compor a confirmacao nativa
    # e garantir auditoria.
    try:
        from cryptography import x509
        from cryptography.hazmat.backends import default_backend

        cert = x509.load_der_x509_certificate(der, default_backend())
        titular = ""
        try:
            from cryptography.x509.oid import NameOID

            attrs = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
            if attrs:
                titular = attrs[0].value
        except Exception:
            titular = ""
        serial_hex = f"{cert.serial_number:X}"
    except Exception:
        titular = "(desconhecido)"
        serial_hex = "(desconhecido)"

    detalhe = (
        f"Titular: {titular or '(sem CN)'}\n"
        f"Numero de serie: {serial_hex}\n"
        f"Repositorio: {store}"
    )

    # Se a extensao pediu confirmacao nativa (recomendado), exibe o
    # MessageBox do Windows antes de executar qualquer operacao.
    confirm_native = bool(msg.get("confirm_native", True))
    if confirm_native and not confirmar_exclusao_nativa(
        "Excluir certificado digital", detalhe
    ):
        log.info("Exclusao cancelada pelo usuario (MessageBox): %s", serial_hex)
        return {"ok": False, "error": "Exclusao cancelada pelo usuario.", "canceled": True}

    log.info("delete store=%s serial=%s titular=%r", store, serial_hex, titular)
    remover_certificado(der, store)
    log.info("delete OK serial=%s", serial_hex)
    return {"ok": True, "serial": serial_hex}


def handle(msg: dict) -> dict:
    action = (msg or {}).get("action")

    if action == "ping":
        return {"ok": True, "pong": True, "version": __version__}

    if action == "list":
        return _handle_list(msg)

    if action == "delete":
        return _handle_delete(msg)

    return {"ok": False, "error": f"acao desconhecida: {action!r}"}


# ---------------------------------------------------------------------------
# Loop principal
# ---------------------------------------------------------------------------


def main() -> None:
    log.info("cert_host iniciado (v%s, pid=%d)", __version__, os.getpid())
    try:
        while True:
            try:
                msg = read_message()
            except Exception as exc:
                log.exception("Falha ao ler mensagem")
                try:
                    send_message(
                        {"ok": False, "error": f"Falha ao ler mensagem: {exc}"}
                    )
                except Exception:
                    pass
                return
            if msg is None:
                return
            try:
                resp = handle(msg)
            except Exception as exc:
                log.exception("Excecao no handler")
                resp = {
                    "ok": False,
                    "error": str(exc),
                    "trace": traceback.format_exc(),
                }
            try:
                send_message(resp)
            except Exception:
                log.exception("Falha ao enviar resposta")
                return
    finally:
        log.info("cert_host finalizado")


if __name__ == "__main__":
    main()
