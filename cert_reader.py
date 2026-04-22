"""
Leitor de certificados digitais do repositório do Windows.

Usa a API nativa do Windows (crypt32.dll) via ctypes para enumerar os
certificados instalados e a biblioteca `cryptography` para decodificar
o conteúdo X.509 em formato DER.

Campos ICP-Brasil (RFC/ITI) reconhecidos no SubjectAlternativeName (otherName):

    OID                  Descrição
    -----------------    ----------------------------------------------------
    2.16.76.1.3.1        Pessoa Física - dadosNasc(8) + CPF(11) + PIS(11)
                         + RG(15) + órgão/UF(6)
    2.16.76.1.3.2        Nome do responsável pelo certificado (e-CNPJ)
    2.16.76.1.3.3        CNPJ da pessoa jurídica
    2.16.76.1.3.4        Dados do responsável pelo e-CNPJ
                         (mesmo formato do 3.1)
    2.16.76.1.3.5        Título de eleitor (12 dígitos)
    2.16.76.1.3.6        CEI da pessoa jurídica (12 dígitos)
    2.16.76.1.3.7        CEI da pessoa física (12 dígitos)
    2.16.76.1.4.x        Campos de profissionais (OAB, CRM, etc.)
"""

from __future__ import annotations

import ctypes
import datetime
from ctypes import wintypes
from dataclasses import dataclass, field
from typing import Iterable

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.x509.oid import ExtensionOID, NameOID


__version__ = "1.1.0"


# ---------------------------------------------------------------------------
# Integração com a API do Windows (crypt32.dll)
# ---------------------------------------------------------------------------

X509_ASN_ENCODING = 0x00000001
PKCS_7_ASN_ENCODING = 0x00010000
CERT_ENCODING = X509_ASN_ENCODING | PKCS_7_ASN_ENCODING


class _CertContext(ctypes.Structure):
    _fields_ = [
        ("dwCertEncodingType", wintypes.DWORD),
        ("pbCertEncoded", ctypes.POINTER(ctypes.c_ubyte)),
        ("cbCertEncoded", wintypes.DWORD),
        ("pCertInfo", ctypes.c_void_p),
        ("hCertStore", wintypes.HANDLE),
    ]


_PCERT_CONTEXT = ctypes.POINTER(_CertContext)


def _load_crypt32():
    crypt32 = ctypes.WinDLL("crypt32.dll", use_last_error=True)

    crypt32.CertOpenSystemStoreW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    crypt32.CertOpenSystemStoreW.restype = wintypes.HANDLE

    crypt32.CertEnumCertificatesInStore.argtypes = [wintypes.HANDLE, _PCERT_CONTEXT]
    crypt32.CertEnumCertificatesInStore.restype = _PCERT_CONTEXT

    crypt32.CertCloseStore.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    crypt32.CertCloseStore.restype = wintypes.BOOL

    crypt32.CertFreeCertificateContext.argtypes = [_PCERT_CONTEXT]
    crypt32.CertFreeCertificateContext.restype = wintypes.BOOL

    crypt32.CertDeleteCertificateFromStore.argtypes = [_PCERT_CONTEXT]
    crypt32.CertDeleteCertificateFromStore.restype = wintypes.BOOL
    return crypt32


def _iter_raw_certificates(store_name: str) -> Iterable[bytes]:
    """Percorre o repositório informado devolvendo os bytes DER de cada cert."""
    crypt32 = _load_crypt32()
    h_store = crypt32.CertOpenSystemStoreW(None, store_name)
    if not h_store:
        raise OSError(
            f"Não foi possível abrir o repositório '{store_name}'. "
            f"Código: {ctypes.get_last_error()}"
        )
    try:
        p_cert = crypt32.CertEnumCertificatesInStore(h_store, None)
        while p_cert:
            cert = p_cert.contents
            size = cert.cbCertEncoded
            data = bytes(cert.pbCertEncoded[:size])
            yield data
            p_cert = crypt32.CertEnumCertificatesInStore(h_store, p_cert)
    finally:
        crypt32.CertCloseStore(h_store, 0)


# ---------------------------------------------------------------------------
# Modelo de dados
# ---------------------------------------------------------------------------


@dataclass
class CertificadoInfo:
    """Resumo amigável de um certificado X.509."""

    store: str
    titular_nome: str = ""
    tipo: str = ""  # e-CPF, e-CNPJ, Outro
    cpf: str = ""
    cnpj: str = ""
    empresa: str = ""
    responsavel_nome: str = ""
    responsavel_cpf: str = ""
    data_nascimento: str = ""
    pis: str = ""
    rg: str = ""
    email: str = ""
    emissor: str = ""
    numero_serie: str = ""
    data_emissao: datetime.datetime | None = None
    data_vencimento: datetime.datetime | None = None
    algoritmo: str = ""
    uso_chave: list[str] = field(default_factory=list)
    outros_sans: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    # Bytes DER brutos – usados para localizar o certificado no repositório
    # do Windows na hora de excluir.
    raw_der: bytes = b""

    @property
    def valido(self) -> bool:
        if not self.data_vencimento:
            return False
        return datetime.datetime.now(datetime.timezone.utc) <= self.data_vencimento

    @property
    def dias_para_vencer(self) -> int | None:
        if not self.data_vencimento:
            return None
        delta = self.data_vencimento - datetime.datetime.now(datetime.timezone.utc)
        return delta.days


# ---------------------------------------------------------------------------
# Decodificação dos campos ICP-Brasil
# ---------------------------------------------------------------------------


OID_PF = "2.16.76.1.3.1"
OID_RESP_NOME = "2.16.76.1.3.2"
OID_CNPJ = "2.16.76.1.3.3"
OID_RESP_PF = "2.16.76.1.3.4"
OID_TITULO_ELEITOR = "2.16.76.1.3.5"
OID_CEI_PJ = "2.16.76.1.3.6"
OID_CEI_PF = "2.16.76.1.3.7"


def _extract_utf8_value(raw: bytes) -> str:
    """
    Extrai o conteúdo textual de um otherName ICP-Brasil.

    Na ASN.1, o valor vem empacotado como uma string UTF-8 / IA5
    (tag 0x0C ou 0x16) dentro do otherName. Fazemos uma leitura
    tolerante para não quebrar em variações entre AC's.
    """
    if not raw:
        return ""
    # cabeçalho ASN.1 básico: <tag><len><conteudo>
    if len(raw) >= 2 and raw[0] in (0x0C, 0x13, 0x16, 0x1E):
        length = raw[1]
        data = raw[2 : 2 + length]
        try:
            return data.decode("utf-8").strip()
        except UnicodeDecodeError:
            return data.decode("latin-1", errors="replace").strip()
    # fallback: tenta decodificar tudo como utf-8
    try:
        return raw.decode("utf-8").strip().strip("\x00")
    except UnicodeDecodeError:
        return raw.decode("latin-1", errors="replace").strip()


def _parse_dados_pf(texto: str):
    """Quebra o campo de 51 caracteres: dataNasc + CPF + PIS + RG + órgão."""
    digits = "".join(c for c in texto if c.isalnum())
    if len(digits) < 19:
        return {}
    nasc_raw = digits[0:8]
    cpf = digits[8:19]
    pis = digits[19:30] if len(digits) >= 30 else ""
    rg = digits[30:45] if len(digits) >= 45 else ""
    orgao = digits[45:51] if len(digits) >= 51 else ""
    try:
        nasc = datetime.datetime.strptime(nasc_raw, "%d%m%Y").date().isoformat()
    except ValueError:
        nasc = nasc_raw
    return {
        "data_nascimento": nasc,
        "cpf": cpf,
        "pis": pis,
        "rg": f"{rg} {orgao}".strip() if rg else "",
    }


def _format_cpf(cpf: str) -> str:
    cpf = "".join(c for c in cpf if c.isdigit())
    if len(cpf) != 11:
        return cpf
    return f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}"


def _format_cnpj(cnpj: str) -> str:
    cnpj = "".join(c for c in cnpj if c.isdigit())
    if len(cnpj) != 14:
        return cnpj
    return f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}"


# ---------------------------------------------------------------------------
# Conversão certificado -> CertificadoInfo
# ---------------------------------------------------------------------------


def _subject_field(cert: x509.Certificate, oid) -> str:
    try:
        attrs = cert.subject.get_attributes_for_oid(oid)
    except Exception:
        return ""
    if not attrs:
        return ""
    return attrs[0].value


def _issuer_common_name(cert: x509.Certificate) -> str:
    try:
        attrs = cert.issuer.get_attributes_for_oid(NameOID.COMMON_NAME)
    except Exception:
        return ""
    if not attrs:
        return ""
    return attrs[0].value


def _parse_certificate(cert_der: bytes, store_name: str) -> CertificadoInfo:
    info = CertificadoInfo(store=store_name)
    info.raw_der = cert_der
    try:
        cert = x509.load_der_x509_certificate(cert_der, default_backend())
    except Exception as exc:
        info.warnings.append(f"Falha ao decodificar X.509: {exc}")
        return info

    # Campos básicos
    info.titular_nome = _subject_field(cert, NameOID.COMMON_NAME)
    info.empresa = _subject_field(cert, NameOID.ORGANIZATION_NAME)
    info.emissor = _issuer_common_name(cert)
    info.numero_serie = f"{cert.serial_number:X}"
    try:
        info.data_emissao = cert.not_valid_before_utc
        info.data_vencimento = cert.not_valid_after_utc
    except AttributeError:
        # Compatibilidade com cryptography < 42
        info.data_emissao = cert.not_valid_before.replace(
            tzinfo=datetime.timezone.utc
        )
        info.data_vencimento = cert.not_valid_after.replace(
            tzinfo=datetime.timezone.utc
        )
    info.algoritmo = cert.signature_hash_algorithm.name.upper() if cert.signature_hash_algorithm else ""

    # E-mail do subject (se houver)
    email = _subject_field(cert, NameOID.EMAIL_ADDRESS)
    if email:
        info.email = email

    # SubjectAlternativeName (SAN) – onde vivem os campos ICP-Brasil
    try:
        san_ext = cert.extensions.get_extension_for_oid(
            ExtensionOID.SUBJECT_ALTERNATIVE_NAME
        )
        san = san_ext.value
    except x509.ExtensionNotFound:
        san = None
    except Exception as exc:
        info.warnings.append(f"Falha ao ler SAN: {exc}")
        san = None

    if san is not None:
        # E-mails alternativos
        for rfc in san.get_values_for_type(x509.RFC822Name):
            if not info.email:
                info.email = rfc
        # Nomes alternativos ICP-Brasil estão em OtherName
        for other in san.get_values_for_type(x509.OtherName):
            oid = other.type_id.dotted_string
            texto = _extract_utf8_value(other.value)
            if oid == OID_PF:
                dados = _parse_dados_pf(texto)
                info.data_nascimento = dados.get("data_nascimento", "")
                info.cpf = _format_cpf(dados.get("cpf", ""))
                info.pis = dados.get("pis", "")
                info.rg = dados.get("rg", "")
            elif oid == OID_RESP_PF:
                dados = _parse_dados_pf(texto)
                info.responsavel_cpf = _format_cpf(dados.get("cpf", ""))
                if not info.data_nascimento:
                    info.data_nascimento = dados.get("data_nascimento", "")
            elif oid == OID_RESP_NOME:
                info.responsavel_nome = texto
            elif oid == OID_CNPJ:
                digits = "".join(c for c in texto if c.isdigit())
                info.cnpj = _format_cnpj(digits)
            elif oid == OID_TITULO_ELEITOR:
                info.outros_sans.append(f"Título de eleitor: {texto}")
            elif oid == OID_CEI_PJ:
                info.outros_sans.append(f"CEI-PJ: {texto}")
            elif oid == OID_CEI_PF:
                info.outros_sans.append(f"CEI-PF: {texto}")
            else:
                info.outros_sans.append(f"{oid}: {texto}")

    # Uso da chave
    try:
        ku = cert.extensions.get_extension_for_oid(ExtensionOID.KEY_USAGE).value
        mapa = [
            ("Assinatura digital", ku.digital_signature),
            ("Não repúdio", ku.content_commitment),
            ("Cifragem de chave", ku.key_encipherment),
            ("Cifragem de dados", ku.data_encipherment),
            ("Acordo de chaves", ku.key_agreement),
            ("Assinatura de certificado", ku.key_cert_sign),
            ("Assinatura de CRL", ku.crl_sign),
        ]
        info.uso_chave = [nome for nome, ativo in mapa if ativo]
    except x509.ExtensionNotFound:
        pass
    except Exception:
        pass

    # Heurística para tipo
    if info.cnpj:
        info.tipo = "e-CNPJ"
    elif info.cpf:
        info.tipo = "e-CPF"
    else:
        info.tipo = "Outro"

    return info


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------


DEFAULT_STORES = ("MY", "CA", "ROOT")


def remover_certificado(cert_der: bytes, store_name: str) -> None:
    """Remove do repositório do Windows o certificado cujo DER coincida.

    Parâmetros
    ----------
    cert_der : bytes
        Bytes DER (X.509) do certificado a ser excluído.
    store_name : str
        Nome do repositório ("MY", "CA", "ROOT", etc.).
    """
    if not cert_der:
        raise ValueError("Bytes do certificado não informados.")

    crypt32 = _load_crypt32()
    h_store = crypt32.CertOpenSystemStoreW(None, store_name)
    if not h_store:
        raise OSError(
            f"Não foi possível abrir o repositório '{store_name}'. "
            f"Código: {ctypes.get_last_error()}"
        )
    try:
        p_cert = crypt32.CertEnumCertificatesInStore(h_store, None)
        while p_cert:
            cert = p_cert.contents
            size = cert.cbCertEncoded
            data = bytes(cert.pbCertEncoded[:size])
            if data == cert_der:
                # CertDeleteCertificateFromStore libera o pCertContext
                # mesmo em caso de falha, então não chamamos Free depois.
                if not crypt32.CertDeleteCertificateFromStore(p_cert):
                    raise OSError(
                        "Falha ao excluir o certificado. "
                        f"Código: {ctypes.get_last_error()}"
                    )
                return
            p_cert = crypt32.CertEnumCertificatesInStore(h_store, p_cert)
        raise OSError("Certificado não encontrado no repositório.")
    finally:
        crypt32.CertCloseStore(h_store, 0)


def listar_certificados(stores: Iterable[str] = ("MY",)) -> list[CertificadoInfo]:
    """Lista os certificados dos repositórios solicitados.

    Stores mais comuns:
        "MY"   – Certificados pessoais (e-CPF / e-CNPJ instalados)
        "CA"   – Autoridades certificadoras intermediárias
        "ROOT" – Autoridades certificadoras raiz confiáveis
    """
    resultados: list[CertificadoInfo] = []
    for store in stores:
        try:
            for der in _iter_raw_certificates(store):
                info = _parse_certificate(der, store)
                resultados.append(info)
        except OSError as exc:
            erro = CertificadoInfo(store=store)
            erro.warnings.append(str(exc))
            resultados.append(erro)
    return resultados


if __name__ == "__main__":
    # Pequeno modo CLI para testes rápidos.
    for cert in listar_certificados(("MY",)):
        print("-" * 60)
        print(f"Repositório : {cert.store}")
        print(f"Tipo        : {cert.tipo}")
        print(f"Titular     : {cert.titular_nome}")
        if cert.cpf:
            print(f"CPF         : {cert.cpf}")
        if cert.cnpj:
            print(f"CNPJ        : {cert.cnpj}")
        if cert.empresa:
            print(f"Empresa     : {cert.empresa}")
        if cert.responsavel_nome:
            print(f"Responsável : {cert.responsavel_nome}")
        if cert.responsavel_cpf:
            print(f"CPF Resp.   : {cert.responsavel_cpf}")
        if cert.email:
            print(f"E-mail      : {cert.email}")
        if cert.data_emissao:
            print(f"Emissão     : {cert.data_emissao:%d/%m/%Y %H:%M}")
        if cert.data_vencimento:
            print(
                f"Vencimento  : {cert.data_vencimento:%d/%m/%Y %H:%M} "
                f"({'válido' if cert.valido else 'expirado'})"
            )
        print(f"Emissor     : {cert.emissor}")
