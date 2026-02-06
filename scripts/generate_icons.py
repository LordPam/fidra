#!/usr/bin/env python3
"""Generate application icons from SVG source.

This script converts the Fidra logo SVG into platform-specific icon formats:
- macOS: .icns (Apple Icon Image)
- Windows: .ico (Windows Icon)

Uses PySide6's SVG rendering (no extra dependencies needed).

Usage:
    python scripts/generate_icons.py

The script will create icons in fidra/resources/icons/
"""

import subprocess
import sys
from pathlib import Path

# Use PySide6 for SVG rendering (already a project dependency)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QImage, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication


def get_project_root() -> Path:
    """Get the project root directory."""
    return Path(__file__).resolve().parent.parent


def svg_to_png(svg_path: Path, png_path: Path, size: int, app: QApplication) -> None:
    """Convert SVG to PNG at specified size using PySide6."""
    renderer = QSvgRenderer(str(svg_path))

    # Create image with transparency
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)

    # Render SVG to image
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    renderer.render(painter)
    painter.end()

    # Save as PNG
    image.save(str(png_path), "PNG")


def create_icns(png_sizes: dict[int, Path], output_path: Path) -> None:
    """Create macOS .icns file from PNG images.

    Uses iconutil which is available on macOS.
    """
    import shutil
    import tempfile

    # Create iconset directory
    with tempfile.TemporaryDirectory() as tmpdir:
        iconset_path = Path(tmpdir) / "Fidra.iconset"
        iconset_path.mkdir()

        # Copy PNGs with correct naming convention for iconutil
        icon_mappings = [
            (16, "icon_16x16.png"),
            (32, "icon_16x16@2x.png"),
            (32, "icon_32x32.png"),
            (64, "icon_32x32@2x.png"),
            (128, "icon_128x128.png"),
            (256, "icon_128x128@2x.png"),
            (256, "icon_256x256.png"),
            (512, "icon_256x256@2x.png"),
            (512, "icon_512x512.png"),
            (1024, "icon_512x512@2x.png"),
        ]

        for size, name in icon_mappings:
            if size in png_sizes:
                shutil.copy(png_sizes[size], iconset_path / name)

        # Run iconutil to create .icns
        result = subprocess.run(
            ["iconutil", "-c", "icns", str(iconset_path), "-o", str(output_path)],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            print(f"iconutil failed: {result.stderr}")
            raise RuntimeError("Failed to create .icns file")


def create_ico(png_sizes: dict[int, Path], output_path: Path) -> None:
    """Create Windows .ico file from PNG images.

    Uses PIL/Pillow for ICO creation.
    """
    try:
        from PIL import Image
    except ImportError:
        print("Warning: Pillow not installed, skipping .ico creation")
        print("Install with: pip install pillow")
        return

    # Windows ICO typically includes these sizes
    ico_sizes = [16, 24, 32, 48, 64, 128, 256]

    images = []
    for size in ico_sizes:
        if size in png_sizes:
            img = Image.open(png_sizes[size])
            images.append(img)

    if images:
        # Save as ICO (first image is the "main" one)
        images[0].save(
            output_path,
            format='ICO',
            sizes=[(img.width, img.height) for img in images],
            append_images=images[1:],
        )


def main():
    # Initialize Qt application (required for SVG rendering)
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    project_root = get_project_root()

    # Source SVG
    svg_path = project_root / "fidra" / "ui" / "theme" / "icons" / "icon.svg"
    if not svg_path.exists():
        print(f"Error: SVG not found at {svg_path}")
        sys.exit(1)

    # Output directory
    output_dir = project_root / "fidra" / "resources" / "icons"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Temporary directory for intermediate PNGs
    tmp_dir = output_dir / "tmp"
    tmp_dir.mkdir(exist_ok=True)

    print(f"Source: {svg_path}")
    print(f"Output: {output_dir}")

    # Generate PNGs at various sizes
    sizes = [16, 24, 32, 48, 64, 128, 256, 512, 1024]
    png_sizes = {}

    print("\nGenerating PNG files...")
    for size in sizes:
        png_path = tmp_dir / f"icon_{size}.png"
        print(f"  {size}x{size}...")
        svg_to_png(svg_path, png_path, size, app)
        png_sizes[size] = png_path

    # Create macOS .icns
    if sys.platform == "darwin":
        print("\nCreating macOS icon (fidra.icns)...")
        icns_path = output_dir / "fidra.icns"
        try:
            create_icns(png_sizes, icns_path)
            print(f"  Created: {icns_path}")
        except Exception as e:
            print(f"  Warning: Could not create .icns: {e}")
            print("  (iconutil is only available on macOS)")
    else:
        print("\nSkipping macOS icon (not on macOS)")

    # Create Windows .ico
    print("\nCreating Windows icon (fidra.ico)...")
    ico_path = output_dir / "fidra.ico"
    try:
        create_ico(png_sizes, ico_path)
        print(f"  Created: {ico_path}")
    except Exception as e:
        print(f"  Warning: Could not create .ico: {e}")

    # Clean up temporary PNGs
    print("\nCleaning up temporary files...")
    for png_path in png_sizes.values():
        if png_path.exists():
            png_path.unlink()
    if tmp_dir.exists():
        tmp_dir.rmdir()

    print("\nDone!")


if __name__ == "__main__":
    main()
