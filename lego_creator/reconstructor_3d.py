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


def _analyze_dimensions(images: list[ProcessedImage], client) -> tuple[int, int]:
    """
    First-pass call: use chain-of-thought stud counting to determine model dimensions.

    Returns (width, depth).
    """
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

    content.append({"type": "text", "text": """You are a LEGO expert counting the stud footprint of a model.

IGNORE the large flat base plate(s) at the very bottom.
Count only the main castle/model structure built on top.

Use the arch opening as a calibration anchor:
- A standard small LEGO arch gate is 2 studs wide.
- Use that known 2-stud width to estimate the wall sections on each side.

Count the wall on each side of the arch by asking: does each wall look about the same width as the arch (2 studs), or half as wide (1 stud)?

Then:
  Width W = left_wall + arch(2) + right_wall
  Depth D = count stud rows from front face to back face

Reason step by step, then end with exactly this line:
DIMS: WxD"""})

    # Run twice for consensus — single-image estimation is noisy
    from collections import Counter
    votes: list[tuple[int, int]] = []
    for attempt in range(2):
        resp = client.invoke_model(
            modelId=CLAUDE_MODEL,
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 400,
                "messages": [{"role": "user", "content": content}],
            }),
        )
        rb = json.loads(resp["body"].read())
        rt = rb["content"][0]["text"].strip()
        logger.debug(f"Dimension attempt {attempt+1}:\n{rt}")

        dims_found = re.findall(r"DIMS:\s*(\d+)\s*[xX×]\s*(\d+)", rt)
        if dims_found:
            w, d = int(dims_found[-1][0]), int(dims_found[-1][1])
            votes.append((w, d))
            logger.info(f"Dimension attempt {attempt+1}: {w}×{d}")
        else:
            m = re.search(r"(\d+)\s*[xX×]\s*(\d+)", rt)
            if m:
                w, d = int(m.group(1)), int(m.group(2))
                votes.append((w, d))
                logger.info(f"Dimension attempt {attempt+1} (fallback): {w}×{d}")
            else:
                logger.warning(f"Dimension attempt {attempt+1}: could not parse")

    if not votes:
        logger.warning("All dimension attempts failed, using default 6×6")
        return 6, 6

    winner = Counter(votes).most_common(1)[0][0]
    ws = sorted(v[0] for v in votes)
    ds = sorted(v[1] for v in votes)
    # If both agree, use that; otherwise use median per axis
    has_majority = Counter(votes).most_common(1)[0][1] > 1
    w = winner[0] if has_majority else ws[len(ws) // 2]
    d = winner[1] if has_majority else ds[len(ds) // 2]
    logger.info(f"Consensus dimensions: {w}×{d} studs (votes: {votes})")
    return w, d


def reconstruct(
    images: list[ProcessedImage],
    client,
    forced_dims: tuple[int, int] | None = None,
) -> tuple[list[Brick], int, int, int]:
    """
    Analyse images and produce a complete 3D brick layout.

    If forced_dims is given it is used directly; otherwise a first call to
    Claude counts the stud dimensions before generating the full grid.

    Args:
        images: List of ProcessedImage objects
        client: Anthropic API client
        forced_dims: Optional (width, depth) override in studs

    Returns:
        Tuple of (bricks_list, model_width, model_depth, model_height)
    """
    logger.info("Starting 3D reconstruction...")

    if forced_dims is not None:
        model_w, model_d = forced_dims
        logger.info(f"Using forced dimensions: {model_w}×{model_d} studs")
    else:
        # Pass 1: count exact stud dimensions
        model_w, model_d = _analyze_dimensions(images, client)

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

    # Build a concrete example row using detected dimensions
    arch_gap = max(1, model_w // 4)  # rough arch gap width
    wall = model_w - 2 - arch_gap
    left = wall // 2
    right = wall - left
    example_front = "Y" * left + "R" + "." * (arch_gap - 1) + "Y" * right
    example_inner = "Y" + "." * (model_w - 2) + "Y"
    example_back = "Y" * model_w

    prompt = f"""You are a LEGO expert. Produce a complete stud-by-stud map of this LEGO model.

FIXED DIMENSIONS — this model is exactly {model_w} studs wide × {model_d} studs deep.
EVERY row must have exactly {model_w} characters.
EVERY layer must have exactly {model_d} rows.
Do NOT use any other dimensions. This is a hard constraint.

COLOR CODES (one letter per stud):
  K=black  G=green  Y=yellow  R=red  B=blue  W=white
  O=orange P=purple N=brown   S=grey C=cyan  T=tan
  .=empty (air / no brick)

OUTPUT FORMAT — one grid per layer, bottom (z=0) first:
  Each row = one row of studs front-to-back (y direction).
  Each column = one column left-to-right (x direction).

RULES:
1. Every stud that has a brick must have the correct color letter.
2. Use . only where there is genuinely no brick.
3. Base layers (black z=0, then green z=1) must be solid {model_w}×{model_d} rectangles.
4. Do NOT repeat the same layer. Skip any layer identical to the previous one.
5. Keep total layer count to 5-8 for a small model.
6. Arch faces the viewer: arch gap at y=0 (the FIRST row of the layer).
   Example wall layer ({model_w} wide, arch gap ~{arch_gap} studs):
     {example_front}   ← y=0 front: walls + arch gap + red doorstep
     {example_inner}   ← y=1: side walls, hollow interior
     {example_back}   ← y={model_d-1}: back wall solid
7. Red door (R): 1 stud wide at y=0, inside the arch gap. No wider.

After the grids: DIMS: {model_w}x{model_d}xH

Output grids and DIMS only — no other text."""

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

    # Pass 1: remove consecutive exact duplicates
    sorted_zs = sorted(layers.keys())
    deduped = []
    prev_grid = None
    for z in sorted_zs:
        grid = layers[z]
        if grid == prev_grid:
            logger.warning(f"Removing duplicate layer z={z} (identical to previous)")
            continue
        deduped.append(grid)
        prev_grid = grid

    # Pass 2: cap consecutive runs of structurally identical wall layers.
    # A "wall pattern" is defined by which cells are non-empty.
    # Allow at most 1 consecutive layer per pattern.
    # EXCEPTION: skip this check for solid layers (all cells filled) — two solid
    # layers of different colours (e.g. black base then green base) have the same
    # pattern but must both be kept.
    final = []
    run_pattern = None
    for grid in deduped:
        is_solid = all(c != "." for row in grid for c in row)
        pattern = tuple(
            tuple(1 if c != "." else 0 for c in row)
            for row in grid
        )
        if not is_solid and pattern == run_pattern:
            logger.warning("Removing repeated wall-pattern layer (consecutive duplicate)")
            continue
        run_pattern = None if is_solid else pattern
        final.append(grid)

    # Pass 3: global exact-grid deduplication — remove any grid that is an exact
    # repeat of a previously-seen grid regardless of position (catches A-B-A patterns).
    seen_grids: set[tuple] = set()
    globally_deduped = []
    for grid in final:
        key = tuple(grid)
        if key in seen_grids:
            logger.warning("Removing globally duplicated layer (non-consecutive exact repeat)")
            continue
        seen_grids.add(key)
        globally_deduped.append(grid)

    layers = {z: grid for z, grid in enumerate(globally_deduped)}
    height = len(layers)

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
