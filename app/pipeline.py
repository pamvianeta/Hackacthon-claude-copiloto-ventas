"""Una pasada completa: transcripción → extracción (Claude o grabación) → verificación de citas → motor.

Modos:
  microfono / simulacion → Claude (modelo rápido; el fuerte al cerrar la sesión)
  repeticion             → respuestas pregrabadas en guiones/repeticion/<caso>.json (sin IA, sin internet)
"""
import json
from functools import lru_cache

from app import catalogo as cat_mod
from app import config, extraccion
from app.motor import cargar_reglas, evaluar
from app.verificador import verificar

DIR_GUIONES = config.RAIZ / "guiones"


@lru_cache(maxsize=1)
def llamadas() -> dict:
    with open(DIR_GUIONES / "llamadas.json", encoding="utf-8") as f:
        return {k: v for k, v in json.load(f).items() if not k.startswith("_")}


def extraccion_grabada(caso: str, n_frases: int) -> dict:
    ruta = DIR_GUIONES / "repeticion" / f"{caso}.json"
    if not ruta.exists():
        raise extraccion.ErrorIA(f"No hay grabación para {caso}")
    with open(ruta, encoding="utf-8") as f:
        pasos = json.load(f)["pasos"]
    previos = [p for p in pasos if p["tras_frases"] <= n_frases]
    return previos[-1]["extraccion"] if previos else {}


def analizar(frases: list[dict], modo: str, caso: str | None = None, cliente: dict | None = None,
             aprendizajes: list[dict] | None = None, final: bool = False,
             descartados: set | None = None, solo_confirmados: set | None = None,
             extraccion_previa: dict | None = None) -> dict:
    """descartados: SKUs que el vendedor marcó ✗. solo_confirmados: para la propuesta, solo los ✓.
    extraccion_previa: reutiliza la última extracción (p. ej. tras un ✓/✗) sin volver a llamar a Claude."""
    catalogo, reglas = cat_mod.obtener(), cargar_reglas()
    if extraccion_previa is not None:
        extr = extraccion_previa
    elif modo == "repeticion":
        extr = extraccion_grabada(caso, len(frases))
    else:
        extr = extraccion.extraer(frases, cliente, aprendizajes, final=final)

    ver = verificar(extr, frases, catalogo, reglas)
    req = ver["requerimiento"]
    sugeridos = req["productos"]
    if descartados:
        req["productos"] = [p for p in req["productos"] if p["sku"] not in descartados]
    if solo_confirmados is not None:
        req["productos"] = [p for p in req["productos"] if p["sku"] in solo_confirmados]
    res = evaluar(req)

    faltantes = res["triaje"]["faltantes"]
    primera = next((f for f in faltantes if f["bloquea"]), faltantes[0] if faltantes else None)
    if primera:
        siguiente = {"texto": primera["pregunta"], "por_que": "Dato necesario para cerrar el triaje y la cotización",
                     "fuente": "catálogo"}
    elif ver["siguiente_pregunta_ia"]:
        siguiente = dict(ver["siguiente_pregunta_ia"], fuente="IA")
    else:
        siguiente = None

    # Cobertura de preguntas clave de los productos detectados
    claves = {(p["sku"], q) for p in sugeridos for q in catalogo.productos[p["sku"]]["preguntas_clave"]}
    respondidas = {(r["sku"], r["pregunta"]) for r in ver["preguntas_respondidas"]} & claves

    return {
        "modo": modo,
        "_extraccion": extr,
        "uso_ia": extr.get("_uso"),
        "sugerencias_producto": [dict(p, nombre=catalogo.productos[p["sku"]]["nombre"],
                                      tipo=catalogo.productos[p["sku"]]["tipo"]) for p in sugeridos],
        "notas": ver["notas"],
        "glosario": ver["glosario"],
        "bloqueados": ver["bloqueados"],
        "siguiente_pregunta": siguiente,
        "cobertura": {"respondidas": len(respondidas), "total": len(claves),
                      "pct": round(100 * len(respondidas) / len(claves)) if claves else 0},
        **res,
    }
