"""Motor determinista: triaje + cotización a partir de requerimientos YA verificados.

Entrada (lo que Claude extrae y el verificador de citas deja pasar):
    {
      "productos": [{"sku": "SIM-BK-01", "cantidad": 2, "cita": "..."}],
      "hechos": {"rto_horas": {"valor": 2, "cita": "..."}},
      "fuera_de_catalogo": [{"cita": "...", "que_pide": "..."}]
    }

Salida: {"triaje": {...}, "cotizacion": {...}, "rechazados": [...], "sugerencias": [...]}
Triaje: rojo (con arquitecto) si CUALQUIER regla se activa; si no, amarillo (faltan datos)
si falta un dato obligatorio; si no, verde (sin arquitecto).
"""
import json
from functools import lru_cache

from app import catalogo as cat_mod
from app import config
from app.cotizador import UNIDADES_CANTIDAD_UNO, cotizar

ETIQUETAS = {"rojo": "Con arquitecto", "amarillo": "Faltan datos", "verde": "Sin arquitecto"}


@lru_cache(maxsize=1)
def cargar_reglas() -> dict:
    with open(config.RAIZ / "reglas" / "reglas.json", encoding="utf-8") as f:
        return json.load(f)


def _cumple(cond: dict, valores: dict) -> bool | None:
    """True / False, o None si el hecho no se conoce."""
    v = valores.get(cond["hecho"])
    if v is None:
        return None
    op, ref = cond["op"], cond["valor"]
    if op == "in":
        return v in ref
    if op == "==":
        return v == ref
    v = float(v)
    return {">": v > ref, "<": v < ref, ">=": v >= ref, "<=": v <= ref}[op]


def _describir(cond: dict, valores: dict) -> str:
    return f"{cond['hecho']} = {valores.get(cond['hecho'])!r} ({cond['op']} {cond['valor']!r})"


def evaluar(req: dict, catalogo=None, reglas=None, hoy=None) -> dict:
    catalogo = catalogo or cat_mod.obtener()
    reglas = reglas or cargar_reglas()
    par = reglas["parametros"]
    hechos_def = reglas["hechos"]

    # ---- 1. Productos: rechazar SKUs inexistentes y unir repetidos
    rechazados, lineas, por_sku = [], [], {}
    for item in req.get("productos", []):
        sku = (item.get("sku") or "").strip().upper()
        if not catalogo.existe(sku):
            rechazados.append({"sku": item.get("sku"), "cita": item.get("cita"),
                               "motivo": "El SKU no existe en el catálogo"})
            continue
        if sku in por_sku:
            previa = por_sku[sku]
            if item.get("cantidad") is not None:
                previa["cantidad"] = max(previa["cantidad"] or 0, item["cantidad"])
            continue
        por_sku[sku] = {"sku": sku, "cantidad": item.get("cantidad"), "cita": item.get("cita"), "origen": "cliente"}
        lineas.append(por_sku[sku])

    hechos = {k: v.get("valor") if isinstance(v, dict) else v for k, v in req.get("hechos", {}).items()}
    citas = {k: v.get("cita") for k, v in req.get("hechos", {}).items() if isinstance(v, dict)}
    faltantes, sugerencias = [], []

    # ---- 2. Dependencias (requiere_alguno_de)
    agregado = True
    while agregado:
        agregado = False
        for ln in list(lineas):
            req_de = catalogo.productos[ln["sku"]]["requiere_alguno_de"]
            if not req_de or set(req_de) & por_sku.keys():
                continue
            if len(req_de) == 1:
                dep = req_de[0]
                nueva = {"sku": dep, "cantidad": None, "cita": None, "origen": f"requerido por {ln['sku']}"}
                lineas.append(nueva)
                por_sku[dep] = nueva
                agregado = True
            elif not any(f.get("dependencia_de") == ln["sku"] for f in faltantes):
                nombres = ", ".join(f"{s} {catalogo.productos[s]['nombre']}" for s in req_de)
                faltantes.append({"tipo": "dependencia", "dependencia_de": ln["sku"], "bloquea": True,
                                  "pregunta": f"{catalogo.productos[ln['sku']]['nombre']} requiere una de estas "
                                              f"licencias: {nombres}. ¿Cuál tienen o cuál contratarían?"})

    # ---- 3. Hechos derivados de las cantidades
    licencias = [ln for ln in lineas if ln["sku"] in par["volumen_m365"]["skus"] and ln["cantidad"]]
    if hechos.get("usuarios_m365") is None and licencias:
        hechos["usuarios_m365"] = max(ln["cantidad"] for ln in licencias)
        citas["usuarios_m365"] = next(ln["cita"] for ln in licencias if ln["cantidad"] == hechos["usuarios_m365"])
    migracion = [ln for ln in lineas if ln["sku"] in ("SIM-AWS-05", "SIM-AZ-04") and ln["cantidad"]]
    if hechos.get("servidores_a_migrar") is None and migracion:
        hechos["servidores_a_migrar"] = sum(ln["cantidad"] for ln in migracion)
        citas["servidores_a_migrar"] = migracion[0]["cita"]

    activadas, pendientes = [], {}

    def activar(regla_id, texto, cita, sku=None, detalle=None):
        if not any(a["regla"] == regla_id and a.get("sku") == sku for a in activadas):
            activadas.append({"regla": regla_id, "texto": texto, "cita": cita, "sku": sku, "detalle": detalle})

    # ---- 4. Umbrales de cada producto (cuando_entra_arquitecto codificado)
    for ln in lineas:
        sku, p = ln["sku"], catalogo.productos[ln["sku"]]
        umb = reglas["productos"].get(sku, {})
        valores = dict(hechos, cantidad=ln["cantidad"])
        if p["tipo"] == "a la medida":
            activar("ESC-01", catalogo.reglas_esc["ESC-01"], ln["cita"], sku, f"{sku} es «a la medida»")
            pendientes[sku] = "Producto a la medida: pendiente de arquitecto de soluciones (ESC-01)"
            continue
        if umb.get("siempre"):
            regla_id = umb.get("esc", f"ARQ-{sku}")
            texto = catalogo.reglas_esc.get(regla_id, umb["texto"])
            activar(regla_id, texto, ln["cita"], sku, umb.get("supuesto"))
            pendientes[sku] = f"Pendiente de arquitecto ({regla_id})"
            continue
        for cond in umb.get("cualquiera", []):
            if _cumple(cond, valores):
                cita = ln["cita"] if cond["hecho"] == "cantidad" else citas.get(cond["hecho"])
                activar(f"ARQ-{sku}", f"{p['nombre']}: {umb['texto']}", cita, sku, _describir(cond, valores))
                pendientes[sku] = f"Pendiente de arquitecto: {umb['texto']}"
                break
        mx = p["cantidad_maxima"]
        if sku not in pendientes and mx is not None and ln["cantidad"] is not None and ln["cantidad"] > mx:
            activar(f"ARQ-{sku}", f"{p['nombre']}: máximo {mx} en el catálogo", ln["cita"], sku,
                    f"cantidad {ln['cantidad']:g} > máximo {mx}")
            pendientes[sku] = f"Pendiente de arquitecto: supera el máximo de {mx}"
        sug = umb.get("sugerir_si")
        if sug and _cumple(sug["condicion"], valores):
            sugerencias.append({"sku": sug["sku"], "en_lugar_de": sku, "motivo": sug["motivo"]})

    # ---- 5. Reglas generales ESC-02..ESC-10
    familias = {}
    for ln in lineas:
        fam = catalogo.productos[ln["sku"]]["familia"]
        if fam in par["familias_infraestructura"]:
            familias.setdefault(fam, ln)
    for esc in reglas["escalamiento"]:
        texto = catalogo.reglas_esc[esc["id"]]
        for cond in esc.get("cualquiera", []):
            if _cumple(cond, hechos):
                activar(esc["id"], texto, citas.get(cond["hecho"]), None, _describir(cond, hechos))
                break
        if esc.get("derivada") == "dos_o_mas_familias_infraestructura" and len(familias) >= 2:
            activar(esc["id"], texto, " / ".join(filter(None, (ln["cita"] for ln in familias.values()))),
                    None, f"Combina {', '.join(sorted(familias))}")

    # ---- 6. Cotización (lo que quedó pendiente de arquitecto no lleva precio)
    plazo = hechos.get("plazo_meses")
    plazo = int(plazo) if plazo in (12, 24, 36) else par["plazo_por_defecto_meses"]
    cot = cotizar(lineas, hechos, plazo, pendientes, catalogo, reglas, hoy)
    if cot["mensual"]["subtotal"] > par["presupuesto_max_mensual_mxn"]:
        activar("ESC-09", catalogo.reglas_esc["ESC-09"], None, None,
                f"La mensualidad cotizada (${cot['mensual']['subtotal']:,.2f}) supera $250,000")

    # ---- 7. Datos que faltan (preguntas pendientes)
    for ln in lineas:
        sku, p = ln["sku"], catalogo.productos[ln["sku"]]
        if sku in pendientes:
            continue
        if (ln["cantidad"] is None and p["unidad_cobro"] not in UNIDADES_CANTIDAD_UNO
                and sku not in par["consumo"]["skus"]):
            faltantes.append({"tipo": "cantidad", "sku": sku, "bloquea": True,
                              "pregunta": p["preguntas_clave"][0] if p["preguntas_clave"] else f"¿Cuántos ({p['unidad_cobro']})?"})
        for h in reglas["productos"].get(sku, {}).get("requiere_saber", []):
            if hechos.get(h) is None and not any(f.get("hecho") == h for f in faltantes):
                faltantes.append({"tipo": "hecho", "hecho": h, "sku": sku, "bloquea": True,
                                  "pregunta": hechos_def[h]["pregunta"]})
    if not lineas:
        faltantes.append({"tipo": "necesidad", "bloquea": True,
                          "pregunta": "¿Qué problema de negocio quieren resolver primero?"})
    if hechos.get("plazo_meses") is None:
        faltantes.append({"tipo": "hecho", "hecho": "plazo_meses", "bloquea": False,
                          "pregunta": hechos_def["plazo_meses"]["pregunta"]})

    # Recomendaciones del catálogo que aún no están
    for ln in lineas:
        for s in catalogo.productos[ln["sku"]]["se_recomienda_con"]:
            if s not in por_sku and not any(x["sku"] == s for x in sugerencias):
                sugerencias.append({"sku": s, "junto_con": ln["sku"],
                                    "motivo": f"El catálogo lo recomienda con {ln['sku']}"})

    if activadas:
        estado = "rojo"
    elif any(f["bloquea"] for f in faltantes):
        estado = "amarillo"
    else:
        estado = "verde"

    renglones = cot["renglones"]
    return {
        "triaje": {
            "estado": estado,
            "etiqueta": ETIQUETAS[estado],
            "reglas_activadas": activadas,
            "faltantes": faltantes,
            "fuera_de_catalogo": req.get("fuera_de_catalogo", []),
            "lineas_estandar": sum(r["estado"] != "pendiente de arquitecto" for r in renglones),
            "lineas_a_la_medida": sum(r["estado"] == "pendiente de arquitecto" for r in renglones),
        },
        "cotizacion": cot,
        "rechazados": rechazados,
        "sugerencias": sugerencias,
        "hechos_usados": hechos,
    }
