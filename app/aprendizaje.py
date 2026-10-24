"""Aprendizaje con el vendedor (✓ Correcto / ✗ No aplica), guardado en SQLite."""
from app import db

MAX_EJEMPLOS = 40


def registrar(frase: str, sku: str, correcto: bool) -> None:
    frase = (frase or "").strip()
    if not frase:
        return
    conn = db.conectar()
    with conn:
        conn.execute(
            "INSERT INTO aprendizajes (frase_cliente, sku, confirmados, descartados) VALUES (?, ?, ?, ?)"
            " ON CONFLICT (frase_cliente, sku) DO UPDATE SET"
            " confirmados = confirmados + excluded.confirmados,"
            " descartados = descartados + excluded.descartados,"
            " fecha = datetime('now','localtime')",
            (frase, sku, int(correcto), int(not correcto)))
    conn.close()


def ejemplos(limite: int = MAX_EJEMPLOS) -> list[dict]:
    """Los que se inyectan en el prompt: confirmados > descartados, los más confirmados primero."""
    conn = db.conectar()
    filas = conn.execute(
        "SELECT frase_cliente, sku, confirmados, descartados FROM aprendizajes"
        " WHERE confirmados > descartados ORDER BY confirmados DESC, fecha DESC LIMIT ?", (limite,)).fetchall()
    conn.close()
    return [dict(f) for f in filas]


def tabla() -> list[dict]:
    conn = db.conectar()
    filas = conn.execute(
        "SELECT a.frase_cliente, a.sku, p.nombre, a.confirmados, a.descartados, a.fecha,"
        " (a.confirmados > a.descartados) AS se_usa FROM aprendizajes a LEFT JOIN productos p ON p.sku = a.sku"
        " ORDER BY a.confirmados DESC, a.fecha DESC").fetchall()
    conn.close()
    return [dict(f) for f in filas]
