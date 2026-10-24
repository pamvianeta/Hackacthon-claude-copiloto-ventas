"""Pruebas de verificación de citas, esquema, modo repetición y de la llamada a Claude (simulada)."""
import json
from types import SimpleNamespace

from app import extraccion
from app.catalogo import obtener
from app.motor import cargar_reglas
from app.pipeline import analizar, llamadas
from app.verificador import cita_valida, normalizar, puntaje_cita, verificar

CAT, REGLAS = obtener(), cargar_reglas()
T = normalizar("Cliente: No podemos estar más de DOS horas sin sistema, ¡cada hora parada nos cuesta mucho! "
               "Son unos 2 TB.")


# ------------------------------------------------------------- verificador
def test_cita_exacta_sin_acentos_ni_signos_pasa():
    assert cita_valida("no podemos estar mas de dos horas sin sistema", T)
    assert cita_valida("«No podemos estar más de dos horas sin sistema»", T)


def test_cita_con_una_palabra_cambiada_de_cinco_pasa_80pct():
    assert puntaje_cita("podemos estar horas sin sistema parada", T) >= 0.8


def test_cita_inventada_o_parafraseada_se_bloquea():
    assert not cita_valida("queremos mudar todo el site sin detener la planta", T)
    assert not cita_valida("el negocio no aguanta caídas largas", T)


def test_numeros_cuentan_y_deben_coincidir():
    assert cita_valida("son unos 2 TB", T)
    assert not cita_valida("son unos 20 TB", T)


def test_cita_vacia_se_bloquea():
    assert not cita_valida("", T)


def test_verificar_separa_y_explica_bloqueos():
    frases = [{"hablante": "cliente", "texto": "Somos 25 personas y usamos Gmail."}]
    extr = {
        "productos": [{"sku": "SIM-M365-01", "cantidad": 25, "cita": "Somos 25 personas"},
                      {"sku": "SIM-M365-03", "cantidad": 25, "cita": "nos preocupa mucho la seguridad"},
                      {"sku": "SIM-NADA-01", "cantidad": 1, "cita": "Somos 25 personas"}],
        "hechos": [{"nombre": "usuarios_m365", "valor": "25", "cita": "Somos 25 personas"},
                   {"nombre": "rto_horas", "valor": "muy poco", "cita": "Somos 25 personas"},
                   {"nombre": "inventado", "valor": "1", "cita": "Somos 25 personas"}],
        "fuera_de_catalogo": [{"cita": "queremos cámaras", "que_pide": "cámaras"}],
        "notas": [{"tema": "Plazo y presupuesto", "resumen": "falta", "estado": "faltante", "cita": ""}],
        "preguntas_respondidas": [{"sku": "SIM-M365-01", "pregunta": "¿Cuántos usuarios?", "cita": "Somos 25 personas"},
                                  {"sku": "SIM-M365-01", "pregunta": "¿Les gusta el café?", "cita": "Somos 25 personas"}],
    }
    v = verificar(extr, frases, CAT, REGLAS)
    assert [p["sku"] for p in v["requerimiento"]["productos"]] == ["SIM-M365-01"]
    assert v["requerimiento"]["hechos"] == {"usuarios_m365": {"valor": 25, "cita": "Somos 25 personas"}}
    assert len(v["notas"]) == 1 and len(v["preguntas_respondidas"]) == 1
    motivos = [b["motivo"] for b in v["bloqueados"]]
    assert len(motivos) == 6  # 2 productos + 2 hechos + 1 fuera de catálogo + 1 pregunta
    assert "El SKU no existe en el catálogo" in motivos
    assert motivos.count("La cita no aparece en la transcripción") == 2


# ------------------------------------------------------------- esquema y prompt
def test_esquema_estricto_y_sin_precios_en_el_prompt():
    esq = extraccion.esquema(CAT, REGLAS)

    def revisar(nodo):
        if isinstance(nodo, dict):
            if nodo.get("type") == "object":
                assert nodo["additionalProperties"] is False
                assert set(nodo["required"]) == set(nodo["properties"])
            for v in nodo.values():
                revisar(v)
        elif isinstance(nodo, list):
            for v in nodo:
                revisar(v)
    revisar(esq)
    assert len(esq["properties"]["productos"]["items"]["properties"]["sku"]["enum"]) == 45
    texto = extraccion.sistema(CAT, REGLAS)[0]["text"]
    assert "precio_mensual_mxn" not in texto and "cargo_unico_mxn" not in texto
    assert "7900" not in texto  # precio de SIM-DC-01


def test_prompt_marca_las_frases_sin_hablante():
    texto = extraccion.mensaje_usuario([{"hablante": "cliente", "texto": "hola", "auto": True},
                                        {"hablante": "vendedor", "texto": "buenas"}], None, [])
    assert "[1] [¿?] hola" in texto and "[2] [Vendedor] buenas" in texto
    assert "hablantes" in extraccion.esquema(CAT, REGLAS)["properties"]


def test_extraer_con_api_simulada(monkeypatch):
    respuesta = {"productos": [{"sku": "SIM-BK-01", "cantidad": 2, "cita": "son unos 2 TB", "dile_al_cliente": "x"}],
                 "hechos": [], "fuera_de_catalogo": [], "notas": [], "preguntas_respondidas": [], "glosario": [],
                 "siguiente_pregunta": {"texto": "¿?", "por_que": "x"}}
    llamadas_api = []

    class Falsa:
        class messages:
            @staticmethod
            def create(**kw):
                llamadas_api.append(kw)
                return SimpleNamespace(
                    stop_reason="end_turn", content=[SimpleNamespace(type="text", text=json.dumps(respuesta))],
                    usage=SimpleNamespace(input_tokens=10, output_tokens=5, cache_read_input_tokens=0))

    monkeypatch.setattr(extraccion, "_api", lambda: Falsa)
    out = extraccion.extraer([{"hablante": "cliente", "texto": "son unos 2 TB"}])
    assert out["productos"][0]["sku"] == "SIM-BK-01"
    kw = llamadas_api[0]
    assert kw["model"] == "claude-haiku-5-5"
    assert kw["output_config"]["format"]["type"] == "json_schema"
    assert kw["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert "temperature" not in kw


# ------------------------------------------------------------- modo repetición de punta a punta
def test_repeticion_caso02_mixto_de_punta_a_punta():
    guion = llamadas()["CASO-02"]
    r = analizar(guion, "repeticion", "CASO-02")
    assert r["triaje"]["estado"] == "rojo"
    assert {"ESC-07", "ARQ-SIM-DC-07"} <= {a["regla"] for a in r["triaje"]["reglas_activadas"]}
    # La cita inventada de SIM-DC-09 queda bloqueada; la UPS sale como fuera de catálogo
    assert [b["item"]["sku"] for b in r["bloqueados"]] == ["SIM-DC-09"]
    assert r["triaje"]["fuera_de_catalogo"][0]["que_pide"].startswith("Equipos UPS")
    c = r["cotizacion"]
    # DC-04 12,900 + DC-08 4,200 + BK-01 2×1,850 + BK-03 2×420 = 21,640
    assert c["mensual"]["subtotal"] == 21640.0
    assert r["cobertura"]["respondidas"] == 5


def test_repeticion_va_cambiando_conforme_avanza_la_llamada():
    guion = llamadas()["CASO-02"]
    assert analizar(guion[:1], "repeticion", "CASO-02")["triaje"]["estado"] == "amarillo"
    temprano = analizar(guion[:2], "repeticion", "CASO-02")
    assert temprano["triaje"]["estado"] == "amarillo"
    assert temprano["siguiente_pregunta"]["fuente"] == "catálogo"


def test_repeticion_caso07_verde_y_caso06_rojo():
    r7 = analizar(llamadas()["CASO-07"], "repeticion", "CASO-07")
    assert r7["triaje"]["estado"] == "verde" and r7["bloqueados"] == []
    assert r7["cotizacion"]["mensual"]["subtotal"] == 5728.0
    r6 = analizar(llamadas()["CASO-06"], "repeticion", "CASO-06")
    assert {"ESC-08", "ESC-10"} <= {a["regla"] for a in r6["triaje"]["reglas_activadas"]}


def test_repeticion_caso01_parece_estandar_hasta_que_aparecen_datos_de_salud():
    guion = llamadas()["CASO-01"]
    antes = analizar(guion[:8], "repeticion", "CASO-01")
    assert antes["triaje"]["estado"] == "amarillo"
    assert "salud" in antes["siguiente_pregunta"]["texto"] and antes["siguiente_pregunta"]["fuente"] == "catálogo"
    despues = analizar(guion[:10], "repeticion", "CASO-01")
    assert despues["triaje"]["estado"] == "rojo"
    esc04 = next(a for a in despues["triaje"]["reglas_activadas"] if a["regla"] == "ESC-04")
    assert esc04["cita"] == "guardamos los expedientes clínicos de los pacientes"
    final = analizar(guion, "repeticion", "CASO-01")
    c = final["cotizacion"]
    assert final["bloqueados"] == [] and c["plazo_meses"] == 24
    assert c["renglones_pendientes_arquitecto"] == ["SIM-M365-03"]
    # (18 × 95 + 25 × 69) × 0.95 por plazo de 24 meses; migración 25 × 350 sin descuento
    assert c["mensual"]["subtotal"] == 3263.25 and c["cargos_unicos"]["subtotal"] == 8750.0


def test_solo_confirmados_pasan_a_la_propuesta():
    guion = llamadas()["CASO-07"]
    r = analizar(guion, "repeticion", "CASO-07", solo_confirmados={"SIM-BK-01", "SIM-BK-05"})
    assert {x["sku"] for x in r["cotizacion"]["renglones"]} == {"SIM-BK-01", "SIM-BK-05"}
