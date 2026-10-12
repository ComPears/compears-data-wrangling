"""Shared count-regression contract for refresh and publication."""
MAX_DROP_RATIO = 0.2
MAX_GROWTH_RATIO = 1.75


def count_change_errors(before: int, after: int, *,
                        max_drop_ratio: float = MAX_DROP_RATIO,
                        max_growth_ratio: float = MAX_GROWTH_RATIO) -> list[str]:
    if before <= 0:
        return []
    errors = []
    if after < before * (1 - max_drop_ratio):
        errors.append(f"count dropped from baseline {before} to {after} (limit {max_drop_ratio:.0%})")
    if after > before * max_growth_ratio:
        errors.append(f"count grew from baseline {before} to {after} (limit {max_growth_ratio:g}x)")
    return errors
