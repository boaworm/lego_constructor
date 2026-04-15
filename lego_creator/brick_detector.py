"""Brick detection using Claude Vision API via AWS Bedrock."""

import json
import logging
import base64

from .models import ProcessedImage
from .config import CLAUDE_MODEL, MAX_TOKENS, BATCH_SIZE_IMAGES

logger = logging.getLogger(__name__)


def detect_bricks(images: list[ProcessedImage], client) -> dict:
    """
    Detect bricks in images using Claude Vision API.

    Sends images in batches to Claude and requests structured JSON output
    with brick type, color, position description, and confidence.

    Args:
        images: List of ProcessedImage objects
        client: Anthropic API client

    Returns:
        Dict mapping image filename to list of detected bricks:
        {
            "image_name.jpg": [
                {"type": "2x4", "color": "red", "position_desc": "front-left", "confidence": 0.95},
                ...
            ]
        }
    """
    detections = {}

    # Process in batches
    for batch_start in range(0, len(images), BATCH_SIZE_IMAGES):
        batch_end = min(batch_start + BATCH_SIZE_IMAGES, len(images))
        batch = images[batch_start:batch_end]

        logger.info(f"Processing batch {batch_start // BATCH_SIZE_IMAGES + 1}: {len(batch)} images")

        # Build content block with images + prompt
        content = []
        for img in batch:
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": img.media_type,
                    "data": img.base64_data.replace("\n", ""),
                },
            })

        # Add text prompt
        prompt = """Analyze these LEGO model images. For each distinct brick you can see, provide:
1. Type: dimensions in studs (e.g., "2x4", "1x2", "1x1")
2. Color: a standard LEGO color name (red, blue, yellow, white, black, green, orange, purple, pink, brown, grey, dark_grey, light_grey, cyan, tan)
3. Position description: which part of the model (e.g., "front-left corner", "center layer 2")
4. Confidence: 0.0-1.0 estimate of how certain you are

Return a JSON object with this structure:
{
  "image_filename": [
    {"type": "2x4", "color": "red", "position_desc": "...", "confidence": 0.95},
    ...
  ]
}

Be thorough and list every visible brick, even if partially obscured."""

        content.append({
            "type": "text",
            "text": prompt,
        })

        # Call Claude via Bedrock
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
        response_data = response['body'].read()
        response_body = json.loads(response_data)
        response_text = response_body['content'][0]['text']
        try:
            response_json = json.loads(response_text)
        except json.JSONDecodeError as e:
            # Try to extract JSON from markdown code blocks
            if "```json" in response_text:
                json_str = response_text.split("```json")[1].split("```")[0].strip()
                try:
                    response_json = json.loads(json_str)
                except json.JSONDecodeError as e2:
                    logger.error(f"Failed to parse extracted JSON: {e2}")
                    logger.error(f"JSON string length: {len(json_str)}, first 300 chars: {json_str[:300]}")
                    response_json = {}
            elif "```" in response_text:
                json_str = response_text.split("```")[1].split("```")[0].strip()
                try:
                    response_json = json.loads(json_str)
                except json.JSONDecodeError as e2:
                    logger.error(f"Failed to parse extracted JSON: {e2}")
                    response_json = {}
            else:
                logger.error(f"Failed to parse JSON response: {response_text[:200]}")
                response_json = {}

        # Map detections to image names
        for img in batch:
            img_key = img.path.name
            detections[img_key] = response_json.get(img_key, [])

    logger.info(f"Detection complete: {sum(len(v) for v in detections.values())} bricks found")
    return detections
