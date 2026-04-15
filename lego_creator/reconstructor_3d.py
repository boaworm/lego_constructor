"""3D reconstruction of brick positions from images using layer ASCII maps."""

import json
import logging
import re

from .models import ProcessedImage, Brick
from .config import CLAUDE_MODEL, MAX_TOKENS, MAX_STUDS_DEFAULT, MAX_LAYERS_DEFAULT

logger = logging.getLogger(__name__)

# Color letter → color name mapping used in ASCII maps
_LETTER_TO_COLOR = {
    "K": "black",
    "G": "green",
    "Y": "yellow",
    "R": "red",
    "B": "blue",
    "W": "white",
    "O": "orange",
    "P": "purple",
    "N": "brown",
    "S": "grey",
    "C": "cyan",
    "T": "tan",
}
_COLOR_TO_LETTER = {v: k for k, v in _LETTER_TO_COLOR.items()}

# Allowed brick sizes (width × depth) in EW orientation
_ALLOWED_SIZES = [
    (2, 8), (2, 6), (2, 4), (2, 3), (2, 2),
    (1, 8), (1, 6), (1, 4), (1, 3), (1, 2), (1, 1),
]


def reconstruct(
    images: list[ProcessedImage],
    client,
) -> tuple[list[Brick], int, int, int]:
    """
    Analyse images and produce a complete 3D brick layout.

    Asks Claude for a per-layer ASCII stud map, then converts it to Brick objects.

    Args:
        images: List of ProcessedImage objects
        client: Anthropic API client

    Returns:
        Tuple of (bricks_list, model_width, model_depth, model_height)
    """
    logger.info("Starting 3D reconstruction...")

    content = []
    for img in images:
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": img.media_type,
                "data": img.base64_data.replace("\n", ""),
            },
        })

    prompt = """You are a LEGO expert. Produce a complete stud-by-stud map of this LEGO model.

COLOR CODES (one letter per stud):
  K=black  G=green  Y=yellow  R=red  B=blue  W=white
  O=orange P=purple N=brown   S=grey C=cyan  T=tan
  .=empty (air / no brick)

OUTPUT FORMAT — one grid per layer, bottom (z=0) first:
  Each row of the grid = one row of studs front-to-back (y direction).
  Each column of the grid = one column of studs left-to-right (x direction).
  All rows must be the same width. All layers must be the same size.

Example for a 4-wide × 3-deep model with 2 layers:
z=0
KKKK
KKKK
KKKK

z=1
YYYY
Y..Y
YYYY

RULES:
1. Every stud that has a brick must have the correct color letter.
2. Use . only where there is genuinely no brick (air gaps, arch openings, etc.).
3. The base layers should be solid — only add . for visible holes or openings.
4. Be precise: count the studs carefully from the image.

After the grids, add one line: DIMS: WxDxH  (width, depth, height in studs)

Output the grids and DIMS line only — no other text."""

    content.append({"type": "text", "text": prompt})

    response = client.invoke_model(
        modelId=CLAUDE_MODEL,
        body=json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": MAX_TOKENS,
            "messages": [{"role": "user", "content": content}],
        }),
    )

    response_body = json.loads(response["body"].read())
    response_text = response_body["content"][0]["text"]
    logger.debug(f"Raw ASCII map response:\n{response_text[:1000]}")

    bricks, width, depth, height = _parse_ascii_maps(response_text)

    logger.info(f"3D reconstruction complete: {len(bricks)} bricks, "
                f"{width}x{depth}x{height} grid")
    return bricks, width, depth, height


def _parse_ascii_maps(text: str) -> tuple[list[Brick], int, int, int]:
    """Parse the ASCII layer maps into Brick objects."""
    layers = {}  # z → list[str] (rows)
    current_z = None
    current_rows = []

    for raw_line in text.splitlines():
        line = raw_line.strip()

        # Layer header: "z=0", "z=1", etc.
        m = re.match(r"z\s*=\s*(\d+)", line, re.IGNORECASE)
        if m:
            if current_z is not None and current_rows:
                layers[current_z] = current_rows
            current_z = int(m.group(1))
            current_rows = []
            continue

        # DIMS line
        if line.upper().startswith("DIMS"):
            if current_z is not None and current_rows:
                layers[current_z] = current_rows
            break

        # Grid row: non-empty line that only contains valid characters
        if current_z is not None and line and re.match(r"^[A-Za-z\.]+$", line):
            current_rows.append(line.upper())

    # Flush last layer
    if current_z is not None and current_rows:
        layers[current_z] = current_rows

    if not layers:
        logger.error("No layer grids found in response")
        raise ValueError("Could not parse layer maps from Claude response")

    # Normalise: ensure all layers have the same width and depth
    width = max(len(row) for rows in layers.values() for row in rows)
    depth = max(len(rows) for rows in layers.values())
    height = max(layers.keys()) + 1

    for z, rows in layers.items():
        # Pad rows to uniform width
        layers[z] = [row.ljust(width, ".") for row in rows]
        # Pad depth
        while len(layers[z]) < depth:
            layers[z].append("." * width)

    # Convert each layer grid to bricks
    bricks = []
    for z in sorted(layers.keys()):
        grid = layers[z]
        layer_bricks = _grid_to_bricks(grid, z)
        bricks.extend(layer_bricks)

    return bricks, width, depth, height


def _grid_to_bricks(grid: list[str], z: int) -> list[Brick]:
    """
    Convert a 2D stud grid at layer z into Brick objects.

    Uses a greedy largest-first tiling: scans left-to-right, top-to-bottom,
    and at each unclaimed stud tries to place the largest allowed brick that fits.
    """
    depth = len(grid)
    width = len(grid[0]) if grid else 0
    claimed = [[False] * width for _ in range(depth)]
    bricks = []

    for y in range(depth):
        for x in range(width):
            if claimed[y][x]:
                continue
            color_letter = grid[y][x]
            if color_letter == ".":
                continue
            color = _LETTER_TO_COLOR.get(color_letter, "grey")

            # Try largest brick first
            placed = False
            for (bw, bd) in _ALLOWED_SIZES:
                # Also try NS orientation (swap w and d)
                for (fw, fd, orientation) in [(bw, bd, "EW"), (bd, bw, "NS")]:
                    if fw == fd and orientation == "NS":
                        continue  # skip duplicate for squares
                    if x + fw > width or y + fd > depth:
                        continue
                    # Check all cells are the same color and unclaimed
                    ok = True
                    for dy in range(fd):
                        for dx in range(fw):
                            if claimed[y + dy][x + dx]:
                                ok = False
                                break
                            if grid[y + dy][x + dx] != color_letter:
                                ok = False
                                break
                        if not ok:
                            break
                    if ok:
                        # Claim cells
                        for dy in range(fd):
                            for dx in range(fw):
                                claimed[y + dy][x + dx] = True
                        # Canonical type: always "AxB" where A≤B
                        brick_type = f"{min(bw,bd)}x{max(bw,bd)}"
                        bricks.append(Brick(
                            type=brick_type,
                            color=color,
                            x=x,
                            y=y,
                            z=z,
                            orientation=orientation,
                            confidence=1.0,
                            source_images=[],
                        ))
                        placed = True
                        break
                if placed:
                    break

            if not placed:
                # Fallback: 1x1
                claimed[y][x] = True
                bricks.append(Brick(
                    type="1x1",
                    color=color,
                    x=x,
                    y=y,
                    z=z,
                    orientation="EW",
                    confidence=1.0,
                    source_images=[],
                ))

    return bricks


def _extract_json(text: str) -> dict | None:
    """Try multiple strategies to extract a JSON object from a response string."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    for marker in ("```json", "```"):
        if marker in text:
            inner = text.split(marker)[1].split("```")[0].strip()
            try:
                return json.loads(inner)
            except json.JSONDecodeError:
                pass
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass
    return None
