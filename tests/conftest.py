import shutil
from collections.abc import Callable, Generator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from PIL.Image import Image

from api import BASE_TMP, JOBS, app


@pytest.fixture
def client() -> Generator[TestClient, Any]:
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def clean_jobs() -> Generator[None, Any]:
    """Limpia JOBS dict y archivos temporales después de cada test."""
    yield
    for job_id, job in list(JOBS.items()):
        shutil.rmtree(job["dir"], ignore_errors=True)
        JOBS.pop(job_id, None)
    # también limpiar cualquier job huérfano en disco
    if BASE_TMP.exists():
        for p in BASE_TMP.iterdir():
            if p.is_dir() and p.name not in JOBS:
                shutil.rmtree(p, ignore_errors=True)


@pytest.fixture
def tmp_image(tmp_path: Path) -> Callable[..., Path]:
    """Factory para crear imágenes temporales."""
    import random

    from PIL import Image

    def _make(filename: str = "test.jpg", size: tuple[int, int] = (100, 100), fmt: str = "JPEG", color: str = "red", noisy: bool = False) -> Path:
        path: Path = tmp_path / filename
        if noisy:
            img: Image = Image.new("RGB", size)
            rng = random.Random(42)
            w, h = size
            img.putdata(
                data=[(rng.randint(0, 255), rng.randint(0, 255), rng.randint(0, 255)) for _ in range(w * h)]
            )
            img.save(fp=path, format=fmt, quality=95)
        else:
            img = Image.new("RGB", size, color=color)
            # para PNG RGBA
            if fmt == "PNG" and color == "rgba":
                img = Image.new("RGBA", size, color=(255, 0, 0, 128))
            img.save(fp=path, format=fmt, quality=95)
        return path

    return _make
