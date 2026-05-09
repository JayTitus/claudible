#!/usr/bin/env bash
# Bootstrap claudible development environment.
# Installs system dependencies, creates a venv, and installs the package.
#
# Usage:
#   ./bootstrap.sh          # dev install (editable + tests)
#   ./bootstrap.sh --user   # user install (uv tool, isolated)

set -euo pipefail

PYTHON_VERSION="3.11"

# Colors
green() { printf '\033[32m%s\033[0m\n' "$*"; }
yellow() { printf '\033[33m%s\033[0m\n' "$*"; }
red() { printf '\033[31m%s\033[0m\n' "$*"; }

# Check for uv
if ! command -v uv &>/dev/null; then
    red "uv not found. Install it first: https://docs.astral.sh/uv/getting-started/installation/"
    exit 1
fi

# Detect platform
install_system_deps() {
    if [[ "$(uname)" == "Linux" ]]; then
        if command -v apt &>/dev/null; then
            yellow "Installing system dependencies (requires sudo)..."
            sudo apt install -y \
                libgirepository1.0-dev \
                libgirepository-2.0-dev \
                libcairo2-dev \
                pkg-config \
                python3-dev \
                gcc \
                gir1.2-ayatanaappindicator3-0.1 \
                xdotool \
                cmake \
                build-essential
        elif command -v dnf &>/dev/null; then
            yellow "Installing system dependencies (requires sudo)..."
            sudo dnf install -y \
                gobject-introspection-devel \
                cairo-devel \
                pkg-config \
                python3-devel \
                gcc \
                xdotool \
                cmake \
                gcc-c++
        else
            yellow "Unsupported package manager. Install these manually:"
            echo "  libgirepository-dev, libcairo2-dev, pkg-config, python3-dev, gcc, xdotool, cmake"
            exit 1
        fi
    elif [[ "$(uname)" == "Darwin" ]]; then
        if command -v brew &>/dev/null; then
            yellow "Installing system dependencies..."
            brew install gobject-introspection cairo pkg-config cmake
        else
            red "Homebrew not found. Install it first: https://brew.sh"
            exit 1
        fi
    fi
}

if [[ "${1:-}" == "--user" ]]; then
    # User install: isolated venv via uv tool
    green "=== Claudible User Install ==="
    install_system_deps
    echo
    yellow "Installing claudible as a tool (isolated environment)..."
    uv tool install . --python "$PYTHON_VERSION"
    echo
    green "Done! Run 'claudible install' to complete setup."
    green "Uninstall with: claudible uninstall && uv tool uninstall claudible"
else
    # Dev install: local venv + editable
    green "=== Claudible Dev Install ==="
    install_system_deps
    echo
    yellow "Creating virtual environment (.venv)..."
    uv venv --python "$PYTHON_VERSION"
    echo
    yellow "Installing claudible in editable mode with dev + linux extras..."
    # shellcheck disable=SC1091
    source .venv/bin/activate
    uv pip install -e ".[linux,dev]"
    echo
    green "Done! Activate with: source .venv/bin/activate"
    green "Then run: claudible install"
fi
