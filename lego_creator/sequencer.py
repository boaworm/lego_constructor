"""Assembly sequencing: group bricks into logical build steps."""

import logging
from collections import defaultdict

from .models import Brick, BuildStep

logger = logging.getLogger(__name__)


def sequence(bricks: list[Brick]) -> list[BuildStep]:
    """
    Sequence bricks into build steps, grouped by layer (z-level).

    Each layer becomes one or more BuildSteps (split if a single layer
    has too many bricks).

    Args:
        bricks: List of Brick objects with (x, y, z) positions

    Returns:
        List of BuildStep objects in assembly order
    """
    if not bricks:
        return []

    # Group bricks by z-layer
    layers = defaultdict(list)
    for brick in bricks:
        layers[brick.z].append(brick)

    # Sort by layer (ascending = bottom to top)
    sorted_layers = sorted(layers.items())

    # Create steps
    steps = []
    cumulative_bricks = []
    step_number = 1

    for layer_z, layer_bricks in sorted_layers:
        # For now, each layer = one step
        # (Could split if layer has >8 bricks, but keeping simple for MVP)

        cumulative_bricks.extend(layer_bricks)
        description = _describe_step(layer_bricks, layer_z)

        step = BuildStep(
            step_number=step_number,
            layer=layer_z,
            bricks_to_add=layer_bricks,
            description=description,
            image_path=None,  # Will be set by instruction_generator
            cumulative_bricks=cumulative_bricks.copy(),
        )
        steps.append(step)
        step_number += 1

    logger.info(f"Sequenced {len(bricks)} bricks into {len(steps)} steps")
    return steps


def _describe_step(bricks: list[Brick], layer: int) -> str:
    """Generate a human-readable description of a build step."""
    if not bricks:
        return f"Layer {layer}"

    # Count by color
    color_counts = defaultdict(int)
    for brick in bricks:
        color_counts[brick.color] += 1

    # Build description
    parts = []
    for color, count in sorted(color_counts.items()):
        parts.append(f"{count} {color}")

    description = f"Layer {layer}: Add {', '.join(parts)} brick(s)"
    return description
