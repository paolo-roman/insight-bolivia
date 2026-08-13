"""Módulo de validación de calidad de datos de comercio exterior.

Proporciona funciones de validación que verifican la integridad y coherencia
de los datos del INE Bolivia antes de autorizar la ingestión a BigQuery.
Incluye validaciones de:
- Completitud (nulos ≤ umbral configurable).
- Integridad de rangos (valor_fob_usd ≥ 0).
- Coherencia física (peso_bruto_kg ≥ peso_neto_kg).
- Formato NANDINA (10 dígitos).
- Tipo de cambio BOB/USD (≈ 6.96).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd


@dataclass
class ValidationResult:
    """Resultado de una validación de datos.

    Attributes
    ----------
    rule_name:
        Nombre de la regla de validación.
    passed:
        ``True`` si la validación pasó.
    message:
        Descripción del resultado.
    details:
        Detalles adicionales (filas afectadas, estadísticas, etc.).
    """

    rule_name: str
    passed: bool
    message: str
    details: dict = field(default_factory=dict)


def validate_nandina_format(
    series: pd.Series,
    *,
    expected_length: int = 10,
) -> ValidationResult:
    """Valida que los códigos NANDINA sean strings de longitud fija.

    Parameters
    ----------
    series:
        Serie con códigos NANDINA.
    expected_length:
        Longitud esperada (por defecto 10 dígitos).

    Returns
    -------
    ValidationResult
    """
    non_null = series.dropna()
    if non_null.empty:
        return ValidationResult(
            rule_name="nandina_format",
            passed=False,
            message="No hay valores NANDINA para validar (todos nulos).",
        )

    as_str = non_null.astype(str)
    wrong_length = as_str[as_str.str.len() != expected_length]
    non_numeric = as_str[~as_str.str.isdigit()]

    passed = len(wrong_length) == 0 and len(non_numeric) == 0
    issues = []
    if len(wrong_length) > 0:
        issues.append(f"{len(wrong_length)} registros con longitud != {expected_length}")
    if len(non_numeric) > 0:
        issues.append(f"{len(non_numeric)} registros con caracteres no numéricos")

    return ValidationResult(
        rule_name="nandina_format",
        passed=passed,
        message="NANDINA OK" if passed else f"NANDINA con errores: {'; '.join(issues)}",
        details={
            "total_registros": len(non_null),
            "longitud_incorrecta": len(wrong_length),
            "no_numericos": len(non_numeric),
            "muestras_incorrectas": wrong_length.head(5).tolist() if len(wrong_length) > 0 else [],
        },
    )


def validate_non_negative(
    series: pd.Series,
    *,
    column_name: str = "valor",
) -> ValidationResult:
    """Valida que todos los valores numéricos sean ≥ 0.

    Parameters
    ----------
    series:
        Serie numérica a validar.
    column_name:
        Nombre descriptivo de la columna para el reporte.

    Returns
    -------
    ValidationResult
    """
    numeric = pd.to_numeric(series, errors="coerce").dropna()
    if numeric.empty:
        return ValidationResult(
            rule_name=f"non_negative_{column_name}",
            passed=True,
            message=f"No hay valores numéricos en {column_name} para validar.",
        )

    negatives = numeric[numeric < 0]
    passed = len(negatives) == 0

    return ValidationResult(
        rule_name=f"non_negative_{column_name}",
        passed=passed,
        message=f"{column_name} OK (todos ≥ 0)" if passed else f"{column_name}: {len(negatives)} valores negativos",
        details={
            "total_registros": len(numeric),
            "negativos": len(negatives),
            "min_valor": float(numeric.min()),
            "max_valor": float(numeric.max()),
        },
    )


def validate_weight_consistency(
    peso_bruto: pd.Series,
    peso_neto: pd.Series,
) -> ValidationResult:
    """Valida coherencia física: peso_bruto ≥ peso_neto.

    Parameters
    ----------
    peso_bruto:
        Serie con peso bruto en kilogramos.
    peso_neto:
        Serie con peso neto en kilogramos.

    Returns
    -------
    ValidationResult
    """
    bruto = pd.to_numeric(peso_bruto, errors="coerce")
    neto = pd.to_numeric(peso_neto, errors="coerce")

    # Solo comparar donde ambos valores son no-nulos
    mask = bruto.notna() & neto.notna()
    comparable = mask.sum()

    if comparable == 0:
        return ValidationResult(
            rule_name="weight_consistency",
            passed=True,
            message="No hay pares de peso bruto/neto para comparar.",
        )

    violations = int((bruto[mask] < neto[mask]).sum())
    passed = bool(violations == 0)

    return ValidationResult(
        rule_name="weight_consistency",
        passed=passed,
        message="Pesos OK (bruto ≥ neto)" if passed else f"Pesos: {violations} registros donde bruto < neto",
        details={
            "pares_comparados": int(comparable),
            "violaciones": int(violations),
            "porcentaje_violaciones": round(float(violations) / float(comparable) * 100, 2) if comparable > 0 else 0.0,
        },
    )


def validate_null_threshold(
    df: pd.DataFrame,
    *,
    max_null_percentage: float = 5.0,
    mandatory_columns: list[str] | None = None,
) -> list[ValidationResult]:
    """Valida que los nulos por columna no excedan un umbral.

    Parameters
    ----------
    df:
        DataFrame de entrada.
    max_null_percentage:
        Porcentaje máximo de nulos permitido por columna.
    mandatory_columns:
        Columnas que deben tener 0% de nulos. Si ``None``, no se aplica.

    Returns
    -------
    list[ValidationResult]
        Lista de resultados, uno por columna que exceda el umbral
        o que sea obligatoria y tenga nulos.
    """
    results: list[ValidationResult] = []
    total = len(df)

    if total == 0:
        results.append(ValidationResult(
            rule_name="null_threshold",
            passed=False,
            message="DataFrame vacío, no se puede validar.",
        ))
        return results

    mandatory = set(mandatory_columns or [])

    for col in df.columns:
        null_count = int(df[col].isnull().sum())
        null_pct = round(null_count / total * 100, 2)

        if col in mandatory and null_count > 0:
            results.append(ValidationResult(
                rule_name=f"mandatory_not_null_{col}",
                passed=False,
                message=f"Columna obligatoria {col!r} tiene {null_count} nulos ({null_pct}%)",
                details={"columna": col, "nulos": null_count, "porcentaje": null_pct},
            ))
        elif null_pct > max_null_percentage:
            results.append(ValidationResult(
                rule_name=f"null_threshold_{col}",
                passed=False,
                message=f"Columna {col!r} excede umbral: {null_pct}% > {max_null_percentage}%",
                details={"columna": col, "nulos": null_count, "porcentaje": null_pct, "umbral": max_null_percentage},
            ))

    if not results:
        results.append(ValidationResult(
            rule_name="null_threshold",
            passed=True,
            message=f"Todas las columnas dentro del umbral de {max_null_percentage}% de nulos.",
        ))

    return results


def validate_exchange_rate(
    cif_bob: pd.Series,
    cif_usd: pd.Series,
    *,
    expected_rate: float = 6.96,
    tolerance: float = 0.10,
) -> ValidationResult:
    """Valida la consistencia del tipo de cambio BOB/USD en importaciones.

    El tipo de cambio oficial de Bolivia es 6.96 BOB/USD (fijo desde 2011).
    Verifica que ``ADU / FRO ≈ 6.96`` con una tolerancia configurable.

    Parameters
    ----------
    cif_bob:
        Serie con valores CIF en Bolivianos (columna ``ADU``).
    cif_usd:
        Serie con valores CIF en dólares (columna ``FRO``).
    expected_rate:
        Tipo de cambio esperado (por defecto 6.96).
    tolerance:
        Tolerancia absoluta permitida (por defecto ±0.10).

    Returns
    -------
    ValidationResult
    """
    bob = pd.to_numeric(cif_bob, errors="coerce")
    usd = pd.to_numeric(cif_usd, errors="coerce")

    # Solo calcular ratio donde ambos son no-nulos y USD > 0
    mask = bob.notna() & usd.notna() & (usd > 0)
    comparable = mask.sum()

    if comparable == 0:
        return ValidationResult(
            rule_name="exchange_rate",
            passed=True,
            message="No hay pares CIF BOB/USD para validar tipo de cambio.",
        )

    ratio = bob[mask] / usd[mask]
    outliers = ratio[(ratio < expected_rate - tolerance) | (ratio > expected_rate + tolerance)]

    passed = len(outliers) == 0

    return ValidationResult(
        rule_name="exchange_rate",
        passed=passed,
        message=(
            f"Tipo de cambio OK (media={ratio.mean():.2f}, esperado={expected_rate})"
            if passed
            else (
                f"Tipo de cambio: {len(outliers)} registros fuera de rango "
                f"[{expected_rate - tolerance}, {expected_rate + tolerance}]"
            )
        ),
        details={
            "pares_comparados": int(comparable),
            "ratio_media": round(float(ratio.mean()), 4),
            "ratio_mediana": round(float(ratio.median()), 4),
            "ratio_min": round(float(ratio.min()), 4),
            "ratio_max": round(float(ratio.max()), 4),
            "outliers": int(len(outliers)),
            "expected_rate": expected_rate,
            "tolerance": tolerance,
        },
    )


def run_export_validations(df: pd.DataFrame) -> list[ValidationResult]:
    """Ejecuta todas las validaciones para un DataFrame de exportaciones.

    Parameters
    ----------
    df:
        DataFrame de exportaciones (ya normalizado).

    Returns
    -------
    list[ValidationResult]
        Lista de resultados de validación.
    """
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
    """Ejecuta todas las validaciones para un DataFrame de importaciones.

    Parameters
    ----------
    df:
        DataFrame de importaciones (ya normalizado).

    Returns
    -------
    list[ValidationResult]
        Lista de resultados de validación.
    """
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
