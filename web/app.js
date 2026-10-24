"use strict";
// Panel del Copiloto Comercial. Sin frameworks. Todo lo que llega del servidor se escapa antes de mostrarse.

const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const dinero = (n) => (n == null ? "—" : n.toLocaleString("es-MX", { style: "currency", currency: "MXN" }));
const MODOS = { microfono: "🎙 Micrófono", simulacion: "▶ Simulación (con IA)", repeticion: "⟲ Repetición (sin IA)" };

const st = {
  ws: null, modo: null, hablante: "cliente", analizando: false,
  vistos: {},            // por sección: claves ya mostradas (para resaltar lo nuevo)
  ultimaFeedback: {},
};

// ------------------------------------------------------------------ utilidades de pantalla
function aviso(texto, error = false) {
  const a = $("#aviso");
  a.hidden = !texto;
  a.textContent = texto || "";
  a.className = "aviso" + (error ? " error" : "");
}

/** Pinta una lista y resalta 2 s los elementos cuya clave no se había visto. */
function pintar(seccion, contenedor, items, clave, html) {
  const antes = st.vistos[seccion] || new Set();
  const ahora = new Set();
  contenedor.innerHTML = items.map((it) => {
    const k = clave(it);
    ahora.add(k);
    return `<div data-nuevo="${antes.has(k) ? 0 : 1}">${html(it)}</div>`;
  }).join("");
  contenedor.querySelectorAll('[data-nuevo="1"]').forEach((el) => el.classList.add("nuevo"));
  st.vistos[seccion] = ahora;
}

function ponerModo(modo, motivo) {
  st.modo = modo;
  const m = $("#modo");
  m.hidden = false;
  m.textContent = MODOS[modo] || modo;
  m.className = "chip modo " + modo;
  if (motivo) aviso(motivo, false);
}

// ------------------------------------------------------------------ WebSocket
function conectar() {
  st.ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`);
  st.ws.onmessage = (e) => {
    const { evento, datos } = JSON.parse(e.data);
    (manejar[evento] || (() => {}))(datos);
  };
  st.ws.onclose = () => aviso("Se perdió la conexión con el servidor. Recarga la página.", true);
}
const enviar = (o) => st.ws && st.ws.readyState === 1 && st.ws.send(JSON.stringify(o));

const manejar = {
  sesion(d) {
    $("#preparar").hidden = true;
    $("#panel").hidden = false;
    const c = d.cliente;
    $("#expediente").innerHTML = `
      <div class="empresa">${esc(c.empresa)}</div>
      <div class="tenue">${esc(c.industria)} · ${esc(c.ciudad)} · ${esc(c.empleados)} empleados · ${esc(c.id)}</div>
      <blockquote>«${esc(c.mensaje_inicial)}»</blockquote>
      <p class="tenue"><b>Por confirmar:</b> ${esc(c.informacion_que_falta)}</p>`;
    $("#ctl-mic").hidden = d.modo !== "microfono";
    $("#ctl-sim").hidden = d.modo === "microfono";
  },
  modo(d) { ponerModo(d.modo, d.motivo); if (d.motivo === "Fin del guion simulado") $("#sim").textContent = "✓ Llamada terminada"; },
  error(d) { aviso(d.mensaje, true); },
  analisis(d) {
    st.analizando = d.en_curso;
    $("#analizando").hidden = !d.en_curso;
    if (!d.en_curso) mic.enviarPendiente();
  },
  transcript(d) {
    const f = d.frase;
    const div = document.createElement("div");
    div.className = `frase ${f.hablante} nuevo`;
    div.innerHTML = `<span class="quien">${f.hablante === "vendedor" ? "Vendedor" : "Cliente"}</span>${esc(f.texto)}`;
    const t = $("#transcripcion");
    t.appendChild(div);
    t.scrollTop = t.scrollHeight;
  },
  triage(d) {
    const s = $("#semaforo");
    s.className = `tarjeta semaforo ${d.estado}`;
    $("#sem-etiqueta").textContent = d.etiqueta;
    const reglas = d.reglas_activadas.map((r) => `
      <div class="regla"><b>${esc(r.regla)}</b> ${esc(r.texto)}
        ${r.cita ? `<div class="cita">Cliente: «${esc(r.cita)}»</div>` : ""}
        ${r.detalle ? `<div class="tenue">${esc(r.detalle)}</div>` : ""}</div>`).join("");
    const falt = d.faltantes.filter((f) => f.bloquea);
    const rc = d.resumen_cotizacion;
    s.querySelector("#sem-detalle").innerHTML = `
      ${reglas}
      ${d.estado !== "rojo" && falt.length ? `<div>Faltan ${falt.length} dato(s) para cotizar:
         <ul>${falt.map((f) => `<li>${esc(f.pregunta)}</li>`).join("")}</ul></div>` : ""}
      ${d.estado === "verde" ? "<div>El vendedor puede cotizar solo: no hace falta arquitecto.</div>" : ""}
      <div class="tenue">Estimado: ${dinero(rc.mensual)}/mes + ${dinero(rc.cargos_unicos)} de cargos únicos (sin IVA)
        · ${d.lineas_estandar} línea(s) estándar · ${d.lineas_a_la_medida} con arquitecto
        ${rc.requiere_autorizacion_gerente ? " · <b>requiere autorización del gerente</b>" : ""}</div>`;
    s.classList.add("nuevo");
    setTimeout(() => s.classList.remove("nuevo"), 2000);
    pintarFuera(d.fuera_de_catalogo);
  },
  notes_update(d) {
    const iconos = { completo: "✓ completo", incompleto: "◐ incompleto", faltante: "○ faltante" };
    pintar("notas", $("#notas"), d.notas, (n) => n.tema + n.estado + n.resumen, (n) => `
      <div class="nota"><span class="estado ${esc(n.estado)}">${iconos[n.estado] || esc(n.estado)}</span>
        <b>${esc(n.tema)}:</b> ${esc(n.resumen)}</div>`);
    const c = d.cobertura;
    $("#cobertura").textContent = c.total ? `· preguntas clave cubiertas: ${c.respondidas} de ${c.total} (${c.pct}%)` : "";
  },
  suggested_question(d) {
    const p = $("#pregunta");
    if (!d.texto) return;
    if (p.textContent !== d.texto) {
      p.textContent = d.texto;
      p.classList.remove("tenue", "nuevo");
      void p.offsetWidth;
      p.classList.add("nuevo");
    }
    $("#pregunta-porque").textContent = d.por_que ? `${d.por_que} (fuente: ${d.fuente})` : "";
  },
  glossary(d) {
    pintar("glosario", $("#glosario"), d.terminos, (g) => g.termino, (g) =>
      `<dt>${esc(g.termino)}</dt><dd>${esc(g.en_lenguaje_comercial)}</dd>`);
  },
  suggestion(d) {
    if (!d.productos.length) return;
    pintar("productos", $("#productos"), d.productos, (p) => p.sku + p.estado, (p) => `
      <div class="producto ${esc(p.estado)}">
        <div class="nombre">${esc(p.nombre)}</div>
        <div class="sku">${esc(p.sku)} · ${esc(p.tipo)}${p.cantidad != null ? ` · cantidad: ${esc(p.cantidad)}` : ""}</div>
        <div class="cita">Cliente: «${esc(p.cita)}»</div>
        <div class="dile"><b>Dile al cliente:</b> ${esc(p.dile_al_cliente)}</div>
        <div class="acciones">
          <button class="ok ${p.estado === "confirmado" ? "activo" : ""}" data-sku="${esc(p.sku)}" data-ok="1">✓ Correcto</button>
          <button class="no ${p.estado === "descartado" ? "activo" : ""}" data-sku="${esc(p.sku)}" data-ok="0">✗ No aplica</button>
        </div>
      </div>`);
  },
  feedback() {},
  blocked(d) {
    const b = $("#bloqueados");
    if (!d.total) { b.innerHTML = ""; return; }
    b.innerHTML = `<details class="bloq"><summary>🛡 ${d.total} sugerencia(s) de la IA bloqueada(s) por no tener respaldo</summary>
      <ul>${d.items.map((x) => `<li>${esc(x.item.sku || x.item.nombre || x.item.que_pide || x.tipo)}:
        ${esc(x.motivo)}${x.item.cita ? ` — <span class="cita">«${esc(x.item.cita)}»</span>` : ""}</li>`).join("")}</ul>
      </details>`;
  },
  proposal_ready(d) { pintarResultado(d); },
};

function pintarFuera(lista) {
  pintar("fuera", $("#fuera"), lista || [], (x) => x.que_pide, (x) => `
    <div class="no-prometer">
      <div class="titulo">⛔ No prometer: ${esc(x.que_pide)}</div>
      <div class="cita">Cliente: «${esc(x.cita)}»</div>
      <div><b>Dile al cliente:</b> «Lo reviso con un especialista y te confirmo».</div>
    </div>`);
}

$("#productos").addEventListener("click", (e) => {
  const b = e.target.closest("button[data-sku]");
  if (b) enviar({ tipo: "feedback", sku: b.dataset.sku, correcto: b.dataset.ok === "1" });
});

// ------------------------------------------------------------------ resultado final
function pintarResultado(d) {
  mic.detener();
  $("#panel").hidden = true;
  $("#resultado").hidden = false;
  window.scrollTo(0, 0);
  const i = d.impacto, b = i.linea_base;
  const metricas = [
    ["Sesiones de levantamiento", i.sesiones, `Antes: ${b.sesiones}`],
    ["Tiempo hasta la propuesta", `${i.minutos_a_propuesta} min`, `Antes: hasta ${b.dias_hasta_propuesta} días`],
    ["Preguntas clave cubiertas", `${i.preguntas_cubiertas_pct}%`, i.preguntas_cubiertas],
    ["Triaje final", i.triaje, i.requiere_arquitecto ? "Con arquitecto, con brief listo" : `Antes: arquitecto ${b.arquitecto}`],
    ["Líneas estándar / con arquitecto", `${i.lineas_estandar} / ${i.lineas_a_la_medida}`, "Lo estándar ya va cotizado"],
    ["Sugerencias bloqueadas", i.sugerencias_bloqueadas, "Sin respaldo en la llamada o en el catálogo"],
  ];
  $("#impacto").innerHTML = metricas.map(([t, v, a]) =>
    `<div class="metrica"><div class="tenue">${esc(t)}</div><div class="valor">${esc(v)}</div><div class="antes">${esc(a)}</div></div>`).join("");

  const c = d.cotizacion;
  if (!d.confirmados.length) {
    $("#propuesta").innerHTML = `<p class="mal">No se confirmó ningún producto con ✓, así que la propuesta va vacía.</p>`;
  } else {
    const filas = c.renglones.map((r) => `<tr>
      <td><b>${esc(r.sku)}</b><br>${esc(r.nombre)}<div class="tenue">${esc(r.notas.join(" · "))}</div>
        <div class="tenue" title="${esc(r.fuente)}">Fuente: catálogo${r.supuestos.length ? " · " + esc(r.supuestos.join(", ")) : ""}</div></td>
      <td class="num">${r.cantidad ?? "?"}</td>
      <td class="num">${dinero(r.mensual_neto)}${r.descuento_pct ? `<div class="tenue">−${r.descuento_pct}%</div>` : ""}</td>
      <td class="num">${dinero(r.cargo_unico)}</td>
      <td>${esc(r.estado)}${r.requiere_autorizacion ? "<div class='mal'>autorización gerente</div>" : ""}</td></tr>`).join("");
    $("#propuesta").innerHTML = `
      <p class="tenue">Plazo ${c.plazo_meses} meses · vigencia hasta ${esc(c.vigencia_hasta)} · precios en MXN</p>
      <div class="tabla-scroll"><table>
        <thead><tr><th>Producto</th><th class="num">Cant.</th><th class="num">Mensual</th><th class="num">Único</th><th>Estado</th></tr></thead>
        <tbody>${filas}</tbody></table></div>
      <div class="totales tabla-scroll"><table>
        <tr><th></th><th class="num">Subtotal</th><th class="num">IVA ${c.iva_pct}%</th><th class="num">Total</th></tr>
        <tr><td>Mensualidad</td><td class="num">${dinero(c.mensual.subtotal)}</td><td class="num">${dinero(c.mensual.iva)}</td><td class="num"><b>${dinero(c.mensual.total)}</b></td></tr>
        <tr><td>Cargos únicos</td><td class="num">${dinero(c.cargos_unicos.subtotal)}</td><td class="num">${dinero(c.cargos_unicos.iva)}</td><td class="num"><b>${dinero(c.cargos_unicos.total)}</b></td></tr>
      </table></div>
      <p class="tenue">Cargos únicos: opción de 3 pagos de ${dinero(c.cargos_unicos.opcion_3_mensualidades)}.
        ${c.requiere_autorizacion_gerente ? "<b class='mal'>El descuento total pasa de 10%: requiere autorización del gerente.</b>" : ""}</p>
      <p class="tenue">${esc(c.aviso)} BORRADOR.</p>`;
  }
  const a = d.archivos || {};
  const etiquetas = { propuesta_docx: "📄 Propuesta (Word)", propuesta_pdf: "📄 Propuesta (PDF)", brief_docx: "📋 Brief para arquitecto (Word)" };
  $("#archivos").innerHTML = Object.entries(a).filter(([, v]) => v).map(([k, v]) =>
    `<a class="boton secundario" href="/salidas/${encodeURIComponent(v)}">${etiquetas[k] || esc(k)}</a>`).join("");
}

// ------------------------------------------------------------------ micrófono (Web Speech API)
const Reconocedor = window.SpeechRecognition || window.webkitSpeechRecognition;
const mic = {
  rec: null, activo: false, buffer: [], provisional: "", desde: 0, reloj: null,

  iniciar() {
    if (!Reconocedor) return;
    this.rec = new Reconocedor();
    this.rec.lang = "es-MX";
    this.rec.continuous = true;
    this.rec.interimResults = true;
    this.rec.onresult = (e) => {
      let prov = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const txt = e.results[i][0].transcript.trim();
        if (e.results[i].isFinal) { if (txt) this.buffer.push(txt); this.enviarPendiente(); }
        else prov += txt + " ";
      }
      if (prov && !this.provisional) this.desde = Date.now();
      this.provisional = prov.trim();
      $("#provisional").textContent = this.provisional;
    };
    this.rec.onend = () => {  // Chrome corta el reconocimiento cada cierto tiempo: se reinicia solo
      if (this.activo) setTimeout(() => { try { this.rec.start(); } catch (_) {} }, 250);
    };
    this.rec.onerror = (e) => {
      if (e.error === "not-allowed" || e.error === "service-not-allowed") {
        aviso("Chrome no tiene permiso para usar el micrófono. Revisa el candado de la barra de direcciones.", true);
        this.detener();
      }
    };
    this.activo = true;
    this.rec.start();
    // Cada 10 s: si hay texto provisional que no se cierra, se fuerza el cierre de la frase.
    this.reloj = setInterval(() => {
      if (this.provisional && Date.now() - this.desde > 10000) { try { this.rec.stop(); } catch (_) {} }
      this.enviarPendiente();
    }, 10000);
    $("#mic").textContent = "⏸ Pausar";
    $("#escuchando").hidden = false;
  },

  detener() {
    this.activo = false;
    clearInterval(this.reloj);
    if (this.rec) try { this.rec.stop(); } catch (_) {}
    this.enviarPendiente(true);
    $("#mic").textContent = "🎙 Iniciar escucha";
    $("#escuchando").hidden = true;
    $("#provisional").textContent = "";
  },

  /** Envía lo acumulado; si hay un análisis en curso, espera (salvo que se fuerce). */
  enviarPendiente(forzar = false) {
    if (!this.buffer.length || (st.analizando && !forzar)) return;
    enviar({ tipo: "frase", hablante: st.hablante, texto: this.buffer.join(" ") });
    this.buffer = [];
  },
};

$("#mic").addEventListener("click", () => (mic.activo ? mic.detener() : mic.iniciar()));
document.querySelectorAll(".seg").forEach((b) => b.addEventListener("click", () => {
  mic.enviarPendiente(true);  // lo dicho hasta ahora pertenece al hablante anterior
  st.hablante = b.dataset.h;
  document.querySelectorAll(".seg").forEach((x) => x.classList.toggle("activo", x === b));
}));

// ------------------------------------------------------------------ simulación y cierre
$("#sim").addEventListener("click", () => {
  const b = $("#sim");
  if (b.dataset.corriendo === "1") { enviar({ tipo: "pausar" }); b.dataset.corriendo = "0"; b.textContent = "▶ Continuar"; }
  else { enviar({ tipo: "simular" }); b.dataset.corriendo = "1"; b.textContent = "⏸ Pausar"; }
});
$("#cerrar").addEventListener("click", () => {
  mic.detener();
  $("#cerrar").disabled = true;
  $("#cerrar").textContent = "Generando propuesta…";
  enviar({ tipo: "cerrar" });
});

// ------------------------------------------------------------------ preparar la reunión
const modoElegido = () => document.querySelector('input[name="modo"]:checked').value;
function revisarPreparacion() {
  const opt = $("#cliente").selectedOptions[0];
  const conGuion = opt && opt.dataset.guion === "1";
  document.querySelectorAll('input[name="modo"]').forEach((r) => {
    if (r.value !== "microfono") r.disabled = !conGuion;
  });
  if (!conGuion && modoElegido() !== "microfono") document.querySelector('input[value="microfono"]').checked = true;
  const esMic = modoElegido() === "microfono";
  $("#consentimiento").hidden = !esMic;
  $("#sin-soporte").hidden = !(esMic && !Reconocedor);
  $("#empezar").disabled = esMic && (!Reconocedor || !$("#acepto").checked);
}
$("#preparar").addEventListener("change", revisarPreparacion);
$("#empezar").addEventListener("click", () => {
  aviso("");
  ponerModo(modoElegido());
  enviar({ tipo: "iniciar", cliente_id: $("#cliente").value, modo: modoElegido() });
});

$("#ver-aprendido").addEventListener("click", async () => {
  const filas = await (await fetch("/api/aprendizajes")).json();
  $("#tabla-aprendido").innerHTML = filas.length ? `<div class="tabla-scroll"><table>
    <tr><th>Frase del cliente</th><th>Producto</th><th class="num">✓</th><th class="num">✗</th><th>¿Se usa?</th></tr>
    ${filas.map((f) => `<tr><td>«${esc(f.frase_cliente)}»</td><td>${esc(f.sku)}<br><span class="tenue">${esc(f.nombre)}</span></td>
      <td class="num">${f.confirmados}</td><td class="num">${f.descartados}</td><td>${f.se_usa ? "Sí" : "No"}</td></tr>`).join("")}
    </table></div>` : "<p>Todavía no hay confirmaciones.</p>";
  $("#dlg-aprendido").showModal();
});

(async function arrancar() {
  const [clientes, salud] = await Promise.all([
    (await fetch("/api/clientes")).json(), (await fetch("/api/salud")).json()]);
  $("#cliente").innerHTML = clientes.map((c) =>
    `<option value="${esc(c.id)}" data-guion="${c.tiene_guion ? 1 : 0}">${esc(c.id)} · ${esc(c.empresa)}${c.tiene_guion ? " · con guion" : ""}</option>`).join("");
  const preferido = clientes.find((c) => c.id === "CASO-02");
  if (preferido) $("#cliente").value = preferido.id;
  const m = document.querySelector(`input[name="modo"][value="${salud.modo_por_defecto}"]`);
  if (m) m.checked = true;
  if (!salud.clave_configurada) aviso("No hay clave de Claude configurada: usa «Repetición (sin IA)».");
  revisarPreparacion();
  conectar();
})();
