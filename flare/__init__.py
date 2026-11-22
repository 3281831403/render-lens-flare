"""Public surface of the lens-flare package."""

from .lens import (
    FlareError,
    aperture_mask,
    chroma_split,
    falloff,
    flare_batch,
    ghost_positions,
    halo_position,
    validate,
    visible_source,
)

__all__ = [
    "FlareError",
    "aperture_mask",
    "chroma_split",
    "falloff",
    "flare_batch",
    "ghost_positions",
    "halo_position",
    "validate",
    "visible_source",
]
