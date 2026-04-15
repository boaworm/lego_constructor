"""Instruction generation: render step images and generate HTML output."""

import base64
import logging
from pathlib import Path
from PIL import Image, ImageDraw
from jinja2 import Template

from .models import BuildStep, LegoModel
from .config import (
    GRID_CELL_PX, GRID_MARGIN_PX, GRID_LINE_COLOR, GRID_LINE_WIDTH,
    STEP_IMAGE_BACKGROUND, NEW_BRICK_HIGHLIGHT_COLOR, NEW_BRICK_BORDER_WIDTH,
    BRICK_COLORS, DEFAULT_COLOR_RGB,
)

logger = logging.getLogger(__name__)


def render_step_image(step: BuildStep, model: LegoModel, output_dir: Path) -> Path:
    """
    Render a top-down grid view of a build step.

    Shows existing bricks (cumulative minus new) in dimmed color,
    and new bricks with a bright yellow border.

    Args:
        step: BuildStep with cumulative_bricks and bricks_to_add
        model: LegoModel for grid dimensions
        output_dir: Directory to save PNG

    Returns:
        Path to generated PNG file
    """
    # Canvas size
    canvas_w = model.width * GRID_CELL_PX + 2 * GRID_MARGIN_PX
    canvas_h = model.depth * GRID_CELL_PX + 2 * GRID_MARGIN_PX

    img = Image.new("RGB", (canvas_w, canvas_h), STEP_IMAGE_BACKGROUND)
    draw = ImageDraw.Draw(img, "RGBA")

    # Draw grid lines
    for x in range(model.width + 1):
        x_px = GRID_MARGIN_PX + x * GRID_CELL_PX
        draw.line([(x_px, GRID_MARGIN_PX), (x_px, canvas_h - GRID_MARGIN_PX)],
                  fill=GRID_LINE_COLOR, width=GRID_LINE_WIDTH)

    for y in range(model.depth + 1):
        y_px = GRID_MARGIN_PX + y * GRID_CELL_PX
        draw.line([(GRID_MARGIN_PX, y_px), (canvas_w - GRID_MARGIN_PX, y_px)],
                  fill=GRID_LINE_COLOR, width=GRID_LINE_WIDTH)

    # Identify new bricks for highlighting
    new_brick_ids = {id(brick) for brick in step.bricks_to_add}

    # Draw existing bricks (cumulative minus new)
    for brick in step.cumulative_bricks:
        if id(brick) not in new_brick_ids:
            _draw_brick(draw, brick, model, dimmed=True)

    # Draw new bricks with highlight
    for brick in step.bricks_to_add:
        _draw_brick(draw, brick, model, dimmed=False, highlight=True)

    # Save
    output_path = output_dir / f"step_{step.step_number:02d}.png"
    img.save(output_path, "PNG")
    logger.info(f"Rendered {output_path.name}")

    return output_path


def _draw_brick(
    draw: ImageDraw.ImageDraw,
    brick,
    model: LegoModel,
    dimmed: bool = False,
    highlight: bool = False,
) -> None:
    """
    Draw a single brick on the canvas.

    Args:
        draw: PIL ImageDraw object
        brick: Brick to draw
        model: LegoModel for coordinate reference
        dimmed: If True, draw with 70% opacity effect
        highlight: If True, draw yellow border
    """
    # Get brick dimensions
    w, d = brick.dimensions()

    # Convert grid coordinates to pixel coordinates
    x_px = GRID_MARGIN_PX + brick.x * GRID_CELL_PX
    y_px = GRID_MARGIN_PX + brick.y * GRID_CELL_PX
    x_px_end = x_px + w * GRID_CELL_PX
    y_px_end = y_px + d * GRID_CELL_PX

    # Get brick color
    color_rgb = BRICK_COLORS.get(brick.color.lower(), DEFAULT_COLOR_RGB)

    # Apply dimming if needed
    if dimmed:
        # Mix with white to simulate 70% opacity
        color_rgb = tuple(
            int(c * 0.7 + 255 * 0.3) for c in color_rgb
        )

    # Draw filled rectangle for brick
    draw.rectangle([x_px, y_px, x_px_end - 1, y_px_end - 1],
                   fill=color_rgb, outline=None)

    # Draw highlight border if new
    if highlight:
        border_size = NEW_BRICK_BORDER_WIDTH
        for i in range(border_size):
            draw.rectangle(
                [x_px + i, y_px + i, x_px_end - 1 - i, y_px_end - 1 - i],
                outline=NEW_BRICK_HIGHLIGHT_COLOR,
                fill=None,
            )

    # Optionally draw brick label (if cell is large enough)
    if GRID_CELL_PX >= 25:
        label = brick.type
        # Simple text centering (Pillow default font)
        try:
            draw.text(
                ((x_px + x_px_end) / 2, (y_px + y_px_end) / 2),
                label,
                fill=(0, 0, 0),
                anchor="mm",
            )
        except Exception:
            pass  # Ignore if text rendering fails


def generate_html(model: LegoModel, steps: list[BuildStep], output_dir: Path, images_folder: Path = None) -> Path:
    """
    Generate HTML instruction file.

    Args:
        model: LegoModel with complete brick data
        steps: List of BuildStep objects (should have image_path set)
        output_dir: Directory to save HTML
        images_folder: Directory containing input images (optional)

    Returns:
        Path to generated HTML file
    """
    # Build parts list
    parts_dict = model.parts_by_color_and_type()
    parts_list = []
    for (color, brick_type), count in sorted(parts_dict.items()):
        parts_list.append({
            "color": color,
            "type": brick_type,
            "count": count,
        })

    total_parts = sum(p["count"] for p in parts_list)

    # Load reference image if available
    reference_image_base64 = None
    if images_folder:
        # Find first image in folder
        for ext in ['jpg', 'jpeg', 'png', 'gif', 'bmp']:
            image_files = list(images_folder.glob(f"*.{ext}")) + list(images_folder.glob(f"*.{ext.upper()}"))
            if image_files:
                image_path = sorted(image_files)[0]
                try:
                    with open(image_path, "rb") as f:
                        reference_image_base64 = base64.b64encode(f.read()).decode("utf-8")
                    break
                except Exception as e:
                    logger.warning(f"Could not load reference image {image_path}: {e}")

    # Prepare step data with base64-encoded images
    steps_data = []
    for step in steps:
        step_data = {
            "step_number": step.step_number,
            "layer": step.layer,
            "description": step.description,
            "new_brick_count": len(step.bricks_to_add),
            "image_base64": None,
        }

        # Embed image as base64
        if step.image_path and step.image_path.exists():
            with open(step.image_path, "rb") as f:
                step_data["image_base64"] = base64.b64encode(f.read()).decode("utf-8")

        steps_data.append(step_data)

    # Render template
    html_template = _get_html_template()
    template = Template(html_template)

    # Create a filter function for color to RGB
    def color_to_rgb(color_name: str) -> str:
        rgb = BRICK_COLORS.get(color_name.lower(), DEFAULT_COLOR_RGB)
        return f"{rgb[0]}, {rgb[1]}, {rgb[2]}"

    html_content = template.render(
        model_name=model.name,
        total_parts=total_parts,
        total_steps=len(steps),
        parts_list=parts_list,
        steps=steps_data,
        color_to_rgb=color_to_rgb,
        reference_image_base64=reference_image_base64,
    )

    # Save
    output_path = output_dir / "instructions.html"
    with open(output_path, "w") as f:
        f.write(html_content)

    logger.info(f"Generated {output_path.name}")
    return output_path


def _get_html_template() -> str:
    """Return the Jinja2 HTML template."""
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ model_name }} - LEGO Instructions</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            line-height: 1.6;
            color: #333;
            background: #f5f5f5;
        }

        .container {
            max-width: 1000px;
            margin: 0 auto;
            padding: 20px;
        }

        header {
            background: white;
            padding: 30px;
            border-radius: 8px;
            margin-bottom: 30px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }

        h1 {
            font-size: 2.5em;
            margin-bottom: 10px;
            color: #222;
        }

        .header-content {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 30px;
            align-items: start;
        }

        .header-info {
            display: flex;
            flex-direction: column;
        }

        .header-stats {
            display: flex;
            gap: 30px;
            margin-top: 20px;
            font-size: 1.1em;
        }

        .reference-image {
            display: flex;
            flex-direction: column;
            align-items: center;
        }

        .reference-image-label {
            font-size: 0.9em;
            color: #888;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 10px;
        }

        .reference-image img {
            max-width: 100%;
            height: auto;
            border: 2px solid #ddd;
            border-radius: 4px;
            max-height: 300px;
        }

        .stat {
            display: flex;
            flex-direction: column;
        }

        .stat-label {
            color: #888;
            font-size: 0.9em;
            text-transform: uppercase;
            letter-spacing: 1px;
        }

        .stat-value {
            font-size: 1.8em;
            font-weight: bold;
            color: #2196F3;
        }

        .parts-section {
            background: white;
            padding: 30px;
            border-radius: 8px;
            margin-bottom: 30px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }

        .parts-section h2 {
            font-size: 1.5em;
            margin-bottom: 20px;
            color: #222;
        }

        .parts-table {
            width: 100%;
            border-collapse: collapse;
        }

        .parts-table th {
            text-align: left;
            padding: 12px;
            border-bottom: 2px solid #ddd;
            background: #f9f9f9;
            font-weight: 600;
        }

        .parts-table td {
            padding: 12px;
            border-bottom: 1px solid #eee;
        }

        .parts-table tr:hover {
            background: #f9f9f9;
        }

        .color-box {
            display: inline-block;
            width: 30px;
            height: 30px;
            border-radius: 4px;
            border: 1px solid #ccc;
            vertical-align: middle;
            margin-right: 10px;
        }

        .steps-section {
            margin-bottom: 30px;
        }

        .step {
            background: white;
            padding: 30px;
            border-radius: 8px;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            page-break-inside: avoid;
        }

        .step-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
            border-bottom: 2px solid #eee;
            padding-bottom: 15px;
        }

        .step-number {
            font-size: 1.3em;
            font-weight: bold;
            color: #2196F3;
        }

        .step-description {
            font-size: 1.1em;
            color: #555;
            margin-bottom: 10px;
        }

        .step-meta {
            font-size: 0.9em;
            color: #999;
        }

        .step-image {
            text-align: center;
            margin: 20px 0;
        }

        .step-image img {
            max-width: 100%;
            height: auto;
            border: 1px solid #ddd;
            border-radius: 4px;
            background: white;
        }

        .step-footer {
            text-align: right;
            font-size: 0.9em;
            color: #999;
            margin-top: 15px;
        }

        @media print {
            body {
                background: white;
            }
            .container {
                max-width: 100%;
            }
            header, .parts-section, .step {
                box-shadow: none;
                page-break-inside: avoid;
            }
        }

        @media (max-width: 768px) {
            .header-content {
                grid-template-columns: 1fr;
            }
            .header-stats {
                flex-direction: column;
                gap: 15px;
            }
            .parts-table {
                font-size: 0.9em;
            }
            .parts-table th, .parts-table td {
                padding: 8px;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div class="header-content">
                <div class="header-info">
                    <h1>{{ model_name }}</h1>
                    <div class="header-stats">
                        <div class="stat">
                            <div class="stat-label">Total Pieces</div>
                            <div class="stat-value">{{ total_parts }}</div>
                        </div>
                        <div class="stat">
                            <div class="stat-label">Build Steps</div>
                            <div class="stat-value">{{ total_steps }}</div>
                        </div>
                    </div>
                </div>
                {% if reference_image_base64 %}
                <div class="reference-image">
                    <div class="reference-image-label">Expected Result</div>
                    <img src="data:image/jpeg;base64,{{ reference_image_base64 }}" alt="Expected Result">
                </div>
                {% endif %}
            </div>
        </header>

        <div class="parts-section">
            <h2>Parts List</h2>
            <table class="parts-table">
                <thead>
                    <tr>
                        <th>Color</th>
                        <th>Type</th>
                        <th style="text-align: right;">Quantity</th>
                    </tr>
                </thead>
                <tbody>
                    {% for part in parts_list %}
                    <tr>
                        <td>
                            <span class="color-box" style="background-color: rgb({{ color_to_rgb(part.color) }});"></span>
                            <span>{{ part.color|capitalize }}</span>
                        </td>
                        <td>{{ part.type }} stud(s)</td>
                        <td style="text-align: right; font-weight: 600;">{{ part.count }}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>

        <div class="steps-section">
            {% for step in steps %}
            <div class="step">
                <div class="step-header">
                    <div>
                        <div class="step-number">Step {{ step.step_number }}</div>
                        <div class="step-description">{{ step.description }}</div>
                        <div class="step-meta">New pieces: {{ step.new_brick_count }}</div>
                    </div>
                </div>
                {% if step.image_base64 %}
                <div class="step-image">
                    <img src="data:image/png;base64,{{ step.image_base64 }}" alt="Step {{ step.step_number }}">
                </div>
                {% endif %}
                <div class="step-footer">Layer {{ step.layer }}</div>
            </div>
            {% endfor %}
        </div>
    </div>
</body>
</html>
"""
