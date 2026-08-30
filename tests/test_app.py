import io
from typing import Literal

from fastapi.testclient import TestClient
import pytest
from PIL import Image

from app import JOBS


def make_jpeg_bytes(size=(200, 200), color="red", quality=95):
    img: Image.Image = Image.new("RGB", size, color=color)
    buf = io.BytesIO()
    img.save(fp=buf, format="JPEG", quality=quality)
    buf.seek(0)
    return buf


def make_noisy_jpeg_bytes(size=(800, 800), quality=95):
    import random

    w, h = size
    img: Image.Image = Image.new(mode="RGB", size=(w, h))
    rng = random.Random(123)
    img.putdata(data=[(rng.randint(0, 255), rng.randint(0, 255), rng.randint(0, 255)) for _ in range(w * h)])
    buf = io.BytesIO()
    img.save(fp=buf, format="JPEG", quality=quality)
    buf.seek(0)
    return buf


def make_png_bytes(size=(100, 100)):
    img: Image.Image = Image.new("RGBA", size, color=(255, 0, 0, 128))
    buf = io.BytesIO()
    img.save(fp=buf, format="PNG")
    buf.seek(0)
    return buf


# Basic


def test_health(client: TestClient) -> None:
    r = client.get(url="/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_docs_available(client: TestClient) -> None:
    assert client.get(url="/docs").status_code == 200
    assert client.get(url="/openapi.json").status_code == 200


# Compress success


def test_compress_single_jpeg(client: TestClient) -> None:
    buf = make_jpeg_bytes()
    r = client.post(
        url="/api/compress",
        files=[("images", ("test.jpg", buf, "image/jpeg"))],
        data={"ratio": "0.5"},
    )
    assert r.status_code == 200
    data = r.json()
    assert "job_id" in data
    assert data["ratio"] == 0.5
    assert len(data["results"]) == 1
    res = data["results"][0]
    assert res["filename"] == "test.jpg"
    assert res["original_size"] > 0
    assert res["new_size"] > 0
    assert 0 < res["percent_of_original"] <= 100
    assert 10 <= res["quality"] <= 95
    assert res["width"] == 200 and res["height"] == 200
    assert res["note"] is None
    assert res["download_url"].startswith(f"/api/download/{data['job_id']}/")
    assert data["zip_url"] == f"/api/download-zip/{data['job_id']}"
    assert data["job_id"] in JOBS


def test_compress_png_lossless(client: TestClient) -> None:
    buf = make_png_bytes()
    r = client.post(
        url="/api/compress",
        files=[("images", ("img.png", buf, "image/png"))],
        data={"ratio": "0.5"},
    )
    assert r.status_code == 200
    res = r.json()["results"][0]
    assert res["quality"] is None
    assert "PNG comprimido sin pérdida" in res["note"]
    assert res["width"] == 100


def test_compress_multiple_files(client: TestClient) -> None:
    buf1 = make_jpeg_bytes(color="red")
    buf2 = make_jpeg_bytes(color="blue")
    r = client.post(
        url="/api/compress",
        files=[
            ("images", ("a.jpg", buf1, "image/jpeg")),
            ("images", ("b.jpg", buf2, "image/jpeg")),
        ],
        data={"ratio": "0.6"},
    )
    assert r.status_code == 200
    assert len(r.json()["results"]) == 2
    assert r.json()["zip_url"] is not None


def test_compress_noisy_image_respects_ratio(client: TestClient) -> None:
    buf = make_noisy_jpeg_bytes(size=(600, 600))
    r = client.post(
        url="/api/compress",
        files=[("images", ("noisy.jpg", buf, "image/jpeg"))],
        data={"ratio": "0.5"},
    )
    assert r.status_code == 200
    res = r.json()["results"][0]
    # para imagen con ruido, la compresión sí debe reducir bastante
    assert res["new_size"] <= res["original_size"] * 0.6  # tolerancia


# Validaciones


def test_compress_no_images_400(client: TestClient) -> None:
    r = client.post(url="/api/compress", data={"ratio": "0.5"})
    assert r.status_code == 400
    assert r.json()["error"] == "No se recibió ninguna imagen."


def test_compress_empty_filename_400(client: TestClient) -> None:
    # sin files pero con data
    r = client.post(url="/api/compress", files=[], data={"ratio": "0.5"})
    assert r.status_code == 400


def test_compress_invalid_ratio_400(client: TestClient) -> None:
    buf = make_jpeg_bytes()
    r = client.post(
        url="/api/compress",
        files=[("images", ("t.jpg", buf, "image/jpeg"))],
        data={"ratio": "invalid"},
    )
    assert r.status_code == 400
    assert r.json()["error"] == "Ratio inválido."


@pytest.mark.parametrize(argnames="bad_ratio", argvalues=["0.01", "0.99", "0", "1", "5"])
def test_compress_ratio_out_of_bounds_400(client: TestClient, bad_ratio: Literal['0.01'] | Literal['0.99'] | Literal['0'] | Literal['1'] | Literal['5']) -> None:
    buf = make_jpeg_bytes()
    r = client.post(
        url="/api/compress",
        files=[("images", ("t.jpg", buf, "image/jpeg"))],
        data={"ratio": bad_ratio},
    )
    assert r.status_code == 400
    assert "El ratio debe estar entre 5% y 95%" in r.json()["error"]


@pytest.mark.parametrize(argnames="ok_ratio", argvalues=["0.05", "0.5", "0.95"])
def test_compress_ratio_boundaries_ok(client: TestClient, ok_ratio: Literal['0.05'] | Literal['0.5'] | Literal['0.95']) -> None:
    buf = make_jpeg_bytes()
    r = client.post(
        url="/api/compress",
        files=[("images", ("t.jpg", buf, "image/jpeg"))],
        data={"ratio": ok_ratio},
    )
    assert r.status_code == 200


def test_compress_unsupported_format_returns_error_in_results(client: TestClient) -> None:
    buf = io.BytesIO(initial_bytes=b"hello world")
    r = client.post(
        url="/api/compress",
        files=[("images", ("file.txt", buf, "text/plain"))],
        data={"ratio": "0.5"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["results"][0]["error"].startswith("Formato no soportado")
    assert data["zip_url"] is None
    # no debe crear files para descarga
    assert data["job_id"] in JOBS
    assert JOBS[data["job_id"]]["files"] == {}


def test_compress_mixed_supported_and_unsupported(client: TestClient) -> None:
    good = make_jpeg_bytes()
    bad = io.BytesIO(initial_bytes=b"not an image")
    r = client.post(
        url="/api/compress",
        files=[
            ("images", ("good.jpg", good, "image/jpeg")),
            ("images", ("bad.txt", bad, "text/plain")),
        ],
        data={"ratio": "0.5"},
    )
    assert r.status_code == 200
    results = {res["filename"]: res for res in r.json()["results"]}
    assert "good.jpg" in results and "error" not in results["good.jpg"]
    assert "bad.txt" in results and "error" in results["bad.txt"]
    assert r.json()["zip_url"] is not None


def test_compress_content_length_exceeded_413(client: TestClient) -> None:
    buf = make_jpeg_bytes()
    # spoof header >60MB
    r = client.post(
        url="/api/compress",
        files=[("images", ("t.jpg", buf, "image/jpeg"))],
        data={"ratio": "0.5"},
        headers={"content-length": str(object=61 * 1024 * 1024)},
    )
    assert r.status_code == 413
    assert "excede el límite de 60 MB" in r.json()["error"]


def test_filename_collision_renames_second(client: TestClient) -> None:
    buf1 = make_jpeg_bytes(color="red")
    buf2 = make_jpeg_bytes(color="blue")
    r = client.post(
        url="/api/compress",
        files=[
            ("images", ("same.jpg", buf1, "image/jpeg")),
            ("images", ("same.jpg", buf2, "image/jpeg")),
        ],
        data={"ratio": "0.5"},
    )
    assert r.status_code == 200
    filenames = [res["filename"] for res in r.json()["results"] if "error" not in res]
    assert filenames[0] == "same.jpg"
    assert filenames[1] == "same_1.jpg"
    # ambos descargables
    job_id = r.json()["job_id"]
    assert client.get(url=f"/api/download/{job_id}/same.jpg").status_code == 200
    assert client.get(url=f"/api/download/{job_id}/same_1.jpg").status_code == 200


# Download


def test_download_success(client: TestClient) -> None:
    buf = make_jpeg_bytes()
    r = client.post(
        url="/api/compress",
        files=[("images", ("dl.jpg", buf, "image/jpeg"))],
        data={"ratio": "0.5"},
    )
    job_id = r.json()["job_id"]
    dl_url = r.json()["results"][0]["download_url"]
    r2 = client.get(url=dl_url)
    assert r2.status_code == 200
    assert len(r2.content) > 0
    # content-disposition
    assert "dl.jpg" in r2.headers.get("content-disposition", "")


def test_download_job_not_found_404(client: TestClient) -> None:
    r = client.get(url="/api/download/badjob123/file.jpg")
    assert r.status_code == 404
    assert "expiró o no existe" in r.json()["detail"]


def test_download_file_not_found_404(client: TestClient) -> None:
    buf = make_jpeg_bytes()
    r = client.post(
        url="/api/compress",
        files=[("images", ("exists.jpg", buf, "image/jpeg"))],
        data={"ratio": "0.5"},
    )
    job_id = r.json()["job_id"]
    r2 = client.get(f"/api/download/{job_id}/noexiste.jpg")
    assert r2.status_code == 404
    assert "Archivo no encontrado" in r2.json()["detail"]


def test_download_zip_success(client: TestClient) -> None:
    b1 = make_jpeg_bytes(color="red")
    b2 = make_jpeg_bytes(color="green")
    r = client.post(
        "/api/compress",
        files=[
            ("images", ("a.jpg", b1, "image/jpeg")),
            ("images", ("b.jpg", b2, "image/jpeg")),
        ],
        data={"ratio": "0.5"},
    )
    zip_url = r.json()["zip_url"]
    r2 = client.get(zip_url)
    assert r2.status_code == 200
    assert r2.headers["content-type"] == "application/zip"
    assert "imagenes_comprimidas.zip" in r2.headers["content-disposition"]
    # verificar zip contiene ambos
    import zipfile

    zbuf = io.BytesIO(initial_bytes=r2.content)
    with zipfile.ZipFile(file=zbuf) as zf:
        names: set[str] = set(zf.namelist())
        assert "a.jpg" in names
        assert "b.jpg" in names


def test_download_zip_no_files_404(client: TestClient) -> None:
    # job con solo errores no tiene zip
    buf = io.BytesIO(initial_bytes=b"bad")
    r = client.post(
        url="/api/compress",
        files=[("images", ("bad.txt", buf, "text/plain"))],
        data={"ratio": "0.5"},
    )
    job_id = r.json()["job_id"]
    r2 = client.get(url=f"/api/download-zip/{job_id}")
    assert r2.status_code == 404


def test_download_zip_invalid_job_404(client: TestClient) -> None:
    assert client.get(url="/api/download-zip/nope").status_code == 404
