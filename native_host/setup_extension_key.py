"""
Garante que o manifest.json da extensao tenha um campo ``key`` que fixa
o ID da extensao no Chrome/Edge.

Se o campo ``key`` ainda nao existir, gera um par RSA-2048 e:
  - grava a chave publica (SubjectPublicKeyInfo, base64) dentro do manifest;
  - salva um backup da chave privada em ``extension_private_key.pem`` ao lado
    deste script (guarde esse arquivo em local seguro; ele e necessario para
    empacotar o .crx se um dia voce quiser distribuir a extensao assinada).

Uso:
    python setup_extension_key.py <caminho do manifest.json>

Saida:
    stdout -> o ID de 32 caracteres (a-p) derivado da chave publica
    stderr -> mensagens informativas
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import sys

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def extension_id_from_pubkey(pub_der: bytes) -> str:
    """Deriva o ID de 32 caracteres conforme a regra do Chrome.

    Chrome pega os primeiros 16 bytes do SHA-256 da chave publica DER
    e mapeia cada nibble (0..15) nas letras 'a'..'p'.
    """
    digest = hashlib.sha256(pub_der).digest()[:16]
    out: list[str] = []
    for b in digest:
        out.append(chr(ord("a") + ((b >> 4) & 0x0F)))
        out.append(chr(ord("a") + (b & 0x0F)))
    return "".join(out)


def main() -> None:
    if len(sys.argv) < 2:
        print(
            "Uso: setup_extension_key.py <caminho do manifest.json>",
            file=sys.stderr,
        )
        sys.exit(2)

    manifest_path = os.path.abspath(sys.argv[1])
    here = os.path.dirname(os.path.abspath(__file__))

    if not os.path.isfile(manifest_path):
        print(
            f"manifest.json nao encontrado: {manifest_path}",
            file=sys.stderr,
        )
        sys.exit(1)

    with open(manifest_path, "r", encoding="utf-8") as fp:
        manifest = json.load(fp)

    pub_b64 = manifest.get("key") or ""

    if not pub_b64:
        print("Gerando par RSA-2048 para fixar o ID...", file=sys.stderr)
        priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        pub_der = priv.public_key().public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        pub_b64 = base64.b64encode(pub_der).decode("ascii")

        priv_pem = priv.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode("ascii")

        priv_path = os.path.join(here, "extension_private_key.pem")
        with open(priv_path, "w", encoding="utf-8", newline="") as fp:
            fp.write(priv_pem)
        print(f"Chave privada salva em: {priv_path}", file=sys.stderr)

        manifest["key"] = pub_b64
        with open(manifest_path, "w", encoding="utf-8", newline="\n") as fp:
            json.dump(manifest, fp, ensure_ascii=False, indent=2)
            fp.write("\n")
        print(
            f"Campo 'key' adicionado em {manifest_path}", file=sys.stderr
        )
    else:
        print("Campo 'key' ja existe no manifest.", file=sys.stderr)

    pub_der = base64.b64decode(pub_b64)
    ext_id = extension_id_from_pubkey(pub_der)
    print(ext_id)


if __name__ == "__main__":
    main()
