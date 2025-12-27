"""Image optimization utilities for web and WebSocket delivery"""
import io
from PIL import Image, ExifTags
from typing import Tuple, Optional

# Configuration
MAX_WIDTH = 1200  # Max width for images
MAX_HEIGHT = 900  # Max height for images
JPEG_QUALITY = 85  # JPEG quality (1-100)
WEBP_QUALITY = 85  # WebP quality (1-100)
MAX_FILE_SIZE_KB = 500  # Target max file size in KB


def fix_image_orientation(img: Image.Image) -> Image.Image:
    """
    Fix image orientation based on EXIF data.
    
    Many cameras and phones save images with an orientation tag in EXIF data
    instead of physically rotating the image. This function applies the rotation.
    
    Args:
        img: PIL Image object
    
    Returns:
        Image with correct orientation
    """
    try:
        # Get EXIF data
        exif = img._getexif()
        
        if exif is None:
            return img
        
        # Find orientation tag
        orientation_key = None
        for tag, value in ExifTags.TAGS.items():
            if value == 'Orientation':
                orientation_key = tag
                break
        
        if orientation_key is None or orientation_key not in exif:
            return img
        
        orientation = exif[orientation_key]
        
        # Apply rotation based on orientation value
        # 1: Normal (no rotation)
        # 2: Mirrored horizontally
        # 3: Rotated 180°
        # 4: Mirrored vertically
        # 5: Mirrored horizontally then rotated 90° CCW
        # 6: Rotated 90° CW (270° CCW)
        # 7: Mirrored horizontally then rotated 90° CW
        # 8: Rotated 90° CCW (270° CW)
        
        if orientation == 2:
            img = img.transpose(Image.FLIP_LEFT_RIGHT)
        elif orientation == 3:
            img = img.rotate(180, expand=True)
        elif orientation == 4:
            img = img.transpose(Image.FLIP_TOP_BOTTOM)
        elif orientation == 5:
            img = img.transpose(Image.FLIP_LEFT_RIGHT)
            img = img.rotate(90, expand=True)
        elif orientation == 6:
            img = img.rotate(270, expand=True)
        elif orientation == 7:
            img = img.transpose(Image.FLIP_LEFT_RIGHT)
            img = img.rotate(270, expand=True)
        elif orientation == 8:
            img = img.rotate(90, expand=True)
        
        print(f"🔄 EXIF orientation tag: {orientation} - Applied correction")
        
    except (AttributeError, KeyError, IndexError, TypeError) as e:
        # No EXIF data or orientation tag, return image as-is
        print(f"ℹ️ No EXIF orientation data found (this is normal for some images)")
        pass
    
    return img


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
    
    # Fix orientation based on EXIF data (CRITICAL for photos from phones!)
    img = fix_image_orientation(img)
    
    # Convert RGBA to RGB if saving as JPEG
    if format == 'JPEG' and img.mode in ('RGBA', 'LA', 'P'):
        # Create white background
        background = Image.new('RGB', img.size, (255, 255, 255))
        if img.mode == 'P':
            img = img.convert('RGBA')
        background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
        img = background
    elif format == 'JPEG' and img.mode not in ('RGB', 'L'):
        # Convert any other mode to RGB
        img = img.convert('RGB')
    
    # Get original dimensions (after orientation fix)
    orig_width, orig_height = img.size
    
    # Calculate new dimensions maintaining aspect ratio
    ratio = min(max_width / orig_width, max_height / orig_height, 1.0)
    
    if ratio < 1.0:
        new_width = int(orig_width * ratio)
        new_height = int(orig_height * ratio)
        
        print(f"📏 Resizing from {orig_width}x{orig_height} to {new_width}x{new_height}")
        
        # Use high-quality resampling
        img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
    else:
        print(f"📏 No resize needed ({orig_width}x{orig_height} already within limits)")
    
    # Save to bytes
    output = io.BytesIO()
    
    if format == 'WEBP':
        img.save(output, format='WEBP', quality=quality, method=6)
        ext = '.webp'
    else:  # JPEG
        # Optimize for progressive loading
        # Remove EXIF data to reduce file size (orientation already applied)
        img.save(output, format='JPEG', quality=quality, optimize=True, progressive=True, exif=b'')
        ext = '.jpg'
    
    optimized_bytes = output.getvalue()
    
    # If still too large, reduce quality iteratively
    current_quality = quality
    while len(optimized_bytes) > MAX_FILE_SIZE_KB * 1024 and current_quality > 60:
        current_quality -= 5
        output = io.BytesIO()
        
        print(f"🗜️ File too large, reducing quality to {current_quality}")
        
        if format == 'WEBP':
            img.save(output, format='WEBP', quality=current_quality, method=6)
        else:
            img.save(output, format='JPEG', quality=current_quality, optimize=True, progressive=True, exif=b'')
        
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
    
    # Check for EXIF orientation
    has_exif = False
    orientation = None
    try:
        exif = img._getexif()
        if exif:
            has_exif = True
            for tag, value in ExifTags.TAGS.items():
                if value == 'Orientation' and tag in exif:
                    orientation = exif[tag]
                    break
    except:
        pass
    
    return {
        'width': img.size[0],
        'height': img.size[1],
        'format': img.format,
        'mode': img.mode,
        'size_kb': len(image_bytes) / 1024,
        'has_exif': has_exif,
        'orientation': orientation
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
    
    # Fix orientation first
    img = fix_image_orientation(img)
    
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
    img.save(output, format='JPEG', quality=quality, optimize=True, exif=b'')
    
    return output.getvalue()