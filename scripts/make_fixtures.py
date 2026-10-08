"""Generate reproducible, synthetic PDF fixtures; no employer or customer data."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas

ROOT = Path(__file__).resolve().parents[1]
text = (ROOT / "examples/clean.txt").read_text()
canvas = Canvas(str(ROOT / "examples/digital.pdf"), invariant=1)
canvas.setFont("Helvetica", 11)
for index, line in enumerate(text.splitlines()):
    canvas.drawString(45, 790 - 22 * index, line)
canvas.save()

image = Image.new("RGB", (1654, 2339), "white")
draw = ImageDraw.Draw(image)
try:
    font = ImageFont.truetype("DejaVuSans.ttf", 24)
except OSError:
    font = ImageFont.load_default(size=24)
for index, line in enumerate(text.splitlines()):
    draw.text((90, 150 + 65 * index), line, font=font, fill="black")
canvas = Canvas(str(ROOT / "examples/scanned.pdf"), invariant=1)
canvas.drawImage(ImageReader(image), 0, 0, width=595, height=842)
canvas.save()

canvas = Canvas(str(ROOT / "examples/mixed.pdf"), invariant=1)
canvas.setFont("Helvetica", 11)
canvas.drawString(45, 790, "Change Order #: MIX-01")
canvas.drawString(45, 765, "Project: Synthetic mixed document")
canvas.showPage()
canvas.drawImage(ImageReader(image), 0, 0, width=595, height=842)
canvas.save()

# A separate form-like PDF with label/value columns and more than one page.
canvas = Canvas(str(ROOT / "examples/audit/two-column.pdf"), invariant=1)
canvas.setFont("Helvetica", 11)
rows = [
    ("Change Order #: 028", "Issue Date: 2026-09-29"),
    ("Project: Harbor Clinic", "Contract Number: HC-21"),
    ("Owner: Harbor Facilities", "Contractor: Beacon Builders"),
]
for index, (left, right) in enumerate(rows):
    canvas.drawString(40, 790 - index * 25, left)
    canvas.drawString(320, 790 - index * 25, right)
canvas.drawString(40, 680, "Description: Add the second floor access reader.")
canvas.drawString(40, 650, "Status: proposed")
canvas.showPage()
canvas.setFont("Helvetica", 11)
for index, line in enumerate(
    [
        "Change Order #: 028",
        "Currency: USD",
        "Original Contract Amount: USD 100,000.00",
        "Prior Changes: USD 5,000.00",
        "Change Amount: USD 800.00",
        "Revised Contract Amount: USD 105,800.00",
        "Schedule Impact: 0 days",
    ]
):
    canvas.drawString(40, 790 - index * 25, line)
canvas.save()
