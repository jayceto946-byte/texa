"""V0.1 pure evidence helper; its existing AST hash remains the approval gate."""
def has_textbook_evidence(state: dict) -> bool:
    if not state.get("use_textbook_context", True):
        return True
    support_status = str((state.get("evidence_support") or {}).get("status") or "")
    if support_status in {"insufficient", "unavailable"}:
        return False
    if state.get("evidence_gate_applied"):
        return bool(state.get("evidence_items"))
    return bool(state.get("evidence_items") or state.get("chapter_contents"))
