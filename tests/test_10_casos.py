"""Los 10 casos del reto contra el motor (sin IA).

Los requerimientos simulan lo que el cliente diría al contestar la «información que falta» de cada caso.
Criterio: estándar → verde (salvo SUP-13), mixto → rojo con renglones estándar ya cotizados,
a la medida → rojo. Montos calculados a mano desde el catálogo.
"""
from datetime import date

import pytest

from app.catalogo import obtener
from app.motor import evaluar

HOY = date(2026, 10, 24)


def ev(productos, hechos=None):
    return evaluar({"productos": [{"sku": s, "cantidad": q, "cita": f"cita {s}"} for s, q in productos],
                    "hechos": {k: {"valor": v, "cita": f"cita {k}"} for k, v in (hechos or {}).items()}}, hoy=HOY)


def reglas(res):
    return {a["regla"] for a in res["triaje"]["reglas_activadas"]}


CASOS = {
    # id: (productos, hechos, estado esperado, reglas que deben estar, mensual esperado o None)
    "CASO-01": ([("SIM-M365-03", 25), ("SIM-BK-02", 25), ("SIM-M365-07", 25)],
                {"regulacion": "ninguna", "plazo_meses": 12}, "verde", set(),
                (425 + 69 + 45) * 25 * 0.92),  # PAQ-01 completo → 8%
    "CASO-02": ([("SIM-DC-04", 1), ("SIM-DC-07", 2), ("SIM-BK-01", 2), ("SIM-DC-08", 1)],
                {"rto_horas": 2, "vcpu_total": 24, "sitios": 3}, "rojo", {"ESC-07"}, 20800),
    "CASO-03": ([("SIM-AWS-04", 1), ("SIM-AWS-01", None), ("SIM-AWS-03", 1)],
                {"consumo_aws_mensual": 120000, "regulacion": "CNBV"}, "rojo", {"ESC-04"},
                120000 + 12000),  # consumo estimado + soporte = máx(12,000; 10% de 120,000)
    "CASO-04": ([("SIM-M365-01", 1200), ("SIM-AZ-02", 1), ("SIM-AZ-03", 60)],
                {"requiere_gpu": True}, "rojo", {"ESC-02", "ARQ-SIM-M365-01", "ARQ-SIM-AZ-03"}, None),
    "CASO-05": ([("SIM-IA-01", 1), ("SIM-IA-04", 1)],
                {"conversaciones_mes": 9000, "integracion_sistemas_internos": False}, "verde", set(),
                8500 * 0.92 + 7000 * 4),  # PAQ-07 sobre la base; excedente sin descuento
    "CASO-06": ([("SIM-OCI-03", 1), ("SIM-OCI-02", 1)], {"oracle_tb": 6}, "rojo", {"ESC-08"}, 0),
    "CASO-07": ([("SIM-BK-01", 2), ("SIM-BK-05", 2), ("SIM-BK-02", 12)], {"regulacion": "otra"}, "verde",
                set(), 5728),
    "CASO-08": ([("SIM-DC-07", 30), ("SIM-AZ-01", None), ("SIM-IA-02", 1)],
                {"nube_hibrida": True, "rto_horas": 4, "usuarios_agente_conocimiento": 2500,
                 "permisos_por_area": True}, "rojo", {"ESC-06", "ARQ-SIM-DC-07", "ARQ-SIM-IA-02"}, None),
    "CASO-09": ([("SIM-M365-02", 30), ("SIM-M365-05", 10)], {"datos_sin_permisos_ordenados": False},
                "verde", set(), 245 * 30 + 590 * 10),
    "CASO-10": ([("SIM-DC-09", None), ("SIM-DC-02", 1)], {"regulacion": "salud", "kva_por_rack": 3},
                "rojo", {"ESC-01", "ESC-04"}, None),
}


@pytest.mark.parametrize("caso", sorted(CASOS))
def test_caso(caso):
    productos, hechos, estado, esperadas, mensual = CASOS[caso]
    res = ev(productos, hechos)
    t = res["triaje"]
    assert t["estado"] == estado, (caso, t["reglas_activadas"], t["faltantes"])
    assert esperadas <= reglas(res)
    assert all(a["cita"] or a["detalle"] for a in t["reglas_activadas"])  # toda regla trae su respaldo
    if mensual is not None:
        assert res["cotizacion"]["mensual"]["subtotal"] == pytest.approx(mensual, abs=0.01)
    tipo = obtener().casos[caso]["tipo_de_caso"]
    if tipo == "mixto":
        assert t["lineas_estandar"] >= 1 and t["lineas_a_la_medida"] >= 0 and estado == "rojo"
    if tipo == "a la medida":
        assert estado == "rojo"


def test_los_10_casos_estan_cubiertos():
    assert set(CASOS) == set(obtener().casos)


def test_caso05_si_las_reservas_estan_en_un_sistema_escala():
    res = ev([("SIM-IA-01", 1)], {"integracion_sistemas_internos": True})
    assert "ESC-05" in reglas(res)


def test_caso09_copilot_sin_licencia_pregunta_cual_tienen():
    res = ev([("SIM-M365-05", 10)])
    assert res["triaje"]["estado"] == "amarillo"
    assert any(f["tipo"] == "dependencia" for f in res["triaje"]["faltantes"])
