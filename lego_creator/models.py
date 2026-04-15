"""Data models for LEGO brick analysis and instruction generation."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import List


@dataclass
class ProcessedImage:
    """An image that has been loaded, resized, and encoded."""
    path: Path
    base64_data: str
    media_type: str  # "image/jpeg", "image/png", "image/webp"


@dataclass
class Brick:
    """A single LEGO brick in 3D space."""
    type: str           # e.g., "2x4", "1x2", "2x2", "1x1"
    color: str          # e.g., "red", "blue", "yellow", "white", "black", "grey"
    x: int              # column (studs, 0-indexed from left)
    y: int              # row (studs, 0-indexed from front)
    z: int              # layer (0 = ground, upward)
    orientation: str    # "EW" (long axis left-right) or "NS" (long axis front-back)
    confidence: float   # 0.0–1.0, how certain we are about this brick
    source_images: List[str] = field(default_factory=list)  # image filenames

    def dimensions(self) -> tuple:
        """Return (width_studs, depth_studs) based on type and orientation."""
        parts = self.type.split("x")
        if len(parts) != 2:
            raise ValueError(f"Invalid brick type: {self.type}")
        w, d = int(parts[0]), int(parts[1])
        # If orientation is NS (north-south), swap width/depth
        if self.orientation == "NS":
            w, d = d, w
        return (w, d)

    def occupies_cells(self) -> set:
        """Return the set of (x, y) cells this brick occupies."""
        w, d = self.dimensions()
        cells = set()
        for dx in range(w):
            for dy in range(d):
                cells.add((self.x + dx, self.y + dy))
        return cells


@dataclass
class BuildStep:
    """A single step in the building sequence."""
    step_number: int
    layer: int  # which z-level this step adds to
    bricks_to_add: List[Brick]
    description: str  # e.g., "Add 3 red 2x4 bricks to layer 1"
    image_path: Path = None  # rendered PNG for this step
    cumulative_bricks: List[Brick] = field(default_factory=list)  # all bricks up to and including this step


@dataclass
class LegoModel:
    """The complete LEGO model."""
    name: str
    bricks: List[Brick]
    steps: List[BuildStep]
    width: int   # max x extent in studs
    depth: int   # max y extent in studs
    height: int  # max z extent in layers

    def part_count(self, color: str = None, brick_type: str = None) -> int:
        """Count bricks matching color and/or type. None means all."""
        count = 0
        for brick in self.bricks:
            if color and brick.color != color:
                continue
            if brick_type and brick.type != brick_type:
                continue
            count += 1
        return count

    def parts_by_color_and_type(self) -> dict:
        """Return {(color, type): count} for parts list."""
        parts = {}
        for brick in self.bricks:
            key = (brick.color, brick.type)
            parts[key] = parts.get(key, 0) + 1
        return parts
