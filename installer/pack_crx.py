"""
Empacota a pasta ``extension/`` em um arquivo CRX3 assinado.

Chrome / Edge (Chromium) aceitam extensões empacotadas no formato CRX3
sem interação do usuário quando registradas como *external extensions*
(chave ``Software\\Google\\Chrome\\Extensions\\<id>`` em ``HKLM``).
O instalador Inno Setup registra essa chave apontando para o CRX que
este script gera.

Formato CRX3 (resumo):
    Magic           "Cr24"            4 bytes
    Versao          3 (u32 LE)        4 bytes
    Header length   N (u32 LE)        4 bytes
    Header          CrxFileHeader     N bytes  (protobuf)
    Archive         ZIP               resto

A assinatura cobre:
    b"CRX3 SignedData\\x00" + u32_LE(len(signed_header_data))
    + signed_header_data + archive

Assinatura: RSASSA-PKCS1-v1_5 com SHA-256 sobre a mensagem acima.

Uso:
    python pack_crx.py <extension_dir> <private_key.pem> <out.crx>

Exemplo::
    python pack_crx.py ..\\extension ..\\native_host\\extension_private_key.pem ..\\extension\\extension.crx
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import struct
import sys
import zipfile

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding


# ---------------------------------------------------------------------------
# Protobuf helpers mínimos (tudo wire-type 2 = length-delimited)
# ---------------------------------------------------------------------------


def _varint(n: int) -> bytes:
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def _tag_len_bytes(field_number: int, data: bytes) -> bytes:
    """Codifica um campo bytes/message (wire type 2)."""
    tag = (field_number << 3) | 2
    return _varint(tag) + _varint(len(data)) + data


# ---------------------------------------------------------------------------
# Construção da estrutura CRX3
# ---------------------------------------------------------------------------


def _build_signed_data(crx_id: bytes) -> bytes:
    """protobuf SignedData { optional bytes crx_id = 1; }"""
    return _tag_len_bytes(1, crx_id)


def _build_asymmetric_key_proof(public_key_der: bytes, signature: bytes) -> bytes:
    """AsymmetricKeyProof { bytes public_key = 1; bytes signature = 2; }"""
    return _tag_len_bytes(1, public_key_der) + _tag_len_bytes(2, signature)


def _build_crx_header(
    public_key_der: bytes, signature: bytes, signed_header_data: bytes
) -> bytes:
    """CrxFileHeader {
        repeated AsymmetricKeyProof sha256_with_rsa = 2;
        optional bytes signed_header_data = 10000;
    }"""
    proof = _build_asymmetric_key_proof(public_key_der, signature)
    header = _tag_len_bytes(2, proof)
    header += _tag_len_bytes(10000, signed_header_data)
    return header


# ---------------------------------------------------------------------------
# Empacotamento da extensao em ZIP
# ---------------------------------------------------------------------------


# Arquivos explicitamente permitidos dentro do CRX. Evitamos incluir
# manifest de desenvolvimento com "key", scripts de build, README etc.
DEFAULT_FILES = [
    "manifest.json",
    "popup.html",
    "popup.css",
    "popup.js",
]

ICON_DIR = "icons"


def _zip_extension(
    extension_dir: str,
    manifest_source: str | None = None,
) -> bytes:
    """Cria um ZIP em memoria contendo apenas os arquivos da extensao."""
    if not os.path.isdir(extension_dir):
        raise FileNotFoundError(
            f"Pasta da extensao nao encontrada: {extension_dir}"
        )

    manifest_source = manifest_source or os.path.join(
        extension_dir, "manifest.store.json"
    )
    if not os.path.isfile(manifest_source):
        # Cai para manifest.json se o de loja nao existir.
        manifest_source = os.path.join(extension_dir, "manifest.json")
        if not os.path.isfile(manifest_source):
            raise FileNotFoundError("manifest.json nao encontrado.")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        # Sempre grava o manifest com nome 'manifest.json' dentro do zip.
        with open(manifest_source, "r", encoding="utf-8") as fp:
            manifest_json = json.load(fp)
        # Nunca incluir o 'key' no CRX (Chrome extrai o id da assinatura).
        manifest_json.pop("key", None)
        zf.writestr(
            "manifest.json",
            json.dumps(manifest_json, ensure_ascii=False, indent=2),
        )

        for nome in DEFAULT_FILES:
            if nome == "manifest.json":
                continue
            src = os.path.join(extension_dir, nome)
            if os.path.isfile(src):
                zf.write(src, nome)

        icon_dir = os.path.join(extension_dir, ICON_DIR)
        if os.path.isdir(icon_dir):
            for arq in sorted(os.listdir(icon_dir)):
                full = os.path.join(icon_dir, arq)
                if os.path.isfile(full):
                    zf.write(full, os.path.join(ICON_DIR, arq))

    return buf.getvalue()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


SIGNATURE_CONTEXT = b"CRX3 SignedData\x00"  # 16 bytes, com null final (spec)


def pack_crx(
    extension_dir: str,
    private_key_pem_path: str,
    output_crx: str,
    manifest_source: str | None = None,
) -> str:
    with open(private_key_pem_path, "rb") as fp:
        priv = serialization.load_pem_private_key(fp.read(), password=None)

    pub_der = priv.public_key().public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    crx_id = hashlib.sha256(pub_der).digest()[:16]
    signed_header_data = _build_signed_data(crx_id)

    zip_bytes = _zip_extension(extension_dir, manifest_source=manifest_source)

    to_sign = (
        SIGNATURE_CONTEXT
        + struct.pack("<I", len(signed_header_data))
        + signed_header_data
        + zip_bytes
    )
    signature = priv.sign(to_sign, padding.PKCS1v15(), hashes.SHA256())

    header = _build_crx_header(pub_der, signature, signed_header_data)

    os.makedirs(os.path.dirname(os.path.abspath(output_crx)) or ".", exist_ok=True)
    with open(output_crx, "wb") as fp:
        fp.write(b"Cr24")
        fp.write(struct.pack("<I", 3))
        fp.write(struct.pack("<I", len(header)))
        fp.write(header)
        fp.write(zip_bytes)

    ext_id = _chrome_id_from_pubkey(pub_der)
    return ext_id


def _chrome_id_from_pubkey(pub_der: bytes) -> str:
    """Replica o algoritmo do Chrome para derivar o ID a partir da chave."""
    digest = hashlib.sha256(pub_der).digest()[:16]
    out = []
    for b in digest:
        out.append(chr(ord("a") + ((b >> 4) & 0x0F)))
        out.append(chr(ord("a") + (b & 0x0F)))
    return "".join(out)


def _main() -> int:
    if len(sys.argv) < 4:
        print(
            "Uso: pack_crx.py <extension_dir> <private_key.pem> <out.crx>",
            file=sys.stderr,
        )
        return 2
    ext_dir = os.path.abspath(sys.argv[1])
    key_path = os.path.abspath(sys.argv[2])
    out_path = os.path.abspath(sys.argv[3])
    try:
        ext_id = pack_crx(ext_dir, key_path, out_path)
    except Exception as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 1
    print(f"CRX gerado: {out_path}")
    print(f"Extension ID: {ext_id}")
    size_kb = os.path.getsize(out_path) / 1024
    print(f"Tamanho: {size_kb:.1f} KB")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
