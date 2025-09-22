import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from fastapi.testclient import TestClient

from backend.app.main import app


def test_upload_rejects_missing_filename() -> None:
    pdf_bytes = b"%PDF-1.4\n%%EOF"
    boundary = "testboundary"
    body = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="file"; filename=""\r\n'
        "Content-Type: application/pdf\r\n"
        "\r\n"
    ).encode() + pdf_bytes + (
        f"\r\n--{boundary}--\r\n"
    ).encode()

    with TestClient(app) as client:
        response = client.post(
            "/upload",
            data=body,
            headers={"content-type": f"multipart/form-data; boundary={boundary}"},
        )

    assert response.status_code == 400
    assert response.json() == {"detail": "Filename is required."}
