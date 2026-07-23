"""Screenshot capture utilities for Kali-AI Agent.

Supports multiple capture methods:
1. mss (cross-platform, Wayland compatible)
2. PIL ImageGrab (X11 only)
3. PyQt6 QScreen (fallback)
"""

import base64
import io


def capture_screenshot_b64() -> str:
    """Capture the full screen and return a base64-encoded JPEG string.

    Tries multiple methods in order of reliability:
    1. mss (works on Wayland + X11 + Windows)
    2. PIL ImageGrab (X11 + Windows only)
    3. PyQt6 native screenshot (universal fallback)
    """
    errors = []

    # Method 1: mss — best cross-platform support
    try:
        import mss
        with mss.mss() as sct:
            # Capture primary monitor
            monitor = sct.monitors[1]  # Primary monitor (0 = all combined)
            img = sct.grab(monitor)
            # Convert to JPEG via PIL
            from PIL import Image
            pil_img = Image.frombytes("RGB", img.size, img.bgra, "raw", "BGRX")
            buf = io.BytesIO()
            pil_img.save(buf, format="JPEG", quality=70)
            return base64.b64encode(buf.getvalue()).decode("utf-8")
    except Exception as e:
        errors.append(f"mss: {e}")

    # Method 2: PIL ImageGrab — works on X11 and Windows
    try:
        from PIL import ImageGrab
        img = ImageGrab.grab()
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=70)
        return base64.b64encode(buf.getvalue()).decode("utf-8")
    except Exception as e:
        errors.append(f"PIL: {e}")

    # Method 3: PyQt6 native — works everywhere Qt works
    try:
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtCore import QBuffer, QIODevice
        app = QApplication.instance()
        if app:
            screen = app.primaryScreen()
            if screen:
                pixmap = screen.grabWindow(0)
                buffer = QBuffer()
                buffer.open(QIODevice.OpenModeFlag.WriteOnly)
                pixmap.save(buffer, "JPEG", 70)
                return base64.b64encode(buffer.data().data()).decode("utf-8")
    except Exception as e:
        errors.append(f"PyQt6: {e}")

    raise RuntimeError(f"All screenshot methods failed: {'; '.join(errors)}")
