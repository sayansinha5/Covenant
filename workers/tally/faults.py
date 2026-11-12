"""Tally's reproducible mistake: invent dimensions for every nth item."""


def invents_dimensions(index: int, fault_rate: float) -> bool:
    """`0.2` means every index divisible by 5 (24 of 120). `0` means never."""
    if fault_rate <= 0:
        return False
    every = max(1, round(1 / fault_rate))
    return index % every == 0


INVENTED_DIMENSIONS = "45 x 30 cm"
