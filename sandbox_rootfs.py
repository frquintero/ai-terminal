"""
Rootfs management for namespace isolation.

Handles extraction, caching, and manifest loading for sandbox images.
"""

import os
import json
import tarfile
import hashlib
from pathlib import Path
from typing import Dict, Any, Optional

CACHE_DIR = Path.home() / ".cache" / "agent_sandbox" / "images"
EXTRACT_DIR = Path.home() / ".cache" / "agent_sandbox" / "extracted"


def get_rootfs_sha256() -> Optional[str]:
    """Get rootfs SHA256 from environment or config"""
    # Priority: env var > config file > latest symlink
    sha256 = os.getenv("SANDBOX_ROOTFS_SHA256")
    if sha256:
        return sha256
    
    # Check for latest symlink
    latest = CACHE_DIR / "py-data-3.11-latest.tar.gz"
    if latest.exists() and latest.is_symlink():
        target = latest.resolve().name
        # Extract sha256 from filename: <sha256>.tar.gz
        return target.replace(".tar.gz", "")
    
    return None


def verify_rootfs_exists(sha256: str) -> bool:
    """Check if rootfs tarball exists in cache"""
    tarball = CACHE_DIR / f"{sha256}.tar.gz"
    return tarball.exists()


def _safe_extract(tar: tarfile.TarFile, path: Path):
    """
    Safely extract tarball, preventing path traversal attacks.
    
    Args:
        tar: Open tarfile object
        path: Destination directory
    """
    def is_safe(member: tarfile.TarInfo) -> bool:
        """Check if tar member is safe to extract"""
        name = Path(member.name)
        # Reject absolute paths or parent directory references
        if name.is_absolute() or ".." in name.parts:
            return False
        return True
    
    # Filter to only safe members
    safe_members = [m for m in tar.getmembers() if is_safe(m)]
    tar.extractall(path, members=safe_members)


def extract_rootfs(sha256: str, force: bool = False) -> Path:
    """
    Extract rootfs tarball to cache directory.
    
    Args:
        sha256: Image SHA256 digest
        force: Force re-extraction even if already extracted
    
    Returns:
        Path to extracted rootfs directory
    """
    extract_path = EXTRACT_DIR / sha256
    
    # Return cached extraction if exists
    if extract_path.exists() and not force:
        return extract_path
    
    # Verify tarball exists
    tarball = CACHE_DIR / f"{sha256}.tar.gz"
    if not tarball.exists():
        raise FileNotFoundError(f"Rootfs not found in cache: {sha256}")
    
    # Verify SHA256
    computed_sha256 = _compute_sha256(tarball)
    if computed_sha256 != sha256:
        raise ValueError(f"SHA256 mismatch: expected {sha256}, got {computed_sha256}")
    
    # Extract safely
    extract_path.mkdir(parents=True, exist_ok=True)
    with tarfile.open(tarball, "r:gz") as tar:
        _safe_extract(tar, extract_path)
    
    # Update directory mtime to current time (tar preserves old timestamps)
    # This prevents cleanup from deleting the freshly extracted rootfs
    os.utime(extract_path, None)
    
    # Cleanup old extractions to save disk space
    cleanup_old_extractions(keep_latest=2)
    
    return extract_path


def load_manifest(rootfs_path: Path) -> Dict[str, Any]:
    """
    Load sandbox manifest from rootfs.
    
    Args:
        rootfs_path: Path to extracted rootfs
    
    Returns:
        Manifest dictionary
    """
    manifest_file = rootfs_path / "etc" / "sandbox_manifest.json"
    
    if not manifest_file.exists():
        # Return minimal fallback manifest
        return {
            "manifest_version": "0.0",
            "python": {"version": "unknown"},
            "python_packages": {},
            "shell_commands": {},
            "command_examples": {}
        }
    
    with open(manifest_file) as f:
        return json.load(f)


def list_cached_images() -> list:
    """List all cached rootfs images"""
    if not CACHE_DIR.exists():
        return []
    
    images = []
    for metadata_file in CACHE_DIR.glob("*.json"):
        try:
            with open(metadata_file) as f:
                meta = json.load(f)
                images.append(meta)
        except Exception:
            continue
    
    return sorted(images, key=lambda x: x.get("build_date", ""), reverse=True)


def cleanup_old_extractions(keep_latest: int = 2):
    """Remove old extracted rootfs directories, keeping latest N"""
    if not EXTRACT_DIR.exists():
        return
    
    extractions = sorted(
        EXTRACT_DIR.iterdir(),
        key=lambda p: p.stat().st_mtime,
        reverse=True
    )
    
    for old_dir in extractions[keep_latest:]:
        if old_dir.is_dir():
            import shutil
            shutil.rmtree(old_dir)


def _compute_sha256(file_path: Path) -> str:
    """Compute SHA256 hash of file"""
    sha256 = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            sha256.update(chunk)
    return sha256.hexdigest()


def get_rootfs_info(sha256: Optional[str] = None) -> Dict[str, Any]:
    """
    Get information about a rootfs image.
    
    Args:
        sha256: Image SHA256, or None to use default
    
    Returns:
        Dict with image information
    """
    if sha256 is None:
        sha256 = get_rootfs_sha256()
    
    if sha256 is None:
        return {"error": "No rootfs configured"}
    
    metadata_file = CACHE_DIR / f"{sha256}.json"
    
    if metadata_file.exists():
        with open(metadata_file) as f:
            return json.load(f)
    
    # Minimal info if no metadata
    tarball = CACHE_DIR / f"{sha256}.tar.gz"
    if tarball.exists():
        return {
            "sha256": sha256,
            "size_bytes": tarball.stat().st_size,
            "path": str(tarball),
            "extracted": (EXTRACT_DIR / sha256).exists()
        }
    
    return {"error": f"Rootfs not found: {sha256}"}


# Example usage
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "list":
        images = list_cached_images()
        print(json.dumps(images, indent=2))
    elif len(sys.argv) > 1 and sys.argv[1] == "info":
        info = get_rootfs_info()
        print(json.dumps(info, indent=2))
    else:
        print("Usage:")
        print("  python sandbox_rootfs.py list   - List cached images")
        print("  python sandbox_rootfs.py info   - Show current image info")
