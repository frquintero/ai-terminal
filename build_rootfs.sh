#!/bin/bash
set -euo pipefail

# ============================================================================
# Rootfs Builder for AI Terminal Namespace Isolation
# ============================================================================
# Creates deterministic, minimal Linux rootfs with controlled toolset
# Output: Cached rootfs image at ~/.cache/agent_sandbox/images/<sha256>.tar.gz
#
# Usage:
#   sudo ./build_rootfs.sh [--image-name py-data-3.11]
#
# Requirements:
#   - debootstrap
#   - Root privileges (for chroot)
#   - ~500MB disk space
# ============================================================================

# Configuration
IMAGE_NAME="${1:-py-data-3.11}"
BUILD_DIR="./rootfs_build"
ROOTFS_DIR="$BUILD_DIR/rootfs"
DEBIAN_SNAPSHOT="20241001T000000Z"
DEBIAN_RELEASE="bookworm"
PYTHON_VERSION="3.11"
CACHE_DIR="$HOME/.cache/agent_sandbox/images"

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() { echo -e "${GREEN}[INFO]${NC} $*"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

# Detect OS and suggest appropriate package install command
detect_os_install_cmd() {
    if [[ -f /etc/os-release ]]; then
        . /etc/os-release
        case "$ID" in
            arch|manjaro)
                echo "sudo pacman -S debootstrap"
                ;;
            ubuntu|debian|linuxmint|pop)
                echo "sudo apt-get install debootstrap"
                ;;
            fedora|rhel|centos)
                echo "sudo dnf install debootstrap"
                ;;
            opensuse*)
                echo "sudo zypper install debootstrap"
                ;;
            *)
                echo "Install debootstrap using your package manager"
                ;;
        esac
    else
        echo "Install debootstrap using your package manager"
    fi
}

# Check prerequisites
check_prereqs() {
    log_info "Checking prerequisites..."
    
    if [[ $EUID -ne 0 ]]; then
        log_error "This script must be run as root (for debootstrap/chroot)"
    fi
    
    if ! command -v debootstrap &>/dev/null; then
        local install_cmd=$(detect_os_install_cmd)
        log_error "debootstrap not found. Install with: $install_cmd"
    fi
    
    log_info "✓ Prerequisites satisfied"
}

# Create base Debian rootfs
create_base_rootfs() {
    log_info "Creating base Debian $DEBIAN_RELEASE rootfs..."
    
    mkdir -p "$BUILD_DIR"
    rm -rf "$ROOTFS_DIR"
    
    # Use snapshot.debian.org for reproducibility
    local mirror="http://snapshot.debian.org/archive/debian/$DEBIAN_SNAPSHOT/"
    
    debootstrap \
        --variant=minbase \
        --include=ca-certificates,apt-transport-https \
        "$DEBIAN_RELEASE" \
        "$ROOTFS_DIR" \
        "$mirror"
    
    log_info "✓ Base rootfs created"
}

# Install system packages
install_system_packages() {
    log_info "Installing system packages..."
    
    # Configure apt to use snapshot for reproducibility
    cat > "$ROOTFS_DIR/etc/apt/sources.list" <<EOF
deb [check-valid-until=no] http://snapshot.debian.org/archive/debian/$DEBIAN_SNAPSHOT/ $DEBIAN_RELEASE main
deb [check-valid-until=no] http://snapshot.debian.org/archive/debian-security/$DEBIAN_SNAPSHOT/ $DEBIAN_RELEASE-security main
EOF
    
    # Prevent interactive prompts
    export DEBIAN_FRONTEND=noninteractive
    
    # Install packages
    chroot "$ROOTFS_DIR" bash -c "
        apt-get update -o Acquire::Check-Valid-Until=false
        apt-get install -y --no-install-recommends \
            coreutils \
            bash \
            grep \
            sed \
            gawk \
            findutils \
            diffutils \
            tar \
            gzip \
            bzip2 \
            xz-utils \
            zip \
            unzip \
            curl \
            wget \
            ca-certificates \
            jq \
            csvkit \
            sqlite3 \
            bc \
            vim \
            nano \
            git \
            make \
            python${PYTHON_VERSION} \
            python${PYTHON_VERSION}-venv \
            python3-pip
        
        # Clean up apt cache
        apt-get clean
        rm -rf /var/lib/apt/lists/*
    "
    
    log_info "✓ System packages installed"
}

# Create Python virtual environment with data stack
setup_python_env() {
    log_info "Setting up Python environment..."
    
    chroot "$ROOTFS_DIR" bash -c "
        # Create venv
        python${PYTHON_VERSION} -m venv /opt/venv
        
        # Upgrade pip
        /opt/venv/bin/pip install --no-cache-dir --upgrade pip
        
        # Install data science packages with pinned versions
        /opt/venv/bin/pip install --no-cache-dir \
            numpy==1.26.4 \
            pandas==2.2.2 \
            scipy==1.13.0 \
            scikit-learn==1.4.2 \
            pyarrow==16.0.0 \
            matplotlib==3.8.4 \
            polars==0.20.31 \
            requests==2.32.0 \
            openpyxl==3.1.2
    "
    
    log_info "✓ Python environment created"
}

# Generate manifest file
generate_manifest() {
    log_info "Generating manifest..."
    
    # Get package versions
    local python_ver
    python_ver=$(chroot "$ROOTFS_DIR" python${PYTHON_VERSION} --version | awk '{print $2}')
    
    # Create manifest
    cat > "$ROOTFS_DIR/etc/sandbox_manifest.json" <<'EOF'
{
  "manifest_version": "1.0",
  "image": {
    "name": "py-data-3.11",
    "version": "1.0.0",
    "build_date": "BUILD_DATE_PLACEHOLDER",
    "architecture": "amd64"
  },
  "os": {
    "distribution": "debian",
    "release": "bookworm",
    "snapshot_date": "2024-10-01"
  },
  "python": {
    "version": "PYTHON_VERSION_PLACEHOLDER",
    "path": "/opt/venv/bin/python3"
  },
  "python_packages": {
    "numpy": "1.26.4",
    "pandas": "2.2.2",
    "scipy": "1.13.0",
    "scikit-learn": "1.4.2",
    "pyarrow": "16.0.0",
    "matplotlib": "3.8.4",
    "polars": "0.20.31",
    "requests": "2.32.0",
    "openpyxl": "3.1.2"
  },
  "shell_commands": {
    "text_processing": [
      "grep", "sed", "awk", "cut", "paste", "join", 
      "tr", "sort", "uniq", "head", "tail", "wc", 
      "diff", "comm", "column"
    ],
    "file_operations": [
      "cp", "mv", "rm", "mkdir", "rmdir", "touch",
      "cat", "less", "more", "find", "xargs", "ln", "ls"
    ],
    "data_tools": [
      "jq", "csvcut", "csvgrep", "csvjoin", "csvstat", 
      "csvlook", "sqlite3", "bc", "date", "seq"
    ],
    "compression": [
      "gzip", "gunzip", "zcat", "bzip2", "bunzip2", 
      "bzcat", "xz", "unxz", "xzcat", "zip", "unzip", "tar"
    ],
    "network": ["curl", "wget"],
    "editors": ["vim", "nano"],
    "development": ["git", "make"]
  },
  "command_examples": {
    "jq": {
      "description": "Parse and transform JSON",
      "examples": [
        "jq '.' file.json - Pretty-print",
        "jq '.field' file.json - Extract field",
        "jq -r '.[] | .name' file.json - Array iteration"
      ]
    },
    "csvcut": {
      "description": "Extract columns from CSV",
      "examples": [
        "csvcut -c 1,3 file.csv - Columns 1 and 3",
        "csvcut -c name,age file.csv - Named columns"
      ]
    },
    "awk": {
      "description": "Pattern scanning and text processing",
      "examples": [
        "awk '{print $1}' file.txt - First column",
        "awk -F, '{print $2}' file.csv - CSV second column"
      ]
    },
    "bc": {
      "description": "Arbitrary precision calculator",
      "examples": [
        "echo '2+2' | bc - Simple math",
        "echo 'scale=2; 10/3' | bc - Decimals"
      ]
    },
    "sqlite3": {
      "description": "SQL database queries",
      "examples": [
        "sqlite3 db.sqlite 'SELECT * FROM users;'"
      ]
    }
  },
  "environment": {
    "PATH": "/opt/venv/bin:/usr/bin:/bin",
    "LANG": "C.UTF-8",
    "OMP_NUM_THREADS": "1",
    "OPENBLAS_NUM_THREADS": "1"
  },
  "capabilities": {
    "networking": false,
    "writable_paths": ["/workspace", "/tmp"]
  }
}
EOF
    
    # Replace placeholders
    sed -i "s/BUILD_DATE_PLACEHOLDER/$(date -u +%Y-%m-%d)/" "$ROOTFS_DIR/etc/sandbox_manifest.json"
    sed -i "s/PYTHON_VERSION_PLACEHOLDER/$python_ver/" "$ROOTFS_DIR/etc/sandbox_manifest.json"
    
    log_info "✓ Manifest generated"
}

# Verify all tools are present
verify_tools() {
    log_info "Verifying tools..."
    
    local missing=0
    local tools=(
        grep sed awk jq csvcut csvgrep bc sqlite3
        curl wget git vim nano python${PYTHON_VERSION}
        tar gzip bzip2 xz zip
    )
    
    for tool in "${tools[@]}"; do
        if ! chroot "$ROOTFS_DIR" which "$tool" &>/dev/null; then
            log_warn "Missing tool: $tool"
            ((missing++))
        fi
    done
    
    # Verify Python packages
    local py_pkgs=(numpy pandas scipy sklearn pyarrow matplotlib)
    for pkg in "${py_pkgs[@]}"; do
        if ! chroot "$ROOTFS_DIR" /opt/venv/bin/python -c "import $pkg" &>/dev/null; then
            log_warn "Missing Python package: $pkg"
            ((missing++))
        fi
    done
    
    if [[ $missing -gt 0 ]]; then
        log_error "$missing tools/packages are missing!"
    fi
    
    log_info "✓ All tools verified"
}

# Create tarball and cache
package_rootfs() {
    log_info "Packaging rootfs..."
    
    # Create tarball
    local tarball="$BUILD_DIR/${IMAGE_NAME}.tar.gz"
    tar czf "$tarball" -C "$ROOTFS_DIR" .
    
    # Calculate sha256
    local sha256
    sha256=$(sha256sum "$tarball" | awk '{print $1}')
    
    log_info "Image SHA256: $sha256"
    
    # Cache the image
    mkdir -p "$CACHE_DIR"
    local cached_path="$CACHE_DIR/${sha256}.tar.gz"
    cp "$tarball" "$cached_path"
    
    # Create symlink with image name
    ln -sf "${sha256}.tar.gz" "$CACHE_DIR/${IMAGE_NAME}-latest.tar.gz"
    
    # Create metadata file
    cat > "$CACHE_DIR/${sha256}.json" <<EOF
{
  "image_name": "$IMAGE_NAME",
  "sha256": "$sha256",
  "build_date": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "size_bytes": $(stat -c%s "$cached_path"),
  "path": "$cached_path"
}
EOF
    
    log_info "✓ Image cached at: $cached_path"
    log_info "✓ Metadata: $CACHE_DIR/${sha256}.json"
    
    echo ""
    echo "=========================================="
    echo "Image: $IMAGE_NAME"
    echo "SHA256: $sha256"
    echo "Path: $cached_path"
    echo "Size: $(du -h "$cached_path" | awk '{print $1}')"
    echo "=========================================="
}

# Cleanup
cleanup() {
    log_info "Cleaning up build directory..."
    rm -rf "$BUILD_DIR"
    log_info "✓ Cleanup complete"
}

# Main execution
main() {
    log_info "Building rootfs image: $IMAGE_NAME"
    echo ""
    
    check_prereqs
    create_base_rootfs
    install_system_packages
    setup_python_env
    generate_manifest
    verify_tools
    package_rootfs
    cleanup
    
    echo ""
    log_info "🎉 Rootfs build complete!"
    log_info "To use: SANDBOX_ROOTFS_SHA256=$sha256 python main.py"
}

main "$@"
