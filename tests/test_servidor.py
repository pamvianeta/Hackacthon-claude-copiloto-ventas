"""Prueba de punta a punta del WebSocket: simulación de CASO-02 sin IA disponible → repetición → propuesta."""
import pytest
from fastapi.testclient import TestClient

from app import config, extraccion


@pytest.fixture
def cliente(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "prueba.db")
    monkeypatch.setattr(config, "SALIDAS_DIR", tmp_path / "salidas")
    monkeypatch.setattr(config, "SEGUNDOS_POR_LINEA", 0)
    monkeypatch.setattr(config, "GENERAR_PDF", False)

    def sin_ia(*a, **k):
        raise extraccion.ErrorIA("sin crédito (simulado en la prueba)")
    monkeypatch.setattr(extraccion, "extraer", sin_ia)
    from app.main import app
    with TestClient(app) as c:
        yield c


def esperar(ws, condicion, maximo=400):
    vistos = []
    for _ in range(maximo):
        m = ws.receive_json()
        vistos.append(m)
        if condicion(m):
            return m, vistos
    raise AssertionError(f"No llegó el evento esperado. Últimos: {[v['evento'] for v in vistos[-10:]]}")


def test_api_rest(cliente):
    assert len(cliente.get("/api/clientes").json()) == 10
    assert cliente.get("/api/salud").json()["ok"]
    assert cliente.get("/api/aprendizajes").json() == []
    assert cliente.get("/salidas/../.env").status_code == 404


def test_simulacion_cae_a_repeticion_y_entrega_propuesta(cliente):
    with cliente.websocket_connect("/ws") as ws:
        ws.send_json({"tipo": "iniciar", "cliente_id": "CASO-02", "modo": "simulacion"})
        m, _ = esperar(ws, lambda m: m["evento"] == "sesion")
        assert m["datos"]["cliente"]["empresa"] == "Aceros del Valle"
        ws.send_json({"tipo": "simular"})
        _, vistos = esperar(ws, lambda m: m["evento"] == "modo" and m["datos"]["motivo"] == "Fin del guion simulado")
        eventos = {v["evento"] for v in vistos}
        assert {"transcript", "triage", "notes_update", "suggested_question", "glossary", "suggestion",
                "blocked"} <= eventos
        cambio = next(v for v in vistos if v["evento"] == "modo" and v["datos"]["modo"] == "repeticion")
        assert "pregrabadas" in cambio["datos"]["motivo"]
        assert [v for v in vistos if v["evento"] == "transcript"][-1]["datos"]["total"] == 13

        for sku in ("SIM-DC-04", "SIM-DC-07", "SIM-DC-08", "SIM-BK-01", "SIM-BK-03"):
            ws.send_json({"tipo": "feedback", "sku": sku, "correcto": True})
            esperar(ws, lambda m: m["evento"] == "feedback")
        ws.send_json({"tipo": "cerrar"})
        m, _ = esperar(ws, lambda m: m["evento"] == "proposal_ready")
        d = m["datos"]
        assert d["triaje"]["estado"] == "rojo"
        assert d["cotizacion"]["mensual"]["subtotal"] == 21640.0
        assert d["impacto"]["sesiones"] == 1 and d["impacto"]["lineas_a_la_medida"] == 1
        assert d["impacto"]["sugerencias_bloqueadas"] == 1
        # Word: propuesta + brief (porque es rojo), descargables
        assert set(d["archivos"]) == {"propuesta_docx", "brief_docx"}
        for nombre in d["archivos"].values():
            resp = cliente.get(f"/salidas/{nombre}")
            assert resp.status_code == 200 and resp.content[:2] == b"PK"
    apr = cliente.get("/api/aprendizajes").json()
    assert {a["sku"] for a in apr} == {"SIM-DC-04", "SIM-DC-07", "SIM-DC-08", "SIM-BK-01", "SIM-BK-03"}


@pytest.mark.parametrize("caso, confirmar, estado, mensual, archivos", [
    ("CASO-07", ["SIM-BK-01", "SIM-BK-05", "SIM-BK-02"], "verde", 5728.0, {"propuesta_docx"}),
    ("CASO-06", ["SIM-OCI-03", "SIM-OCI-02"], "rojo", 0.0, {"propuesta_docx", "brief_docx"}),
    ("CASO-01", ["SIM-M365-03", "SIM-BK-04", "SIM-BK-02", "SIM-M365-06"], "rojo", 3263.25,
     {"propuesta_docx", "brief_docx"}),
])
def test_repeticion_de_punta_a_punta(cliente, caso, confirmar, estado, mensual, archivos):
    with cliente.websocket_connect("/ws") as ws:
        ws.send_json({"tipo": "iniciar", "cliente_id": caso, "modo": "repeticion"})
        esperar(ws, lambda m: m["evento"] == "sesion")
        ws.send_json({"tipo": "simular"})
        esperar(ws, lambda m: m["evento"] == "modo" and m["datos"]["motivo"] == "Fin del guion simulado")
        for sku in confirmar:
            ws.send_json({"tipo": "feedback", "sku": sku, "correcto": True})
            esperar(ws, lambda m: m["evento"] == "feedback")
        ws.send_json({"tipo": "cerrar"})
        d = esperar(ws, lambda m: m["evento"] == "proposal_ready")[0]["datos"]
        assert d["triaje"]["estado"] == estado
        assert d["cotizacion"]["mensual"]["subtotal"] == mensual
        assert set(d["archivos"]) == archivos


def test_microfono_sin_ia_avisa_error_y_guarda_frases(cliente):
    with cliente.websocket_connect("/ws") as ws:
        ws.send_json({"tipo": "iniciar", "cliente_id": "CASO-01", "modo": "microfono"})
        esperar(ws, lambda m: m["evento"] == "sesion")
        ws.send_json({"tipo": "frase", "hablante": "cliente", "texto": "Somos 25 en la clínica"})
        esperar(ws, lambda m: m["evento"] == "transcript")
        m, _ = esperar(ws, lambda m: m["evento"] == "error")
        assert "IA no está disponible" in m["datos"]["mensaje"]


def test_microfono_automatico_la_ia_etiqueta_quien_habla(cliente, monkeypatch):
    vistas = []

    def ia_falsa(frases, *a, **k):
        vistas.append([f.get("auto") for f in frases])
        return {"productos": [], "hechos": [], "fuera_de_catalogo": [], "notas": [], "preguntas_respondidas": [],
                "glosario": [], "siguiente_pregunta": {"texto": "", "por_que": ""},
                "hablantes": [{"linea": 1, "hablante": "vendedor"}, {"linea": 2, "hablante": "cliente"},
                              {"linea": 99, "hablante": "cliente"}]}  # renglón inexistente: se ignora
    monkeypatch.setattr(extraccion, "extraer", ia_falsa)
    with cliente.websocket_connect("/ws") as ws:
        ws.send_json({"tipo": "iniciar", "cliente_id": "CASO-05", "modo": "microfono"})
        esperar(ws, lambda m: m["evento"] == "sesion")
        ws.send_json({"tipo": "frase", "hablante": "auto", "texto": "¿Cuántos mensajes reciben al día?"})
        ws.send_json({"tipo": "frase", "hablante": "auto", "texto": "Como trescientos WhatsApps diarios"})
        m, vistos = esperar(ws, lambda m: m["evento"] == "speakers" and
                            {c["indice"] for c in m["datos"]["cambios"]} >= {1})
        primera = next(v for v in vistos if v["evento"] == "transcript")
        assert primera["datos"]["frase"]["auto"] is True
        etiquetas = {c["indice"]: c["hablante"] for v in vistos if v["evento"] == "speakers"
                     for c in v["datos"]["cambios"]}
        assert etiquetas == {0: "vendedor", 1: "cliente"}
    assert vistas[0][0] is True  # Claude recibió la frase sin etiqueta


def test_descartar_quita_el_producto_del_triaje(cliente):
    with cliente.websocket_connect("/ws") as ws:
        ws.send_json({"tipo": "iniciar", "cliente_id": "CASO-02", "modo": "repeticion"})
        esperar(ws, lambda m: m["evento"] == "sesion")
        ws.send_json({"tipo": "simular"})
        esperar(ws, lambda m: m["evento"] == "modo" and m["datos"]["motivo"] == "Fin del guion simulado")
        ws.send_json({"tipo": "feedback", "sku": "SIM-DC-07", "correcto": False})
        esperar(ws, lambda m: m["evento"] == "feedback")
        m, _ = esperar(ws, lambda m: m["evento"] == "triage"
                       and "SIM-DC-07" not in m["datos"]["resumen_cotizacion"]["pendientes_arquitecto"])
        assert m["datos"]["estado"] != "rojo" or "ESC-07" in {a["regla"] for a in m["datos"]["reglas_activadas"]}
