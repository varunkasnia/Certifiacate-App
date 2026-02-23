import random
import string
import qrcode
from io import BytesIO
import base64


def generate_game_pin(length: int = 6) -> str:
    """Generate a random numeric game PIN"""
    return ''.join(random.choices(string.digits, k=length))


def generate_qr_code(data: str) -> str:
    """Generate QR code and return as base64 encoded string"""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    
    buffer = BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)
    
    img_base64 = base64.b64encode(buffer.getvalue()).decode()
    return f"data:image/png;base64,{img_base64}"


def validate_file_size(file_size: int, max_size: int) -> bool:
    """Check if file size is within allowed limit"""
    return file_size <= max_size


def format_time(seconds: float) -> str:
    """Format seconds into human-readable time"""
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes = int(seconds // 60)
    secs = seconds % 60
    return f"{minutes}m {secs:.1f}s"
