import copy
import csv
import shutil

from app import config, db
from app.catalogo import leer_json
from app.validador import comparar_csv, comparar_db, validar_json

DATOS = leer_json()


def test_json_sin_errores():
    assert [h for h in validar_json(DATOS) if h.nivel == "ERROR"] == []


def test_csv_y_db_coinciden_con_json():
    carpeta = config.CATALOGO_JSON.parent
    assert comparar_csv(DATOS, carpeta / "csv") == []
    assert comparar_db(DATOS, carpeta / "catalogo-simulado.db") == []


def test_detecta_referencia_rota_y_sku_repetido():
    d = copy.deepcopy(DATOS)
    d["productos"][0]["requiere_alguno_de"] = ["SIM-NO-EXISTE"]
    d["productos"].append(copy.deepcopy(d["productos"][1]))
    errores = [h.mensaje for h in validar_json(d) if h.nivel == "ERROR"]
    assert any("SIM-NO-EXISTE" in m for m in errores)
    assert any("repetida" in m for m in errores)


def test_detecta_precio_distinto_en_csv(tmp_path):
    origen = config.CATALOGO_JSON.parent / "csv"
    shutil.copytree(origen, tmp_path / "csv")
    ruta = tmp_path / "csv" / "productos.csv"
    with open(ruta, encoding="utf-8-sig", newline="") as f:
        filas = list(csv.DictReader(f))
    filas[0]["precio_mensual_mxn"] = "9999"
    with open(ruta, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=filas[0].keys())
        w.writeheader()
        w.writerows(filas)
    difs = comparar_csv(DATOS, tmp_path / "csv")
    assert len(difs) == 1 and "SIM-DC-01.precio_mensual_mxn" in difs[0].mensaje


def test_carga_sqlite(tmp_path):
    ruta = tmp_path / "prueba.db"
    conteos = db.inicializar(ruta)
    assert conteos["productos"] == 45
    assert conteos["clientes"] == 10
    assert conteos["paquete_productos"] == sum(len(q["productos"]) for q in DATOS["paquetes"])
    # Recargar no duplica clientes
    assert db.inicializar(ruta)["clientes"] == 10
