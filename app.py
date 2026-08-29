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

app = FastAPI(title="Smush — compresor de imágenes (API)")

MAX_CONTENT_LENGTH = 60 * 1024 * 1024  # 60 MB por request

BASE_TMP = Path(tempfile.gettempdir()) / "image-compressor-jobs"
BASE_TMP.mkdir(parents=True, exist_ok=True)

# job_id -> {"dir": Path, "created": float, "files": {filename: Path}}
JOBS: dict[str, dict] = {}
JOB_TTL_SECONDS = 60 * 30  # limpiar trabajos de más de 30 minutos


def _cleanup_old_jobs() -> None:
    now = time.time()
    expired = [jid for jid, job in JOBS.items() if now - job["created"] > JOB_TTL_SECONDS]
    for jid in expired:
        shutil.rmtree(JOBS[jid]["dir"], ignore_errors=True)
        JOBS.pop(jid, None)


@app.post("/api/compress")
async def api_compress(
    request: Request,
    images: list[UploadFile] = File(default=[]),
    ratio: str = Form(default="0.5"),
):
    # Límite de tamaño similar a Flask MAX_CONTENT_LENGTH
    clen = request.headers.get("content-length")
    if clen is not None:
        try:
            if int(clen) > MAX_CONTENT_LENGTH:
                return JSONResponse(
                    {"error": "El tamaño total excede el límite de 60 MB."},
                    status_code=413,
                )
        except ValueError:
            pass

    _cleanup_old_jobs()

    if not images or all(not f.filename for f in images):
        return JSONResponse({"error": "No se recibió ninguna imagen."}, status_code=400)

    try:
        ratio_val = float(ratio)
    except ValueError:
        return JSONResponse({"error": "Ratio inválido."}, status_code=400)

    if not (0.05 <= ratio_val <= 0.95):
        return JSONResponse(
            {"error": "El ratio debe estar entre 5% y 95%."}, status_code=400
        )

    job_id = uuid.uuid4().hex
    job_dir = BASE_TMP / job_id
    input_dir = job_dir / "in"
    output_dir = job_dir / "out"
    input_dir.mkdir(parents=True)
    output_dir.mkdir(parents=True)

    results = []
    output_paths: dict[str, Path] = {}

    for f in images:
        original_name = Path(f.filename or "imagen").name
        # Si filename viene vacío, generar uno
        if not original_name or original_name == "imagen":
            original_name = f"imagen_{uuid.uuid4().hex[:6]}"
        ext = Path(original_name).suffix.lower()

        if ext not in SUPPORTED_EXTENSIONS:
            results.append(
                {
                    "filename": original_name,
                    "error": f"Formato no soportado ({ext or 'sin extensión'}).",
                }
            )
            continue

        in_path = input_dir / original_name
        out_path = output_dir / original_name

        # Manejar colisión de nombres dentro del mismo job evitando overwrite
        counter = 1
        stem = in_path.stem
        while in_path.exists() or out_path.exists():
            original_name = f"{stem}_{counter}{ext}"
            in_path = input_dir / original_name
            out_path = output_dir / original_name
            counter += 1

        try:
            contents = await f.read()
            in_path.write_bytes(contents)
        except Exception as e:  # noqa: BLE001
            results.append(
                {"filename": original_name, "error": f"Error al guardar: {e}"}
            )
            continue

        try:
            meta = await run_in_threadpool(
                compress_to_target, in_path, out_path, ratio_val
            )
            pct = round(meta["new_size"] / meta["original_size"] * 100, 1)
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
            results.append({"filename": original_name, "error": str(e)})
        except Exception as e:  # noqa: BLE001
            results.append(
                {"filename": original_name, "error": f"Error al procesar: {e}"}
            )

    JOBS[job_id] = {"dir": job_dir, "created": time.time(), "files": output_paths}

    return JSONResponse(
        {
            "job_id": job_id,
            "ratio": ratio_val,
            "results": results,
            "zip_url": f"/api/download-zip/{job_id}" if output_paths else None,
        }
    )


@app.get("/api/download/{job_id}/{filename:path}")
async def api_download(job_id: str, filename: str):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="El trabajo expiró o no existe.")
    path = job["files"].get(filename)
    if not path or not path.exists():
        raise HTTPException(status_code=404, detail="Archivo no encontrado.")
    return FileResponse(path, filename=filename)


@app.get("/api/download-zip/{job_id}")
async def api_download_zip(job_id: str):
    job = JOBS.get(job_id)
    if not job or not job["files"]:
        raise HTTPException(status_code=404, detail="El trabajo expiró o no existe.")

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for fname, path in job["files"].items():
            zf.write(path, arcname=fname)
    buffer.seek(0)

    headers = {"Content-Disposition": 'attachment; filename="imagenes_comprimidas.zip"'}
    return StreamingResponse(buffer, media_type="application/zip", headers=headers)


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/json/version")
async def json_version():
    # Expuesto porque probes externos lo piden; devuelve versión del paquete
    try:
        from importlib.metadata import version as pkg_version

        ver = pkg_version("smush")
    except Exception:
        ver = "0.1.0"
    return {"version": ver}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="127.0.0.1", port=5000, reload=True)
