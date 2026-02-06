#!/bin/bash
# Build Fidra for macOS
#
# This script builds Fidra.app and optionally creates a DMG installer.
#
# Usage:
#   ./scripts/build_macos.sh          # Build app only
#   ./scripts/build_macos.sh --dmg    # Build app and create DMG
#
# Requirements:
#   - Python 3.11+
#   - pip install pyinstaller cairosvg pillow
#   - create-dmg (brew install create-dmg) for DMG creation

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Get script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

echo -e "${GREEN}Building Fidra for macOS${NC}"
echo "Project root: $PROJECT_ROOT"
echo ""

# Check for pyinstaller
if ! command -v pyinstaller &> /dev/null; then
    echo -e "${RED}Error: pyinstaller not found${NC}"
    echo "Install with: pip install pyinstaller"
    exit 1
fi

# Generate icons if they don't exist
ICON_PATH="$PROJECT_ROOT/fidra/resources/icons/fidra.icns"
if [ ! -f "$ICON_PATH" ]; then
    echo -e "${YELLOW}Generating application icons...${NC}"
    python scripts/generate_icons.py
fi

# Clean previous builds
echo -e "${YELLOW}Cleaning previous builds...${NC}"
rm -rf build dist

# Run PyInstaller
echo -e "${YELLOW}Running PyInstaller...${NC}"
pyinstaller fidra.spec --noconfirm

# Check if build succeeded
if [ ! -d "dist/Fidra.app" ]; then
    echo -e "${RED}Build failed: Fidra.app not found${NC}"
    exit 1
fi

echo -e "${GREEN}Build complete: dist/Fidra.app${NC}"

# Get app size
APP_SIZE=$(du -sh dist/Fidra.app | cut -f1)
echo "App size: $APP_SIZE"

# Create DMG if requested
if [ "$1" == "--dmg" ]; then
    echo ""
    echo -e "${YELLOW}Creating DMG installer...${NC}"

    # Check for create-dmg
    if ! command -v create-dmg &> /dev/null; then
        echo -e "${RED}Error: create-dmg not found${NC}"
        echo "Install with: brew install create-dmg"
        exit 1
    fi

    # Get version from pyproject.toml
    VERSION=$(grep 'version = ' pyproject.toml | head -1 | cut -d'"' -f2)
    DMG_NAME="Fidra-${VERSION}-macOS.dmg"

    # Remove old DMG if exists
    rm -f "dist/$DMG_NAME"

    # Create DMG
    create-dmg \
        --volname "Fidra" \
        --volicon "$ICON_PATH" \
        --window-pos 200 120 \
        --window-size 600 400 \
        --icon-size 100 \
        --icon "Fidra.app" 150 190 \
        --hide-extension "Fidra.app" \
        --app-drop-link 450 185 \
        "dist/$DMG_NAME" \
        "dist/Fidra.app"

    echo -e "${GREEN}DMG created: dist/$DMG_NAME${NC}"
    DMG_SIZE=$(du -sh "dist/$DMG_NAME" | cut -f1)
    echo "DMG size: $DMG_SIZE"
fi

echo ""
echo -e "${GREEN}Build successful!${NC}"
