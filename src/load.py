"""Módulo de carga de datos a Google BigQuery.

Implementa cargas idempotentes mediante hash SHA-256 y sentencias MERGE (upsert)
sobre la clave natural compuesta del grano completo (fecha, codigo_nandina,
pais_iso, tipo_operacion, id_departamento, id_via_transporte, id_aduana).
"""
