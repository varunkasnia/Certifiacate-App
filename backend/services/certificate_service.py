import io
from datetime import datetime
from typing import Dict

from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.colors import HexColor


def build_certificate_overlay_bytes(player_name: str) -> io.BytesIO:
    packet = io.BytesIO()
    cert_canvas = canvas.Canvas(packet, pagesize=letter)

    # Main recipient name in center area.
    cert_canvas.setFillColor(HexColor("#1f2937"))
    cert_canvas.setFont("Helvetica-Bold", 36)
    cert_canvas.drawCentredString(306, 396, player_name)

    # Small completion caption below recipient name.
    cert_canvas.setFillColor(HexColor("#4b5563"))
    cert_canvas.setFont("Helvetica", 14)
    cert_canvas.drawCentredString(306, 366, f"Certificate generated on {datetime.utcnow().strftime('%Y-%m-%d')}")

    cert_canvas.save()
    packet.seek(0)
    return packet


def generate_certificate_pdf(template_path: str, player_name: str) -> io.BytesIO:
    template_reader = PdfReader(template_path)
    overlay_reader = PdfReader(build_certificate_overlay_bytes(player_name))
    writer = PdfWriter()

    if not template_reader.pages:
        raise ValueError("Certificate template has no pages")

    first_page = template_reader.pages[0]
    first_page.merge_page(overlay_reader.pages[0])
    writer.add_page(first_page)

    for page in template_reader.pages[1:]:
        writer.add_page(page)

    output = io.BytesIO()
    writer.write(output)
    output.seek(0)
    return output


def calculate_certificate_eligibility(correct_answers: int, total_questions: int, threshold: int) -> Dict[str, float]:
    accuracy = 0.0 if total_questions == 0 else (correct_answers / total_questions) * 100
    return {
        "accuracy": round(accuracy, 2),
        "threshold": threshold,
        "eligible": accuracy >= threshold,
    }
