"""Modelos de datos y esquemas Pydantic para Google Cloud Firestore (Modo Nativo).

Define la estructura de documentos y validaciones de tipos para las 4 colecciones
operacionales de la plataforma:
- `user_profiles`: Perfiles de usuario y roles RBAC (admin, analyst, viewer).
- `dwh_catalog`: Catálogo de Data Warehouses y metadatos de vistas BigQuery/Streamlit.
- `audit_log`: Registro inmutable de auditoría de acciones del usuario y del sistema.
- `ui_analytics`: Telemetría y analítica de interacción en el dashboard de Streamlit.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Expresión regular estándar para validación básica y robusta de formato email
EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")


class UserRole(StrEnum):
    """Roles de usuario soportados en el control de acceso (RBAC)."""

    ADMIN = "admin"
    ANALYST = "analyst"
    VIEWER = "viewer"


class FirestoreBaseModel(BaseModel):
    """Modelo base con configuración compartida para documentos de Firestore."""

    model_config = ConfigDict(
        populate_by_name=True,
        validate_assignment=True,
        extra="forbid",
        use_enum_values=True,
    )

    def to_firestore_dict(self, *, exclude_none: bool = False) -> dict[str, Any]:
        """Serializa el modelo a un diccionario compatible con Google Cloud Firestore.

        Parameters
        ----------
        exclude_none:
            Si es True, excluye los campos cuyo valor sea None.

        Returns
        -------
        dict[str, Any]
        """
        return self.model_dump(mode="python", exclude_none=exclude_none)

    @classmethod
    def from_firestore_dict(cls, data: dict[str, Any]) -> FirestoreBaseModel:
        """Instancia el modelo desde un diccionario obtenido de un DocumentSnapshot de Firestore.

        Parameters
        ----------
        data:
            Diccionario con datos crudos del documento.

        Returns
        -------
        Instancia validada del modelo Pydantic.
        """
        return cls.model_validate(data)


class UserProfile(FirestoreBaseModel):
    """Esquema de documento para la colección `user_profiles`.

    Document ID: `auth_uid` de Firebase Authentication.
    """

    display_name: str = Field(..., min_length=1, description="Nombre completo o visible del usuario.")
    email: str = Field(..., description="Correo electrónico del usuario.")
    organization: str = Field(default="", description="Organización o equipo al que pertenece el usuario.")
    role: UserRole = Field(default=UserRole.VIEWER, description="Rol RBAC del usuario (admin, analyst, viewer).")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Fecha y hora de creación de la cuenta.",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Fecha y hora de última actualización del perfil.",
    )

    @field_validator("email")
    @classmethod
    def validate_email_format(cls, value: str) -> str:
        """Valida que el correo electrónico tenga una estructura válida."""
        cleaned = value.strip().lower()
        if not EMAIL_REGEX.match(cleaned):
            raise ValueError(f"Formato de correo electrónico inválido: '{value}'")
        return cleaned

    @field_validator("display_name")
    @classmethod
    def validate_display_name_not_blank(cls, value: str) -> str:
        """Valida que el nombre de usuario no esté compuesto únicamente de espacios en blanco."""
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("El display_name no puede ser una cadena vacía.")
        return cleaned


class CatalogView(FirestoreBaseModel):
    """Esquema de vista asociada a un Data Warehouse en `dwh_catalog.views`."""

    view_name: str = Field(..., min_length=1, description="Nombre técnico de la vista SQL / Materializada en BigQuery.")
    display_name: str = Field(..., min_length=1, description="Título legible de la vista para la interfaz de usuario.")
    description: str = Field(default="", description="Descripción del propósito y métricas de la vista.")
    bq_view_path: str = Field(..., min_length=1, description="Ruta completa en BigQuery (dataset.vista).")
    chart_type: str = Field(
        default="table",
        description="Tipo de gráfico predeterminado (line, bar, choropleth, scatter, table, etc.).",
    )
    is_public: bool = Field(default=True, description="Indica si la vista está disponible para usuarios públicos.")
    sort_order: int = Field(default=1, ge=1, description="Orden de presentación en el menú del dashboard.")


class DwhCatalog(FirestoreBaseModel):
    """Esquema de documento para la colección `dwh_catalog`.

    Document ID: `code` del Data Warehouse (ej: `comercio_exterior`).
    """

    code: str = Field(..., min_length=1, description="Código identificador único del DWH (ej: comercio_exterior).")
    name: str = Field(..., min_length=1, description="Nombre legible del Data Warehouse.")
    description: str = Field(..., min_length=1, description="Descripción detallada del contenido del DWH.")
    bq_dataset: str = Field(..., min_length=1, description="Nombre del dataset en BigQuery.")
    bq_project: str = Field(default="insightbolivia-dwh", description="ID del proyecto Google Cloud en BigQuery.")
    streamlit_url: str = Field(default="", description="URL de la aplicación interactiva en Streamlit.")
    icon: str = Field(default="📦", description="Emoji o ícono identificador del DWH.")
    status: str = Field(default="active", description="Estado operativo (active, maintenance, inactive).")
    data_source: str = Field(..., min_length=1, description="Fuente oficial de los datos (ej: INE).")
    update_frequency: str = Field(default="mensual", description="Frecuencia estimada de actualización de datos.")
    last_data_refresh: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Fecha y hora de la última ingesta exitosa de datos.",
    )
    record_count: int = Field(default=0, ge=0, description="Total de registros consolidados en el DWH.")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Fecha de registro en el catálogo.",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Fecha de última modificación de metadatos.",
    )
    views: list[CatalogView] = Field(
        default_factory=list,
        description="Lista de vistas SQL y visualizaciones asociadas al Data Warehouse.",
    )

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        """Valida que el estado pertenezca a los valores estándar permitidos."""
        allowed_statuses = {"active", "inactive", "maintenance", "deprecated"}
        cleaned = value.strip().lower()
        if cleaned not in allowed_statuses:
            raise ValueError(f"Estado '{value}' no permitido. Valores válidos: {allowed_statuses}")
        return cleaned


class AuditLog(FirestoreBaseModel):
    """Esquema de documento para la colección `audit_log`.

    Document ID: Autogenerado por Firestore.
    """

    user_id: str = Field(..., min_length=1, description="Identificador del usuario (auth_uid o 'system').")
    action: str = Field(..., min_length=1, description="Acción ejecutada (query, export, etl_load, login, etc.).")
    resource_type: str = Field(default="general", description="Tipo de recurso accedido (view, dataset, etl, auth).")
    resource_id: str = Field(default="", description="Identificador del recurso afectado.")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Metadatos contextuales de la operación.")
    ip_address: str = Field(default="", description="Dirección IP de origen del cliente.")
    user_agent: str = Field(default="", description="Cadena User-Agent del navegador o cliente.")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Marca temporal UTC del evento de auditoría.",
    )


class UiAnalytics(FirestoreBaseModel):
    """Esquema de documento para la colección `ui_analytics`.

    Document ID: Autogenerado por Firestore.
    """

    session_id: str = Field(..., min_length=1, description="Identificador único de la sesión de usuario (UUID).")
    user_id: str | None = Field(default=None, description="Identificador del usuario autenticado si aplica.")
    page: str = Field(..., min_length=1, description="Página o sección del dashboard interactuada.")
    event_type: str = Field(
        ...,
        min_length=1,
        description="Tipo de evento registrado (page_view, filter_apply, export_csv, etc.).",
    )
    event_data: dict[str, Any] = Field(default_factory=dict, description="Parámetros y filtros aplicados en el evento.")
    duration_ms: int | None = Field(
        default=None,
        ge=0,
        description="Duración en milisegundos de la interacción o procesamiento.",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Marca temporal UTC en que ocurrió el evento.",
    )
