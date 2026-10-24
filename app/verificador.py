"""Verificador anti-alucinación: todo lo que Claude extrae debe estar respaldado por la transcripción.

Una cita pasa si, normalizada (sin acentos, sin signos, minúsculas), al menos el 80% de sus
palabras "largas" (más de 3 letras, o que contienen un número) aparecen juntas en un tramo de la
transcripción. Si la cita no tiene palabras largas, debe aparecer completa tal cual (normalizada).
"""
import re
import unicodedata
from collections import Counter

UMBRAL = 0.8


def normalizar(texto: str) -> list[str]:
    t = unicodedata.normalize("NFD", texto or "")
    t = "".join(c for c in t if unicodedata.category(c) != "Mn").lower()
    return re.sub(r"[^a-z0-9ñ]+", " ", t).split()


def _larga(palabra: str) -> bool:
    return len(palabra) > 3 or any(c.isdigit() for c in palabra)


def puntaje_cita(cita: str, tokens_transcripcion: list[str]) -> float:
    """0..1: qué fracción de la cita aparece en el mejor tramo de la transcripción."""
    c = normalizar(cita)
    if not c:
        return 0.0
    largas = [w for w in c if _larga(w)]
    T = tokens_transcripcion
    if not largas:
        n = len(c)
        return 1.0 if any(T[i:i + n] == c for i in range(len(T) - n + 1)) else 0.0
    objetivo = Counter(largas)
    ancho = len(c) + 3
    mejor = 0
    for i in range(max(1, len(T) - ancho + 1)):
        ventana = Counter(T[i:i + ancho])
        mejor = max(mejor, sum(min(n, ventana[w]) for w, n in objetivo.items()))
        if mejor == len(largas):
            break
    return mejor / len(largas)


def cita_valida(cita: str, tokens_transcripcion: list[str]) -> bool:
    return puntaje_cita(cita, tokens_transcripcion) >= UMBRAL


def _valor_hecho(definicion: dict, crudo):
    """Convierte el valor que escribió Claude al tipo del hecho. None si no es válido."""
    tipo = definicion["tipo"]
    s = str(crudo).strip().lower()
    if tipo == "booleano":
        return {"true": True, "sí": True, "si": True, "false": False, "no": False}.get(s)
    if tipo == "numero":
        s = s.replace("$", "").replace(",", "").replace(" ", "").replace("%", "")
        try:
            v = float(s)
        except ValueError:
            return None
        if "valores" in definicion and v not in definicion["valores"]:
            return None
        return int(v) if v.is_integer() else v
    if tipo == "texto":
        valor = str(crudo).strip()
        return valor if valor in definicion.get("valores", [valor]) else None
    return None


def verificar(extraccion: dict, frases: list[dict], catalogo, reglas: dict) -> dict:
    """Separa lo respaldado de lo bloqueado. Devuelve el requerimiento listo para el motor."""
    T = normalizar(" ".join(f["texto"] for f in frases))
    bloqueados = []

    def bloquear(tipo, item, motivo):
        bloqueados.append({"tipo": tipo, "item": item, "motivo": motivo})

    productos = []
    for p in extraccion.get("productos", []):
        if not catalogo.existe(p.get("sku", "")):
            bloquear("producto", p, "El SKU no existe en el catálogo")
        elif not cita_valida(p.get("cita", ""), T):
            bloquear("producto", p, "La cita no aparece en la transcripción")
        else:
            productos.append(p)

    hechos = {}
    for h in extraccion.get("hechos", []):
        definicion = reglas["hechos"].get(h.get("nombre"))
        if definicion is None:
            bloquear("hecho", h, "Dato desconocido para el motor")
            continue
        valor = _valor_hecho(definicion, h.get("valor"))
        if valor is None:
            bloquear("hecho", h, f"Valor no válido para {h['nombre']}")
        elif not cita_valida(h.get("cita", ""), T):
            bloquear("hecho", h, "La cita no aparece en la transcripción")
        else:
            hechos[h["nombre"]] = {"valor": valor, "cita": h["cita"]}

    fuera = []
    for x in extraccion.get("fuera_de_catalogo", []):
        if cita_valida(x.get("cita", ""), T):
            fuera.append(x)
        else:
            bloquear("fuera_de_catalogo", x, "La cita no aparece en la transcripción")

    notas = []
    for n in extraccion.get("notas", []):
        if n.get("estado") == "faltante" or cita_valida(n.get("cita", ""), T):
            notas.append(n)
        else:
            bloquear("nota", n, "La cita no aparece en la transcripción")

    respondidas = []
    for r in extraccion.get("preguntas_respondidas", []):
        prod = catalogo.productos.get(r.get("sku"))
        if not prod or r.get("pregunta") not in prod["preguntas_clave"]:
            bloquear("pregunta", r, "La pregunta no es una de las preguntas clave de ese producto")
        elif not cita_valida(r.get("cita", ""), T):
            bloquear("pregunta", r, "La cita no aparece en la transcripción")
        else:
            respondidas.append(r)

    return {
        "requerimiento": {"productos": productos, "hechos": hechos, "fuera_de_catalogo": fuera},
        "notas": notas,
        "preguntas_respondidas": respondidas,
        "glosario": extraccion.get("glosario", []),
        "siguiente_pregunta_ia": extraccion.get("siguiente_pregunta"),
        "hablantes": [h for h in extraccion.get("hablantes", [])
                      if h.get("hablante") in ("cliente", "vendedor") and isinstance(h.get("linea"), int)],
        "bloqueados": bloqueados,
    }
