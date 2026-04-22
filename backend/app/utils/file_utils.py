"""File utility functions for deduplication and file operations."""

import hashlib
from pathlib import Path


def compute_file_hash(file_path: str, algorithm: str = 'sha256', chunk_size: int = 1024 * 1024) -> str:
    """
    Compute the hash of a file for deduplication purposes.

    Args:
        file_path: Path to the file to hash
        algorithm: Hash algorithm to use (default: 'sha256')
        chunk_size: Size of chunks to read in bytes (default: 1MB)

    Returns:
        Hex digest of the file hash

    Raises:
        FileNotFoundError: If the file does not exist
        PermissionError: If the file cannot be read
        ValueError: If the algorithm is not supported
        IOError: If an error occurs during file reading
    """
    path = Path(file_path)

    # Validate file exists
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    if not path.is_file():
        raise FileNotFoundError(f"Path is not a file: {file_path}")

    # Validate algorithm is supported
    try:
        hasher = hashlib.new(algorithm)
    except ValueError as e:
        raise ValueError(f"Unsupported hash algorithm: {algorithm}") from e

    # Read file in chunks and compute hash
    try:
        with open(path, 'rb') as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                hasher.update(chunk)
    except PermissionError as e:
        raise PermissionError(f"Permission denied reading file: {file_path}") from e
    except IOError as e:
        raise IOError(f"Error reading file {file_path}: {e}") from e

    return hasher.hexdigest()
