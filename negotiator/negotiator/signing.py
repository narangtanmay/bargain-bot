"""Ed25519 signatures on supplier confirmations, over canonical JSON of every field except the signature.

The simulated suppliers derive their keys from the run seed, so a seeded run is reproducible. That makes the
signature proof that a confirmation was not changed after the supplier sent it, not proof of who the supplier is:
we operate the demo suppliers.
"""

import hashlib
import json

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat


def payload(confirmation):
    body = {k: v for k, v in confirmation.items() if k != "signature"}
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def key_from_seed(seed, name):
    return Ed25519PrivateKey.from_private_bytes(hashlib.sha256(f"supplier-key|{seed}|{name}".encode()).digest())


def public_hex(private_key):
    return private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()


def sign(private_key, confirmation):
    return {**confirmation, "signature": private_key.sign(payload(confirmation)).hex()}


def verify(public_key_hex, confirmation):
    """True only if the confirmation carries a signature by this public key over exactly its other fields."""
    try:
        key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key_hex))
        key.verify(bytes.fromhex(confirmation["signature"]), payload(confirmation))
        return True
    except (InvalidSignature, ValueError, KeyError, TypeError):
        return False
