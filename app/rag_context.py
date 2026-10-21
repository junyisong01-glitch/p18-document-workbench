"""RAG-only packing. Retrieval scores, stored chunks and source locators stay intact."""
from copy import deepcopy

from app.retrieval import duplicate_key


def evidence_groups(hits):
    """Collapse conservative duplicates, retaining every real source identity.

    Use the existing retrieval equivalence rule (including kind/version/config).
    An upstream group with different member texts stays atomic; never infer that
    merely similar passages, tables or code are interchangeable.
    """
    result = []
    positions = {}
    for hit in hits:
        members = [deepcopy(member) for member in hit.get('members', [hit])]
        keys = [duplicate_key(dict(hit, **member)) for member in members]
        key = keys[0] if keys and all(k == keys[0] for k in keys) else None
        if key is not None and key in positions:
            group = result[positions[key]]
            existing = group.setdefault('members', [deepcopy(group)])
            identities = {(m['document_id'], m['revision'], m['index_token'], m['chunk_id']) for m in existing}
            for member in members:
                identity = tuple(member[k] for k in ('document_id', 'revision', 'index_token', 'chunk_id'))
                if identity not in identities:
                    existing.append(member)
                    identities.add(identity)
        else:
            group = deepcopy(hit)
            if key is not None:
                positions[key] = len(result)
            result.append(group)
    return result


def model_evidence(evidence):
    """Full text and source identities go to the model, drawing coordinates do not.

    Full locators remain in server tickets, consent evidence and returned
    citations for version-checked original previews. Exact wire messages are
    separately previewed, hashed, budgeted and compared again before dispatch.
    """
    result = deepcopy(evidence)
    for group in result:
        group.pop('sources', None)
        for member in group.get('members', []):
            member.pop('sources', None)
    return result
