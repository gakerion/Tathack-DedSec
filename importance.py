import math
import json

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
    weights=None,
):
    if operation not in OPERATION_SEVERITY or impact not in EXTERNAL_IMPACT:
        raise ValueError("Invalid operation or impact.")

    if (
        type(affected_count) not in (int, float)
        or not math.isfinite(affected_count)
        or affected_count < 0
        or type(scope_threshold) not in (int, float)
        or not math.isfinite(scope_threshold)
        or scope_threshold < 1
        or weights is not None
        or any(
            type(value) is not bool
            for value in (
                backup_verified,
                automatic_restore_supported,
                manual_restore_supported,
                reversible,
            )
        )
    ):
        raise ValueError("Invalid importance calculation arguments.")

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

    base_weights = {
        "C": 0.35,
        "R": 0.30,
        "S": 0.20,
        "E": 0.15,
    }

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
        "provisional": modifies
        and (recovery["status"] == "unknown" or impact == "unknown"),
    }
