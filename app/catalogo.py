"""Acceso al catálogo simulado. El JSON es la única fuente de verdad."""
import json
from functools import lru_cache
from pathlib import Path

from app import config


class Catalogo:
    def __init__(self, datos: dict):
        self.datos = datos
        self.aviso = datos["aviso"]
        self.familias = {f["id"]: f for f in datos["familias"]}
        self.productos = {p["sku"]: p for p in datos["productos"]}
        self.paquetes = {q["id"]: q for q in datos["paquetes"]}
        self.condiciones = {c["concepto"]: c["regla"] for c in datos["condiciones_comerciales"]}
        self.reglas_esc = {r["id"]: r["cuando_entra_un_arquitecto"] for r in datos["reglas_escalamiento"]}
        self.casos = {c["id"]: c for c in datos["casos_clientes"]}

    def existe(self, sku: str) -> bool:
        return sku in self.productos


def leer_json(ruta: Path | None = None) -> dict:
    with open(ruta or config.CATALOGO_JSON, encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def obtener() -> Catalogo:
    return Catalogo(leer_json())
