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
| **Base Operacional** | Google Cloud Firestore + Firebase Auth | Catálogo, auditoría, usuarios (NoSQL) |
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
- Cuenta en Google Cloud Platform (capa gratuita: BigQuery, Cloud Firestore)
- Proyecto en Firebase Console (Firebase Authentication)

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
# Editar secrets.toml con credenciales de GCP (BigQuery y Cloud Firestore)
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
├── firestore/
│   ├── rules/                  # Reglas de seguridad declarativas (firestore.rules)
│   ├── indexes/                # Índices compuestos (firestore.indexes.json)
│   └── seeds/                  # Datos semilla del catálogo (seed_catalog.json)
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
├── docs/                       # Guías técnicas, informes de seguridad y troubleshooting
│   └── GUIA_CARGAS_MANUALES_Y_TROUBLESHOOTING.md
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
uv run pytest --cov=src --cov=streamlit_app --cov-report=term-missing --cov-fail-under=90

# Auditoría de seguridad de dependencias
uv run pip-audit

# Iniciar entorno Jupyter para Notebooks EDA
uv run jupyter notebook

# Ejecutar orquestador EDA con Papermill
uv run papermill notebooks/00_orquestador_eda.ipynb notebooks/output/eda_run.ipynb

# Aprovisionar datasets, tablas del modelo estrella, vistas y dimensiones en BigQuery
uv run python -m src.init_dwh

# Inicializar catálogo operacional en Cloud Firestore
uv run python -m src.seed_firestore

# Cargar indicadores macroeconómicos de benchmark regional (Banco Mundial)
uv run python -m src.extract_benchmark

# Ejecutar pipeline ETL completo de Comercio Exterior (INE Bolivia)
uv run python -m src.main

# Ejecutar pipeline ETL en modo simulación (dry-run)
uv run python -m src.main --dry-run

# Ejecutar pipeline ETL con filtro temporal (filtrado optimizado de archivos por gestión)
uv run python -m src.main --date-range "2024"

# Procesar un archivo específico localmente (omitiendo web scraping del INE)
uv run python -m src.main --skip-extract --file "data/raw/comercio exterior/exportaciones/EXPORTACIONES 2024p.xlsx"

# Ejecutar pipeline ETL forzando reprocesamiento con filtro de gestión
uv run python -m src.main --force-reprocess --date-range "2024"

# Ejecutar aplicación Streamlit (local)
uv run streamlit run streamlit_app/app.py

# Ejecutar suite de pruebas End-to-End (E2E) y verificación de latencia
uv run pytest tests/test_e2e_streamlit.py
```

> **Guía Técnica de Operaciones:** Para instrucciones detalladas sobre backfill histórico, cargas manuales por archivo y resolución de incidencias, consulta la [Guía de Cargas Manuales y Troubleshooting](docs/GUIA_CARGAS_MANUALES_Y_TROUBLESHOOTING.md).

---

## Despliegue en la Nube y Acceso Público

### 🌐 Aplicativo Web en Vivo
El dashboard interactivo de **InsightBolivia** está desplegado en la nube con acceso público:

- **Streamlit Community Cloud:** [https://insightbolivia.streamlit.app](https://insightbolivia.streamlit.app) *(URL Oficial)*
- **Espejo Alternativo (Streamlit Cloud):** [https://insight-bolivia.streamlit.app](https://insight-bolivia.streamlit.app)

---

### 🚀 Guía de Despliegue Paso a Paso

#### 1. Despliegue en Streamlit Community Cloud (Instancia Principal)
1. Iniciar sesión en [Streamlit Community Cloud](https://share.streamlit.io/) con la cuenta de GitHub asociada.
2. Hacer clic en **"New app"** y seleccionar el repositorio:
   - **Repository:** `paolo-roman/insight-bolivia` (o `insightbolivia/insight-bolivia`)
   - **Branch:** `main`
   - **Main file path:** `streamlit_app/app.py`
   - **App URL:** `insightbolivia` (genera `https://insightbolivia.streamlit.app`)
3. En la sección **"Advanced settings" > "Secrets"**, pegar el contenido TOML de credenciales (basado en `streamlit_app/.streamlit/secrets.toml.example`):
   ```toml
   [gcp_service_account]
   type = "service_account"
   project_id = "insight-bolivia"
   private_key_id = "tu-private-key-id"
   private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
   client_email = "streamlit-sa@insight-bolivia.iam.gserviceaccount.com"
   client_id = "tu-client-id"
   auth_uri = "https://accounts.google.com/o/oauth2/auth"
   token_uri = "https://oauth2.googleapis.com/token"
   auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
   client_x509_cert_url = "https://www.googleapis.com/robot/v1/metadata/x509/..."

   [bigquery]
   project_id = "insight-bolivia"
   dataset = "comercio_exterior"
   location = "US"

   [firestore]
   database = "(default)"
   project_id = "insight-bolivia"
   ```
4. Hacer clic en **"Deploy"**.

#### 2. Despliegue de Espejo de Respaldo en Streamlit Community Cloud
Para contar con una instancia espejo de alta disponibilidad y redundancia sin costo ($0 USD):
1. En [Streamlit Community Cloud](https://share.streamlit.io/), hacer clic nuevamente en **"New app"**.
2. Seleccionar el mismo repositorio `paolo-roman/insight-bolivia`, rama `main` y archivo principal `streamlit_app/app.py`.
3. En **App URL**, personalizar el subdominio a `insight-bolivia` (generando `https://insight-bolivia.streamlit.app`).
4. Replicar los mismos secretos TOML en **"Advanced settings" > "Secrets"** y hacer clic en **"Deploy"**.

> **Nota sobre infraestructura en la nube:** Plataformas como Hugging Face Spaces han restringido los entornos de ejecución con cómputo backend (Streamlit, Gradio, Docker) a planes de suscripción de pago (PRO), por lo que Streamlit Community Cloud se consolida como la solución oficial, nativa y 100% gratuita dentro de las cuotas Free Tier.

---

### ⚡ Rendimiento, SLA y Control de Costos ($0 USD)

- **Latencia de Respuesta ($\le 3.0$ segundos):** Todas las páginas del aplicativo consumen exclusivamente **Vistas SQL Pre-agregadas** en BigQuery (`vw_balanza_comercial_mensual`, `vw_socios_comerciales`, `vw_top_productos_exportados`), complementadas con caché en memoria `@st.cache_data(ttl=3600)`.
- **Protección de Memoria:** Límite estricto de **50,000 registros** en el Centro de Descargas para prevenir errores Out-Of-Memory (OOM) en el contenedor de Streamlit Cloud (1 GB RAM).
- **Cero Costos Cloud:** El volumen de escaneo se mantiene por debajo de 1 TB/mes en BigQuery y las operaciones de Firestore se mantienen dentro de las 50,000 lecturas/día del *Always Free Tier*.
- **Telemetría y Observabilidad:** Registro automático no bloqueante de eventos de interacción y vistas en Cloud Firestore (`ui_analytics`).

---

## Licencia

Este proyecto está licenciado bajo la **BSD 3-Clause License**. Consulta el archivo [LICENSE](LICENSE) para más detalles.

> **Marca registrada:** El nombre "InsightBolivia" y su branding asociado son marcas del titular del copyright. La licencia otorga permiso para usar, modificar y redistribuir el código fuente, pero **NO** otorga permiso para usar el nombre "InsightBolivia" para endosar o promocionar productos derivados sin autorización previa.
