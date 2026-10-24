"""Una sesión de llamada: transcripción, análisis en vivo, ✓/✗ del vendedor y cierre con propuesta.

Eventos que se envían al navegador (contrato del WebSocket):
  sesion, modo, error, analisis (auxiliar: {en_curso} para que el micrófono acumule frases),
  speakers (auxiliar: Claude etiquetó quién dijo cada frase «auto»),
  transcript, notes_update, triage, suggested_question, glossary, suggestion, feedback, blocked,
  proposal_ready
"""
import asyncio
import json
import time
from datetime import datetime

from app import aprendizaje, config, db, extraccion
from app.pipeline import DIR_GUIONES, analizar, llamadas

LINEA_BASE = {"sesiones": 3, "dias_hasta_propuesta": 21, "arquitecto": "casi siempre"}


class Sesion:
    def __init__(self, enviar, cliente: dict, modo: str):
        self.enviar = enviar  # async (evento, datos)
        self.cliente = cliente
        self.modo = modo
        self.frases: list[dict] = []
        self.confirmados: set[str] = set()
        self.descartados: set[str] = set()
        self.resultado: dict | None = None
        self.analizando = False
        self.pendiente = False
        self.cerrada = False
        self.inicio = time.monotonic()
        self.tarea_sim: asyncio.Task | None = None
        self.tareas: set[asyncio.Task] = set()
        conn = db.conectar()
        with conn:
            self.id = conn.execute("INSERT INTO sesiones (cliente_id, modo) VALUES (?, ?)",
                                   (cliente["id"], modo)).lastrowid
        conn.close()

    # ------------------------------------------------------------ entrada
    async def iniciar(self):
        await self.enviar("sesion", {"sesion_id": self.id, "cliente": self.cliente, "modo": self.modo,
                                     "tiene_guion": self.cliente["id"] in llamadas()})
        await self.enviar("modo", {"modo": self.modo, "motivo": None})

    async def agregar_frase(self, hablante: str, texto: str):
        """hablante: cliente | vendedor | auto (lo decide Claude en el siguiente análisis)."""
        texto = (texto or "").strip()
        if not texto or self.cerrada:
            return
        auto = hablante == "auto"
        frase = {"hablante": "vendedor" if hablante == "vendedor" else "cliente", "texto": texto,
                 "hora": datetime.now().strftime("%H:%M:%S"), "auto": auto}
        self.frases.append(frase)
        conn = db.conectar()
        with conn:
            frase["id"] = conn.execute("INSERT INTO frases (sesion_id, hablante, texto) VALUES (?, ?, ?)",
                                       (self.id, frase["hablante"], texto)).lastrowid
        conn.close()
        await self.enviar("transcript", {"frase": frase, "indice": len(self.frases) - 1, "total": len(self.frases)})
        self._en_segundo_plano(self.solicitar_analisis())

    def _en_segundo_plano(self, corrutina):
        t = asyncio.create_task(corrutina)
        self.tareas.add(t)
        t.add_done_callback(self.tareas.discard)

    # ------------------------------------------------------------ simulación (guion cada N segundos)
    def iniciar_simulacion(self):
        if self.tarea_sim and not self.tarea_sim.done():
            return
        self.tarea_sim = asyncio.create_task(self._simular())

    def pausar_simulacion(self):
        if self.tarea_sim:
            self.tarea_sim.cancel()

    async def _simular(self):
        guion = llamadas().get(self.cliente["id"], [])
        for linea in guion[len(self.frases):]:
            if self.cerrada:
                return
            await self.agregar_frase(linea["hablante"], linea["texto"])
            await asyncio.sleep(config.SEGUNDOS_POR_LINEA)
        await self.enviar("modo", {"modo": self.modo, "motivo": "Fin del guion simulado"})

    # ------------------------------------------------------------ análisis
    async def solicitar_analisis(self):
        """Si ya hay un análisis en curso no se lanza otro: se marca pendiente y se corre al terminar."""
        if self.analizando:
            self.pendiente = True
            return
        self.analizando = True
        await self.enviar("analisis", {"en_curso": True})
        try:
            while True:
                self.pendiente = False
                await self._analizar()
                if not self.pendiente or self.cerrada:
                    break
        finally:
            self.analizando = False
            if not self.cerrada:
                await self.enviar("analisis", {"en_curso": False})

    def _puede_repetir(self) -> bool:
        return self.modo == "simulacion" and (DIR_GUIONES / "repeticion" / f"{self.cliente['id']}.json").exists()

    async def _correr(self, final=False, solo_confirmados=None, previa=None):
        return await asyncio.to_thread(
            analizar, list(self.frases), self.modo, self.cliente["id"], self.cliente,
            aprendizaje.ejemplos(), final, set(self.descartados), solo_confirmados, previa)

    async def _analizar(self, previa=None):
        try:
            r = await self._correr(previa=previa)
        except extraccion.ErrorIA as e:
            if not self._puede_repetir():
                await self.enviar("error", {"mensaje": f"La IA no está disponible: {e}. "
                                                       "Las frases se siguen guardando."})
                return
            self.modo = "repeticion"
            await self.enviar("modo", {"modo": "repeticion",
                                       "motivo": f"La IA no está disponible ({e}). Se usan respuestas pregrabadas."})
            r = await self._correr()
        self.resultado = r
        await self._aplicar_hablantes(r.get("hablantes", []))
        await self._emitir(r)

    async def _aplicar_hablantes(self, etiquetas: list[dict]):
        """Claude etiqueta las frases «auto»; una vez etiquetada, la frase ya no cambia."""
        cambios = []
        for h in etiquetas:
            i = h["linea"] - 1
            if 0 <= i < len(self.frases) and self.frases[i].get("auto"):
                f = self.frases[i]
                f.update(hablante=h["hablante"], auto=False, por_ia=True)
                cambios.append({"indice": i, "hablante": h["hablante"]})
        if not cambios:
            return
        conn = db.conectar()
        with conn:
            conn.executemany("UPDATE frases SET hablante = ? WHERE id = ?",
                             [(self.frases[c["indice"]]["hablante"], self.frases[c["indice"]]["id"]) for c in cambios])
        conn.close()
        await self.enviar("speakers", {"cambios": cambios})

    async def _emitir(self, r: dict):
        t, c = r["triaje"], r["cotizacion"]
        await self.enviar("triage", {**t, "resumen_cotizacion": {
            "mensual": c["mensual"]["subtotal"], "cargos_unicos": c["cargos_unicos"]["subtotal"],
            "por_definir": c["renglones_por_definir"], "pendientes_arquitecto": c["renglones_pendientes_arquitecto"],
            "requiere_autorizacion_gerente": c["requiere_autorizacion_gerente"]}})
        await self.enviar("notes_update", {"notas": r["notas"], "cobertura": r["cobertura"]})
        await self.enviar("suggested_question", r["siguiente_pregunta"] or {})
        await self.enviar("glossary", {"terminos": r["glosario"]})
        productos = [dict(p, estado=("confirmado" if p["sku"] in self.confirmados else
                                     "descartado" if p["sku"] in self.descartados else "pendiente"))
                     for p in r["sugerencias_producto"]]
        await self.enviar("suggestion", {"productos": productos, "recomendados": r["sugerencias"],
                                         "rechazados": r["rechazados"]})
        await self.enviar("blocked", {"total": len(r["bloqueados"]) + len(r["rechazados"]),
                                      "items": r["bloqueados"]})

    # ------------------------------------------------------------ ✓ / ✗ del vendedor
    async def feedback(self, sku: str, correcto: bool):
        cita = next((p["cita"] for p in (self.resultado or {}).get("sugerencias_producto", []) if p["sku"] == sku), "")
        (self.confirmados if correcto else self.descartados).add(sku)
        (self.descartados if correcto else self.confirmados).discard(sku)
        aprendizaje.registrar(cita, sku, correcto)
        await self.enviar("feedback", {"sku": sku, "correcto": correcto, "confirmados": sorted(self.confirmados),
                                       "descartados": sorted(self.descartados)})
        if self.analizando:
            self.pendiente = True  # el análisis en curso se repite al terminar, ya con el ✓/✗
        elif self.resultado:
            await self._analizar(previa=self.resultado["_extraccion"])  # recalcula sin llamar a Claude

    # ------------------------------------------------------------ cierre
    async def cerrar(self) -> dict | None:
        if self.cerrada:
            return None
        self.cerrada = True
        self.pausar_simulacion()
        while self.analizando:
            await asyncio.sleep(0.1)
        r = None
        if self.modo != "repeticion":
            try:
                r = await self._correr(final=True, solo_confirmados=set(self.confirmados))
            except extraccion.ErrorIA as e:
                await self.enviar("error", {"mensaje": f"Cierre sin IA ({e}); se usa el último análisis."})
        if r is None:
            previa = self.resultado["_extraccion"] if self.resultado else {}
            r = await self._correr(solo_confirmados=set(self.confirmados), previa=previa)
        minutos = round((time.monotonic() - self.inicio) / 60, 1)
        t, c = r["triaje"], r["cotizacion"]
        impacto = {
            "sesiones": 1,
            "preguntas_cubiertas_pct": r["cobertura"]["pct"],
            "preguntas_cubiertas": f"{r['cobertura']['respondidas']} de {r['cobertura']['total']}",
            "minutos_a_propuesta": minutos,
            "triaje": t["etiqueta"],
            "requiere_arquitecto": t["estado"] == "rojo",
            "lineas_estandar": t["lineas_estandar"],
            "lineas_a_la_medida": t["lineas_a_la_medida"],
            "sugerencias_bloqueadas": len(r["bloqueados"]) + len(r["rechazados"]),
            "linea_base": LINEA_BASE,
        }
        archivos = {}
        try:
            from app import documentos  # entregable 6
            archivos = await asyncio.to_thread(documentos.generar, self, r, impacto)
        except ImportError:
            pass
        self._guardar_cierre(r, impacto, archivos)
        await self.enviar("proposal_ready", {"triaje": t, "cotizacion": c, "impacto": impacto, "archivos": archivos,
                                             "confirmados": sorted(self.confirmados), "notas": r["notas"],
                                             "fuera_de_catalogo": t["fuera_de_catalogo"]})
        return r

    def _guardar_cierre(self, r, impacto, archivos):
        t, c = r["triaje"], r["cotizacion"]
        conn = db.conectar()
        with conn:
            conn.execute("UPDATE sesiones SET fin = datetime('now','localtime'), triaje_final = ?,"
                         " preguntas_cubiertas_pct = ?, minutos_a_propuesta = ?, modo = ? WHERE id = ?",
                         (t["estado"], impacto["preguntas_cubiertas_pct"], impacto["minutos_a_propuesta"],
                          self.modo, self.id))
            for n in r["notas"]:
                conn.execute("INSERT OR REPLACE INTO notas (sesion_id, campo, valor, estado, cita) VALUES (?,?,?,?,?)",
                             (self.id, n["tema"], n["resumen"], n["estado"], n.get("cita")))
            for p in r["sugerencias_producto"]:
                estado = ("confirmado" if p["sku"] in self.confirmados else
                          "descartado" if p["sku"] in self.descartados else "sugerido")
                conn.execute("INSERT INTO requerimientos (sesion_id, sku, cantidad, cita, estado) VALUES (?,?,?,?,?)",
                             (self.id, p["sku"], p.get("cantidad"), p.get("cita"), estado))
            for b in r["bloqueados"]:
                conn.execute("INSERT INTO requerimientos (sesion_id, sku, cita, estado, motivo_bloqueo)"
                             " VALUES (?,?,?,'bloqueado',?)",
                             (self.id, b["item"].get("sku") or b["item"].get("nombre"), b["item"].get("cita"), b["motivo"]))
            pid = conn.execute(
                "INSERT INTO propuestas (sesion_id, cliente_id, plazo_meses, triaje, subtotal_mensual, subtotal_unico,"
                " iva, total, descuento_max_pct, requiere_autorizacion, vigencia_hasta, archivo_docx, archivo_pdf)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (self.id, self.cliente["id"], c["plazo_meses"], t["estado"], c["mensual"]["subtotal"],
                 c["cargos_unicos"]["subtotal"], c["mensual"]["iva"] + c["cargos_unicos"]["iva"],
                 c["mensual"]["total"] + c["cargos_unicos"]["total"], c["descuento_max_pct"],
                 int(c["requiere_autorizacion_gerente"]), c["vigencia_hasta"],
                 archivos.get("propuesta_docx"), archivos.get("propuesta_pdf"))).lastrowid
            for x in c["renglones"]:
                conn.execute(
                    "INSERT INTO propuesta_lineas (propuesta_id, sku, nombre, cantidad, mensual_lista, mensual_neto,"
                    " cargo_unico, descuentos, estado, fuente, nota) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (pid, x["sku"], x["nombre"], x["cantidad"], x["mensual_lista"], x["mensual_neto"], x["cargo_unico"],
                     json.dumps(x["descuentos"], ensure_ascii=False), x["estado"], x["fuente"], "; ".join(x["notas"])))
        conn.close()

    def detener(self):
        self.cerrada = True
        self.pausar_simulacion()
        for t in list(self.tareas):
            t.cancel()
