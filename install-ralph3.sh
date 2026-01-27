#!/bin/bash
# Install ralph3 to your PATH

INSTALL_DIR="${1:-$HOME/.local/bin}"

# Create directory if needed
mkdir -p "$INSTALL_DIR"

# Copy script
cp "$(dirname "$0")/ralph3.sh" "$INSTALL_DIR/ralph3"
chmod +x "$INSTALL_DIR/ralph3"

echo "Installed ralph3 to $INSTALL_DIR/ralph3"

# Check if in PATH
if [[ ":$PATH:" != *":$INSTALL_DIR:"* ]]; then
  echo ""
  echo "Note: $INSTALL_DIR is not in your PATH."
  echo "Add this to your ~/.zshrc or ~/.bashrc:"
  echo "  export PATH=\"$INSTALL_DIR:\$PATH\""
fi
