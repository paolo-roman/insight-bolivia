# Reglas de Desarrollo Obligatorias: InsightBolivia (Antigravity & Cursor)

Este archivo define las reglas y estándares de desarrollo obligatorios para todos los asistentes de IA (Antigravity, Cursor, Copilot, etc.) y desarrolladores que trabajen en el proyecto **InsightBolivia**.

---

## 1. Normas Técnicas Obligatorias (Core Rules)

1. **Gestor de Paquetes Python (`uv` Exclusivo):**
   - Jamás ejecutes `python`, `pip` o `pip3` directamente.
   - Toda ejecución de Python, pruebas o gestión de dependencias en el backend DEBE realizarse a través de `uv` (ej: `uv run <comando>`, `uv sync`, `uv add <paquete>`).

2. **Calidad de Código, Estilo y Security Linting (Ruff):**
   - Todo código escrito debe cumplir con PEP 8 y ser validado mediante `uv run ruff check .`.
   - Se exige **0 errores y 0 advertencias** antes de dar por finalizada cualquier tarea.

3. **Pruebas Unitarias y Cobertura Mínima (90%):**
   - Toda funcionalidad nueva o modificada debe incluir sus correspondientes pruebas unitarias en la suite `pytest`.
   - Cobertura mínima obligatoria del **90%** por archivo/script nuevo o modificado (`uv run pytest --cov=src --cov-fail-under=90`).
   - Todas las pruebas deben pasar antes de autorizar commits o finalizar tareas.

4. **Documentación, README y CHANGELOG:**
   - **`CHANGELOG.md` de actualización OBLIGATORIA:** Registrar todo cambio siguiendo la especificación *Keep a Changelog* (secciones: `Added`, `Changed`, `Fixed`, `Removed`, `Security`).
   - **`README.md`:** Actualizar si el cambio afecta la arquitectura, configuración de entorno, endpoints o comandos de ejecución.

5. **Seguridad, Auditoría y Secretos:**
   - **CERO credenciales hardcodeadas:** Prohibido escribir claves API, Service Account Keys o secretos en el código. Usar exclusivamente variables de entorno (`.env`), `st.secrets` y GitHub Secrets.
   - **Usuarios de prueba:** Prohibición absoluta de cambiar, resetear o modificar contraseñas de usuarios de prueba internos.
   - Ejecutar auditorías de seguridad periódicas (`uv run ruff check .`, `pip-audit` o herramientas de SAST/SCA).

6. **Base de Datos y Migraciones Versionadas:**
   - Todo cambio en esquemas de base de datos o configuración NoSQL debe ser versionado mediante archivos declarativos en `firestore/` (`rules/`, `indexes/`, `seeds/`) o scripts DDL en `sql/ddl/` (para BigQuery).

7. **Límite de Longitud de Archivos y Scripts (Máximo 500 Líneas):**
   - Ningún archivo, módulo o script de código debe sobrepasar las **500 líneas de código**.
   - Se debe preservar una alta legibilidad, modularidad y principio de responsabilidad única.
   - Si un archivo se acerca o supera las 500 líneas, debe ser refactorizado y modularizado en componentes o submódulos más pequeños y especializados.

---

## 2. Estándares de Arquitectura e Ingeniería de Datos

### 2.1 BigQuery (OLAP) & Control de Costos Capa Gratuita ($0 USD)
- **Regla de Oro en Streamlit:** Queda **estrictamente prohibido** ejecutar `SELECT * FROM fact_comercio_exterior` o escaneos crudos masivos desde Streamlit.
- **Consumo exclusivo de Vistas:** Streamlit debe consumir únicamente Vistas SQL o Vistas Materializadas pre-agregadas (`vw_balanza_comercial_mensual`, `vw_top_productos_exportados`, `vw_socios_comerciales`).
- **Filtrado por Rango de Fechas:** Toda consulta SQL debe incluir filtros explícitos por la columna de particionamiento `fecha` para aprovechar el particionamiento mensual y clustering (`codigo_nandina`, `pais_iso`), manteniendo el escaneo dentro del límite gratuito de 1 TB/mes.

### 2.2 Pipeline ETL Resiliente en Python
- **Extracción (`extract.py`):** Implementar cabeceras `User-Agent` de navegador real, reintentos exponenciales (`urllib3.util.retry.Retry`), timeout explícito (`timeout=30`) y manejo defensivo de certificados SSL para portales gubernamentales (`ine.gob.bo`).
- **Idempotencia de Carga (`load.py`):** Calcular el hash SHA-256 del archivo descargado y verificarlo en `operations.etl_control_log`. La carga a BigQuery debe usar sentencias `MERGE` (upsert) sobre la clave natural compuesta de grano completo (`fecha`, `codigo_nandina`, `pais_iso`, `tipo_operacion`, `id_departamento`, `id_via_transporte`, `id_aduana`).
- **Calidad de Datos (`validate.py`):** Integrar **Great Expectations (GX)** para validar completitud (nulos $\le 5\%$), integridad de rangos (`valor_fob_usd` $\ge 0$) y coherencia física (`peso_bruto_kg` $\ge$ `peso_neto_kg`) antes de autorizar la ingestión final.

### 2.3 Cloud Firestore (OLTP) & Seguridad
- **Reglas de Seguridad Declarativas:** Toda colección y documento en Cloud Firestore debe contar con reglas de seguridad granulares versionadas en `firestore/rules/firestore.rules`.
- **Control de Cuotas en Capa Gratuita:** Mantener las lecturas/escrituras dentro de los límites del Always Free Tier de Firestore (50k lecturas/día, 20k escrituras/día) mediante el uso de TTLs y agregaciones en BigQuery.

### 2.4 Aplicativo Web Streamlit UI/UX
- **Caching Decorators:** Aplicar `@st.cache_data(ttl=3600)` en todas las funciones que realicen consultas a BigQuery o Cloud Firestore.
- **Límite de Descargas de Seguridad:** Limitar las descargas a un máximo estricto de **50,000 registros** y exigir la selección de filtros obligatorios para evitar errores de falta de memoria (OOM) en Streamlit Cloud (límite de 1 GB RAM).

---

## 3. Convenciones de Git y Estilo de Código

- **Commits:** Seguir la convención *Conventional Commits*: `feat:`, `fix:`, `docs:`, `chore:`, `test:`, `refactor:`.
- **Ramas:** `main` (producción), `develop` (integración), `feature/nombre-tarea`, `hotfix/nombre-arreglo`.
- **Nomenclatura Python:** `snake_case` para funciones y variables, `PascalCase` para clases, `UPPER_CASE` para constantes.
- **Nomenclatura SQL:** Palabras clave en MAYÚSCULAS (`SELECT`, `FROM`, `WHERE`, `JOIN`), nombres de tablas y columnas en `snake_case`.

---

## 4. Checklist Obligatorio Antes de Finalizar Cualquier Tarea

- [ ] ¿Se ejecutaron las pruebas con `uv run pytest` y la cobertura es $\ge 90\%$ en archivos nuevos/modificados?
- [ ] ¿El linter no muestra errores ni advertencias (`uv run ruff check .`)?
- [ ] ¿Ningún archivo o script nuevo/modificado sobrepasa el límite de 500 líneas de código?
- [ ] ¿Se registró el cambio en `CHANGELOG.md` siguiendo *Keep a Changelog*?
- [ ] ¿Se actualizó `README.md` si hubo cambios en comandos, arquitectura o secretos?
- [ ] ¿Se crearon los scripts DDL de migración si se modificó el esquema de base de datos?
- [ ] ¿Se verificó que no existan credenciales hardcodeadas?
