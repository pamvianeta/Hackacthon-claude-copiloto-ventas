"""Base SQLite del copiloto.

- Tablas del catálogo: se borran y se recargan desde el JSON en cada arranque
  (el JSON manda; la base es solo una copia para consultar).
- Tablas de la app (sesiones, notas, aprendizajes, propuestas...): se conservan.
- Clientes: se precargan los 10 casos como expedientes (sin duplicar).

Uso manual:  py -m app.db
"""
import json
import sqlite3
from pathlib import Path

from app import config
from app.catalogo import leer_json

ESQUEMA_CATALOGO = """
DROP TABLE IF EXISTS paquete_productos;
DROP TABLE IF EXISTS paquetes;
DROP TABLE IF EXISTS productos;
DROP TABLE IF EXISTS familias;
DROP TABLE IF EXISTS condiciones_comerciales;
DROP TABLE IF EXISTS reglas_escalamiento;
DROP TABLE IF EXISTS aviso;

CREATE TABLE aviso (texto TEXT);
CREATE TABLE familias (id TEXT PRIMARY KEY, nombre TEXT, descripcion TEXT, problemas_que_resuelve TEXT);
CREATE TABLE productos (
  sku TEXT PRIMARY KEY, familia TEXT REFERENCES familias(id), nombre TEXT, descripcion TEXT,
  tipo TEXT, segmento TEXT, unidad_cobro TEXT,
  precio_mensual_mxn REAL, cargo_unico_mxn REAL, cantidad_minima INTEGER, cantidad_maxima INTEGER,
  plazo_minimo_meses INTEGER, nivel_servicio TEXT, tiempo_implementacion TEXT,
  requiere_alguno_de TEXT,   -- lista en JSON
  se_recomienda_con TEXT,    -- lista en JSON
  senal_del_cliente TEXT,
  preguntas_clave TEXT,      -- lista en JSON
  cuando_entra_arquitecto TEXT);
CREATE TABLE paquetes (id TEXT PRIMARY KEY, nombre TEXT, para_quien TEXT, descuento_pct REAL);
CREATE TABLE paquete_productos (paquete TEXT REFERENCES paquetes(id), sku TEXT REFERENCES productos(sku));
CREATE TABLE condiciones_comerciales (concepto TEXT PRIMARY KEY, regla TEXT);
CREATE TABLE reglas_escalamiento (id TEXT PRIMARY KEY, cuando_entra_un_arquitecto TEXT);
"""

ESQUEMA_APP = """
CREATE TABLE IF NOT EXISTS clientes (
  id TEXT PRIMARY KEY, empresa TEXT, industria TEXT, ciudad TEXT, empleados INTEGER,
  mensaje_inicial TEXT, informacion_que_falta TEXT,
  tipo_esperado TEXT          -- respuesta de referencia del reto; solo para pruebas, no se muestra al vendedor
);
CREATE TABLE IF NOT EXISTS sesiones (
  id INTEGER PRIMARY KEY AUTOINCREMENT, cliente_id TEXT REFERENCES clientes(id),
  modo TEXT CHECK (modo IN ('microfono','simulacion','repeticion')),
  inicio TEXT DEFAULT (datetime('now','localtime')), fin TEXT,
  triaje_final TEXT, preguntas_cubiertas_pct REAL, minutos_a_propuesta REAL
);
CREATE TABLE IF NOT EXISTS frases (
  id INTEGER PRIMARY KEY AUTOINCREMENT, sesion_id INTEGER REFERENCES sesiones(id),
  hablante TEXT CHECK (hablante IN ('cliente','vendedor')), texto TEXT,
  fecha TEXT DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS notas (
  id INTEGER PRIMARY KEY AUTOINCREMENT, sesion_id INTEGER REFERENCES sesiones(id),
  campo TEXT, valor TEXT, estado TEXT CHECK (estado IN ('completo','incompleto','faltante')),
  cita TEXT, fecha TEXT DEFAULT (datetime('now','localtime')),
  UNIQUE (sesion_id, campo)
);
CREATE TABLE IF NOT EXISTS requerimientos (
  id INTEGER PRIMARY KEY AUTOINCREMENT, sesion_id INTEGER REFERENCES sesiones(id),
  sku TEXT, cantidad REAL, cita TEXT,
  estado TEXT CHECK (estado IN ('sugerido','confirmado','descartado','bloqueado')),
  motivo_bloqueo TEXT, fecha TEXT DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS aprendizajes (
  id INTEGER PRIMARY KEY AUTOINCREMENT, frase_cliente TEXT, sku TEXT,
  confirmados INTEGER DEFAULT 0, descartados INTEGER DEFAULT 0,
  fecha TEXT DEFAULT (datetime('now','localtime')),
  UNIQUE (frase_cliente, sku)
);
CREATE TABLE IF NOT EXISTS propuestas (
  id INTEGER PRIMARY KEY AUTOINCREMENT, sesion_id INTEGER REFERENCES sesiones(id),
  cliente_id TEXT REFERENCES clientes(id), plazo_meses INTEGER, triaje TEXT,
  subtotal_mensual REAL, subtotal_unico REAL, iva REAL, total REAL,
  descuento_max_pct REAL, requiere_autorizacion INTEGER, vigencia_hasta TEXT,
  archivo_docx TEXT, archivo_pdf TEXT, fecha TEXT DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS propuesta_lineas (
  id INTEGER PRIMARY KEY AUTOINCREMENT, propuesta_id INTEGER REFERENCES propuestas(id),
  sku TEXT, nombre TEXT, cantidad REAL,
  mensual_lista REAL, mensual_neto REAL, cargo_unico REAL,
  descuentos TEXT,            -- lista en JSON: [{"concepto", "pct"}]
  estado TEXT CHECK (estado IN ('cotizado','por definir','pendiente de arquitecto')),
  fuente TEXT, nota TEXT
);
"""


def conectar(ruta: Path | None = None) -> sqlite3.Connection:
    ruta = Path(ruta or config.DB_PATH)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(ruta, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _lista(v):
    return json.dumps(v, ensure_ascii=False)


def inicializar(ruta: Path | None = None, datos: dict | None = None) -> dict:
    """Crea/recarga la base y devuelve cuántos registros quedaron por tabla."""
    datos = datos or leer_json()
    conn = conectar(ruta)
    with conn:
        conn.executescript(ESQUEMA_CATALOGO)
        conn.executescript(ESQUEMA_APP)
        conn.execute("INSERT INTO aviso VALUES (?)", (datos["aviso"],))
        conn.executemany(
            "INSERT INTO familias VALUES (:id, :nombre, :descripcion, :problemas_que_resuelve)",
            datos["familias"])
        for p in datos["productos"]:
            fila = dict(p, requiere_alguno_de=_lista(p["requiere_alguno_de"]),
                        se_recomienda_con=_lista(p["se_recomienda_con"]),
                        preguntas_clave=_lista(p["preguntas_clave"]))
            conn.execute(
                "INSERT INTO productos VALUES (:sku, :familia, :nombre, :descripcion, :tipo, :segmento,"
                " :unidad_cobro, :precio_mensual_mxn, :cargo_unico_mxn, :cantidad_minima, :cantidad_maxima,"
                " :plazo_minimo_meses, :nivel_servicio, :tiempo_implementacion, :requiere_alguno_de,"
                " :se_recomienda_con, :senal_del_cliente, :preguntas_clave, :cuando_entra_arquitecto)", fila)
        for q in datos["paquetes"]:
            conn.execute("INSERT INTO paquetes VALUES (?, ?, ?, ?)",
                         (q["id"], q["nombre"], q["para_quien"], q["descuento_pct"]))
            conn.executemany("INSERT INTO paquete_productos VALUES (?, ?)",
                             [(q["id"], s) for s in q["productos"]])
        conn.executemany("INSERT INTO condiciones_comerciales VALUES (:concepto, :regla)",
                         datos["condiciones_comerciales"])
        conn.executemany("INSERT INTO reglas_escalamiento VALUES (:id, :cuando_entra_un_arquitecto)",
                         datos["reglas_escalamiento"])
        conn.executemany(
            "INSERT OR IGNORE INTO clientes VALUES (:id, :empresa, :industria, :ciudad, :empleados,"
            " :mensaje_inicial, :informacion_que_falta, :tipo_de_caso)", datos["casos_clientes"])
    tablas = ["familias", "productos", "paquetes", "paquete_productos", "condiciones_comerciales",
              "reglas_escalamiento", "clientes", "sesiones", "aprendizajes", "propuestas"]
    conteos = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tablas}
    conn.close()
    return conteos


if __name__ == "__main__":
    for tabla, n in inicializar().items():
        print(f"{tabla:25} {n}")
    print(f"\nBase lista en {config.DB_PATH}")
