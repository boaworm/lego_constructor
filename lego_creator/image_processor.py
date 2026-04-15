"""Image loading, validation, and preprocessing."""

import base64
from pathlib import Path
from PIL import Image
import logging

from .models import ProcessedImage
from .config import SUPPORTED_FORMATS, MAX_IMAGE_DIMENSION

logger = logging.getLogger(__name__)


def load_images(folder: Path) -> list[ProcessedImage]:
    """
    Load all supported image files from a folder (non-recursive).

    Args:
        folder: Path to folder containing images

    Returns:
        List of ProcessedImage objects, sorted by filename
    """
    folder = Path(folder)
    if not folder.is_dir():
        raise ValueError(f"Folder not found: {folder}")

    processed = []
    for image_path in sorted(folder.iterdir()):
        if image_path.suffix.lower() not in SUPPORTED_FORMATS:
            continue

        try:
            processed_img = _process_single_image(image_path)
            processed.append(processed_img)
            logger.info(f"Loaded {image_path.name}")
        except Exception as e:
            logger.warning(f"Failed to load {image_path.name}: {e}")

    if not processed:
        raise ValueError(f"No supported images found in {folder}")

    logger.info(f"Loaded {len(processed)} images")
    return processed


def _process_single_image(image_path: Path) -> ProcessedImage:
    """
    Load, validate, resize, and encode a single image.

    Args:
        image_path: Path to image file

    Returns:
        ProcessedImage with base64-encoded data
    """
    # Open and validate
    img = Image.open(image_path)

    # Convert to RGB (handle RGBA, grayscale, etc.)
    if img.mode != "RGB":
        img = img.convert("RGB")

    # Resize if too large (preserve aspect ratio)
    if max(img.size) > MAX_IMAGE_DIMENSION:
        img.thumbnail((MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION), Image.Resampling.LANCZOS)
        logger.debug(f"Resized {image_path.name} to {img.size}")

    # Encode to base64
    buffer = _encode_image_to_base64(img, image_path.suffix.lower())

    # Determine media type
    suffix = image_path.suffix.lower()
    media_type_map = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }
    media_type = media_type_map.get(suffix, "image/jpeg")

    return ProcessedImage(
        path=image_path,
        base64_data=buffer,
        media_type=media_type,
    )


def _encode_image_to_base64(img: Image.Image, original_suffix: str) -> str:
    """
    Encode a PIL Image to base64-encoded bytes.

    Args:
        img: PIL Image object
        original_suffix: Original file extension (to preserve format)

    Returns:
        Base64-encoded string
    """
    import io

    # Determine format for save
    format_map = {
        ".jpg": "JPEG",
        ".jpeg": "JPEG",
        ".png": "PNG",
        ".webp": "WEBP",
    }
    save_format = format_map.get(original_suffix.lower(), "JPEG")

    # Save to bytes buffer
    buffer = io.BytesIO()
    img.save(buffer, format=save_format, quality=95)
    buffer.seek(0)

    # Encode to base64
    b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
    return b64
