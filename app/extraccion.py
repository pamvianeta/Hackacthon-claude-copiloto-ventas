"""Extracción de requerimientos con Claude.

Claude SOLO extrae (productos, hechos, notas, glosario, fuera de catálogo), cada cosa con su cita
textual. Nunca ve precios ni los calcula. La salida está obligada a un esquema JSON estricto con
listas cerradas de SKUs y de hechos; después pasa por app.verificador y por app.motor.

Determinismo: la API ya no acepta `temperature` (desde 2026-10-21), así que se usa esquema estricto
+ enums cerrados + esfuerzo bajo en el modelo rápido.
"""
import json

import anthropic

from app import config
from app import catalogo as cat_mod
from app.motor import cargar_reglas

TEMAS_NOTAS = ["Necesidad principal", "Tamaño (usuarios, equipos, TB)", "Situación actual",
               "Continuidad y tiempos", "Seguridad y regulación", "Plazo y presupuesto"]

INSTRUCCIONES = """Eres el copiloto de un vendedor NO técnico de servicios de TI (datos SIMULADOS de un hackathon).
Lees la transcripción de una llamada con un cliente y extraes requerimientos estructurados.

REGLAS (obligatorias):
1. Solo puedes proponer SKUs del CATÁLOGO de abajo. Propón un producto solo si el cliente expresa una
   necesidad que ese producto resuelve (usa "senal_del_cliente" y "descripcion" como guía).
2. Si el cliente pide algo que NINGÚN producto del catálogo resuelve, va en "fuera_de_catalogo".
   Nunca lo aproximes a un SKU parecido.
3. Cada producto, hecho, nota, pregunta respondida y elemento fuera de catálogo lleva "cita":
   un fragmento COPIADO TEXTUALMENTE de la transcripción (de 3 a 25 palabras), sin parafrasear,
   sin corregir y sin juntar frases de distintos renglones. Si no hay frase que lo respalde, no lo incluyas.
4. "cantidad" solo si el cliente DIJO EN LA LLAMADA un número para la unidad de cobro de ese producto, y
   entonces la "cita" de ese producto debe ser la frase donde dijo ese número; si no, null.
   El EXPEDIENTE es solo contexto: nunca saques de ahí cantidades, hechos ni regulación.
5. "hechos": solo los de la lista HECHOS, solo si el cliente lo dijo explícitamente en la llamada, y la cita
   debe contener la evidencia (el número dicho, o la palabra que lo prueba: p. ej. «pacientes» para salud).
   Valor numérico: solo dígitos (ej. "300000", "2", "0.5"). Booleano: "true" o "false".
   Texto: uno de los valores permitidos. RTO en horas, RPO en minutos.
6. NUNCA menciones precios, montos, descuentos ni plazos de entrega. Tú no cotizas.
7. "dile_al_cliente": una frase en lenguaje de negocio, sin tecnicismos ni promesas, que el vendedor
   puede decir para explicar por qué ese producto le sirve.
8. "notas": una por tema de la lista; estado "completo" (ya se sabe lo necesario), "incompleto"
   (se sabe algo) o "faltante" (nada; en ese caso cita = "" y resumen = qué falta).
9. "preguntas_respondidas": de las preguntas_clave de los productos propuestos, las que el cliente ya
   contestó; copia el texto de la pregunta EXACTO del catálogo.
10. "glosario": hasta 6 términos técnicos que salieron en la llamada, explicados para el vendedor en
    lenguaje de negocio; también lo que dijo el cliente traducido a concepto técnico.
11. "siguiente_pregunta": la pregunta más útil que falta para cerrar el levantamiento en esta sesión,
    preferentemente una de las preguntas_clave.
12. "hablantes": para cada renglón marcado [¿?] di quién habla, por el contenido: el VENDEDOR pregunta,
    ofrece, explica servicios o agradece; el CLIENTE describe su empresa, sus sistemas, problemas,
    cantidades y necesidades. Usa el número del renglón. Si un renglón no está marcado [¿?], no lo incluyas.
"""


def _catalogo_para_prompt(catalogo) -> str:
    campos = ("sku", "familia", "nombre", "tipo", "descripcion", "unidad_cobro", "senal_del_cliente",
              "preguntas_clave")
    productos = [{k: p[k] for k in campos} for p in catalogo.productos.values()]  # sin precios
    return json.dumps(productos, ensure_ascii=False, separators=(",", ":"))


def _hechos_para_prompt(reglas) -> str:
    return json.dumps({k: {c: v[c] for c in ("tipo", "descripcion", "valores") if c in v}
                       for k, v in reglas["hechos"].items()}, ensure_ascii=False, separators=(",", ":"))


def esquema(catalogo, reglas) -> dict:
    texto = {"type": "string"}
    cita = {"type": "string"}

    def obj(props):
        return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}

    return obj({
        "productos": {"type": "array", "items": obj({
            "sku": {"type": "string", "enum": sorted(catalogo.productos)},
            "cantidad": {"anyOf": [{"type": "number"}, {"type": "null"}]},
            "cita": cita, "dile_al_cliente": texto})},
        "hechos": {"type": "array", "items": obj({
            "nombre": {"type": "string", "enum": sorted(reglas["hechos"])},
            "valor": texto, "cita": cita})},
        "fuera_de_catalogo": {"type": "array", "items": obj({"cita": cita, "que_pide": texto})},
        "notas": {"type": "array", "items": obj({
            "tema": {"type": "string", "enum": TEMAS_NOTAS},
            "resumen": texto,
            "estado": {"type": "string", "enum": ["completo", "incompleto", "faltante"]},
            "cita": cita})},
        "preguntas_respondidas": {"type": "array", "items": obj({
            "sku": {"type": "string", "enum": sorted(catalogo.productos)}, "pregunta": texto, "cita": cita})},
        "glosario": {"type": "array", "items": obj({"termino": texto, "en_lenguaje_comercial": texto})},
        "siguiente_pregunta": obj({"texto": texto, "por_que": texto}),
        "hablantes": {"type": "array", "items": obj({
            "linea": {"type": "integer"}, "hablante": {"type": "string", "enum": ["cliente", "vendedor"]}})},
    })


def sistema(catalogo, reglas) -> list[dict]:
    """Bloque fijo (instrucciones + catálogo + hechos) con caché: no cambia entre llamadas."""
    texto = (f"{INSTRUCCIONES}\nCATÁLOGO (sin precios):\n{_catalogo_para_prompt(catalogo)}\n\n"
             f"HECHOS que puedes extraer:\n{_hechos_para_prompt(reglas)}")
    return [{"type": "text", "text": texto, "cache_control": {"type": "ephemeral"}}]


def mensaje_usuario(frases: list[dict], cliente: dict | None, aprendizajes: list[dict]) -> str:
    partes = []
    if cliente:
        partes.append(f"EXPEDIENTE: {cliente['empresa']} · {cliente['industria']} · {cliente['ciudad']} · "
                      f"{cliente['empleados']} empleados.")
    if aprendizajes:
        ejemplos = "\n".join(f"- «{a['frase_cliente']}» → {a['sku']} (confirmado {a['confirmados']} veces)"
                             for a in aprendizajes)
        partes.append(f"EJEMPLOS CONFIRMADOS POR VENDEDORES (frase del cliente → producto correcto):\n{ejemplos}")
    lineas = "\n".join(f"[{i}] [{'¿?' if f.get('auto') else f['hablante'].capitalize()}] {f['texto']}"
                       for i, f in enumerate(frases, start=1))
    partes.append(f"TRANSCRIPCIÓN HASTA AHORA:\n{lineas}")
    return "\n\n".join(partes)


class ErrorIA(Exception):
    """La IA no respondió algo utilizable (sin crédito, sin internet, rechazo, etc.)."""


_cliente_api = None


def _api():
    global _cliente_api
    if _cliente_api is None:
        if not config.ANTHROPIC_API_KEY:
            raise ErrorIA("No hay clave de Claude configurada")
        _cliente_api = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY, timeout=60.0, max_retries=1)
    return _cliente_api


def extraer(frases: list[dict], cliente: dict | None = None, aprendizajes: list[dict] | None = None,
            final: bool = False) -> dict:
    """Llama a Claude. final=True usa el modelo fuerte (cierre de sesión)."""
    catalogo, reglas = cat_mod.obtener(), cargar_reglas()
    modelo = config.MODELO_FUERTE if final else config.MODELO_RAPIDO
    # En vivo: sin razonamiento interno (Haiku 5.5 lo permite con esfuerzo bajo) para responder en segundos.
    # Al cerrar: el modelo fuerte con su razonamiento adaptativo por defecto.
    extra = {} if final else {"thinking": {"type": "disabled"}}
    try:
        r = _api().messages.create(
            model=modelo,
            max_tokens=16000,
            system=sistema(catalogo, reglas),
            messages=[{"role": "user", "content": mensaje_usuario(frases, cliente, aprendizajes or [])}],
            output_config={"effort": "medium" if final else "low",
                           "format": {"type": "json_schema", "schema": esquema(catalogo, reglas)}},
            **extra,
        )
    except anthropic.AuthenticationError as e:
        raise ErrorIA("La clave de Claude no es válida") from e
    except anthropic.RateLimitError as e:
        raise ErrorIA("Demasiadas solicitudes a Claude; intenta en un momento") from e
    except anthropic.APIStatusError as e:
        if "credit balance" in str(e.message):
            raise ErrorIA("La cuenta de Claude no tiene crédito") from e
        raise ErrorIA(f"Error {e.status_code} de la API de Claude") from e
    except anthropic.APIConnectionError as e:
        raise ErrorIA("Sin conexión con la API") from e
    if r.stop_reason in ("refusal", "max_tokens"):
        raise ErrorIA(f"Respuesta incompleta ({r.stop_reason})")
    texto = next((b.text for b in r.content if b.type == "text"), "")
    datos = json.loads(texto)
    datos["_uso"] = {"modelo": modelo, "entrada": r.usage.input_tokens, "salida": r.usage.output_tokens,
                     "cache_leida": r.usage.cache_read_input_tokens or 0,
                     "cache_creada": r.usage.cache_creation_input_tokens or 0}
    return datos
