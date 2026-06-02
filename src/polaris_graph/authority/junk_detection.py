"""Signal C — structural junk detection (replaces ~20 deny frozensets).

Phase 0a (GH #983). Data-driven (LAW VI). ZERO host names in code.

All patterns live in config/authority/junk_patterns.yaml as STRUCTURAL shapes
(schema.org JSON-LD types, login-wall flags, self-published PATH shapes). The
self-interest class is computed (host-org token vs the claim's vendor token),
not regex.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from src.polaris_graph.authority.source_class import (
    AuthorityConfidence,
    SourceClass,
)


@dataclass
class JunkResult:
    fired: bool
    junk_class: str = ""
    source_class: SourceClass = SourceClass.UNKNOWN
    ceiling: float = 1.0
    confidence: AuthorityConfidence = AuthorityConfidence.MEDIUM
    reasons: list[str] = field(default_factory=list)


def _compiled_patterns(junk_data: dict) -> dict:
    """Compile + cache the regexes per junk-class (keyed in-place on the dict)."""
    cache_key = "_compiled"
    if cache_key in junk_data:
        return junk_data[cache_key]
    compiled: dict[str, dict] = {}
    for name, spec in junk_data["junk_classes"].items():
        compiled[name] = {
            "precedence": spec["precedence"],
            "ceiling": spec["ceiling"],
            "source_class": SourceClass(spec["source_class"]),
            "target": list(spec.get("target", [])),
            "patterns": [re.compile(p, re.IGNORECASE) for p in spec.get("patterns", [])],
        }
    junk_data[cache_key] = compiled
    return compiled


def _host_org_token(host: str) -> str:
    """The registrable-ish org token of a host (the label before the suffix)."""
    if not host:
        return ""
    parts = [p for p in host.lower().split(".") if p and p != "www"]
    if len(parts) >= 2:
        return parts[-2]
    return parts[0] if parts else ""


def detect_junk(
    *,
    host: str,
    url_path: str,
    body: str,
    jsonld: str,
    claim_vendor_token: str,
    junk_data: dict,
) -> JunkResult:
    """Return the highest-precedence junk-class that fires, else not-fired."""
    compiled = _compiled_patterns(junk_data)

    target_text = {
        "url_path": url_path or "",
        "body": body or "",
        "jsonld": jsonld or "",
    }

    fired: list[tuple[int, str, dict]] = []  # (precedence, name, spec)

    for name, spec in compiled.items():
        if name == "self_interest":
            org = _host_org_token(host)
            vendor = (claim_vendor_token or "").strip().lower()
            if org and vendor and org == vendor:
                fired.append((spec["precedence"], name, spec))
            continue
        hit = False
        for tgt in spec["target"]:
            text = target_text.get(tgt, "")
            if text and any(rx.search(text) for rx in spec["patterns"]):
                hit = True
                break
        if hit:
            fired.append((spec["precedence"], name, spec))

    if not fired:
        return JunkResult(fired=False)

    fired.sort(key=lambda t: t[0])  # lowest precedence number wins
    _, name, spec = fired[0]
    # Confidence: HIGH when a JSON-LD pattern was the evidence, else MEDIUM.
    conf = AuthorityConfidence.MEDIUM
    if "jsonld" in spec["target"] and jsonld:
        conf = AuthorityConfidence.HIGH
    return JunkResult(
        fired=True,
        junk_class=name,
        source_class=spec["source_class"],
        ceiling=spec["ceiling"],
        confidence=conf,
        reasons=[f"structural junk pattern fired: {name}"],
    )
