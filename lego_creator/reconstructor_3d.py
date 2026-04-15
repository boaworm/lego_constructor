"""3D reconstruction of brick positions from detections."""

import json
import logging

from .models import ProcessedImage, Brick
from .config import CLAUDE_MODEL, MAX_TOKENS, MAX_STUDS_DEFAULT, MAX_LAYERS_DEFAULT

logger = logging.getLogger(__name__)


def reconstruct(
    images: list[ProcessedImage],
    detections: dict,
    client,
) -> tuple[list[Brick], int, int, int]:
    """
    Reconstruct 3D brick positions from multiple images and detections.

    Sends all images + detection summary to Claude and asks it to place
    each unique brick at (x, y, z, orientation) on a stud grid.

    Args:
        images: List of ProcessedImage objects
        detections: Dict from brick_detector output
        client: Anthropic API client

    Returns:
        Tuple of (bricks_list, model_width, model_depth, model_height)
    """
    logger.info("Starting 3D reconstruction...")

    # Build content with all images
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

    # Prepare detection summary for context
    detection_summary = json.dumps(detections, indent=2)

    # Prompt for 3D reconstruction
    prompt = f"""You have already analyzed these LEGO model images and detected the following bricks per image:

{detection_summary}

Now, synthesize all of this information into a unified 3D model. Place each unique brick at specific (x, y, z, orientation) coordinates on a stud grid.

Requirements:
1. Use a 3D coordinate system where:
   - x = column (0 = left, increasing to the right)
   - y = row (0 = front, increasing backward)
   - z = layer (0 = ground, increasing upward)
   - All values are in studs (1 stud = unit grid)

2. For each brick, determine:
   - Its grid position (x, y, z)
   - Its orientation: "EW" if the long axis runs left-right, "NS" if it runs front-back
   - (For a 2x4 brick in EW orientation at x=1, y=2, z=0, it occupies studs x=1-2, y=2, z=0)

3. Bricks must not overlap on the same layer.

4. Use the multiple images to triangulate positions. Bricks visible in multiple views should have consistent positions.

5. Return the maximum dimensions needed: width (max x+1), depth (max y+1), height (max z+1).

Return ONLY a valid JSON object (no markdown, no comments):
{{
  "bricks": [
    {{"type": "2x4", "color": "red", "x": 0, "y": 0, "z": 0, "orientation": "EW"}},
    {{"type": "1x1", "color": "blue", "x": 2, "y": 0, "z": 0, "orientation": "EW"}},
    ...
  ],
  "width": 10,
  "depth": 8,
  "height": 3
}}

Be precise with positions. Use all available visual information from the images."""

    content.append({
        "type": "text",
        "text": prompt,
    })

    # Call Claude via Bedrock with all images
    response = client.invoke_model(
        modelId=CLAUDE_MODEL,
        body=json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": MAX_TOKENS,
            "messages": [{
                "role": "user",
                "content": content,
            }],
        }),
    )

    # Parse response
    response_body = json.loads(response['body'].read())
    response_text = response_body['content'][0]['text']
    try:
        result = json.loads(response_text)
    except json.JSONDecodeError:
        # Try to extract JSON from markdown code blocks
        if "```json" in response_text:
            json_str = response_text.split("```json")[1].split("```")[0].strip()
            result = json.loads(json_str)
        elif "```" in response_text:
            json_str = response_text.split("```")[1].split("```")[0].strip()
            result = json.loads(json_str)
        else:
            logger.error(f"Failed to parse JSON response: {response_text[:500]}")
            raise ValueError("Could not parse 3D reconstruction from Claude")

    # Convert to Brick objects and validate
    bricks = []
    for brick_data in result.get("bricks", []):
        brick = Brick(
            type=brick_data["type"],
            color=brick_data["color"],
            x=brick_data["x"],
            y=brick_data["y"],
            z=brick_data["z"],
            orientation=brick_data["orientation"],
            confidence=0.9,  # Set by Claude, we trust the reconstruction
            source_images=[img.path.name for img in images],
        )
        bricks.append(brick)

    # Extract model dimensions
    width = result.get("width", MAX_STUDS_DEFAULT)
    depth = result.get("depth", MAX_STUDS_DEFAULT)
    height = result.get("height", MAX_LAYERS_DEFAULT)

    # Validate no overlaps
    _validate_no_overlaps(bricks)

    logger.info(f"3D reconstruction complete: {len(bricks)} bricks, "
                f"{width}x{depth}x{height} grid")

    return bricks, width, depth, height


def _validate_no_overlaps(bricks: list[Brick]) -> None:
    """Check that no two bricks occupy the same cell on the same layer."""
    occupied = {}  # (x, y, z) -> brick
    for brick in bricks:
        w, d = brick.dimensions()
        for dx in range(w):
            for dy in range(d):
                key = (brick.x + dx, brick.y + dy, brick.z)
                if key in occupied:
                    other = occupied[key]
                    logger.warning(
                        f"Overlap detected: {brick.color} {brick.type} at {key} "
                        f"overlaps {other.color} {other.type}"
                    )
                    # For now, keep going; could raise an error if strict
                occupied[key] = brick
