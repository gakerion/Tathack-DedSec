import math,json


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
    impact="unknown",
    backup_verified=False,
    automatic_restore_supported=False,
    manual_restore_supported=False,
    reversible=True,
    scope_threshold=10,
):
    if operation not in OPERATION_SEVERITY:
        return 0

    if impact not in EXTERNAL_IMPACT:
        return 0
    
    if (
        type(affected_count) is not int
        or affected_count < 0
        or type(scope_threshold) is not int
        or scope_threshold < 1
    ):
        raise ValueError("Invalid resource count or scope threshold.")

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

    score = constants["M"] * (
        0.35 * constants["C"]
        + 0.30 * constants["R"]
        + 0.20 * constants["S"]
        + 0.15 * constants["E"]
    )

    return {
        "importance": round(score, 3),
        "constants": constants,
        "recovery_status": recovery["status"],
        "provisional": modifies and (
            recovery["status"] == "unknown" or impact == "unknown"
        ),
    }