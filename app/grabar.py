"""Regraba el modo Repetición con respuestas REALES de Claude (necesita clave con crédito).

Uso:  py -m app.grabar CASO-02
Reproduce el guion y guarda la extracción de Claude en los mismos puntos de la grabación actual.
"""
import json
import sys

from app import extraccion
from app.catalogo import obtener
from app.pipeline import DIR_GUIONES, llamadas


def main(caso: str) -> int:
    guion = llamadas().get(caso)
    if not guion:
        print(f"Casos con guion: {', '.join(llamadas())}")
        return 1
    ruta = DIR_GUIONES / "repeticion" / f"{caso}.json"
    puntos = [len(guion) // 2, len(guion)]
    if ruta.exists():
        with open(ruta, encoding="utf-8") as f:
            puntos = [p["tras_frases"] for p in json.load(f)["pasos"]]
    cliente = obtener().casos.get(caso)
    pasos = []
    for n in puntos:
        print(f"Claude analiza las primeras {n} frases…")
        extr = extraccion.extraer(guion[:n], cliente, [], final=(n == len(guion)))
        uso = extr.pop("_uso")
        print(f"  {len(extr['productos'])} productos, {len(extr['hechos'])} hechos · {uso}")
        pasos.append({"tras_frases": n, "extraccion": extr})
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump({"_nota": f"Modo REPETICIÓN: respuestas REALES de Claude grabadas con py -m app.grabar {caso}.",
                   "pasos": pasos}, f, ensure_ascii=False, indent=1)
    print(f"✓ Grabado en {ruta}")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else ""))
    except extraccion.ErrorIA as e:
        print(f"✗ {e}")
        sys.exit(1)
