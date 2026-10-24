"""Servidor del Copiloto Comercial: página, API de expedientes/aprendizajes y WebSocket de la llamada.

Mensajes del navegador por WebSocket (/ws), en JSON con campo "tipo":
  iniciar  {cliente_id, modo: microfono|simulacion|repeticion}
  frase    {hablante: cliente|vendedor, texto}        (modo micrófono)
  simular  {}  /  pausar {}                           (guion cada SEGUNDOS_POR_LINEA)
  feedback {sku, correcto: true|false}
  cerrar   {}
El servidor responde con {"evento": ..., "datos": ...} (ver app/sesion.py).
"""
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import aprendizaje, config, db
from app.pipeline import llamadas
from app.sesion import Sesion

MODOS = {"microfono", "simulacion", "repeticion"}


@asynccontextmanager
async def ciclo_de_vida(_app):
    db.inicializar()  # recarga el catálogo desde el JSON en cada arranque
    config.SALIDAS_DIR.mkdir(exist_ok=True)
    yield


app = FastAPI(title="Copiloto Comercial (datos simulados)", lifespan=ciclo_de_vida)
app.mount("/web", StaticFiles(directory=config.WEB_DIR), name="web")


@app.get("/")
def inicio():
    return FileResponse(config.WEB_DIR / "index.html")


@app.get("/api/salud")
def salud():
    # Solo dice SI hay clave; jamás la devuelve.
    return {
        "ok": True,
        "clave_configurada": bool(config.ANTHROPIC_API_KEY),
        "modelo_rapido": config.MODELO_RAPIDO,
        "modelo_fuerte": config.MODELO_FUERTE,
        "modo_por_defecto": config.MODO_POR_DEFECTO,
        "catalogo_encontrado": config.CATALOGO_JSON.exists(),
    }


def _cliente(cliente_id: str) -> dict | None:
    conn = db.conectar()
    fila = conn.execute("SELECT id, empresa, industria, ciudad, empleados, mensaje_inicial, informacion_que_falta"
                        " FROM clientes WHERE id = ?", (cliente_id,)).fetchone()
    conn.close()
    return dict(fila) if fila else None


@app.get("/api/clientes")
def clientes():
    conn = db.conectar()
    filas = conn.execute("SELECT id, empresa, industria, ciudad, empleados FROM clientes ORDER BY id").fetchall()
    conn.close()
    guiones = llamadas()
    return [dict(f, tiene_guion=f["id"] in guiones) for f in filas]


@app.get("/api/aprendizajes")
def aprendizajes():
    return aprendizaje.tabla()


@app.get("/salidas/{nombre}")
def descargar(nombre: str):
    ruta = (config.SALIDAS_DIR / nombre).resolve()
    if ruta.parent != config.SALIDAS_DIR.resolve() or not ruta.exists():
        raise HTTPException(404, "No existe")
    return FileResponse(ruta, filename=nombre)


@app.websocket("/ws")
async def ws(websocket: WebSocket):
    await websocket.accept()
    candado = asyncio.Lock()
    sesion: Sesion | None = None

    async def enviar(evento: str, datos):
        async with candado:
            await websocket.send_json({"evento": evento, "datos": datos})

    try:
        while True:
            msg = await websocket.receive_json()
            tipo = msg.get("tipo")
            if tipo == "iniciar":
                cliente = _cliente(msg.get("cliente_id", ""))
                modo = msg.get("modo") if msg.get("modo") in MODOS else config.MODO_POR_DEFECTO
                if not cliente:
                    await enviar("error", {"mensaje": "Expediente no encontrado"})
                    continue
                if modo != "microfono" and cliente["id"] not in llamadas():
                    await enviar("error", {"mensaje": f"{cliente['id']} no tiene guion; usa el micrófono"})
                    continue
                if sesion:
                    sesion.detener()
                sesion = Sesion(enviar, cliente, modo)
                await sesion.iniciar()
            elif sesion is None:
                await enviar("error", {"mensaje": "Primero inicia una sesión"})
            elif tipo == "frase":
                await sesion.agregar_frase(msg.get("hablante", "cliente"), msg.get("texto", ""))
            elif tipo == "simular":
                sesion.iniciar_simulacion()
            elif tipo == "pausar":
                sesion.pausar_simulacion()
            elif tipo == "feedback":
                await sesion.feedback(msg.get("sku", ""), bool(msg.get("correcto")))
            elif tipo == "cerrar":
                await sesion.cerrar()
    except WebSocketDisconnect:
        if sesion:
            sesion.detener()
