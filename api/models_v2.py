from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class PropertyDto(ApiModel):
    id: str
    source_url: str | None = None
    agency_id: str | None = None
    titulo: str | None = None
    descripcion: str | None = None
    operacion: str | None = None
    tipo_propiedad: str | None = None
    precio: float | None = None
    moneda: str | None = None
    ambientes: int | None = None
    dormitorios: int | None = None
    banos: int | None = None
    superficie_total: float | None = None
    superficie_cubierta: float | None = None
    imagenes: list[str] = Field(default_factory=list)
    latitud: float | None = None
    longitud: float | None = None
    geo: dict[str, Any] | None = None
    alcances: list[str] = Field(default_factory=list)
    ranking: dict[str, Any] | None = None


class SearchResponse(BaseModel):
    contrato: Literal["eretz_api_property_v1"]
    ranking: str | None
    sort: Literal["relevance", "price_asc", "price_desc"]
    consulta: str | None
    total: int
    limit: int
    offset: int
    data: list[PropertyDto]


class MapPoint(BaseModel):
    id: str
    latitud: float
    longitud: float
    precio: float | None
    moneda: str | None
    operacion: str | None
    tipo_propiedad: str | None
    titulo: str | None


class MapResponse(BaseModel):
    contrato: Literal["eretz_api_property_v1"]
    total_matches: int
    viewport_matches: int
    returned_points: int
    truncated: bool
    limit: int
    data: list[MapPoint]


class AgencyContact(BaseModel):
    status: Literal["AVAILABLE", "UNAVAILABLE"]
    phone: str | None
    whatsapp: str | None
    email: str | None


class AgencyDto(BaseModel):
    agency_id: str
    name: str
    logo: str | None
    website: str | None
    contact: AgencyContact


class AgencyResponse(BaseModel):
    contrato: Literal["eretz_api_property_v1"]
    data: AgencyDto


class BatchResponse(BaseModel):
    contrato: Literal["eretz_api_property_v1"]
    items: list[PropertyDto]
    missing_ids: list[str]
    requested_ids: list[str]
