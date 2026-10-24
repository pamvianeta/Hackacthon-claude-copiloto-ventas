"""Chequeo rápido antes de la demo. Uso: py -m app.chequeo_demo   (agrega --ia para probar Claude)"""
import shutil
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

from app import config, db
from app.catalogo import obtener
from app.pipeline import analizar, llamadas
from app.validador import validar_todo

ESPERADO = {"CASO-01": "rojo", "CASO-02": "rojo", "CASO-07": "verde", "CASO-06": "rojo"}


def paso(nombre, fn):
    try:
        detalle = fn()
        print(f"  ✓ {nombre}{f' — {detalle}' if detalle else ''}")
        return True
    except Exception as e:  # el chequeo debe seguir aunque algo falle
        print(f"  ✗ {nombre} — {e}")
        return False


def catalogo():
    hallazgos = validar_todo()
    errores = [h for h in hallazgos if h.nivel == "ERROR"]
    assert not errores, f"{len(errores)} errores en el catálogo"
    difs = [h for h in hallazgos if h.origen != "JSON"]
    return "0 errores; CSV y .db idénticos al JSON" if not difs else f"{len(difs)} diferencias en CSV/.db"


def repeticiones():
    res = []
    for caso, estado in ESPERADO.items():
        r = analizar(llamadas()[caso], "repeticion", caso)
        assert r["triaje"]["estado"] == estado, f"{caso} dio {r['triaje']['estado']}, se esperaba {estado}"
        res.append(f"{caso} {estado}")
    return ", ".join(res)


def documentos():
    from app import documentos as docs
    tmp = Path(tempfile.mkdtemp())
    anterior = config.SALIDAS_DIR
    config.SALIDAS_DIR = tmp
    try:
        r = analizar(llamadas()["CASO-02"], "repeticion", "CASO-02")
        sesion = SimpleNamespace(id=0, cliente=obtener().casos["CASO-02"])
        archivos = docs.generar(sesion, r, {})
        assert "propuesta_docx" in archivos and "brief_docx" in archivos
        return "Word OK" + (" + PDF OK" if archivos.get("propuesta_pdf") else " (PDF no disponible: se entrega solo Word)")
    finally:
        config.SALIDAS_DIR = anterior
        shutil.rmtree(tmp, ignore_errors=True)


def clave():
    if not config.ANTHROPIC_API_KEY:
        raise RuntimeError("no hay ANTHROPIC_API_KEY en .env; la demo funcionará en Repetición")
    return "sí (usa --ia para probar que tenga crédito)"


def ia():
    from app import extraccion
    out = extraccion.extraer(llamadas()["CASO-07"][:4])
    return f"{out['_uso']['modelo']}: {len(out['productos'])} productos sugeridos"


def main() -> int:
    print("Chequeo antes de la demo")
    ok = all([
        paso("Catálogo", catalogo),
        paso("Base SQLite", lambda: f"{db.inicializar()['clientes']} expedientes"),
        paso("Modo Repetición (sin IA)", repeticiones),
        paso("Documentos", documentos),
        paso("Clave de Claude configurada", clave),
    ])
    if "--ia" in sys.argv:
        ok = paso("Llamada real a Claude", ia) and ok
    print("\nListo para la demo." if ok else "\nHay puntos en ✗: revísalos (el modo Repetición sirve de respaldo).")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
