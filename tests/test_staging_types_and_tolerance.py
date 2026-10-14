"""Pruebas unitarias para tipado defensivo en staging, tolerancia GX y filtrado temporal."""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from src.main import _discover_files_to_process
from src.transform import transform_to_staging
from src.validate import (
    build_comercio_exterior_suite,
    validate_transformed_data,
    validate_weight_consistency,
)

if TYPE_CHECKING:
    from pathlib import Path


class TestWeightConsistencyTolerance:
    """Pruebas de tolerancia física de peso en validaciones y Great Expectations."""

    def test_validate_weight_consistency_default_strict(self) -> None:
        bruto = pd.Series([100.0, 40.0])
        neto = pd.Series([100.0, 50.0])  # 1 violación de 2 = 50%
        res = validate_weight_consistency(bruto, neto)
        assert res.passed is False
        assert "Pesos: 1 registros" in res.message

    def test_validate_weight_consistency_with_tolerance_passes(self) -> None:
        bruto = pd.Series([100.0] * 99 + [40.0])  # 1 de 100 = 1%
        neto = pd.Series([100.0] * 99 + [50.0])
        res = validate_weight_consistency(bruto, neto, max_violation_pct=1.0)
        assert res.passed is True
        assert res.details["violaciones"] == 1

    def test_build_comercio_exterior_suite_has_mostly_on_weight(self) -> None:
        suite = build_comercio_exterior_suite()
        weight_exp = next(
            e for e in suite.expectations if type(e).__name__ == "ExpectColumnPairValuesAToBeGreaterThanB"
        )
        assert getattr(weight_exp, "mostly", None) == 0.99

    def test_gx_validation_accepts_minor_weight_inconsistency(self) -> None:
        # Generar 100 registros con 1 violación (1% <= 1%)
        records = []
        for i in range(100):
            records.append({
                "id_transaccion": i + 1,
                "fecha": "2024-01-01",
                "codigo_nandina": "0901110000",
                "pais_iso": "BOL",
                "id_departamento": 1,
                "id_via_transporte": 1,
                "id_aduana": 101,
                "tipo_operacion": "EXPORTACION",
                "valor_fob_usd": 1000.0,
                "valor_cif_usd": 0.0,
                "valor_fob_bob": 6960.0,
                "peso_neto_kg": 50.0,
                "peso_bruto_kg": 40.0 if i == 0 else 60.0,  # 1 registro anómalo
                "contenido_fino": 0.0,
                "anio": 2024,
                "mes": 1,
                "trimestre": 1,
            })
        df = pd.DataFrame(records)
        report = validate_transformed_data(df)
        assert report.success is True


class TestStagingDefensiveTyping:
    """Pruebas de conversión defensiva de tipos a string en staging y carga."""

    def test_transform_to_staging_formats_capitulo_nandina_as_string(self) -> None:
        raw = pd.DataFrame({
            "GESTION": [2024, 2024],
            "MES": [1, 2],
            "NANDINA": ["0901110000", "8471300000"],
            "CAP": [9, 84],  # Enteros que antes generaban ArrowTypeError
            "SECC": [2, 16],
            "CODACT2": [111, 222],
            "VALOR": [100.0, 200.0],
            "KILBRU": [10.0, 20.0],
            "KILNET": [10.0, 20.0],
        })
        stg = transform_to_staging(raw, operation_type="exportaciones")
        assert "capitulo_nandina" in stg.columns
        assert list(stg["capitulo_nandina"]) == ["09", "84"]
        assert all(isinstance(val, str) for val in stg["capitulo_nandina"])
        assert list(stg["seccion_nandina"]) == ["2", "16"]
        assert list(stg["codigo_actividad"]) == ["111", "222"]

    def test_transform_to_staging_handles_nan_and_floats_in_codes(self) -> None:
        raw = pd.DataFrame({
            "GESTION": [2024, 2024],
            "MES": [1, 2],
            "NANDINA": ["0901110000", "8471300000"],
            "SECC": [np.nan, 3.0],
            "CUCI3": [np.nan, 752.0],
            "VALOR": [100.0, 200.0],
        })
        stg = transform_to_staging(raw, operation_type="exportaciones")
        assert pd.isna(stg["seccion_nandina"].iloc[0])
        assert stg["seccion_nandina"].iloc[1] == "3"
        assert pd.isna(stg["codigo_cuci"].iloc[0])
        assert stg["codigo_cuci"].iloc[1] == "752"


class TestDiscoverFilesDateRangeFiltering:
    """Pruebas para filtrado de archivos por año en _discover_files_to_process."""

    def test_discover_filters_by_date_range_year(self, tmp_path: Path) -> None:
        exp_dir = tmp_path / "exportaciones"
        exp_dir.mkdir(parents=True)
        (exp_dir / "Exportaciones 1992.xlsx").write_bytes(b"dummy")
        (exp_dir / "EXPORTACIONES_2019.xlsx").write_bytes(b"dummy")
        (exp_dir / "EXPORTACIONES 2024p.xlsx").write_bytes(b"dummy")
        (exp_dir / "EXPORTACIONES 2025p.xlsx").write_bytes(b"dummy")

        opts_2024 = argparse.Namespace(
            file=None,
            operation="exportaciones",
            skip_extract=True,
            date_range="2024",
        )
        discovered = _discover_files_to_process(opts_2024, tmp_path)
        assert len(discovered) == 1
        assert discovered[0][0].name == "EXPORTACIONES 2024p.xlsx"

    def test_discover_without_date_range_includes_all(self, tmp_path: Path) -> None:
        exp_dir = tmp_path / "exportaciones"
        exp_dir.mkdir(parents=True)
        (exp_dir / "Exportaciones 1992.xlsx").write_bytes(b"dummy")
        (exp_dir / "EXPORTACIONES 2024p.xlsx").write_bytes(b"dummy")

        opts_all = argparse.Namespace(
            file=None,
            operation="exportaciones",
            skip_extract=True,
            date_range=None,
        )
        discovered = _discover_files_to_process(opts_all, tmp_path)
        assert len(discovered) == 2
