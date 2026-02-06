#!/bin/bash
# Quick-start script for Fidra

echo "🚀 Starting Fidra..."
echo ""

# Check if virtual environment is activated
if [[ -z "$VIRTUAL_ENV" ]]; then
    echo "⚠️  Warning: No virtual environment detected"
    echo "   Run: source .venv/bin/activate"
    echo ""
fi

# Run the application
python main.py

echo ""
echo "👋 Fidra closed"
