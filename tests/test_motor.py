"""Pruebas del motor de triaje y cotizador. Los montos esperados están calculados a mano desde el catálogo."""
from datetime import date

import pytest

from app.catalogo import obtener
from app.motor import cargar_reglas, evaluar

CAT = obtener()
REGLAS = cargar_reglas()
HOY = date(2026, 10, 24)


def ev(productos=(), hechos=None, fuera=()):
    req = {"productos": [dict(zip(("sku", "cantidad", "cita"), p)) for p in productos],
           "hechos": {k: {"valor": v, "cita": f"cita de {k}"} for k, v in (hechos or {}).items()},
           "fuera_de_catalogo": list(fuera)}
    return evaluar(req, hoy=HOY)


def reglas_de(res):
    return {a["regla"] for a in res["triaje"]["reglas_activadas"]}


def renglon(res, sku):
    return next(r for r in res["cotizacion"]["renglones"] if r["sku"] == sku)


# ------------------------------------------------------------- 3 casos del reto
def test_caso07_estandar_contadores():
    """SAT pide 5 años: no es regulación de ESC-04 → sin arquitecto."""
    res = ev([("SIM-BK-01", 2, "son como 2 TB de archivos de clientes"),
              ("SIM-BK-05", 2, "el SAT nos pide guardarlos 5 años"),
              ("SIM-BK-02", 12, "los 12 usamos Microsoft 365")],
             {"regulacion": "otra"})
    t, c = res["triaje"], res["cotizacion"]
    assert t["estado"] == "verde" and t["etiqueta"] == "Sin arquitecto"
    assert [f for f in t["faltantes"] if f["bloquea"]] == []
    # 2×1,850 + 2×600 + 12×69 = 5,728 ; cargo único BK-01 una vez (SUP-01)
    assert c["mensual"] == {"subtotal": 5728.0, "iva": 916.48, "total": 6644.48}
    assert c["cargos_unicos"]["subtotal"] == 2500.0
    assert "SUP-01" in renglon(res, "SIM-BK-01")["supuestos"]
    assert c["vigencia_hasta"] == "2026-11-23"
    assert all(r["fuente"].startswith("catalogo-simulado.json") for r in c["renglones"])


def test_caso02_mixto_aceros():
    """RTO de 2 h activa ESC-07 y el umbral de DRaaS; lo demás se cotiza como estándar."""
    res = ev([("SIM-DC-04", 1, "nuestro ERP corre en dos servidores"),
              ("SIM-DC-07", 2, "no podemos estar más de dos horas sin sistema"),
              ("SIM-BK-01", 2, "respaldamos unos 2 TB"),
              ("SIM-DC-08", 1, "las tres sucursales se conectan al ERP")],
             {"rto_horas": 2, "vcpu_total": 24, "sitios": 3, "plazo_meses": 12})
    t, c = res["triaje"], res["cotizacion"]
    assert t["estado"] == "rojo"
    assert {"ESC-07", "ARQ-SIM-DC-07"} <= reglas_de(res)
    assert all(a["cita"] for a in t["reglas_activadas"])
    assert renglon(res, "SIM-DC-07")["estado"] == "pendiente de arquitecto"
    assert t["lineas_estandar"] == 3 and t["lineas_a_la_medida"] == 1
    # PAQ-04 no aplica porque DRaaS quedó pendiente: 12,900 + 3,700 + 4,200
    assert c["paquetes_aplicados"] == []
    assert c["mensual"]["subtotal"] == 20800.0
    assert c["cargos_unicos"]["subtotal"] == 3500 + 2500 + 6000


def test_caso06_a_la_medida_oracle():
    res = ev([("SIM-OCI-03", 1, "una base de datos Oracle de 6 TB"),
              ("SIM-OCI-02", 1, "una base de datos Oracle de 6 TB")],
             {"oracle_tb": 6})
    assert res["triaje"]["estado"] == "rojo"
    assert {"ESC-08", "ARQ-SIM-OCI-03", "ARQ-SIM-OCI-02"} <= reglas_de(res)
    assert res["cotizacion"]["mensual"]["subtotal"] == 0
    assert set(res["cotizacion"]["renglones_pendientes_arquitecto"]) == {"SIM-OCI-03", "SIM-OCI-02"}


def test_caso01_con_solo_el_primer_mensaje_faltan_datos():
    """Clínica: se detecta M365 Premium pero falta cuántos usuarios y si guardan datos de salud (SUP-13)."""
    res = ev([("SIM-M365-03", None, "una recepcionista abrió un archivo y se cifraron las computadoras")])
    t = res["triaje"]
    assert t["estado"] == "amarillo"
    preguntas = " ".join(f["pregunta"] for f in t["faltantes"])
    assert "usuarios" in preguntas and "salud" in preguntas


def test_caso01_si_guardan_expedientes_pasa_a_arquitecto():
    res = ev([("SIM-M365-03", 25, "somos 25")], {"regulacion": "salud"})
    assert res["triaje"]["estado"] == "rojo"
    assert "ESC-04" in reglas_de(res)


# ------------------------------------------------------------- anti-alucinación
def test_sku_inventado_se_rechaza():
    res = ev([("SIM-XX-99", 3, "algo"), ("SIM-BK-02", 10, "diez usuarios")])
    assert res["rechazados"][0]["sku"] == "SIM-XX-99"
    assert [r["sku"] for r in res["cotizacion"]["renglones"]] == ["SIM-BK-02"]


def test_fuera_de_catalogo_no_se_cotiza():
    fuera = [{"cita": "queremos cámaras de seguridad", "que_pide": "videovigilancia"}]
    res = ev([("SIM-BK-02", 10, "diez usuarios")], fuera=fuera)
    assert res["triaje"]["fuera_de_catalogo"] == fuera
    assert len(res["cotizacion"]["renglones"]) == 1


def test_sin_productos_faltan_datos():
    assert ev()["triaje"]["estado"] == "amarillo"


def test_parametros_salen_del_texto_del_catalogo():
    """Cada número de reglas.json → parametros debe aparecer escrito en el catálogo."""
    p = REGLAS["parametros"]
    cond = " ".join(CAT.condiciones.values())
    assert f"{p['iva_pct']}%" in cond and f"{p['vigencia_dias']} días" in cond
    assert f"{p['descuento_plazo_pct']['24']}%" in CAT.condiciones["Plazo de 24 meses"]
    assert f"{p['descuento_plazo_pct']['36']}%" in CAT.condiciones["Plazo de 36 meses"]
    assert f"{p['volumen_m365']['pct']}%" in cond and f"{p['volumen_m365']['desde_usuarios']} usuarios" in cond
    assert f"{p['descuento_max_sin_autorizacion_pct']}%" in CAT.condiciones["Descuento máximo del vendedor"]
    for sku in p["soporte_247"]["skus"]:
        d = CAT.productos[sku]["descripcion"]
        assert f"{p['soporte_247']['pct_consumo']}% del consumo" in d and "$12,000" in d
    ia = CAT.productos[p["conversaciones_ia"]["sku"]]["descripcion"]
    assert "2,000 conversaciones" in ia and f"${p['conversaciones_ia']['precio_adicional_mxn']} cada una" in ia
    assert "$250,000" in CAT.reglas_esc["ESC-09"]


def test_reglas_json_cubre_los_45_productos_con_su_texto_original():
    assert set(REGLAS["productos"]) == set(CAT.productos)
    for sku, umb in REGLAS["productos"].items():
        assert umb["texto"] == CAT.productos[sku]["cuando_entra_arquitecto"], sku
    usados = {c["hecho"] for u in REGLAS["productos"].values() for c in u.get("cualquiera", [])}
    usados |= {c["hecho"] for e in REGLAS["escalamiento"] for c in e.get("cualquiera", [])}
    usados |= {h for u in REGLAS["productos"].values() for h in u.get("requiere_saber", [])}
    assert usados - {"cantidad"} <= set(REGLAS["hechos"])
    assert [e["id"] for e in REGLAS["escalamiento"]] == [f"ESC-{i:02d}" for i in range(1, 11)]


# ------------------------------------------------------------- reglas comerciales
def test_paquete_plazo_y_volumen_se_suman_y_piden_gerente():
    res = ev([("SIM-M365-03", 100, "somos 100"), ("SIM-BK-02", 100, "los 100"), ("SIM-M365-07", 100, "soporte")],
             {"plazo_meses": 36, "regulacion": "ninguna"})
    r = renglon(res, "SIM-M365-03")
    assert r["descuento_pct"] == 10 + 8 + 3  # plazo + PAQ-01 + volumen
    assert r["mensual_neto"] == round(425 * 100 * 0.79, 2)
    assert renglon(res, "SIM-M365-07")["descuento_pct"] == 18  # soporte no es licencia (SUP-02)
    assert res["cotizacion"]["requiere_autorizacion_gerente"]
    assert res["cotizacion"]["paquetes_aplicados"][0]["id"] == "PAQ-01"


def test_plazo_24_no_descuenta_cargos_unicos():
    res = ev([("SIM-DC-01", 1, "un servidor")], {"kva_total": 0.8, "plazo_meses": 24})
    r = renglon(res, "SIM-DC-01")
    assert r["mensual_neto"] == 7900 * 0.95 and r["cargo_unico"] == 5000
    assert not res["cotizacion"]["requiere_autorizacion_gerente"]


@pytest.mark.parametrize("consumo, esperado", [(None, 12000), (80000, 12000), (200000, 20000)])
def test_soporte_247_maximo_entre_minimo_y_10pct(consumo, esperado):
    hechos = {"consumo_aws_mensual": consumo} if consumo else {}
    res = ev([("SIM-AWS-03", 1, "nadie cuida la nube de noche")], hechos)
    assert renglon(res, "SIM-AWS-03")["mensual_neto"] == esperado
    # La dependencia de consumo se agrega sola y queda por definir si no hay monto (SUP-05/SUP-08)
    consumo_ln = renglon(res, "SIM-AWS-01")
    assert consumo_ln["origen"] == "requerido por SIM-AWS-03"
    assert consumo_ln["estado"] == ("por definir" if consumo is None else "cotizado")


def test_ia01_conversaciones_adicionales():
    res = ev([("SIM-IA-01", 1, "cientos de WhatsApps")],
             {"conversaciones_mes": 3000, "integracion_sistemas_internos": False})
    assert renglon(res, "SIM-IA-01")["mensual_neto"] == 8500 + 1000 * 4
    assert res["triaje"]["estado"] == "verde"


def test_ia01_con_sistema_de_reservas_escala():
    res = ev([("SIM-IA-01", 1, "para reservar")], {"integracion_sistemas_internos": True})
    assert {"ESC-05", "ARQ-SIM-IA-01"} <= reglas_de(res)


def test_e3_siempre_va_a_arquitecto_por_esc02():
    res = ev([("SIM-M365-04", 400, "somos 400")])
    assert "ESC-02" in reglas_de(res)
    assert renglon(res, "SIM-M365-04")["estado"] == "pendiente de arquitecto"


def test_mas_de_300_usuarios_business_activa_esc02():
    res = ev([("SIM-M365-03", 350, "somos 350")], {"regulacion": "ninguna"})
    assert {"ESC-02", "ARQ-SIM-M365-03"} <= reglas_de(res)


def test_a_la_medida_activa_esc01():
    res = ev([("SIM-IA-05", None, "que la IA capture pedidos en el ERP")])
    assert "ESC-01" in reglas_de(res)


def test_dependencia_unica_se_agrega_y_pide_cantidad():
    res = ev([("SIM-BK-03", 3, "tres servidores")])
    assert renglon(res, "SIM-BK-01")["estado"] == "por definir"
    assert res["triaje"]["estado"] == "amarillo"


def test_dependencia_con_varias_opciones_se_pregunta():
    res = ev([("SIM-M365-05", 10, "queremos Copilot")])
    assert any(f["tipo"] == "dependencia" for f in res["triaje"]["faltantes"])
    assert res["triaje"]["estado"] == "amarillo"


def test_cantidad_debajo_del_minimo_cotiza_el_minimo():
    res = ev([("SIM-M365-06", 3, "tres buzones")])
    r = renglon(res, "SIM-M365-06")
    assert r["cantidad"] == 5 and r["cargo_unico"] == 5 * 350


def test_nube_y_data_center_es_hibrida_esc06():
    res = ev([("SIM-DC-01", 1, "el servidor del cuarto"), ("SIM-AZ-01", None, "ya usamos Azure")],
             {"kva_total": 1})
    assert "ESC-06" in reglas_de(res)


def test_mensualidad_mayor_a_250mil_activa_esc09():
    # 100 TB × 1,850 + 3 racks × 21,500 + 4,200 = 253,700 > 250,000, sin que ningún producto escale solo
    hechos = {"kva_por_rack": 4, "sitios": 1}
    res = ev([("SIM-BK-01", 100, "100 TB"), ("SIM-DC-02", 3, "tres racks"), ("SIM-DC-08", 1, "enlace")], hechos)
    assert reglas_de(res) == {"ESC-09"}
    assert res["cotizacion"]["mensual"]["subtotal"] == 253700
    res2 = ev([("SIM-BK-01", 100, "100 TB"), ("SIM-DC-02", 3, "tres racks")], hechos)  # 249,500
    assert res2["triaje"]["estado"] == "verde"
