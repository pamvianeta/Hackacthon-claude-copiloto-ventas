# Copiloto Comercial (overlay) · Hackathon Claude

> **Datos SIMULADOS.** Ningún producto, precio o condición es oficial de Alestra.

Copiloto en tiempo real para vendedores: escucha la llamada, toma notas, hace triaje
(sin arquitecto / con arquitecto / faltan datos) y genera el borrador de propuesta en Word.
Claude **solo extrae requerimientos con cita textual**; los precios los calcula un motor
determinista en Python usando únicamente el catálogo.

## Cómo correrlo (Windows, Google Chrome)

Requisito: Python 3.11 o superior (`py --version`).

```
py -m pip install -r requirements.txt
py -m uvicorn app.main:app --port 8000
```

Abre **Google Chrome** en <http://localhost:8000>. (El micrófono solo funciona en `localhost` o `https`).

### Clave de Claude
Copia `.env.example` como `.env` y pon tu clave en `ANTHROPIC_API_KEY`.
Sin clave, la app funciona en **modo Repetición (sin IA)**.

### Opcional: entorno aislado
```
py -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m uvicorn app.main:app --port 8000
```

### Revisar el catálogo
```
py -m app.validador      # coherencia del JSON y comparación contra CSV y .db
py -m app.db             # (re)crea data/copiloto.db; el servidor también lo hace al arrancar
py -m pytest             # pruebas automáticas
py -m app.demo_motor CASO-02   # triaje y cotización de un ejemplo, sin IA (CASO-07, CASO-02, CASO-06)
py -m app.probar_clave         # prueba mínima de la clave de Claude (cuesta centavos)
py -m app.grabar CASO-02       # regraba el modo Repetición con respuestas reales de Claude
```

### Cómo se evita que la IA invente
1. Claude **no ve precios**: solo nombres, descripciones, señales del cliente y preguntas clave.
2. Su respuesta está obligada a un **esquema JSON estricto** con listas cerradas de SKUs y de datos.
3. Cada cosa que extrae lleva una **cita textual**; el verificador ([app/verificador.py](app/verificador.py)) la busca en la transcripción (sin acentos ni signos, ≥ 80% de las palabras de más de 3 letras). Lo que no aparece se **bloquea** y se cuenta en pantalla.
4. Los precios, descuentos y el triaje los calcula Python ([app/motor.py](app/motor.py), [app/cotizador.py](app/cotizador.py)) solo con el catálogo y [reglas/reglas.json](reglas/reglas.json).
Los supuestos para las ambigüedades del catálogo están en [SUPUESTOS.md](SUPUESTOS.md).

## Antes de la demo (1 minuto)
```
py -m app.chequeo_demo --ia
```
Revisa catálogo, base, modo Repetición, Word/PDF y la clave de Claude. Si la IA falla, la demo sigue en
**Repetición (sin IA)**: el panel lo indica en la barra superior.

**Recorrido sugerido (CASO-02, mixto):** elegir *CASO-02 · Aceros del Valle* → *Simular llamada* → *Empezar* →
*Reproducir llamada* → ver semáforo, siguiente pregunta, tarjetas, «No prometer: UPS» y «1 sugerencia bloqueada» →
✓ en los productos → *Cerrar sesión y generar propuesta* → tablero de impacto + Word/PDF + brief.

Para usarlo como **overlay**, abre la página en una ventana angosta de Chrome a un lado de la videollamada.

## Qué cubre cada parte

| Pieza | Archivo |
|---|---|
| Catálogo → SQLite y validador | [app/db.py](app/db.py), [app/validador.py](app/validador.py) |
| Reglas de arquitecto codificadas | [reglas/reglas.json](reglas/reglas.json) |
| Triaje y cotizador deterministas | [app/motor.py](app/motor.py), [app/cotizador.py](app/cotizador.py) |
| Extracción con Claude (esquema estricto, sin precios) | [app/extraccion.py](app/extraccion.py) |
| Verificación de citas | [app/verificador.py](app/verificador.py) |
| Sesión, simulador, respaldo a Repetición | [app/sesion.py](app/sesion.py), [app/main.py](app/main.py) |
| Panel overlay con micrófono | [web/](web/) |
| Aprendizaje ✓/✗ | [app/aprendizaje.py](app/aprendizaje.py) |
| Propuesta, brief y PDF | [app/documentos.py](app/documentos.py) |
| Pruebas (61) | [tests/](tests/) |

## Estructura

| Carpeta / archivo | Qué contiene |
|---|---|
| `catalogo-simulado/` | Datos del reto. `catalogo-simulado.json` es la **única fuente de verdad**. |
| `app/` | Servidor (FastAPI + WebSocket), motor de reglas, cotizador, integración con Claude, Word. |
| `web/` | Panel overlay (HTML/CSS/JS sin frameworks). |
| `reglas/reglas.json` | Umbrales de "cuándo entra arquitecto" codificados (para revisión del equipo). |
| `guiones/` | Guiones de llamada simulada y del modo repetición. |
| `tests/` | Pruebas automáticas (`py -m pytest`). |
| `data/` | Base SQLite generada (no se sube). |
| `salidas/` | Propuestas y briefs generados (no se suben). |
| `bitacora.md` | Bitácora de supervisión. |

## Modos
- **Micrófono**: Web Speech API de Chrome (es-MX), transcripción en vivo.
- **Simulación**: guion línea por línea cada 3 s, con IA.
- **Repetición (sin IA)**: guion y respuestas pregrabadas; respaldo si falla la API o internet.
