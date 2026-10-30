"""Stable fingerprints for locally collected admission evidence."""
import hashlib
import json
import re


def normalize_evidence_text(text):
    """Normalize formatting whitespace without changing source wording."""
    return re.sub(r'\s+', ' ', str(text)).strip()


def evidence_fingerprint(documents):
    """Hash sorted (source, normalized full text) pairs, independent of timestamps/order."""
    pairs = sorted(
        (str(item.get('source', '')).strip(), normalize_evidence_text(item.get('text', '')))
        for item in documents
        if isinstance(item, dict)
    )
    canonical = json.dumps(pairs, ensure_ascii=False, separators=(',', ':'))
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()
