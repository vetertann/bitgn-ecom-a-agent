ALLOWED_OUTCOMES = {
    "OUTCOME_OK",
    "OUTCOME_DENIED_SECURITY",
    "OUTCOME_NONE_CLARIFICATION",
    "OUTCOME_NONE_UNSUPPORTED",
    "OUTCOME_ERR_INTERNAL",
}


def verify_scratchpad(scratchpad: dict) -> bool:
    answer = scratchpad.get("answer")
    outcome = scratchpad.get("outcome")
    refs = scratchpad.get("refs", [])
    gates = scratchpad.get("gates", {})

    if not isinstance(answer, str) or not answer.strip():
        raise ValueError("scratchpad.answer must be a non-empty string")
    if outcome not in ALLOWED_OUTCOMES:
        raise ValueError(f"scratchpad.outcome must be one of {sorted(ALLOWED_OUTCOMES)}")
    if not isinstance(refs, list) or not all(isinstance(ref, str) for ref in refs):
        raise ValueError("scratchpad.refs must be a list of strings")
    if not refs:
        raise ValueError("scratchpad.refs must contain at least one grounding reference")
    if not isinstance(gates, dict):
        raise ValueError("scratchpad.gates must be a dict when present")
    if outcome == "OUTCOME_OK" and any(value == "NO" for value in gates.values()):
        raise ValueError("OUTCOME_OK is not allowed when any gate is NO")
    return True
