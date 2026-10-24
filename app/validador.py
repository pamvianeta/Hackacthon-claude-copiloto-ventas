"""Validador del catálogo.

1) Revisa que el JSON sea coherente (referencias, tipos, precios, paquetes).
2) Coteja el CSV y el .db entregados contra el JSON y reporta diferencias.

Niveles:  ERROR = dato roto (el motor no debe confiar en él)
          AVISO = ambigüedad que resolvemos con un supuesto (ver SUPUESTOS.md)
          INFO  = dato a tener en cuenta

Uso:  py -m app.validador
"""
import csv
import sqlite3
import sys
import unicodedata
from collections import Counter, namedtuple
from pathlib import Path

from app import config
from app.catalogo import leer_json

Hallazgo = namedtuple("Hallazgo", "nivel origen mensaje")

TIPOS = {"estándar", "configurable", "a la medida"}
CONTEOS_ESPERADOS = {"familias": 7, "productos": 45, "paquetes": 7,
                     "condiciones_comerciales": 11, "reglas_escalamiento": 10, "casos_clientes": 10}
LLAVES = {"familias": "id", "productos": "sku", "paquetes": "id",
          "condiciones_comerciales": "concepto", "reglas_escalamiento": "id", "casos_clientes": "id"}
CAMPOS_PRODUCTO = ["sku", "familia", "nombre", "descripcion", "tipo", "segmento", "unidad_cobro",
                   "precio_mensual_mxn", "cargo_unico_mxn", "cantidad_minima", "cantidad_maxima",
                   "plazo_minimo_meses", "nivel_servicio", "tiempo_implementacion", "requiere_alguno_de",
                   "se_recomienda_con", "senal_del_cliente", "preguntas_clave", "cuando_entra_arquitecto"]


def _nfc(s):
    return unicodedata.normalize("NFC", s) if isinstance(s, str) else s


# ---------------------------------------------------------------- 1) JSON
def validar_json(d: dict) -> list[Hallazgo]:
    h = []
    J = "JSON"

    for tabla, esperado in CONTEOS_ESPERADOS.items():
        n = len(d.get(tabla, []))
        if n != esperado:
            h.append(Hallazgo("AVISO", J, f"{tabla}: hay {n} registros, se esperaban {esperado}"))
        llaves = Counter(r[LLAVES[tabla]] for r in d.get(tabla, []))
        for k, c in llaves.items():
            if c > 1:
                h.append(Hallazgo("ERROR", J, f"{tabla}: la llave {k} está repetida {c} veces"))

    P = {p["sku"]: p for p in d["productos"]}
    familias = {f["id"] for f in d["familias"]}

    for p in d["productos"]:
        s = p.get("sku", "?")
        faltan = [c for c in CAMPOS_PRODUCTO if c not in p]
        if faltan:
            h.append(Hallazgo("ERROR", J, f"{s}: faltan campos {faltan}"))
            continue
        if p["familia"] not in familias:
            h.append(Hallazgo("ERROR", J, f"{s}: familia {p['familia']} no existe"))
        if _nfc(p["tipo"]) not in TIPOS:
            h.append(Hallazgo("ERROR", J, f"{s}: tipo inválido «{p['tipo']}»"))
        for campo in ("requiere_alguno_de", "se_recomienda_con"):
            for ref in p[campo]:
                if ref not in P:
                    h.append(Hallazgo("ERROR", J, f"{s}: {campo} apunta a {ref}, que no existe"))
        for campo in ("precio_mensual_mxn", "cargo_unico_mxn"):
            if p[campo] is not None and p[campo] < 0:
                h.append(Hallazgo("ERROR", J, f"{s}: {campo} negativo"))
        mn, mx = p["cantidad_minima"], p["cantidad_maxima"]
        if mn is not None and mx is not None and mn > mx:
            h.append(Hallazgo("ERROR", J, f"{s}: cantidad mínima {mn} mayor que máxima {mx}"))

        sin_precio = p["precio_mensual_mxn"] is None and p["cargo_unico_mxn"] is None
        a_la_medida = _nfc(p["tipo"]) == "a la medida"
        if a_la_medida and not sin_precio:
            h.append(Hallazgo("ERROR", J, f"{s}: es «a la medida» pero tiene precio"))
        if a_la_medida and p["cuando_entra_arquitecto"] != "Siempre":
            h.append(Hallazgo("AVISO", J, f"{s}: es «a la medida» y su umbral de arquitecto no dice «Siempre»"))
        if sin_precio and not a_la_medida:
            h.append(Hallazgo("AVISO", J, f"{s}: sin precio de lista ({p['unidad_cobro']}); "
                                          "se cotiza «por definir» salvo consumo estimado (SUP-08)"))
        if p["precio_mensual_mxn"] is not None and p["plazo_minimo_meses"] is None:
            h.append(Hallazgo("AVISO", J, f"{s}: tiene mensualidad pero no plazo mínimo"))
        if "10% del consumo" in p["descripcion"]:
            h.append(Hallazgo("AVISO", J, f"{s}: el precio real es máx($12,000; 10% del consumo) y solo "
                                          "está en el texto; el cotizador lo programa (SUP-07)"))
        if "adicionales cuestan" in p["descripcion"]:
            h.append(Hallazgo("AVISO", J, f"{s}: cobro por excedente solo en el texto; el cotizador "
                                          "lo programa (SUP-09)"))
        unidad = p["unidad_cobro"]
        if (p["cargo_unico_mxn"] and unidad.startswith("por ") and unidad != "por mes"):
            h.append(Hallazgo("AVISO", J, f"{s}: se cobra «{unidad}» y tiene cargo único de "
                                          f"${p['cargo_unico_mxn']:,.0f}; se cobra una vez por renglón (SUP-01)"))
        if p["familia"] == "M365" and mn is not None and mn >= 300:
            h.append(Hallazgo("AVISO", J, f"{s}: mínimo {mn} usuarios choca con ESC-02 (más de 300 → "
                                          "arquitecto); aplica la regla más estricta (SUP-04)"))
        if not p["cuando_entra_arquitecto"]:
            h.append(Hallazgo("INFO", J, f"{s}: sin umbral de arquitecto; por sí solo no escala (SUP-10)"))

    for q in d["paquetes"]:
        for s in q["productos"]:
            if s not in P:
                h.append(Hallazgo("ERROR", J, f"{q['id']}: incluye {s}, que no existe"))
                continue
            p = P[s]
            req = p["requiere_alguno_de"]
            if req and not set(req) & set(q["productos"]):
                h.append(Hallazgo("AVISO", J, f"{q['id']}: {s} requiere uno de {req} y el paquete no lo "
                                              "incluye; se agrega como «por definir» (SUP-05)"))
            if p["precio_mensual_mxn"] is None:
                h.append(Hallazgo("INFO", J, f"{q['id']}: {s} no tiene mensualidad; el "
                                             f"{q['descuento_pct']}% del paquete no le aplica (SUP-06)"))

    tipos_caso = Counter(c["tipo_de_caso"] for c in d["casos_clientes"])
    h.append(Hallazgo("INFO", J, f"productos por tipo: {dict(Counter(p['tipo'] for p in d['productos']))}; "
                                 f"casos por tipo: {dict(tipos_caso)}"))
    return h


# ---------------------------------------------------------------- 2) CSV y .db
def _norm(v, es_lista=False):
    """Lleva un valor a una forma comparable: vacío -> None, números -> float, listas -> tupla."""
    if es_lista:
        if v is None or v == "":
            return None
        if isinstance(v, str):
            v = v.split("|")
        return tuple(_nfc(str(x).strip()) for x in v) or None
    if v is None or v == "" or v == []:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    v = _nfc(str(v).strip())
    try:
        return float(v.replace(",", "")) if v.replace(",", "").replace(".", "", 1).lstrip("-").isdigit() else v
    except ValueError:
        return v


def _comparar_tabla(origen, tabla, ref: list[dict], otra: list[dict]) -> list[Hallazgo]:
    h = []
    llave = LLAVES[tabla]
    A = {r[llave]: r for r in ref}
    B = {r[llave]: r for r in otra}
    for k in A.keys() - B.keys():
        h.append(Hallazgo("AVISO", origen, f"{tabla}: {k} está en el JSON pero no aquí"))
    for k in B.keys() - A.keys():
        h.append(Hallazgo("AVISO", origen, f"{tabla}: {k} está aquí pero no en el JSON"))
    columnas_json = set(ref[0].keys()) if ref else set()
    columnas_otra = set(otra[0].keys()) if otra else set()
    for c in sorted(columnas_json - columnas_otra):
        h.append(Hallazgo("AVISO", origen, f"{tabla}: falta la columna {c}"))
    for k in sorted(A.keys() & B.keys()):
        for c in sorted(columnas_json & columnas_otra):
            es_lista = isinstance(A[k][c], list)
            va, vb = _norm(A[k][c], es_lista), _norm(B[k][c], es_lista)
            if va != vb:
                h.append(Hallazgo("AVISO", origen, f"{tabla} {k}.{c}: JSON={A[k][c]!r} vs aquí={B[k][c]!r}"))
    return h


def comparar_csv(d: dict, carpeta: Path) -> list[Hallazgo]:
    h = []
    for tabla in LLAVES:
        ruta = carpeta / f"{tabla}.csv"
        if not ruta.exists():
            h.append(Hallazgo("AVISO", "CSV", f"no existe {ruta.name}"))
            continue
        with open(ruta, encoding="utf-8-sig", newline="") as f:
            filas = list(csv.DictReader(f))
        h += _comparar_tabla("CSV", tabla, d[tabla], filas)
    return h


def comparar_db(d: dict, ruta: Path) -> list[Hallazgo]:
    if not ruta.exists():
        return [Hallazgo("AVISO", "DB", f"no existe {ruta.name}")]
    conn = sqlite3.connect(f"file:{ruta}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    h = []
    try:
        for tabla in LLAVES:
            filas = [dict(r) for r in conn.execute(f"SELECT * FROM {tabla}")]
            h += _comparar_tabla("DB", tabla, d[tabla], filas)
        pp = {}
        for paquete, sku in conn.execute("SELECT paquete, sku FROM paquete_productos"):
            pp.setdefault(paquete, set()).add(sku)
        for q in d["paquetes"]:
            if pp.get(q["id"], set()) != set(q["productos"]):
                h.append(Hallazgo("AVISO", "DB", f"paquete_productos {q['id']}: {sorted(pp.get(q['id'], []))} "
                                                 f"vs JSON {q['productos']}"))
        (aviso,) = conn.execute("SELECT texto FROM aviso").fetchone()
        if _nfc(aviso) != _nfc(d["aviso"]):
            h.append(Hallazgo("AVISO", "DB", "el texto de aviso difiere del JSON"))
    finally:
        conn.close()
    return h


def validar_todo() -> list[Hallazgo]:
    d = leer_json()
    carpeta = config.CATALOGO_JSON.parent
    return (validar_json(d) + comparar_csv(d, carpeta / "csv")
            + comparar_db(d, carpeta / "catalogo-simulado.db"))


def main() -> int:
    hallazgos = validar_todo()
    for origen in ("JSON", "CSV", "DB"):
        propios = [x for x in hallazgos if x.origen == origen]
        print(f"\n=== {origen}: {len(propios)} hallazgos ===")
        if not propios:
            print("  ✓ Sin diferencias contra el JSON")
        for nivel in ("ERROR", "AVISO", "INFO"):
            for x in propios:
                if x.nivel == nivel:
                    print(f"  [{nivel}] {x.mensaje}")
    errores = sum(x.nivel == "ERROR" for x in hallazgos)
    print(f"\nResumen: {errores} errores, {sum(x.nivel == 'AVISO' for x in hallazgos)} avisos, "
          f"{sum(x.nivel == 'INFO' for x in hallazgos)} informativos.")
    return 1 if errores else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
