"""Per-case salted identifier hashing (sha256_salted_v1).

All parties hash account ids with the case salt so identifiers JOIN inside the clean room
while remaining meaningless outside it. (A production system would use PSI or an HSM-held
salt; the per-case salt models the same property for the demo and is documented as such.)
"""

from __future__ import annotations

import hashlib
import secrets


def new_case_salt() -> str:
    return secrets.token_hex(16)


def hash_account(salt: str, account_id: str) -> str:
    return hashlib.sha256(f"{salt}:{account_id}".encode()).hexdigest()
