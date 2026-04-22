"""Testes unitários do parser de certificados ICP-Brasil.

Gera certificados X.509 sintéticos com OIDs ICP-Brasil no
SubjectAlternativeName usando a própria biblioteca ``cryptography``
e valida a extração de CPF, CNPJ, responsável etc. feita pelo
``cert_reader``.
"""

from __future__ import annotations

import datetime
from typing import Iterable

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

import cert_reader


# ---------------------------------------------------------------------------
# Helpers para montar certificados sintéticos
# ---------------------------------------------------------------------------


def _asn1_utf8(s: str) -> bytes:
    """Codifica uma string como UTF8String ASN.1 (tag 0x0C).

    Suficiente para valores de até 127 bytes — o bastante para os
    campos ICP-Brasil que testamos aqui.
    """
    data = s.encode("utf-8")
    assert len(data) < 128, "teste requer valor curto"
    return bytes([0x0C, len(data)]) + data


def _build_cert(
    common_name: str,
    san_others: Iterable[tuple[str, str]] = (),
    organization: str = "",
    email: str = "",
    not_before: datetime.datetime | None = None,
    not_after: datetime.datetime | None = None,
) -> bytes:
    now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
    not_before = not_before or (now - datetime.timedelta(days=30))
    not_after = not_after or (now + datetime.timedelta(days=365))

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    attrs = [x509.NameAttribute(NameOID.COMMON_NAME, common_name)]
    if organization:
        attrs.append(x509.NameAttribute(NameOID.ORGANIZATION_NAME, organization))
    if email:
        attrs.append(x509.NameAttribute(NameOID.EMAIL_ADDRESS, email))
    name = x509.Name(attrs)

    san_values: list[x509.GeneralName] = []
    for oid_str, valor in san_others:
        san_values.append(
            x509.OtherName(
                type_id=x509.ObjectIdentifier(oid_str),
                value=_asn1_utf8(valor),
            )
        )
    if email:
        san_values.append(x509.RFC822Name(email))

    builder = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(
            x509.Name(
                [x509.NameAttribute(NameOID.COMMON_NAME, "AC TESTE ICP-Brasil")]
            )
        )
        .public_key(key.public_key())
        .serial_number(0xABCDEF123456)
        .not_valid_before(not_before)
        .not_valid_after(not_after)
    )
    if san_values:
        builder = builder.add_extension(
            x509.SubjectAlternativeName(san_values), critical=False
        )
    builder = builder.add_extension(
        x509.KeyUsage(
            digital_signature=True,
            content_commitment=True,
            key_encipherment=True,
            data_encipherment=False,
            key_agreement=False,
            key_cert_sign=False,
            crl_sign=False,
            encipher_only=False,
            decipher_only=False,
        ),
        critical=True,
    )

    cert = builder.sign(key, hashes.SHA256())
    return cert.public_bytes(serialization_encoding())


def serialization_encoding():
    from cryptography.hazmat.primitives.serialization import Encoding

    return Encoding.DER


# ---------------------------------------------------------------------------
# Testes puros de formatação/parse
# ---------------------------------------------------------------------------


class TestFormatadores:
    def test_format_cpf_completo(self):
        assert cert_reader._format_cpf("12345678901") == "123.456.789-01"

    def test_format_cpf_com_ruido(self):
        assert cert_reader._format_cpf("123.456.789-01") == "123.456.789-01"

    def test_format_cpf_tamanho_errado_devolve_digitos(self):
        # Funcao descarta nao-digitos e, se o total nao chegar a 11,
        # devolve os digitos sem mascara (aceitando qualquer tamanho).
        assert cert_reader._format_cpf("123") == "123"
        assert cert_reader._format_cpf("abc") == ""

    def test_format_cnpj_completo(self):
        assert cert_reader._format_cnpj("12345678000190") == "12.345.678/0001-90"

    def test_format_cnpj_com_mascara(self):
        assert cert_reader._format_cnpj("12.345.678/0001-90") == "12.345.678/0001-90"

    def test_format_cnpj_sem_digitos_suficientes(self):
        # Sem 14 digitos, a funcao devolve somente os digitos filtrados.
        assert cert_reader._format_cnpj("abc") == ""
        assert cert_reader._format_cnpj("123") == "123"


class TestParseDadosPF:
    def test_bloco_completo(self):
        # 8 (nasc) + 11 (cpf) + 11 (pis) + 15 (rg) + 6 (orgao) = 51
        bloco = "15081980" + "12345678901" + "12345678901" + "123456789012345" + "SSPSP0"
        dados = cert_reader._parse_dados_pf(bloco)
        assert dados["data_nascimento"] == "1980-08-15"
        assert dados["cpf"] == "12345678901"
        assert dados["pis"] == "12345678901"
        assert "123456789012345" in dados["rg"]

    def test_bloco_parcial_retorna_vazio(self):
        assert cert_reader._parse_dados_pf("abc") == {}

    def test_data_invalida_retorna_como_string(self):
        bloco = "99999999" + "12345678901" + "0" * 11 + "0" * 15 + "000000"
        dados = cert_reader._parse_dados_pf(bloco)
        assert dados["data_nascimento"] == "99999999"
        assert dados["cpf"] == "12345678901"


class TestExtractUtf8Value:
    def test_utf8_com_tag(self):
        raw = bytes([0x0C, 5]) + b"abcde"
        assert cert_reader._extract_utf8_value(raw) == "abcde"

    def test_sem_cabecalho_tenta_utf8_puro(self):
        assert cert_reader._extract_utf8_value(b"hello") == "hello"

    def test_bytes_vazios(self):
        assert cert_reader._extract_utf8_value(b"") == ""

    def test_printable_string(self):
        raw = bytes([0x13, 3]) + b"xyz"
        assert cert_reader._extract_utf8_value(raw) == "xyz"


class TestValidadeCertificado:
    def test_sem_data_nao_valido(self):
        info = cert_reader.CertificadoInfo(store="MY")
        assert info.valido is False
        assert info.dias_para_vencer is None

    def test_expirado(self):
        info = cert_reader.CertificadoInfo(
            store="MY",
            data_vencimento=datetime.datetime.now(datetime.timezone.utc)
            - datetime.timedelta(days=10),
        )
        assert info.valido is False
        assert info.dias_para_vencer is not None
        assert info.dias_para_vencer < 0

    def test_valido(self):
        info = cert_reader.CertificadoInfo(
            store="MY",
            data_vencimento=datetime.datetime.now(datetime.timezone.utc)
            + datetime.timedelta(days=100),
        )
        assert info.valido is True
        assert info.dias_para_vencer is not None
        assert 98 <= info.dias_para_vencer <= 100


# ---------------------------------------------------------------------------
# Testes end-to-end com certificados sintéticos
# ---------------------------------------------------------------------------


class TestParseCertificate:
    def test_ecpf_completo(self):
        pf_data = (
            "15081980"
            + "12345678901"
            + "98765432100"
            + "123456789012345"
            + "SSPSP0"
        )
        der = _build_cert(
            common_name="JOAO DA SILVA:12345678901",
            san_others=[("2.16.76.1.3.1", pf_data)],
            email="joao@exemplo.com.br",
        )
        info = cert_reader._parse_certificate(der, "MY")

        assert info.titular_nome == "JOAO DA SILVA:12345678901"
        assert info.tipo == "e-CPF"
        assert info.cpf == "123.456.789-01"
        assert info.data_nascimento == "1980-08-15"
        assert info.pis == "98765432100"
        assert info.email == "joao@exemplo.com.br"
        assert info.raw_der == der
        assert info.emissor == "AC TESTE ICP-Brasil"
        assert "Assinatura digital" in info.uso_chave
        assert "Nao repudio" in info.uso_chave or "Não repúdio" in info.uso_chave
        assert info.store == "MY"

    def test_ecnpj_completo(self):
        pf_resp = (
            "20031975"
            + "11122233344"  # CPF responsável
            + "0" * 11
            + "0" * 15
            + "000000"
        )
        der = _build_cert(
            common_name="EMPRESA FULANO LTDA:12345678000190",
            organization="EMPRESA FULANO LTDA",
            san_others=[
                ("2.16.76.1.3.2", "MARIA OLIVEIRA"),
                ("2.16.76.1.3.3", "12345678000190"),
                ("2.16.76.1.3.4", pf_resp),
            ],
        )
        info = cert_reader._parse_certificate(der, "MY")

        assert info.tipo == "e-CNPJ"
        assert info.cnpj == "12.345.678/0001-90"
        assert info.responsavel_nome == "MARIA OLIVEIRA"
        assert info.responsavel_cpf == "111.222.333-44"
        assert info.empresa == "EMPRESA FULANO LTDA"
        assert info.store == "MY"

    def test_outros_sans_capturados(self):
        der = _build_cert(
            common_name="TESTE:00000000000",
            san_others=[
                ("2.16.76.1.3.5", "123456789012"),  # título eleitor
                ("2.16.76.1.3.6", "987654321000"),  # CEI-PJ
                ("2.16.76.1.3.7", "111222333444"),  # CEI-PF
            ],
        )
        info = cert_reader._parse_certificate(der, "CA")

        textos = " | ".join(info.outros_sans)
        assert "Titulo de eleitor" in textos or "Título de eleitor" in textos
        assert "CEI-PJ: 987654321000" in textos
        assert "CEI-PF: 111222333444" in textos

    def test_certificado_sem_san_vira_outro(self):
        der = _build_cert(common_name="SEM ICP-BRASIL")
        info = cert_reader._parse_certificate(der, "MY")

        assert info.tipo == "Outro"
        assert info.cpf == ""
        assert info.cnpj == ""
        assert info.titular_nome == "SEM ICP-BRASIL"

    def test_bytes_invalidos_nao_quebram(self):
        info = cert_reader._parse_certificate(b"\x00\x01\x02lixo", "MY")
        assert info.tipo == ""
        assert info.warnings  # pelo menos um aviso
        assert any("X.509" in w for w in info.warnings)

    def test_numero_serie_em_hex(self):
        der = _build_cert(common_name="X")
        info = cert_reader._parse_certificate(der, "MY")
        assert info.numero_serie == f"{0xABCDEF123456:X}"


# ---------------------------------------------------------------------------
# Versão exposta
# ---------------------------------------------------------------------------


def test_tem_versao():
    assert cert_reader.__version__
    # SemVer simples
    partes = cert_reader.__version__.split(".")
    assert len(partes) == 3
    assert all(p.isdigit() for p in partes)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
