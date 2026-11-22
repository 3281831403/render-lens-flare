"""Lens-flare geometry, masking and color helpers.

Screen coordinates are normalized UV pairs ``(u, v)``: ``(0.0, 0.0)`` is
the top-left corner and ``(1.0, 1.0)`` is the bottom-right corner.  A
point is on screen when both components are in ``[0, 1]``.  Intensities
and RGB channels are normalized to ``[0, 1]``.  The tests compare floats
with an absolute tolerance of ``1e-6``.
"""

import math
from collections.abc import Mapping

EPS = 1e-6
CENTER = (0.5, 0.5)


class FlareError(Exception):
    """Raised when flare input is malformed or cannot be rendered."""


def _finite_number(value):
    """Return ``True`` for a finite real number (booleans excluded)."""
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def _pair(value):
    """Return ``(u, v)`` as floats, or ``None`` when malformed."""
    if isinstance(value, (str, bytes)):
        return None
    try:
        u, v = value
    except (TypeError, ValueError):
        return None
    if not (_finite_number(u) and _finite_number(v)):
        return None
    return float(u), float(v)


def _uv_in_range(uv):
    """Return the clamped UV when both components lie in ``[0, 1]`` +/- EPS."""
    pair = _pair(uv)
    if pair is None:
        return None
    if not all(-EPS <= component <= 1.0 + EPS for component in pair):
        return None
    return (
        min(max(pair[0], 0.0), 1.0),
        min(max(pair[1], 0.0), 1.0),
    )


def _positive_int(value):
    """Return ``True`` for an integer greater than zero (booleans excluded)."""
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _validate_depth_map(depth_map):
    """Return the depth map as rows of floats or raise ``FlareError``."""
    if isinstance(depth_map, (str, bytes)):
        raise FlareError("depth_map must be a non-empty rectangular sequence")
    try:
        rows = list(depth_map)
    except TypeError:
        raise FlareError("depth_map must be a non-empty rectangular sequence")
    if not rows:
        raise FlareError("depth_map must be non-empty")
    width = None
    parsed = []
    for row in rows:
        if isinstance(row, (str, bytes)):
            raise FlareError("depth_map must be a non-empty rectangular sequence")
        try:
            cells = list(row)
        except TypeError:
            raise FlareError("depth_map must be a non-empty rectangular sequence")
        if width is None:
            width = len(cells)
            if width == 0:
                raise FlareError("depth_map rows must be non-empty")
        elif len(cells) != width:
            raise FlareError("depth_map must be rectangular")
        parsed_row = []
        for cell in cells:
            if not _finite_number(cell):
                raise FlareError("depth_map cells must be finite numbers")
            parsed_row.append(float(cell))
        parsed.append(parsed_row)
    return parsed


def ghost_positions(uv, count, spread):
    """Return up to ``count`` ghost positions on the screen.

    The image center is ``(0.5, 0.5)``.  Let ``d = uv - center``.  The
    candidate parameters are evenly spaced over ``[-spread, +spread]``:
    for index ``i``, ``t_i = -spread + 2 * spread * i / (count - 1)``
    (``t_0 = 0`` when ``count == 1``).  The candidate is
    ``center + t_i * d``.  The candidates are therefore centrosymmetric
    around the image center; a source at the center maps entirely to the
    center.

    Candidates whose u or v lies outside ``[0, 1]`` by more than ``1e-6``
    are dropped.  Accepted points are clamped to the screen.  The
    returned list follows increasing ``i``.

    Args:
        uv: Source screen UV, a pair of floats in ``[0, 1]``.
        count: Positive number of candidates to generate.
        spread: Non-negative half-extent of the symmetric parameter range.

    Returns:
        A list of at most ``count`` ``(u, v)`` tuples.

    Raises:
        FlareError: If ``uv`` is malformed or outside ``[0, 1]``,
            ``count <= 0``, or ``spread < 0``.
    """
    source = _uv_in_range(uv)
    if source is None:
        raise FlareError("uv out of range")
    if not _positive_int(count):
        raise FlareError("count must be a positive integer")
    if not _finite_number(spread) or spread < 0.0:
        raise FlareError("spread must be non-negative")

    center_u, center_v = CENTER
    du = source[0] - center_u
    dv = source[1] - center_v

    ghosts = []
    for index in range(count):
        if count == 1:
            t = 0.0
        else:
            t = -spread + 2.0 * spread * index / (count - 1)
        u = center_u + t * du
        v = center_v + t * dv
        if not (-EPS <= u <= 1.0 + EPS and -EPS <= v <= 1.0 + EPS):
            continue
        ghosts.append((
            min(max(round(u, 10), 0.0), 1.0),
            min(max(round(v, 10), 0.0), 1.0),
        ))
    return ghosts


def visible_source(uv, depth_map):
    """Return whether the source at ``uv`` is visible above the depth map.

    ``depth_map`` is a non-empty rectangular 2D sequence, one row per
    vertical sample, ordered top-to-bottom.  Each cell is an occluder
    depth in ``[0, 1]``: a value within ``1e-6`` of ``0.0`` means there is
    no occluder (background), while a positive value means an occluder in
    front of the source.  The source is visible only on an empty cell;
    brightness and color are irrelevant.

    Sampling is nearest-neighbour: column
    ``min(int(u * width), width - 1)`` and row
    ``min(int(v * height), height - 1)``.  ``uv`` must be on screen.

    Args:
        uv: Source screen UV, a pair of floats in ``[0, 1]``.
        depth_map: Non-empty rectangular sequence of depth rows.

    Returns:
        ``True`` when the sampled cell is background, otherwise ``False``.

    Raises:
        FlareError: If ``uv`` is outside ``[0, 1]`` or ``depth_map`` is
            empty or ragged.
    """
    source = _uv_in_range(uv)
    if source is None:
        raise FlareError("uv out of range")
    rows = _validate_depth_map(depth_map)

    height = len(rows)
    width = len(rows[0])
    u, v = source
    column = min(int(u * width), width - 1)
    row = min(int(v * height), height - 1)
    return abs(rows[row][column]) <= EPS


def chroma_split(rgb, amount):
    """Split an RGB sample into red/blue chromatic-aberration offsets.

    ``rgb`` is an ``(r, g, b)`` tuple with channels in ``[0, 1]``.
    ``amount`` is a non-negative normalized offset.  Red moves toward 1
    by ``amount``, green stays unchanged, and blue moves toward 0 by
    ``amount``.  Every output channel is clamped to ``[0, 1]``.  The red
    and blue channels move in opposite directions instead of together.

    Args:
        rgb: Three normalized color channels.
        amount: Channel offset in ``[0, 1]``.

    Returns:
        A three-tuple of floats in ``[0, 1]``.

    Raises:
        FlareError: If ``rgb`` is not three finite values in ``[0, 1]``,
            or ``amount`` is outside ``[0, 1]``.
    """
    if isinstance(rgb, (str, bytes)):
        raise FlareError("rgb must be three channels in [0, 1]")
    try:
        channels = list(rgb)
    except TypeError:
        raise FlareError("rgb must be three channels in [0, 1]")
    if len(channels) != 3 or not all(
        _finite_number(channel) and 0.0 <= channel <= 1.0 for channel in channels
    ):
        raise FlareError("rgb must be three channels in [0, 1]")
    if not _finite_number(amount) or not 0.0 <= amount <= 1.0:
        raise FlareError("amount must be in [0, 1]")

    red, green, blue = (float(channel) for channel in channels)
    red = min(max(red + amount, 0.0), 1.0)
    blue = min(max(blue - amount, 0.0), 1.0)
    return (red, green, blue)


def aperture_mask(uv, blades):
    """Return a binary regular-polygon aperture mask at ``uv``.

    The polygon is centered at ``(0.5, 0.5)`` with circumradius ``0.5``.
    It has ``blades`` vertices; the first vertex points along +u (angle
    0), and the remaining vertices follow counter-clockwise in screen
    space.  A point on or inside the polygon returns ``1.0``; a point
    outside returns ``0.0``.  This is a polygonal mask, not a circle of
    radius ``0.5``.

    Args:
        uv: Screen UV to test.
        blades: Number of polygon sides, an integer greater than or
            equal to 3.

    Returns:
        ``1.0`` inside/on the polygon, otherwise ``0.0``.

    Raises:
        FlareError: If ``blades`` is not an integer greater than or equal
            to 3.
    """
    if (
        not isinstance(blades, int)
        or isinstance(blades, bool)
        or blades < 3
    ):
        raise FlareError("blades must be an integer >= 3")
    point = _pair(uv)
    if point is None:
        raise FlareError("uv must be a finite pair")

    center_u, center_v = CENTER
    radius = 0.5
    vertices = []
    for index in range(blades):
        angle = 2.0 * math.pi * index / blades
        vertices.append(
            (
                center_u + radius * math.cos(angle),
                center_v + radius * math.sin(angle),
            )
        )

    inside = True
    for index in range(blades):
        au, av = vertices[index]
        bu, bv = vertices[(index + 1) % blades]
        edge_u = bu - au
        edge_v = bv - av
        rel_u = point[0] - au
        rel_v = point[1] - av
        cross = edge_u * rel_v - edge_v * rel_u
        if cross < -1e-9:
            inside = False
            break

    return 1.0 if inside else 0.0


def halo_position(uv, center):
    """Return the halo center for a source at ``uv``.

    The halo is the point reflection of the source through ``center``:
    ``(2 * center_u - u, 2 * center_v - v)``.  The result is not clamped
    and may fall outside the screen for a source near an edge.  Relative
    to ``center``, the halo is in the opposite direction from the source.

    Args:
        uv: Source screen UV.
        center: Screen UV of the optical center.

    Returns:
        The reflected ``(u, v)`` tuple.
    """
    source = _pair(uv)
    pivot = _pair(center)
    if source is None or pivot is None:
        raise FlareError("uv and center must be finite pairs")
    return (
        2.0 * pivot[0] - source[0],
        2.0 * pivot[1] - source[1],
    )


def falloff(dist, radius, power):
    """Return a smooth radial falloff in ``[0, 1]``.

    For ``0 <= dist <= radius`` the value is
    ``(1 - dist / radius) ** power``.  It is ``1.0`` at ``dist == 0``,
    reaches exactly ``0.0`` at ``dist == radius``, and stays ``0.0``
    beyond the radius.  This is a curved falloff, not a linear ramp.

    Args:
        dist: Non-negative distance from the flare center.
        radius: Positive falloff radius.
        power: Positive curve exponent.

    Returns:
        A float in ``[0, 1]``.

    Raises:
        FlareError: If ``dist < 0``, ``radius <= 0``, or ``power <= 0``.
    """
    if not _finite_number(dist) or dist < 0.0:
        raise FlareError("dist must be non-negative")
    if not _finite_number(radius) or radius <= 0.0:
        raise FlareError("radius must be positive")
    if not _finite_number(power) or power <= 0.0:
        raise FlareError("power must be positive")
    if dist >= radius:
        return 0.0
    return (1.0 - dist / radius) ** power


def validate(uv, count, intensity):
    """Return a list of human-readable problems for one light source.

    The checks and problem strings, in order, are:

    1. ``uv``: both components must be finite and in ``[0, 1]`` with
       ``1e-6`` slack.  Problem: ``"uv out of range"``.
    2. ``count``: must be an integer greater than 0 (booleans are not
       accepted).  Problem: ``"count must be a positive integer"``.
    3. ``intensity``: must be finite and in ``[0, 1]`` with ``1e-6``
       slack.  Problem: ``"intensity out of range"``.

    An empty list means the source is valid.  This helper only reports
    problems; it does not raise for invalid values.

    Args:
        uv: Source screen UV.
        count: Requested number of ghosts.
        intensity: Normalized source intensity.

    Returns:
        A list containing zero to three problem strings.
    """
    problems = []
    if _uv_in_range(uv) is None:
        problems.append("uv out of range")
    if not _positive_int(count):
        problems.append("count must be a positive integer")
    if (
        not _finite_number(intensity)
        or not -EPS <= intensity <= 1.0 + EPS
    ):
        problems.append("intensity out of range")
    return problems


def _validated_config(config):
    """Validate the batch config and return the fields the batch needs."""
    if not isinstance(config, Mapping):
        raise FlareError("config must be a mapping")

    required = (
        "count",
        "spread",
        "blades",
        "power",
        "radius",
        "rgb",
        "amount",
        "depth_map",
    )
    missing = [key for key in required if key not in config]
    if missing:
        raise FlareError("config is missing: " + ", ".join(missing))

    count = config["count"]
    spread = config["spread"]
    blades = config["blades"]
    power = config["power"]
    radius = config["radius"]

    if not _positive_int(count):
        raise FlareError("count must be a positive integer")
    if not _finite_number(spread) or spread < 0.0:
        raise FlareError("spread must be non-negative")
    if not isinstance(blades, int) or isinstance(blades, bool) or blades < 3:
        raise FlareError("blades must be an integer >= 3")
    if not _finite_number(power) or power <= 0.0:
        raise FlareError("power must be positive")
    if not _finite_number(radius) or radius <= 0.0:
        raise FlareError("radius must be positive")

    # Validate rgb/amount eagerly so a malformed config is rejected even
    # for an empty source list.
    chroma_split(config["rgb"], config["amount"])

    return {
        "count": count,
        "spread": float(spread),
        "blades": blades,
        "power": float(power),
        "radius": float(radius),
        "rgb": tuple(float(channel) for channel in config["rgb"]),
        "amount": float(config["amount"]),
        "depth_map": _validate_depth_map(config["depth_map"]),
    }


def flare_batch(sources, config):
    """Generate flare data for a sequence of light sources.

    Each source is a mapping with ``"uv"`` and ``"intensity"``.  The
    ``config`` mapping must provide ``count``, ``spread``, ``blades``,
    ``power``, ``radius``, ``rgb``, ``amount`` and ``depth_map`` with the
    same meanings as the individual helpers.

    The return value maps a source index to a record::

        {
            "uv": (u, v),
            "intensity": intensity,
            "ghosts": [(u, v), ...],
            "ghost_weights": [intensity, ...],
            "visible": bool,
            "halo": (u, v),
            "halo_weight": intensity,
            "chroma": (r, g, b),
            "aperture": float,
            "falloff": float,
        }

    ``ghosts`` and ``ghost_weights`` have equal length.  The chroma,
    aperture and falloff fields are intensity-weighted (multiplied by the
    source intensity), so a zero-intensity source contributes all-zero
    effect values while retaining its geometry.  The radial falloff uses
    the distance from the source UV to the image center.

    Every source and the config are validated before any result is
    returned.  If any input is invalid (bad UV, non-positive count,
    out-of-range intensity, malformed config), no partial result is
    returned: ``FlareError`` is raised and caller-owned inputs are not
    mutated.  An empty ``sources`` sequence returns ``{}``.

    Args:
        sources: Sequence of ``{"uv": (u, v), "intensity": float}``.
        config: Batch rendering options.

    Returns:
        A dict keyed by source index in source order.

    Raises:
        FlareError: If the config or any source is invalid.
    """
    options = _validated_config(config)

    if isinstance(sources, (str, bytes)):
        raise FlareError("sources must be a sequence of mappings")
    try:
        entries = list(sources)
    except TypeError:
        raise FlareError("sources must be a sequence of mappings")

    # Validate every source before producing any record.
    prepared = []
    for index, source in enumerate(entries):
        if not isinstance(source, Mapping):
            raise FlareError("source %d must be a mapping" % index)
        if "uv" not in source or "intensity" not in source:
            raise FlareError("source %d needs uv and intensity" % index)
        uv = source["uv"]
        intensity = source["intensity"]
        problems = validate(uv, options["count"], intensity)
        if problems:
            raise FlareError(
                "source %d: %s" % (index, "; ".join(problems))
            )
        prepared.append((_uv_in_range(uv), float(intensity)))

    count = options["count"]
    spread = options["spread"]
    blades = options["blades"]
    power = options["power"]
    radius = options["radius"]
    rgb = options["rgb"]
    amount = options["amount"]
    depth_map = options["depth_map"]

    result = {}
    center_u, center_v = CENTER
    for index, (uv, intensity) in enumerate(prepared):
        u, v = float(uv[0]), float(uv[1])

        # Each source gets its own fresh ghost list.
        ghosts = ghost_positions((u, v), count, spread)
        ghost_weights = [intensity for _ in ghosts]

        halo = halo_position((u, v), CENTER)
        chroma = chroma_split(rgb, amount)
        aperture = aperture_mask((u, v), blades)
        distance = math.hypot(u - center_u, v - center_v)
        radial = falloff(distance, radius, power)

        result[index] = {
            "uv": (u, v),
            "intensity": intensity,
            "ghosts": ghosts,
            "ghost_weights": ghost_weights,
            "visible": visible_source((u, v), depth_map),
            "halo": halo,
            "halo_weight": intensity,
            "chroma": tuple(channel * intensity for channel in chroma),
            "aperture": aperture * intensity,
            "falloff": radial * intensity,
        }
    return result
