import math


OPERATION_SEVERITY = {
    "read": 0.0,
    "search": 0.0,
    "create": 0.25,
    "move": 0.40,
    "edit": 0.50,
    "overwrite": 0.85,
    "delete": 1.00,
}

EXTERNAL_IMPACT = {
    "local": 0.0,
    "shared": 0.5,
    "external": 1.0,
    "unknown": 1.0,
}

def calculate_recovery(
    backup_verified=False,
    automatic_restore_supported=False,
    manual_restore_supported=False,
    reversible=True,
):
    if not reversible:
        return {"status": "unavailable", "value": 1.0}

    if backup_verified and automatic_restore_supported:
        return {"status": "automatic_verified", "value": 0.0}

    if backup_verified and manual_restore_supported:
        return {"status": "manual_verified", "value": 0.5}

    return {"status": "unknown", "value": 1.0}

def calculate_importance(
    operation,
    affected_count,
    impact="local",
    backup_verified=False,
    automatic_restore_supported=False,
    manual_restore_supported=False,
    reversible=True,
    scope_threshold=10,
):
    if operation not in OPERATION_SEVERITY or impact not in EXTERNAL_IMPACT:
        raise ValueError("Unknown operation or impact.")

    if (
        type(affected_count) not in (int, float)
        or not math.isfinite(affected_count)
        or affected_count < 0
        or type(scope_threshold) not in (int, float)
        or not math.isfinite(scope_threshold)
        or scope_threshold < 1
    ):
        raise ValueError("Invalid resource count or scope threshold.")

    if any(type(value) is not bool for value in (backup_verified,
            automatic_restore_supported, manual_restore_supported, reversible)):
        raise ValueError("Recovery facts must be boolean values.")

    recovery = calculate_recovery(
        backup_verified,
        automatic_restore_supported,
        manual_restore_supported,
        reversible,
    )

    modifies = operation not in {"read", "search"} and affected_count > 0

    constants = {
        "M": int(modifies),
        "C": OPERATION_SEVERITY[operation],
        "R": recovery["value"],
        "S": min(
            1.0,
            math.log1p(affected_count) / math.log1p(scope_threshold),
        ),
        "E": EXTERNAL_IMPACT[impact],
    }

    # Base AHP-derived weights
    base_weights = {
        "C": 0.457,
        "R": 0.301,
        "S": 0.158,
        "E": 0.084,
    }

    # Dynamic re-normalization when E = 0 (controlled local environment)
    if impact == "local":
        active_sum = base_weights["C"] + base_weights["R"] + base_weights["S"]
        weights = {
            "C": base_weights["C"] / active_sum,
            "R": base_weights["R"] / active_sum,
            "S": base_weights["S"] / active_sum,
            "E": 0.0,
        }
    else:
        weights = base_weights

    score = constants["M"] * (
        weights["C"] * constants["C"]
        + weights["R"] * constants["R"]
        + weights["S"] * constants["S"]
        + weights["E"] * constants["E"]
    )

    return {
        "importance": round(score, 3),
        "constants": constants,
        "weights_used": {k: round(v, 3) for k, v in weights.items()},
        "recovery_status": recovery["status"],
        "provisional": modifies and (
            recovery["status"] == "unknown" or impact == "unknown"
        ),
    }
