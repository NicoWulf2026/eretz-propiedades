from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

ALLOWED_PROPERTY_TYPES = {
    "casa",
    "departamento",
    "terreno",
    "local",
    "oficina",
    "cochera",
    "galpon",
    "otro",
}

ALLOWED_MONEDAS = {"ARS", "USD"}
# Operaciones reconocidas por InmoCapital (FASE 1 — Sprint A).
# - consultar: operacion desconocida o no detectada → no rechazar, publicar con consultar
# - venta_y_alquiler: propiedad publicada simultáneamente como venta y alquiler
ALLOWED_OPERACIONES = {
    "venta",
    "alquiler",
    "alquiler_temporario",
    "consultar",
    "venta_y_alquiler",
    "proyecto",  # legacy — no eliminar
}


@dataclass
class Propiedad:
    url: str
    titulo: str
    precio: Optional[int] = None
    moneda: Optional[str] = None
    direccion: Optional[str] = None
    barrio: Optional[str] = None
    barrio_normalizado: Optional[str] = None
    tipo_propiedad: str = "otro"
    descripcion: str = ""
    dormitorios: Optional[int] = None
    banos: Optional[int] = None
    ambientes: Optional[int] = None
    metros: Optional[int] = None
    imagenes: List[str] = field(default_factory=list)
    ciudad: Optional[str] = None
    operacion: Optional[str] = None
    latitud: Optional[float] = None
    longitud: Optional[float] = None
    fuente: Optional[str] = None
    scraped_at: Optional[str] = None

    def __post_init__(self) -> None:
        if self.operacion:
            self.operacion = self.operacion.lower().strip()
        if not self.scraped_at:
            self.scraped_at = datetime.now(timezone.utc).isoformat()

    def calcular_score(self) -> int:
        score = 0
        if self.precio is not None:
            score += 1
        if self.metros is not None:
            score += 1
        if self.direccion:
            score += 1
        if self.imagenes:
            score += 1
        if self.operacion in ALLOWED_OPERACIONES:
            score += 1
        return score

    def to_payload(self) -> Dict[str, Any]:
        return {
            "url": self.url,
            "titulo": self.titulo,
            "precio": self.precio,
            "moneda": self.moneda,
            "direccion": self.direccion,
            "barrio": self.barrio,
            "barrio_normalizado": self.barrio_normalizado,
            "tipo_propiedad": self.tipo_propiedad,
            "descripcion": self.descripcion,
            "dormitorios": self.dormitorios,
            "banos": self.banos,
            "ambientes": self.ambientes,
            "metros": self.metros,
            "imagenes": self.imagenes,
            "ciudad": self.ciudad,
            "operacion": self.operacion,
            "latitud": self.latitud,
            "longitud": self.longitud,
            "fuente": self.fuente,
            "scraped_at": self.scraped_at,
            "calidad_score": self.calcular_score(),
        }

    def is_valid(self) -> bool:
        if not self.url or not self.url.startswith("http"):
            return False
        if not self.titulo or len(self.titulo.strip()) < 3:
            return False
        if not self.direccion and not self.barrio:
            return False
        if self.tipo_propiedad not in ALLOWED_PROPERTY_TYPES:
            return False
        if self.moneda and self.moneda not in ALLOWED_MONEDAS:
            return False
        return True