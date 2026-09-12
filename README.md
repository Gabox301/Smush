# Smush — compresor de imágenes

Aplicación para comprimir imágenes AVIF, WEBP, JPEG y PNG a un
porcentaje objetivo del tamaño original, manteniendo siempre las
dimensiones. Backend en FastAPI y UI 100% en Python con Flet
(escritorio, navegador y móvil), lista para correr local o
desplegarse como servicio.

## Cómo funciona

Para cada imagen, el servidor prueba distintos valores de "calidad"
con búsqueda binaria hasta encontrar el más alto que da un archivo
igual o menor al % de tamaño pedido. Así se pierde la menor calidad
visual posible para llegar al peso objetivo. Las dimensiones nunca
se tocan.

La herramienta también convierte entre formatos (AVIF, WEBP, JPEG, PNG):
además de cambiar el formato, comprime buscando la mejor calidad que
entre en el peso máximo elegido (100% = que no pese más que el original).

## Correr en local (UI Flet)

La interfaz está construida íntegramente en Python con
[Flet](https://flet.dev): no hay HTML/CSS/JS. Por ser Flet, la misma UI
corre en escritorio (Windows/macOS/Linux), en el navegador y en móvil,
y llama directo a `compressor_core.compress_to_target`.

```bash
# requiere uv: https://docs.astral.sh/uv/getting-started/installation/
uv sync

# 1) descargar las fuentes de marca (solo la primera vez)
uv run python scripts/fetch_fonts.py

# 2) correr la app (escritorio)
uv run python flet_app.py

# 3) o correrla en el navegador
uv run flet run --web flet_app.py
```

Elegís imágenes con el selector de archivos, ajustás el % objetivo con
el slider y guardás cada resultado o todo junto en un ZIP donde quieras.
Los archivos comprimidos intermedios viven en una carpeta temporal y se
autolimpian a los 30 minutos.

## Generar el ejecutable (.exe) de escritorio

Empaquetá la UI en un único ejecutable Windows autónomo con
[`flet pack`](https://flet.dev/docs/publish) (usa PyInstaller por
debajo).

```bash
# requiere uv: https://docs.astral.sh/uv/getting-started/installation/
uv sync --group dev

# descargar las fuentes si aún no lo hiciste (assets/fonts/)
uv run python scripts/fetch_fonts.py

# empaquetar en dist/Smush.exe (incluye la carpeta assets: logo y fuentes)
uv run flet pack flet_app.py --name Smush --icon "assets/img/favicon.ico" --add-data "assets;assets" -y
```

El binario resulta en `dist/Smush.exe` y no necesita Python instalado para
ejecutarse. En Linux/macOS cambiá el separador de `--add-data` por `:` en
lugar de `;`.

## API REST (FastAPI)

El backend expone además una API REST para integrar la compresión desde
otros servicios. Para correrla en local:

```bash
uv sync
uv run python api.py
```

Queda escuchando en `http://localhost:5000`, con la doc automática
(Swagger) en `http://localhost:5000/docs`. Endpoints principales:
`POST /api/compress`, `GET /api/download/{job_id}/{filename}` y
`GET /api/download-zip/{job_id}`.

### Modo "producción" con Uvicorn

```bash
uv sync --frozen
uv run uvicorn api:app --host 0.0.0.0 --port 8000 --workers 2
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
uv run pytest -v
uv run pytest --cov       # cobertura (pytest-cov incluido en dev)
```

## Estructura del proyecto

```
flet_app.py             # punto de entrada de la UI Flet (multiplataforma)
smush_gui/              # interfaz Flet modular:
  app.py                #   controlador (navegación, compresión, conversión, guardado)
  theme.py              #   tokens de diseño y componentes base
  landing.py            #   vista de landing
  tool.py               #   vista de la herramienta (compresión + conversión)
  components/           #   primitivas UI (botones, cards, filas)
  helpers.py            #   assets, fuentes, miniaturas, utilidades
api.py                  # API REST FastAPI (/api/compress, /api/download/...)
scripts/fetch_fonts.py  # descarga las fuentes TTF a assets/fonts/
compressor_core/      # compresión (búsqueda binaria) y conversión:
  formats.py          #   constantes, formatos, validación
  metadata.py         #   TypedDicts de resultados y guards
  image_ops.py        #   operaciones Pillow (alfa, EXIF/ICC)
  encode.py           #   codificadores por formato
  search.py           #   búsqueda de calidad/paleta
  quality.py          #   PSNR con numpy opcional
  pipeline.py         #   compress_to_target, convert_format
assets/                 # recursos de marca y UI Flet
  img/                  #   isotipos, favicon, apple-touch-icon
  fonts/                #   TTF de marca (descargados)
tests/
  test_compressor_core.py
  test_app.py
  test_smush_gui.py
  test_components.py
  test_theme.py
  test_helpers.py
  conftest.py
pyproject.toml          # dependencias (uv) + config de ruff
uv.lock                 # lockfile reproducible
```

## Lint

```bash
uvx ruff check .       # lint (reglas en [tool.ruff.lint] de pyproject.toml)
```
