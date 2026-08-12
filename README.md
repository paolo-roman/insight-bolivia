# InsightBolivia

**Plataforma centralizada de ingeniería de datos y analítica** orientada a la extracción, transformación, almacenamiento y visualización automática de datos abiertos en Bolivia.

El proyecto inicia procesando y analizando los datos de **Comercio Exterior (Exportaciones e Importaciones)** del Instituto Nacional de Estadística (INE), para posteriormente incorporar métricas internacionales (Banco Mundial, CEPAL).

---

## Arquitectura

| Componente | Tecnología | Propósito |
|:---|:---|:---|
| **Orquestación** | GitHub Actions | Cron jobs diarios para pipeline ETL |
| **ETL** | Python (Pandas, Polars, Requests, BeautifulSoup4) | Extracción, transformación y carga de datos |
| **Data Warehouse** | Google BigQuery | Almacenamiento analítico (Star Schema) |
| **Base Operacional** | Supabase (PostgreSQL) | Catálogo, auditoría, usuarios |
| **Calidad de Datos** | Great Expectations | Validación automatizada de esquemas y datos |
| **Visualización** | Streamlit + Plotly | Dashboard interactivo |
| **Gestión de Paquetes** | uv | Entornos virtuales y dependencias |
| **Linter** | Ruff | Análisis estático y formateo (PEP 8) |
| **Tests** | Pytest | Pruebas unitarias y de integración |

---

## Requisitos Previos

- **Python** ≥ 3.11
- **uv** ≥ 0.4 — [Instrucciones de instalación](https://docs.astral.sh/uv/getting-started/installation/)
- **Git** ≥ 2.40
- Cuenta en Google Cloud Platform (capa gratuita)
- Cuenta en Supabase (capa gratuita)

---

## Setup Local

### 1. Clonar el repositorio

```bash
git clone https://github.com/insightbolivia/insight-bolivia.git
cd insight-bolivia
```

### 2. Instalar dependencias con `uv`

```bash
# Instalar todas las dependencias (incluyendo dev)
uv sync

# Verificar instalación
uv run python --version
```

> **Nota:** `uv sync` crea automáticamente un entorno virtual (`.venv/`) y genera el lockfile determinista (`uv.lock`).

### 3. Configurar variables de entorno

```bash
# Copiar la plantilla de variables de entorno
cp .env.example .env

# Editar .env con tus credenciales (nunca comitear este archivo)
```

Consulta `.env.example` para la lista completa de variables requeridas.

### 4. Configurar secretos de Streamlit (opcional)

```bash
cp streamlit_app/.streamlit/secrets.toml.example streamlit_app/.streamlit/secrets.toml
# Editar secrets.toml con credenciales de GCP y Supabase
```

---

## Estructura del Proyecto

```
insight-bolivia/
├── .github/workflows/          # Pipelines CI/CD y ETL (GitHub Actions)
├── gx/                         # Great Expectations (validación de datos)
│   ├── expectations/
│   ├── checkpoints/
│   └── great_expectations.yml
├── src/                        # Paquete principal del pipeline ETL
│   ├── __init__.py
│   ├── extract.py              # Extracción de datos (INE Bolivia)
│   ├── transform.py            # Transformación y normalización
│   ├── load.py                 # Carga a BigQuery (idempotente)
│   ├── validate.py             # Validación con Great Expectations
│   └── config.py               # Lectura de configuración
├── sql/
│   ├── ddl/                    # Scripts DDL para BigQuery
│   └── views/                  # Vistas SQL pre-agregadas
├── supabase/
│   └── migrations/             # Migraciones versionadas (PostgreSQL)
├── tests/                      # Suite de pruebas (pytest)
│   ├── __init__.py
│   └── fixtures/               # Datos de prueba (XLSX, CSV, DBF)
├── streamlit_app/              # Aplicación web (Streamlit)
│   ├── app.py                  # Punto de entrada
│   ├── pages/                  # Páginas del dashboard
│   ├── components/             # Componentes reutilizables
│   └── .streamlit/
│       └── secrets.toml.example
├── notebooks/                  # Jupyter notebooks (EDA)
├── config/
│   └── config.yaml             # Configuración del pipeline
├── data/
│   └── raw/                    # Archivos fuente descargados
├── .env.example                # Plantilla de variables de entorno
├── .gitignore                  # Exclusiones de Git
├── pyproject.toml              # Configuración del proyecto (uv, Ruff, pytest)
├── uv.lock                     # Lockfile determinista
├── LICENSE                     # BSD 3-Clause
├── CHANGELOG.md                # Registro de cambios
├── README.md                   # Este archivo
└── last_run.txt                # Timestamp para mantener cron activo
```

---

## Comandos Frecuentes

```bash
# Instalar/actualizar dependencias
uv sync

# Ejecutar linter (Ruff)
uv run ruff check .

# Formatear código
uv run ruff format .

# Ejecutar pruebas
uv run pytest

# Ejecutar pruebas con cobertura
uv run pytest --cov=src --cov-report=term-missing --cov-fail-under=90

# Auditoría de seguridad de dependencias
uv run pip-audit

# Ejecutar aplicación Streamlit (local)
uv run streamlit run streamlit_app/app.py
```

---

## Licencia

Este proyecto está licenciado bajo la **BSD 3-Clause License**. Consulta el archivo [LICENSE](LICENSE) para más detalles.

> **Marca registrada:** El nombre "InsightBolivia" y su branding asociado son marcas del titular del copyright. La licencia otorga permiso para usar, modificar y redistribuir el código fuente, pero **NO** otorga permiso para usar el nombre "InsightBolivia" para endosar o promocionar productos derivados sin autorización previa.
