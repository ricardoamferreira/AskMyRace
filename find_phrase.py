from backend.app.services.pdf_loader import load_pdf_chunks
from pathlib import Path

pdf_path = Path("race_examples") / "Swansea 70.3 2025 Athlete Guide (5).pdf"
with pdf_path.open("rb") as f:
    data = f.read()
chunks, _ = load_pdf_chunks(data)
for chunk in chunks:
    if "race morning" in chunk.text.lower():
        text = chunk.text.replace("\n", " ")
        print(f"page {chunk.page}: {text}")
