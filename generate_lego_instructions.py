#!/usr/bin/env python3
"""CLI entry point for LEGO Instructions Creator."""

import sys
import os
import logging
import shutil
from pathlib import Path

import click
import boto3
import json

# Load environment variables from .env file
env_file = Path(__file__).parent / ".env"
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                key, value = line.split("=", 1)
                os.environ[key] = value

# Add parent directory to path so we can import lego_creator
sys.path.insert(0, str(Path(__file__).parent))

from lego_creator.image_processor import load_images
from lego_creator.reconstructor_3d import reconstruct
from lego_creator.sequencer import sequence
from lego_creator.instruction_generator import render_step_image, generate_html
from lego_creator.models import LegoModel

logger = logging.getLogger(__name__)


@click.command()
@click.argument("folder", type=str)
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
@click.option("--size", default=None,
              help="Override model dimensions as WxD studs (e.g. --size 4x4). "
                   "Use this when auto-detection gets the wrong count.")
def main(folder: str, verbose: bool, size: str | None):
    """
    Generate LEGO building instructions from a folder of images.

    FOLDER should contain images of an assembled LEGO model from various angles.
    """
    # Setup logging
    log_level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    try:
        folder_path = Path(folder).resolve()

        # Validate folder exists
        if not folder_path.is_dir():
            click.echo(f"❌ Error: {folder_path} is not a directory", err=True)
            sys.exit(1)

        click.echo(f"🧱 LEGO Instructions Creator")
        click.echo(f"Processing: {folder_path}")
        click.echo()

        # Create AWS Bedrock client
        # Set AWS credentials from environment
        bearer_token = os.getenv("AWS_BEARER_TOKEN_BEDROCK")
        aws_region = os.getenv("AWS_REGION", "us-east-1")

        if not bearer_token:
            click.echo(f"❌ Error: AWS_BEARER_TOKEN_BEDROCK environment variable not set", err=True)
            sys.exit(1)

        try:
            client = boto3.client(
                'bedrock-runtime',
                region_name=aws_region
            )
        except Exception as e:
            click.echo(f"❌ Error: Could not initialize AWS Bedrock client: {e}", err=True)
            sys.exit(1)

        # Phase 1: Load images
        click.echo("📸 Phase 1: Loading images...")
        images = load_images(folder_path)
        click.echo(f"   ✓ Loaded {len(images)} images")

        # Phase 2: Analyse images and reconstruct 3D model in one pass
        click.echo("🔍 Phase 2: Analysing model and reconstructing 3D layout...")

        forced_dims = None
        if size:
            import re as _re
            m = _re.match(r"(\d+)[xX×](\d+)", size.strip())
            if not m:
                click.echo(f"❌ Error: --size must be WxD (e.g. 4x4), got {size!r}", err=True)
                sys.exit(1)
            forced_dims = (int(m.group(1)), int(m.group(2)))
            click.echo(f"   Using fixed dimensions: {forced_dims[0]}×{forced_dims[1]} studs")

        bricks, width, depth, height = reconstruct(images, client, forced_dims=forced_dims)
        click.echo(f"   ✓ Detected footprint: {width}×{depth} studs — if wrong, rerun with --size {width}x{depth}")
        click.echo(f"   ✓ Placed {len(bricks)} brick(s) in 3D space ({width}×{depth}×{height} studs)")

        # Phase 4: Sequencing
        click.echo("📋 Phase 4: Sequencing build steps...")
        steps = sequence(bricks)
        click.echo(f"   ✓ Created {len(steps)} build step(s)")

        # Phase 5: Generate output
        click.echo("📄 Phase 5: Generating instructions...")
        output_dir = folder_path / "output"
        if output_dir.exists():
            shutil.rmtree(output_dir)
        output_dir.mkdir(exist_ok=True)

        # Render step images
        for step in steps:
            model = LegoModel(
                name=folder_path.name,
                bricks=bricks,
                steps=steps,
                width=width,
                depth=depth,
                height=height,
            )
            step.image_path = render_step_image(step, model, output_dir)

        # Generate HTML
        model = LegoModel(
            name=folder_path.name,
            bricks=bricks,
            steps=steps,
            width=width,
            depth=depth,
            height=height,
        )
        html_path = generate_html(model, steps, output_dir, folder_path)

        click.echo(f"   ✓ Generated {len(steps)} step image(s)")
        click.echo(f"   ✓ Generated instructions.html")

        # Summary
        click.echo()
        click.echo("✅ Success!")
        click.echo(f"📁 Output saved to: {output_dir}")
        click.echo(f"🌐 Open in browser: {html_path}")

    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        if verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
