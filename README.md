# Smush — compresor de imágenes

Aplicación web para comprimir imágenes AVIF, WEBP, JPEG y PNG a un
porcentaje objetivo del tamaño original, manteniendo siempre las
dimensiones. Backend en FastAPI, frontend propio (HTML/CSS/JS, sin
frameworks), lista para correr local o desplegarse como servicio.

## Cómo funciona

Para cada imagen, el servidor prueba distintos valores de "calidad"
con búsqueda binaria hasta encontrar el más alto que da un archivo
igual o menor al % de tamaño pedido. Así se pierde la menor calidad
visual posible para llegar al peso objetivo. Las dimensiones nunca
se tocan.

## Correr en local

```bash
# requiere uv: https://docs.astral.sh/uv/getting-started/installation/
uv sync
uv run python app.py
```

Abrí `http://localhost:5000` en el navegador. También disponible la doc automática en `http://localhost:5000/docs`.

## Interfaz nativa multiplataforma (UI 100% Python con Flet)

La misma interfaz, replicando el diseño web, pero construida íntegramente
en Python con [Flet](https://flet.dev). Sin HTML: los controles llaman
directo a `compressor_core.compress_to_target`. Al ser Flet, corre en
escritorio (Windows/macOS/Linux), en el navegador y en móvil.

```bash
# 1) descargar las fuentes de marca (solo la primera vez)
uv run python scripts/fetch_fonts.py

# 2) correr la app (escritorio)
uv run python flet_app.py

# 3) correr en el navegador
uv run flet run --web flet_app.py
```

Elegís imágenes con el selector de archivos, ajustás el % objetivo con
el slider y guardás cada resultado o todo junto en un ZIP donde quieras.
Los archivos comprimidos intermedios viven en una carpeta temporal y se
autolimpian a los 30 minutos.

## Correr en local con Uvicorn (modo "producción")

```bash
uv sync --frozen
uv run uvicorn app:app --host 0.0.0.0 --port 8000 --workers 2
```

## Notas de producción

- Los archivos subidos y procesados se guardan en una carpeta
  temporal del sistema (`tempfile.gettempdir()/image-compressor-jobs`)
  y se descartan automáticamente a los 30 minutos de creados
  (ver `JOB_TTL_SECONDS` en `app.py`). En un despliegue con más de
  una réplica, cada una tiene su propio almacenamiento temporal:
  para ese caso conviene mover los archivos a un bucket (S3, GCS)
  en lugar de disco local.
- `MAX_CONTENT_LENGTH` en `app.py` limita el tamaño total de subida
  por request a 60 MB; ajustalo según necesites.
- Para correr detrás de un proxy (nginx, Cloud Run, etc.) no hace
  falta configuración extra: Uvicorn ya sirve en `0.0.0.0`.
- La compresión es CPU-bound (Pillow); FastAPI la ejecuta en threadpool vía `run_in_threadpool` para no bloquear el event loop.

## Tests

```bash
uv sync --group dev
uv run pytest -v          # 49 tests, ~4s
uv run pytest --cov       # con coverage si agregás pytest-cov
```

Cobertura actual: `compressor_core.py` (format, quality, PNG lossless, WEBP/AVIF, errores) y `app.py` (health, compress, validaciones ratio, formatos, colisión de nombres, límite 60MB, download/zip, 404). Ver `tests/` para detalles.

## Estructura del proyecto

```
flet_app.py             # punto de entrada de la UI Flet (multiplataforma)
smush_gui/              # interfaz Flet modular:
  app.py                #   controlador (navegación, compresión, guardado)
  theme.py              #   tokens de diseño y componentes base
  landing.py            #   vista de landing
  tool.py               #   vista de la herramienta
  helpers.py            #   assets, fuentes, miniaturas, utilidades
app.py                  # API REST FastAPI (/api/compress, /api/download/...)
scripts/fetch_fonts.py  # descarga las fuentes TTF a assets/fonts/
compressor_core.py      # lógica de compresión (búsqueda binaria de calidad)
assets/                 # recursos de marca y UI Flet
  img/                  #   isotipos, favicon, apple-touch-icon
  fonts/                #   TTF de marca (descargados)
tests/
  test_compressor_core.py
  test_app.py
  conftest.py
pyproject.toml          # dependencias (uv)
uv.lock                 # lockfile reproducible
Dockerfile
```
