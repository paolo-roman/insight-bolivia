"""Módulo de validación de calidad de datos de comercio exterior.

Proporciona validaciones de integridad y coherencia tanto mediante reglas
nativas en Pandas como a través del framework Great Expectations (GX 1.x)
para asegurar la calidad antes de autorizar la ingestión a BigQuery.
"""

from __future__ import annotations

import contextlib
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Excepciones y Modelos de Resultados
# ---------------------------------------------------------------------------


class DataQualityError(Exception):
    """Excepción lanzada cuando los datos no superan los umbrales de calidad."""


@dataclass
class ValidationResult:
    """Resultado de una validación ligera en Pandas."""

    rule_name: str
    passed: bool
    message: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class GXValidationReport:
    """Reporte consolidado de ejecución de una Expectation Suite de Great Expectations."""

    success: bool
    suite_name: str
    total_expectations: int
    successful_expectations: int
    failed_expectations: int
    data_docs_url: str | None = None
    failed_details: list[dict[str, Any]] = field(default_factory=list)
    summary_message: str = ""


# ---------------------------------------------------------------------------
# Validaciones Ligeras en Pandas
# ---------------------------------------------------------------------------


def validate_nandina_format(series: pd.Series, *, expected_length: int = 10) -> ValidationResult:
    """Valida que los códigos NANDINA sean strings numéricos de longitud fija."""
    non_null = pd.Series(series.dropna())
    if non_null.empty:
        return ValidationResult("nandina_format", False, "No hay valores NANDINA para validar (todos nulos).")

    as_str = non_null.astype(str)
    wrong_length = pd.Series(as_str[as_str.str.len() != expected_length])
    non_numeric = pd.Series(as_str[~as_str.str.isdigit()])

    passed = len(wrong_length) == 0 and len(non_numeric) == 0
    issues: list[str] = []
    if len(wrong_length) > 0:
        issues.append(f"{len(wrong_length)} registros con longitud != {expected_length}")
    if len(non_numeric) > 0:
        issues.append(f"{len(non_numeric)} registros con caracteres no numéricos")

    return ValidationResult(
        "nandina_format",
        passed,
        "NANDINA OK" if passed else f"NANDINA con errores: {'; '.join(issues)}",
        {
            "total_registros": len(non_null),
            "longitud_incorrecta": len(wrong_length),
            "no_numericos": len(non_numeric),
            "muestras_incorrectas": wrong_length.head(5).tolist() if len(wrong_length) > 0 else [],
        },
    )


def validate_non_negative(series: pd.Series, *, column_name: str = "valor") -> ValidationResult:
    """Valida que todos los valores numéricos sean ≥ 0."""
    numeric = pd.Series(pd.to_numeric(series, errors="coerce")).dropna()
    if numeric.empty:
        return ValidationResult(f"non_negative_{column_name}", True, f"No hay valores numéricos en {column_name}.")

    negatives = pd.Series(numeric[numeric < 0])
    passed = len(negatives) == 0
    return ValidationResult(
        f"non_negative_{column_name}",
        passed,
        f"{column_name} OK (todos ≥ 0)" if passed else f"{column_name}: {len(negatives)} valores negativos",
        {
            "total_registros": len(numeric),
            "negativos": len(negatives),
            "min_valor": float(numeric.min()),
            "max_valor": float(numeric.max()),
        },
    )


def validate_weight_consistency(peso_bruto: pd.Series, peso_neto: pd.Series) -> ValidationResult:
    """Valida coherencia física: peso_bruto ≥ peso_neto."""
    bruto = pd.to_numeric(peso_bruto, errors="coerce")
    neto = pd.to_numeric(peso_neto, errors="coerce")

    mask = bruto.notna() & neto.notna()
    comparable = int(mask.sum())
    if comparable == 0:
        return ValidationResult("weight_consistency", True, "No hay pares de peso bruto/neto para comparar.")

    bruto_valid = bruto[mask]
    neto_valid = neto[mask]
    violations = int((bruto_valid < neto_valid).sum())
    passed = violations == 0
    return ValidationResult(
        "weight_consistency",
        passed,
        "Pesos OK (bruto ≥ neto)" if passed else f"Pesos: {violations} registros donde bruto < neto",
        {
            "pares_comparados": comparable,
            "violaciones": violations,
            "porcentaje_violaciones": round(violations / comparable * 100, 2) if comparable > 0 else 0.0,
        },
    )


def validate_null_threshold(
    df: pd.DataFrame,
    *,
    max_null_percentage: float = 5.0,
    mandatory_columns: list[str] | None = None,
) -> list[ValidationResult]:
    """Valida que los nulos por columna no excedan un umbral configurable."""
    results: list[ValidationResult] = []
    total = len(df)
    if total == 0:
        return [ValidationResult("null_threshold", False, "DataFrame vacío, no se puede validar.")]

    mandatory = set(mandatory_columns or [])
    for col in df.columns:
        null_count = int(df[col].isnull().sum())
        null_pct = round(null_count / total * 100, 2)
        if col in mandatory and null_count > 0:
            results.append(
                ValidationResult(
                    f"mandatory_not_null_{col}",
                    False,
                    f"Columna obligatoria {col!r} tiene {null_count} nulos ({null_pct}%)",
                    {"columna": col, "nulos": null_count, "porcentaje": null_pct},
                )
            )
        elif null_pct > max_null_percentage:
            results.append(
                ValidationResult(
                    f"null_threshold_{col}",
                    False,
                    f"Columna {col!r} excede umbral: {null_pct}% > {max_null_percentage}%",
                    {"columna": col, "nulos": null_count, "porcentaje": null_pct, "umbral": max_null_percentage},
                )
            )

    if not results:
        results.append(
            ValidationResult("null_threshold", True, f"Todas las columnas dentro de {max_null_percentage}% de nulos.")
        )
    return results


def validate_exchange_rate(
    cif_bob: pd.Series,
    cif_usd: pd.Series,
    *,
    expected_rate: float = 6.96,
    tolerance: float = 0.10,
) -> ValidationResult:
    """Valida la consistencia del tipo de cambio BOB/USD en importaciones."""
    bob = pd.to_numeric(cif_bob, errors="coerce")
    usd = pd.to_numeric(cif_usd, errors="coerce")

    mask = bob.notna() & usd.notna() & (usd > 0)
    comparable = int(mask.sum())
    if comparable == 0:
        return ValidationResult("exchange_rate", True, "No hay pares CIF BOB/USD para validar tipo de cambio.")

    bob_valid = bob[mask]
    usd_valid = usd[mask]
    ratio = bob_valid / usd_valid
    outliers = ratio[(ratio < expected_rate - tolerance) | (ratio > expected_rate + tolerance)]
    passed = len(outliers) == 0

    return ValidationResult(
        "exchange_rate",
        passed,
        (
            f"Tipo de cambio OK (media={ratio.mean():.2f}, esperado={expected_rate})"
            if passed
            else (
                f"Tipo de cambio: {len(outliers)} registros fuera de rango "
                f"[{expected_rate - tolerance}, {expected_rate + tolerance}]"
            )
        ),
        {
            "pares_comparados": comparable,
            "ratio_media": round(float(ratio.mean()), 4),
            "ratio_mediana": round(float(ratio.median()), 4),
            "ratio_min": round(float(ratio.min()), 4),
            "ratio_max": round(float(ratio.max()), 4),
            "outliers": len(outliers),
            "expected_rate": expected_rate,
            "tolerance": tolerance,
        },
    )


def run_export_validations(df: pd.DataFrame) -> list[ValidationResult]:
    """Ejecuta todas las validaciones ligeras para un DataFrame de exportaciones."""
    results: list[ValidationResult] = []
    if "NANDINA" in df.columns:
        results.append(validate_nandina_format(df["NANDINA"]))
    if "VALOR" in df.columns:
        results.append(validate_non_negative(df["VALOR"], column_name="VALOR_FOB"))
    if "KILBRU" in df.columns and "KILNET" in df.columns:
        results.append(validate_weight_consistency(df["KILBRU"], df["KILNET"]))

    mandatory = ["GESTION", "MES", "NANDINA", "PAIS", "VALOR"]
    existing_mandatory = [c for c in mandatory if c in df.columns]
    results.extend(validate_null_threshold(df, mandatory_columns=existing_mandatory))
    return results


def run_import_validations(df: pd.DataFrame) -> list[ValidationResult]:
    """Ejecuta todas las validaciones ligeras para un DataFrame de importaciones."""
    results: list[ValidationResult] = []
    if "NANDINA" in df.columns:
        results.append(validate_nandina_format(df["NANDINA"]))
    if "FOB" in df.columns:
        results.append(validate_non_negative(df["FOB"], column_name="FOB"))
    if "FRO" in df.columns:
        results.append(validate_non_negative(df["FRO"], column_name="CIF_FRONTERA"))
    if "ADU" in df.columns and "FRO" in df.columns:
        results.append(validate_exchange_rate(df["ADU"], df["FRO"]))

    mandatory = ["GESTION", "MES", "NANDINA", "PAIS", "FOB"]
    existing_mandatory = [c for c in mandatory if c in df.columns]
    results.extend(validate_null_threshold(df, mandatory_columns=existing_mandatory))
    return results


# ---------------------------------------------------------------------------
# Great Expectations (GX 1.x) Suite & Execution Engine
# ---------------------------------------------------------------------------


def build_comercio_exterior_suite(suite_name: str = "comercio_exterior_suite") -> Any:
    """Construye programáticamente la Expectation Suite para Comercio Exterior en GX 1.x."""
    import great_expectations as gx
    import great_expectations.expectations as gxe

    expectations: list[Any] = []

    # 1. Columnas clave no nulas (integridad estricta 100%)
    for col in ["fecha", "codigo_nandina", "pais_iso", "tipo_operacion"]:
        expectations.append(gxe.ExpectColumnValuesToNotBeNull(column=col))

    # 2. Columnas obligatorias con tolerancia de nulos <= 5% (mostly=0.95)
    for col in ["valor_fob_usd", "id_departamento", "id_via_transporte", "id_aduana", "anio", "mes", "trimestre"]:
        expectations.append(gxe.ExpectColumnValuesToNotBeNull(column=col, mostly=0.95))

    # 3. Rangos de valores no negativos y coherencia temporal
    expectations.append(gxe.ExpectColumnValuesToBeBetween(column="valor_fob_usd", min_value=0.0))
    expectations.append(gxe.ExpectColumnValuesToBeBetween(column="valor_fob_bob", min_value=0.0))
    expectations.append(gxe.ExpectColumnValuesToBeBetween(column="mes", min_value=1, max_value=12))
    expectations.append(gxe.ExpectColumnValuesToBeBetween(column="trimestre", min_value=1, max_value=4))

    # 4. Coherencia física: peso bruto >= peso neto
    expectations.append(
        gxe.ExpectColumnPairValuesAToBeGreaterThanB(
            column_A="peso_bruto_kg", column_B="peso_neto_kg", or_equal=True
        )
    )

    # 5. Formato NANDINA (exactamente 10 dígitos numéricos) y dominio de tipo de operación
    expectations.append(gxe.ExpectColumnValuesToMatchRegex(column="codigo_nandina", regex=r"^\d{10}$"))
    expectations.append(
        gxe.ExpectColumnValuesToBeInSet(column="tipo_operacion", value_set=["EXPORTACION", "IMPORTACION"])
    )

    return gx.ExpectationSuite(name=suite_name, expectations=expectations)


def get_gx_context(project_root_dir: str | Path | None = None, mode: str = "file") -> Any:
    """Obtiene o inicializa el DataContext de Great Expectations."""
    import great_expectations as gx

    if mode == "ephemeral":
        return gx.get_context(mode="ephemeral")

    resolved_root = Path(project_root_dir) if project_root_dir else Path.cwd()
    gx_dir = resolved_root / "gx"
    if not gx_dir.exists() and (resolved_root.parent / "gx").exists():
        resolved_root = resolved_root.parent

    try:
        return gx.get_context(mode="file", project_root_dir=resolved_root)
    except Exception as exc:
        logger.warning("No se pudo cargar FileDataContext en %s (%s). Usando ephemeral.", resolved_root, exc)
        return gx.get_context(mode="ephemeral")


def save_comercio_exterior_suite(
    context: Any | None = None,
    suite: Any | None = None,
    suite_name: str = "comercio_exterior_suite",
) -> Any:
    """Persiste la Expectation Suite en el contexto de GX."""
    ctx = context or get_gx_context()
    target_suite = suite or build_comercio_exterior_suite(suite_name=suite_name)
    with contextlib.suppress(Exception):
        ctx.suites.add(target_suite)
    return target_suite


def validate_transformed_data(
    df: pd.DataFrame,
    *,
    suite_name: str = "comercio_exterior_suite",
    context: Any | None = None,
    build_docs_on_failure: bool = True,
    build_docs: bool = False,
    raise_on_error: bool = False,
) -> GXValidationReport:
    """Ejecuta la suite de Great Expectations sobre un DataFrame transformado."""
    import great_expectations as gx

    ctx = context or get_gx_context()

    # Resolver suite
    try:
        suite = ctx.suites.get(suite_name)
    except Exception:
        suite = build_comercio_exterior_suite(suite_name=suite_name)
        with contextlib.suppress(Exception):
            ctx.suites.add(suite)

    # Configurar BatchDefinition y ValidationDefinition
    ds_name = f"pandas_runtime_{abs(hash(suite_name)) % 10000}"
    try:
        ds = ctx.data_sources.get(ds_name)
    except Exception:
        ds = ctx.data_sources.add_pandas(ds_name)

    asset_name = "df_asset"
    try:
        da = ds.get_asset(asset_name)
    except Exception:
        da = ds.add_dataframe_asset(asset_name)

    batch_def_name = "batch_def"
    try:
        bd = da.get_batch_definition(batch_def_name)
    except Exception:
        bd = da.add_batch_definition_whole_dataframe(batch_def_name)

    val_def_name = f"val_def_{suite_name}"
    try:
        vd = ctx.validation_definitions.get(val_def_name)
    except Exception:
        vd = gx.ValidationDefinition(data=bd, suite=suite, name=val_def_name)
        with contextlib.suppress(Exception):
            ctx.validation_definitions.add(vd)

    validation_result = vd.run(batch_parameters={"dataframe": df})
    success = bool(validation_result.success)

    results_list = getattr(validation_result, "results", [])
    total_exp = len(results_list)
    success_count = sum(1 for r in results_list if getattr(r, "success", False))
    failed_count = total_exp - success_count

    failed_details: list[dict[str, Any]] = []
    for r in results_list:
        if not getattr(r, "success", False):
            exp_config = getattr(r, "expectation_config", {})
            exp_type = (
                getattr(exp_config, "type", None)
                or getattr(exp_config, "expectation_type", None)
                or str(exp_config)
            )
            failed_details.append(
                {
                    "expectation_type": exp_type,
                    "kwargs": getattr(exp_config, "kwargs", {}),
                    "result": getattr(r, "result", {}),
                }
            )

    data_docs_url: str | None = None
    if build_docs or (build_docs_on_failure and not success):
        try:
            docs_dict = ctx.build_data_docs()
            if isinstance(docs_dict, dict) and "local_site" in docs_dict:
                data_docs_url = docs_dict["local_site"]
            elif isinstance(docs_dict, dict) and docs_dict:
                data_docs_url = next(iter(docs_dict.values()))
        except Exception as exc:
            logger.warning("No se pudo compilar Data Docs: %s", exc)

    summary_msg = (
        f"Validación de Calidad GX EXITOSA: {success_count}/{total_exp} expectativas cumplidas."
        if success
        else f"Validación de Calidad GX FALLIDA: {failed_count}/{total_exp} expectativas no cumplidas."
    )

    report = GXValidationReport(
        success=success,
        suite_name=suite_name,
        total_expectations=total_exp,
        successful_expectations=success_count,
        failed_expectations=failed_count,
        data_docs_url=data_docs_url,
        failed_details=failed_details,
        summary_message=summary_msg,
    )

    if not success and raise_on_error:
        raise DataQualityError(f"{summary_msg} Detalles: {failed_details}")

    return report


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Inicializando Data Context y Expectation Suite de Great Expectations...")
    gx_context = get_gx_context()
    gx_suite = save_comercio_exterior_suite(context=gx_context)
    print(f"Suite '{gx_suite.name}' configurada exitosamente con {len(gx_suite.expectations)} expectativas.")
