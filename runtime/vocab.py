import hashlib
from typing import Dict, List, Tuple

# Stable namespace prefix to ensure consistent hashing across versions
_NAMESPACE = "alp.vocab/1/"

# Canonical vocabulary with human-readable meanings
# Note: '@in' and '@out' are accepted as aliases for 'in'/'out' keys in nodes
_VOCAB_MEANINGS: List[Tuple[str, str]] = [
    ("@def", "declare entity/type"),
    ("@fn", "function node"),
    ("@op", "primitive operation (symbolic)"),
    ("@llm", "LLM operation"),
    ("@tool", "external tool call"),
    ("@flow", "control/data edges"),
    ("@in", "inputs"),
    ("@out", "outputs"),
    ("@expect", "output contract/schema"),
    ("@shape", "schema/struct definition"),
    ("@intent", "macro that expands to subgraph"),
    ("@emb", "embedding literal/ref"),
    ("@pkg", "package import (signed)"),
    ("@caps", "capability/privilege requirement"),
    ("@const", "constant literal"),
    ("@var", "runtime variable"),
    ("@err", "error handling policy"),
    ("@retry", "retry policy"),
    ("@cache", "memoization key"),
    ("@idemp", "idempotency declaration"),
    ("@trace", "provenance tag"),
    ("@hash", "content hash"),
    ("@ver", "version pin"),
    ("@meta", "arbitrary metadata"),
    ("@test", "example/fixture"),
]


def _token_to_cid(token: str) -> str:
    h = hashlib.sha256((_NAMESPACE + token).encode("utf-8")).hexdigest()
    # Shorten but keep enough bits to avoid accidental collisions in this small set
    return "0x" + h[:16]


# Build maps
VOCAB: Dict[str, str] = {tok: _token_to_cid(tok) for tok, _ in _VOCAB_MEANINGS}
CID_TO_TOKEN: Dict[str, str] = {cid.lower(): tok for tok, cid in VOCAB.items()}
MEANINGS: Dict[str, str] = {tok: meaning for tok, meaning in _VOCAB_MEANINGS}


def token_to_cid(token: str) -> str:
    return VOCAB.get(token) or _token_to_cid(token)


def cid_to_token(cid_or_token: str) -> str:
    if not isinstance(cid_or_token, str):
        return cid_or_token
    if cid_or_token in VOCAB:
        return cid_or_token
    low = cid_or_token.lower()
    return CID_TO_TOKEN.get(low, cid_or_token)


# Keys that may appear as top-level fields and should be normalized to their textual aliases
_TOP_LEVEL_KEYS = {
    "@const": "@const",
    "@op": "@op",
    "@llm": "@llm",
    "@retry": "@retry",
    "@expect": "@expect",
    "@shape": "@shape",
    "@intent": "@intent",
    "@emb": "@emb",
    "@pkg": "@pkg",
    "@caps": "@caps",
    "@var": "@var",
    "@err": "@err",
    "@cache": "@cache",
    "@idemp": "@idemp",
    "@trace": "@trace",
    "@hash": "@hash",
    "@ver": "@ver",
    "@meta": "@meta",
    "@tool": "@tool",
    "@test": "@test",
    "@in": "in",   # normalize to existing field name
    "@out": "out",  # normalize to existing field name
}

# Precompute CID aliases for top-level keys
_CID_KEY_ALIASES: Dict[str, str] = {}
for t, normalized in _TOP_LEVEL_KEYS.items():
    _CID_KEY_ALIASES[token_to_cid(t).lower()] = normalized

# Kinds we recognize and normalize
_KIND_ALIASES = {
    "@shape": "@shape",
    "@fn": "@fn",
    "@flow": "@flow",
}
_KIND_CID_ALIASES: Dict[str, str] = {token_to_cid(k).lower(): v for k, v in _KIND_ALIASES.items()}


def normalize_node(node: dict) -> dict:
    if not isinstance(node, dict):
        return node
    # Normalize kind
    kind = node.get("kind")
    if isinstance(kind, str):
        k = cid_to_token(kind)
        # Only map known kinds
        if k in _KIND_ALIASES:
            node["kind"] = _KIND_ALIASES[k]
    # Normalize top-level keys that may be expressed as CIDs
    to_add = {}
    to_del = []
    for k, v in list(node.items()):
        if not isinstance(k, str):
            continue
        if k in _TOP_LEVEL_KEYS:
            # Already textual; ensure normalized alias
            norm = _TOP_LEVEL_KEYS[k]
            if norm != k:
                to_add[norm] = v
                to_del.append(k)
            continue
        low = k.lower()
        if low in _CID_KEY_ALIASES:
            norm = _CID_KEY_ALIASES[low]
            to_add[norm] = v
            to_del.append(k)
    for k in to_del:
        try:
            del node[k]
        except Exception:
            pass
    node.update(to_add)
    return node


def export_vocab_list() -> List[dict]:
    """Return a list of { token, cid, meaning } for documentation/SDK shipping."""
    items = []
    for tok, meaning in _VOCAB_MEANINGS:
        items.append({
            "token": tok,
            "cid": VOCAB[tok],
            "meaning": meaning,
        })
    return items