# Guion del video de demo (≤ 3:30) · Copiloto Comercial

> Caso: **CASO-01 · Clínica Dental Sonrisa Norte** (datos simulados). Llamada **real** por Google Meet,
> escuchada con el micrófono de la laptop del vendedor. Probado con Claude real el 24/oct: el semáforo
> pasa a rojo (ESC-04) justo en la frase de los expedientes y las cámaras salen como «No prometer».

## Reparto
- **Vendedor:** comparte su pantalla (copiloto + Meet) y es quien graba.
- **Cliente (Dra. Laura, dueña de la clínica):** otra persona del equipo, en otra laptop, dentro del Meet.
- **Voz en off** (opcional, se graba después): textos en *cursiva* abajo.

## Antes de grabar (10 min)
1. `py -m app.chequeo_demo --ia` → todo en ✓. Reiniciar el servidor y recargar Chrome (Ctrl+F5).
   Si la app abre ya con un usuario, presionar **Salir** para que la grabación empiece en la pantalla **Entrar**.
2. **Laptop del vendedor:** cuarto silencioso, **sin audífonos**, volumen de Meet ~60%. Chrome con dos ventanas:
   Meet a la izquierda (1/3) y el copiloto a la derecha (2/3).
3. Grabar pantalla **con audio del sistema y del micrófono** (Recortes de Windows: Win+Shift+R, o OBS).
4. **Hacer un ensayo completo** antes de la toma buena (cuesta ~US$0.10).
5. Reglas para hablar: frases completas, ritmo tranquilo, **pausa de 3 segundos después de cada frase del cliente**
   (el copiloto tarda 5–9 s en analizar; en la edición se acelera la espera).

## Escena por escena

| Tiempo | Escena | En pantalla | Qué se dice |
|---|---|---|---|
| 0:00–0:20 | **1. El problema** | Título + 3 cifras: «3 sesiones · hasta 3 semanas · arquitecto casi siempre» | *«En Alestra, levantar requerimientos toma tres reuniones y la propuesta hasta tres semanas. El catálogo, los precios y los arquitectos existen… pero no llegan al vendedor cuando el cliente pregunta.»* |
| 0:20–0:40 | **2. Entrar y preparar** | Abrir http://localhost:8000 → pantalla **Entrar** → escribir el correo (p. ej. `ana.lopez@empresa.com`) → **Entrar con mi cuenta corporativa** → «Hola, Ana. Prepara tu reunión» → elegir **CASO-01 · Clínica Dental Sonrisa Norte** → **Escuchar micrófono** → casilla de consentimiento → **Empezar** → **🎙 Iniciar escucha** | *«La vendedora entra con su cuenta corporativa y, antes de la llamada, el copiloto carga el expediente del cliente.»* |
| 0:35–2:15 | **3. La llamada (en vivo)** | Meet + copiloto lado a lado. Ver tabla de diálogo abajo | Diálogo |
| 2:15–2:45 | **4. Confirmar y cerrar** | ✓ en las tarjetas correctas; ✗ en una que no aplique; abrir «🛡 N sugerencias bloqueadas»; **Cerrar sesión y generar propuesta** | *«El vendedor decide: solo lo que confirma entra a la propuesta. Y lo que la IA dijo sin respaldo en la llamada, se bloquea.»* |
| 2:45–3:15 | **5. Resultado** | Tablero de impacto → abrir **Propuesta (Word)** (SKU, fuente, IVA, «BORRADOR») → abrir **Brief para arquitecto** (ESC-04 con la frase del cliente, lo ya cotizado, cámaras fuera de catálogo) | *«Una sola sesión, propuesta en minutos. Lo estándar ya va cotizado con precios del catálogo; lo que necesita arquitecto le llega con un brief, para que el cliente no repita su explicación.»* |
| 3:15–3:30 | **6. Cierre** | Diagrama simple o texto: «Claude entiende · Python calcula · el vendedor decide» + link del repo | *«Claude nunca ve ni calcula precios: extrae lo que dijo el cliente, con la cita que lo prueba. El motor cotiza solo con el catálogo.»* |

## Diálogo de la llamada (escena 3)

| # | Quién | Frase (decirla tal cual o muy parecida) | Qué debe verse en el copiloto (para señalar en la edición) |
|---|---|---|---|
| 1 | Vendedor | «Hola doctora, gracias por su tiempo. Cuénteme, ¿qué está pasando en la clínica?» | La frase aparece como «Detectando…» y luego **Vendedor (IA)** |
| 2 | Cliente | «Usamos correos de Gmail personales y el mes pasado una recepcionista abrió un archivo y se cifraron todas las computadoras. Queremos algo más seguro.» | Tarjeta **Microsoft 365 Business Premium**; semáforo 🟡 |
| 3 | Vendedor | «Entiendo, qué mal momento. ¿Cuántas personas trabajan en la clínica y cuántas computadoras tienen?» | — |
| 4 | Cliente | «Somos 25 personas y tenemos 18 computadoras.» | **Siguiente pregunta:** «¿Manejan datos de salud…?» (sale del catálogo, no de la IA) |
| 5 | Vendedor | «¿Y cómo respaldan hoy la información?» | — |
| 6 | Cliente | «La verdad no respaldamos nada. Queremos respaldar el correo y los archivos de las 25 personas.» | Tarjetas de **respaldo** (laptops, Microsoft 365) |
| 7 | Vendedor | «¿Quieren conservar los correos que ya tienen en Gmail?» | — |
| 8 | Cliente | «Sí, queremos pasar los correos de las 25 cuentas sin perder nada. Ah, y también queremos poner cámaras de seguridad en la recepción.» | Tarjeta **Migración de correo** y tarjeta roja **⛔ No prometer: cámaras** |
| 9 | Vendedor | «Lo de las cámaras lo reviso con un especialista y le confirmo. Una pregunta importante: ¿guardan expedientes o datos de salud de sus pacientes?» | (El vendedor **lee la frase sugerida** de la tarjeta roja) |
| 10 | Cliente | «Sí, guardamos los expedientes clínicos de los pacientes y sus radiografías.» | **Semáforo 🔴 Con arquitecto · ESC-04**, con esa frase como cita |
| 11 | Vendedor | «Perfecto. ¿A qué plazo les interesaría contratar: doce, veinticuatro o treinta y seis meses?» | — |
| 12 | Cliente | «A veinticuatro meses.» | Estimado con descuento por plazo; notas casi completas |

Después de la frase 12: **Pausar** la escucha y esperar a que termine «Analizando…».

**Resultado esperado** (ensayo con Claude real): propuesta de **$3,263.25/mes + $8,750 único** (sin IVA) a 24 meses
— respaldo de laptops 18 × $95 y de Microsoft 365 25 × $69 con −5% por plazo; migración de 25 buzones × $350 —
y **Microsoft 365 Premium pendiente de arquitecto** por ESC-04. Costo de IA de una toma: ~US$0.10.

## Qué confirmar en la escena 4
- ✓ **Microsoft 365 Business Premium**, **Migración de correo**, **Backup de laptops**, **Backup de Microsoft 365**.
- ✗ cualquier tarjeta que no corresponda (por ejemplo, un respaldo sin cantidad o Business Basic si aparece).
- Abrir «🛡 sugerencias bloqueadas» y señalar una: *la IA dedujo algo que el cliente no dijo y se bloqueó*.

## Plan B (si algo falla al grabar)
- **El micrófono no capta bien al cliente:** que el «cliente» hable en el mismo cuarto, cerca de la laptop del vendedor
  (sin Meet), o subir el volumen.
- **La IA tarda o falla:** grabar con **«Simular llamada»** o **«Repetición (sin IA)»** de CASO-01 (misma historia, guion
  pregrabado) y decirlo en el video.
- **Resultado distinto al esperado:** la IA no es 100% igual en cada toma; si el semáforo no cambia en la frase 10,
  repetir la frase con «expedientes clínicos de los pacientes».

## Para Devpost
- Exportar en 1080p, subir a **YouTube (no listado)** o Vimeo y pegar el link en Devpost.
- Duración final ≤ 3:30: acelerar 1.5× las esperas de «Analizando…» y cortar silencios.
