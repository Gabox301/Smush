"""
Compresor de imágenes — API REST (FastAPI).

Exponé endpoints para comprimir imágenes AVIF/WEBP/JPEG/PNG a un % de
tamaño objetivo, y descargar los resultados (individualmente o en ZIP),
manteniendo siempre las dimensiones originales. La interfaz gráfica
oficial es la UI Flet (flet_app.py), que llama directo a compressor_core.
"""

from __future__ import annotations

import io
import shutil
import tempfile
import time
import uuid
import zipfile
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse
from starlette.responses import StreamingResponse

from compressor_core import (
    SUPPORTED_EXTENSIONS,
    UnsupportedFormatError,
    compress_to_target,
)
from compressor_core.metadata import CompressMeta

app = FastAPI(title="Smush — compresor de imágenes (API)")

MAX_CONTENT_LENGTH = 60 * 1024 * 1024  # 60 MB por request

# El core acepta (0, 1]; la API es más estricta a propósito: fuera de este
# rango el resultado no tiene sentido como "compresión".
RATIO_MIN = 0.05
RATIO_MAX = 0.95

BASE_TMP: Path = Path(tempfile.gettempdir()) / "image-compressor-jobs"
BASE_TMP.mkdir(parents=True, exist_ok=True)

# job_id -> {"dir": Path, "created": float, "files": {filename: Path}}
JOBS: dict[str, dict] = {}
JOB_TTL_SECONDS = 60 * 30  # limpiar trabajos de más de 30 minutos


def _cleanup_old_jobs() -> None:
    now: float = time.time()
    expired: list[str] = [jid for jid, job in JOBS.items() if now - job["created"] > JOB_TTL_SECONDS]
    for jid in expired:
        shutil.rmtree(JOBS[jid]["dir"], ignore_errors=True)
        JOBS.pop(jid, None)


@app.post(path="/api/compress")
async def api_compress(
    request: Request,
    images: list[UploadFile] = File(default_factory=list),  # noqa: B008 — patrón documentado de FastAPI
    ratio: str = Form(default="0.5"),
) -> JSONResponse:
    # Límite de tamaño similar a Flask MAX_CONTENT_LENGTH
    clen: str | None = request.headers.get("content-length")
    if clen is not None:
        try:
            if int(clen) > MAX_CONTENT_LENGTH:
                return JSONResponse(
                    content={"error": "El tamaño total excede el límite de 60 MB."},
                    status_code=413,
                )
        except ValueError:
            pass

    _cleanup_old_jobs()

    if not images or all(not f.filename for f in images):
        return JSONResponse(content={"error": "No se recibió ninguna imagen."}, status_code=400)

    try:
        ratio_val = float(ratio)
    except ValueError:
        return JSONResponse(content={"error": "Ratio inválido."}, status_code=400)

    if not (RATIO_MIN <= ratio_val <= RATIO_MAX):
        return JSONResponse(
            content={"error": f"El ratio debe estar entre {RATIO_MIN * 100:.0f}% y {RATIO_MAX * 100:.0f}%."},
            status_code=400,
        )

    job_id: str = uuid.uuid4().hex
    job_dir: Path = BASE_TMP / job_id
    input_dir: Path = job_dir / "in"
    output_dir: Path = job_dir / "out"
    input_dir.mkdir(parents=True)
    output_dir.mkdir(parents=True)

    results = []
    output_paths: dict[str, Path] = {}

    for f in images:
        original_name: str = Path(f.filename or "imagen").name
        # Si filename viene vacío, generar uno
        if not original_name or original_name == "imagen":
            original_name = f"imagen_{uuid.uuid4().hex[:6]}"
        ext: str = Path(original_name).suffix.lower()

        if ext not in SUPPORTED_EXTENSIONS:
            results.append(
                {
                    "filename": original_name,
                    "error": f"Formato no soportado ({ext or 'sin extensión'}).",
                }
            )
            continue

        in_path: Path = input_dir / original_name
        out_path: Path = output_dir / original_name

        # Manejar colisión de nombres dentro del mismo job evitando overwrite
        counter = 1
        stem: str = in_path.stem
        while in_path.exists() or out_path.exists():
            original_name = f"{stem}_{counter}{ext}"
            in_path = input_dir / original_name
            out_path = output_dir / original_name
            counter += 1

        try:
            contents: bytes = await f.read()
            in_path.write_bytes(data=contents)
        except Exception as e:  # noqa: BLE001
            results.append(
                {"filename": original_name, "error": f"Error al guardar: {e}"}
            )
            continue

        try:
            meta: CompressMeta = await run_in_threadpool(
                compress_to_target, in_path, out_path, ratio_val
            )
            pct: float = round(number=meta["new_size"] / meta["original_size"] * 100, ndigits=1)
            results.append(
                {
                    "filename": original_name,
                    "original_size": meta["original_size"],
                    "new_size": meta["new_size"],
                    "percent_of_original": pct,
                    "quality": meta["quality"],
                    "width": meta["width"],
                    "height": meta["height"],
                    "note": meta["note"],
                    "download_url": f"/api/download/{job_id}/{original_name}",
                }
            )
            output_paths[original_name] = out_path
        except UnsupportedFormatError as e:
            results.append({"filename": original_name, "error": str(object=e)})
        except Exception as e:  # noqa: BLE001
            results.append(
                {"filename": original_name, "error": f"Error al procesar: {e}"}
            )

    JOBS[job_id] = {"dir": job_dir, "created": time.time(), "files": output_paths}

    return JSONResponse(
        content={
            "job_id": job_id,
            "ratio": ratio_val,
            "results": results,
            "zip_url": f"/api/download-zip/{job_id}" if output_paths else None,
        }
    )


@app.get(path="/api/download/{job_id}/{filename:path}")
async def api_download(job_id: str, filename: str) -> FileResponse:
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="El trabajo expiró o no existe.")
    path = job["files"].get(filename)
    if not path or not path.exists():
        raise HTTPException(status_code=404, detail="Archivo no encontrado.")
    return FileResponse(path, filename=filename)


@app.get(path="/api/download-zip/{job_id}")
async def api_download_zip(job_id: str) -> StreamingResponse:
    job = JOBS.get(job_id)
    if not job or not job["files"]:
        raise HTTPException(status_code=404, detail="El trabajo expiró o no existe.")

    buffer = io.BytesIO()
    with zipfile.ZipFile(file=buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for fname, path in job["files"].items():
            zf.write(filename=path, arcname=fname)
    buffer.seek(0)

    headers: dict[str, str] = {"Content-Disposition": 'attachment; filename="imagenes_comprimidas.zip"'}
    return StreamingResponse(content=buffer, media_type="application/zip", headers=headers)


@app.get(path="/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get(path="/json/version")
async def json_version() -> dict[str, str]:
    # Expuesto porque probes externos lo piden; devuelve versión del paquete
    try:
        from importlib.metadata import version as pkg_version

        ver: str = pkg_version(distribution_name="smush")
    except Exception:  # noqa: BLE001
        # Sin metadata instalada (checkout sin pip install): versión dummy.
        ver = "0.1.0"
    return {"version": ver}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app="api:app", host="127.0.0.1", port=5000, reload=True)
