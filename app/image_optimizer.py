"""Image optimization utilities for web and WebSocket delivery"""
import io
from PIL import Image
from typing import Tuple, Optional

# Configuration
MAX_WIDTH = 1200  # Max width for images
MAX_HEIGHT = 900  # Max height for images
JPEG_QUALITY = 85  # JPEG quality (1-100)
WEBP_QUALITY = 85  # WebP quality (1-100)
MAX_FILE_SIZE_KB = 500  # Target max file size in KB


def optimize_image(
    image_bytes: bytes,
    max_width: int = MAX_WIDTH,
    max_height: int = MAX_HEIGHT,
    quality: int = JPEG_QUALITY,
    format: str = 'JPEG'
) -> Tuple[bytes, str]:
    """
    Optimize an image for web delivery.
    
    Args:
        image_bytes: Original image bytes
        max_width: Maximum width in pixels
        max_height: Maximum height in pixels
        quality: Compression quality (1-100)
        format: Output format ('JPEG' or 'WEBP')
    
    Returns:
        Tuple of (optimized_bytes, extension)
    """
    # Open image
    img = Image.open(io.BytesIO(image_bytes))
    
    # Convert RGBA to RGB if saving as JPEG
    if format == 'JPEG' and img.mode in ('RGBA', 'LA', 'P'):
        # Create white background
        background = Image.new('RGB', img.size, (255, 255, 255))
        if img.mode == 'P':
            img = img.convert('RGBA')
        background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
        img = background
    
    # Get original dimensions
    orig_width, orig_height = img.size
    
    # Calculate new dimensions maintaining aspect ratio
    ratio = min(max_width / orig_width, max_height / orig_height, 1.0)
    
    if ratio < 1.0:
        new_width = int(orig_width * ratio)
        new_height = int(orig_height * ratio)
        
        # Use high-quality resampling
        img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
    
    # Save to bytes
    output = io.BytesIO()
    
    if format == 'WEBP':
        img.save(output, format='WEBP', quality=quality, method=6)
        ext = '.webp'
    else:  # JPEG
        # Optimize for progressive loading
        img.save(output, format='JPEG', quality=quality, optimize=True, progressive=True)
        ext = '.jpg'
    
    optimized_bytes = output.getvalue()
    
    # If still too large, reduce quality iteratively
    current_quality = quality
    while len(optimized_bytes) > MAX_FILE_SIZE_KB * 1024 and current_quality > 60:
        current_quality -= 5
        output = io.BytesIO()
        
        if format == 'WEBP':
            img.save(output, format='WEBP', quality=current_quality, method=6)
        else:
            img.save(output, format='JPEG', quality=current_quality, optimize=True, progressive=True)
        
        optimized_bytes = output.getvalue()
    
    return optimized_bytes, ext


def get_image_info(image_bytes: bytes) -> dict:
    """
    Get information about an image.
    
    Args:
        image_bytes: Image bytes
    
    Returns:
        Dict with width, height, format, mode, size
    """
    img = Image.open(io.BytesIO(image_bytes))
    
    return {
        'width': img.size[0],
        'height': img.size[1],
        'format': img.format,
        'mode': img.mode,
        'size_kb': len(image_bytes) / 1024
    }


def create_thumbnail(
    image_bytes: bytes,
    size: Tuple[int, int] = (300, 300),
    quality: int = 80
) -> bytes:
    """
    Create a thumbnail from an image.
    
    Args:
        image_bytes: Original image bytes
        size: Thumbnail size (width, height)
        quality: JPEG quality
    
    Returns:
        Thumbnail bytes
    """
    img = Image.open(io.BytesIO(image_bytes))
    
    # Convert RGBA to RGB
    if img.mode in ('RGBA', 'LA', 'P'):
        background = Image.new('RGB', img.size, (255, 255, 255))
        if img.mode == 'P':
            img = img.convert('RGBA')
        background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
        img = background
    
    # Create thumbnail maintaining aspect ratio
    img.thumbnail(size, Image.Resampling.LANCZOS)
    
    # Save to bytes
    output = io.BytesIO()
    img.save(output, format='JPEG', quality=quality, optimize=True)
    
    return output.getvalue()