#!/bin/bash
# Taskmaster setup script

echo "======================================"
echo "Taskmaster Setup"
echo "======================================"
echo ""

# Check Python version
echo "Checking Python installation..."
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is not installed"
    echo "Please install Python 3.6 or higher"
    exit 1
fi

PYTHON_VERSION=$(python3 --version | awk '{print $2}')
echo "Found Python $PYTHON_VERSION"
echo ""

# Check pip
echo "Checking pip installation..."
if ! command -v pip3 &> /dev/null; then
    echo "Error: pip3 is not installed"
    echo "Please install pip3"
    exit 1
fi
echo "pip3 is installed"
echo ""

# Install dependencies
echo "Installing dependencies..."
pip3 install pyyaml

if [ $? -ne 0 ]; then
    echo "Error: Failed to install dependencies"
    exit 1
fi
echo "Dependencies installed successfully"
echo ""

# Make scripts executable
echo "Making scripts executable..."
chmod +x taskmaster.py
echo "Scripts are now executable"
echo ""

# Create log directory
echo "Creating directories..."
mkdir -p /tmp
echo "Directories created"
echo ""

# Test import
echo "Testing installation..."
python3 -c "import yaml; print('PyYAML OK')" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "Warning: Could not import yaml module"
    echo "You may need to add ~/.local/bin to your PATH"
    echo "Or install with: sudo pip3 install pyyaml"
fi
echo ""

# Final message
echo "======================================"
echo "Setup Complete!"
echo "======================================"
echo ""
echo "To start taskmaster:"
echo "  ./taskmaster.py config.yaml"
echo ""
echo "Or use the test configuration:"
echo "  ./taskmaster.py test_config.yaml"
echo ""
echo "For more information, see README.md"
echo ""