import io
import re

import qrcode
import qrcode.image.svg


def qr_svg(text):
    """Render text as an inline SVG QR code (made on the server)."""
    img = qrcode.make(text, image_factory=qrcode.image.svg.SvgPathImage, box_size=10, border=2,
                      error_correction=qrcode.constants.ERROR_CORRECT_M)
    buf = io.BytesIO()
    img.save(buf)
    svg = buf.getvalue().decode("utf-8")
    svg = re.sub(r"<\?xml[^>]*\?>\s*", "", svg)          # drop the XML header so it can be inlined in HTML
    return svg
