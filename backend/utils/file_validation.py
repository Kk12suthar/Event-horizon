"""File upload validation utilities"""

from fastapi import UploadFile, HTTPException, status
from typing import List, Set
import re

# Allowed file extensions
ALLOWED_EXTENSIONS: Set[str] = {
    'csv', 'xlsx', 'xls', 'json', 'xml', 'txt', 'pdf', 'png', 'jpg', 'jpeg'
}

# Maximum file size in bytes (100MB - reduced from 500MB for security)
MAX_FILE_SIZE = 100 * 1024 * 1024

# Maximum filename length
MAX_FILENAME_LENGTH = 255

# Dangerous content patterns (basic malware detection)
DANGEROUS_PATTERNS = [
    b'<script',
    b'<?php',
    b'#!/bin/bash',
    b'#!/bin/sh',
    b'cmd.exe',
    b'powershell.exe',
]


async def validate_file_upload(file: UploadFile, max_size: int = MAX_FILE_SIZE) -> bytes:
    """
    Validate uploaded file for security
    
    Args:
        file: FastAPI UploadFile object
        max_size: Maximum allowed file size in bytes
        
    Returns:
        File content as bytes
        
    Raises:
        HTTPException: If validation fails
    """
    
    # Read file content
    content = await file.read()
    await file.seek(0)  # Reset file pointer for potential re-reading
    
    # Check file size
    size = len(content)
    
    if size == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty file not allowed"
        )
    
    if size > max_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Maximum size: {max_size / 1024 / 1024:.1f}MB, your file: {size / 1024 / 1024:.1f}MB"
        )
    
    # Check extension
    filename = file.filename or ""
    
    if not filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename is required"
        )
    
    # Extract extension
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ""
    
    if not ext or ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type '.{ext}' not allowed. Allowed types: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )
    
    # Check for malicious content (basic scan)
    content_lower = content.lower()
    for pattern in DANGEROUS_PATTERNS:
        if pattern in content_lower:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File contains potentially malicious content and cannot be uploaded"
            )
    
    # Sanitize filename (remove path traversal attempts)
    sanitized_filename = sanitize_filename(filename)
    if sanitized_filename != filename:
        # Update the file object's filename
        file.filename = sanitized_filename
    
    return content


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename to prevent path traversal and other attacks
    
    SECURITY ENHANCEMENTS:
    - Removes path components (/ and \)
    - Filters null bytes and control characters
    - Prevents path traversal (..)
    - Blocks reserved names (Windows)
    - Enforces maximum length
    
    Args:
        filename: Original filename
        
    Returns:
        Sanitized filename
        
    Raises:
        HTTPException: If filename is invalid or dangerous
    """
    if not filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename cannot be empty"
        )
    
    # Check for null bytes (path traversal attempt)
    if '\x00' in filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid filename: contains null bytes"
        )
    
    # Remove any path components (both Unix and Windows)
    filename = filename.split('/')[-1].split('\\')[-1]
    
    # Check for path traversal patterns BEFORE sanitization
    if '..' in filename or filename.startswith('.'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid filename: path traversal attempt detected"
        )
    
    # Remove control characters (0x00-0x1F, 0x7F)
    filename = ''.join(char for char in filename if ord(char) >= 32 and ord(char) != 127)
    
    # Remove dangerous characters, keep only alphanumeric, spaces, hyphens, underscores, and dots
    filename = re.sub(r'[^\w\s\-\.]', '', filename)
    
    # Check for Windows reserved names
    reserved_names = {
        'CON', 'PRN', 'AUX', 'NUL',
        'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
        'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9'
    }
    name_without_ext = filename.rsplit('.', 1)[0].upper()
    if name_without_ext in reserved_names:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid filename: '{name_without_ext}' is a reserved system name"
        )
    
    # Ensure filename is not empty after sanitization
    if not filename or filename == '.' or filename.strip() == '':
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid filename after sanitization"
        )
    
    # Enforce maximum length
    if len(filename) > MAX_FILENAME_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Filename too long (max {MAX_FILENAME_LENGTH} characters)"
        )
    
    return filename


def validate_file_extension(filename: str, allowed_extensions: List[str] = None) -> bool:
    """
    Validate file extension
    
    Args:
        filename: Filename to check
        allowed_extensions: List of allowed extensions (without dots). If None, uses ALLOWED_EXTENSIONS
        
    Returns:
        True if extension is allowed, False otherwise
    """
    if allowed_extensions is None:
        allowed_extensions = list(ALLOWED_EXTENSIONS)
    
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ""
    return ext in allowed_extensions


async def validate_image_upload(file: UploadFile, max_size: int = 5 * 1024 * 1024) -> bytes:
    """
    Validate uploaded image file (stricter validation for images)
    
    Args:
        file: FastAPI UploadFile object
        max_size: Maximum allowed file size (default 5MB for images)
        
    Returns:
        File content as bytes
        
    Raises:
        HTTPException: If validation fails
    """
    # Check extension first
    filename = file.filename or ""
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ""
    
    allowed_image_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    
    if ext not in allowed_image_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid image format. Allowed: {', '.join(allowed_image_extensions)}"
        )
    
    # Validate with standard checks
    content = await validate_file_upload(file, max_size)
    
    # Additional image-specific validation
    # Check for common image magic bytes
    image_signatures = {
        b'\x89PNG': 'png',
        b'\xFF\xD8\xFF': 'jpeg',
        b'GIF87a': 'gif',
        b'GIF89a': 'gif',
        b'RIFF': 'webp',  # RIFF is for WebP (also checks for 'WEBP' later)
    }
    
    is_valid_image = False
    for signature, format_name in image_signatures.items():
        if content.startswith(signature):
            is_valid_image = True
            break
    
    if not is_valid_image:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File does not appear to be a valid image (invalid file signature)"
        )
    
    return content


def get_file_size_mb(size_bytes: int) -> float:
    """Convert bytes to megabytes"""
    return size_bytes / (1024 * 1024)


def format_file_size(size_bytes: int) -> str:
    """Format file size in human-readable format"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f}{unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f}TB"


def validate_file_path(file_path: str, allowed_base_dir: str) -> str:
    """
    Validate that a file path is within an allowed directory
    
    SECURITY: Prevents directory traversal attacks by ensuring
    the resolved absolute path is within the allowed base directory
    
    Args:
        file_path: Path to validate
        allowed_base_dir: Base directory that file must be within
        
    Returns:
        Absolute path if valid
        
    Raises:
        HTTPException: If path is outside allowed directory
    """
    import os
    from pathlib import Path
    
    try:
        # Resolve to absolute paths
        base_path = Path(allowed_base_dir).resolve()
        target_path = Path(file_path).resolve()
        
        # Check if target is within base directory
        if not str(target_path).startswith(str(base_path)):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Path traversal attempt detected: file path outside allowed directory"
            )
        
        return str(target_path)
    except Exception as e:
        if isinstance(e, HTTPException):
            raise
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file path: {str(e)}"
        )


def is_safe_path(base_dir: str, path: str) -> bool:
    """
    Check if a path is safe (within base directory)
    
    Args:
        base_dir: Base directory
        path: Path to check
        
    Returns:
        True if safe, False otherwise
    """
    from pathlib import Path
    
    try:
        base_path = Path(base_dir).resolve()
        target_path = Path(path).resolve()
        return str(target_path).startswith(str(base_path))
    except:
        return False

