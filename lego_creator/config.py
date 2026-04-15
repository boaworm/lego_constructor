"""Configuration constants for LEGO Instructions Creator."""

import os

# Claude API
CLAUDE_MODEL = os.getenv("ANTHROPIC_MODEL", "anthropic.claude-opus-4-6-v1")
MAX_TOKENS = 8192

# Image processing
SUPPORTED_FORMATS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_IMAGE_DIMENSION = 1024  # longest side in pixels
BATCH_SIZE_IMAGES = 10  # max images to send in a single detection call

# Grid rendering
GRID_CELL_PX = 30  # pixels per stud in top-down visualization
GRID_MARGIN_PX = 40
GRID_LINE_COLOR = (200, 200, 200)  # light grey
GRID_LINE_WIDTH = 1

# Model constraints
MAX_STUDS_DEFAULT = 48  # max width/depth
MAX_LAYERS_DEFAULT = 20  # max height

# Standard LEGO colors (color name → RGB)
BRICK_COLORS = {
    "red": (204, 0, 0),
    "blue": (0, 85, 191),
    "yellow": (255, 205, 0),
    "white": (242, 243, 243),
    "black": (27, 42, 52),
    "green": (39, 142, 74),
    "orange": (255, 128, 20),
    "purple": (155, 38, 182),
    "pink": (255, 192, 203),
    "brown": (139, 69, 19),
    "grey": (108, 110, 116),
    "dark_grey": (56, 61, 65),
    "light_grey": (194, 194, 194),
    "cyan": (0, 176, 240),
    "tan": (208, 188, 126),
}

# Default color if unmapped
DEFAULT_COLOR = "grey"
DEFAULT_COLOR_RGB = BRICK_COLORS[DEFAULT_COLOR]

# Step image rendering
STEP_IMAGE_BACKGROUND = (255, 255, 255)  # white
NEW_BRICK_HIGHLIGHT_COLOR = (255, 255, 0)  # bright yellow
NEW_BRICK_BORDER_WIDTH = 3
EXISTING_BRICK_OPACITY = 0.7  # alpha blending approximation (via color mixing)
BRICK_LABEL_FONT_SIZE = 10  # approximate, Pillow will use default
