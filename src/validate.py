"""Módulo de validación de calidad de datos con Great Expectations (GX).

Valida completitud (nulos ≤ 5%), integridad de rangos (valor_fob_usd ≥ 0)
y coherencia física (peso_bruto_kg ≥ peso_neto_kg) antes de autorizar
la ingestión final a BigQuery.
"""
