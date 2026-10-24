"""Cotizador determinista. Todo precio sale del catálogo o de reglas.json; nada lo calcula Claude.

Cada renglón lleva su SKU, su fuente y los supuestos (SUP-xx) que se le aplicaron.
"""
from datetime import date, timedelta

# Unidades en las que, si no hay cantidad, se asume 1 (no son "por usuario/servidor/TB").
UNIDADES_CANTIDAD_UNO = {"por mes", "cargo único", "cargo único por prueba", "% del consumo (mínimo mensual)"}


def _cargo_unico_por_cantidad(unidad: str) -> bool:
    """SUP-01: el cargo único se cobra una vez por renglón en productos 'por <unidad> al mes'.
    En 'por mes' (cada unidad es una instancia) y en 'cargo único por X' sí se multiplica."""
    return not (unidad.startswith("por ") and unidad.endswith("al mes"))


def _r(x):
    return None if x is None else round(x + 0.0, 2)


def cotizar(lineas: list[dict], hechos: dict, plazo: int, pendientes: dict, catalogo, reglas: dict,
            hoy: date | None = None) -> dict:
    """lineas: [{sku, cantidad, cita, origen}]; hechos: {nombre: valor}; pendientes: {sku: motivo}."""
    par = reglas["parametros"]
    pct_plazo = par["descuento_plazo_pct"].get(str(plazo), 0)
    soporte = par["soporte_247"]
    consumo = par["consumo"]
    vol = par["volumen_m365"]
    ia = par["conversaciones_ia"]
    renglones = []

    for ln in lineas:
        p = catalogo.productos[ln["sku"]]
        r = {
            "sku": p["sku"], "nombre": p["nombre"], "tipo": p["tipo"], "unidad": p["unidad_cobro"],
            "cantidad": ln.get("cantidad"), "cita": ln.get("cita"), "origen": ln.get("origen", "cliente"),
            "precio_unitario_mensual": p["precio_mensual_mxn"], "cargo_unico_unitario": p["cargo_unico_mxn"],
            "mensual_lista": None, "mensual_neto": None, "variable_mensual": 0.0, "cargo_unico": None,
            "descuentos": [], "descuento_pct": 0, "requiere_autorizacion": False,
            "estado": "cotizado", "notas": [], "supuestos": [],
            "fuente": f"catalogo-simulado.json › productos › {p['sku']} "
                      f"(precio_mensual_mxn={p['precio_mensual_mxn'] if p['precio_mensual_mxn'] is not None else 'sin precio'}, "
                      f"cargo_unico_mxn={p['cargo_unico_mxn'] if p['cargo_unico_mxn'] is not None else 'sin precio'})",
        }
        renglones.append(r)
        sku = p["sku"]

        if sku in pendientes or p["tipo"] == "a la medida":
            r["estado"] = "pendiente de arquitecto"
            r["notas"].append(pendientes.get(sku, "Producto a la medida: pendiente de arquitecto de soluciones"))
            continue

        if sku in consumo["skus"]:
            r["supuestos"].append(consumo["supuesto"])
            monto = hechos.get(consumo["skus"][sku])
            if monto is None:
                r["estado"] = "por definir"
                r["notas"].append("Según consumo: se cotiza con el consumo estimado del cliente")
            else:
                r["cantidad"] = 1
                r["mensual_lista"] = r["mensual_neto"] = float(monto)
                r["notas"].append("Monto estimado por el cliente; se cobra lo que realmente use. Sin descuentos")
            continue

        cantidad = ln.get("cantidad")
        if cantidad is None:
            if p["unidad_cobro"] in UNIDADES_CANTIDAD_UNO:
                cantidad = 1
                if sku == "SIM-BK-06":
                    r["supuestos"].append("SUP-12")
            else:
                r["estado"] = "por definir"
                r["notas"].append(f"Falta la cantidad ({p['unidad_cobro']})")
                continue
        mn = p["cantidad_minima"]
        if mn is not None and cantidad < mn:
            r["notas"].append(f"El mínimo es {mn}; se cotiza el mínimo (el cliente pidió {cantidad:g})")
            cantidad = mn
        r["cantidad"] = cantidad

        precio = p["precio_mensual_mxn"]
        if sku in soporte["skus"]:
            r["supuestos"].append(soporte["supuesto"])
            base = hechos.get(soporte["skus"][sku])
            if base is None:
                precio = soporte["minimo_mxn"]
                r["notas"].append(f"Se cotiza el mínimo de ${soporte['minimo_mxn']:,}; se ajusta al 10% del consumo")
            else:
                precio = max(soporte["minimo_mxn"], base * soporte["pct_consumo"] / 100)
                r["notas"].append(f"Máximo entre ${soporte['minimo_mxn']:,} y {soporte['pct_consumo']}% de "
                                  f"${base:,.0f} de consumo")
            r["precio_unitario_mensual"] = precio

        if precio is not None:
            r["mensual_lista"] = precio * cantidad
        if p["cargo_unico_mxn"] is not None:
            if _cargo_unico_por_cantidad(p["unidad_cobro"]):
                r["cargo_unico"] = p["cargo_unico_mxn"] * cantidad
            else:
                r["cargo_unico"] = p["cargo_unico_mxn"]
                if cantidad != 1:
                    r["supuestos"].append("SUP-01")
                    r["notas"].append("Cargo único una sola vez por renglón")

        if sku == ia["sku"]:
            r["supuestos"].append(ia["supuesto"])
            conv = hechos.get(ia["hecho"])
            if conv is None:
                r["notas"].append(f"Incluye {ia['incluidas']:,} conversaciones al mes; cada adicional "
                                  f"${ia['precio_adicional_mxn']}")
            else:
                extra = max(0, conv - ia["incluidas"])
                r["variable_mensual"] = extra * ia["precio_adicional_mxn"]
                r["notas"].append(f"{conv:,.0f} conversaciones/mes: {extra:,.0f} adicionales × "
                                  f"${ia['precio_adicional_mxn']} (sin descuento)")

        if r["mensual_lista"]:
            if pct_plazo:
                r["descuentos"].append({"concepto": f"Plazo {plazo} meses", "pct": pct_plazo})
            if sku in vol["skus"] and cantidad >= vol["desde_usuarios"]:
                r["descuentos"].append({"concepto": f"Volumen Microsoft 365 ({vol['desde_usuarios']}+ usuarios)",
                                        "pct": vol["pct"]})
                r["supuestos"].append(vol["supuesto"])

    # Paquetes (SUP-06): solo si TODOS sus productos están cotizados; un paquete por renglón; solo mensualidades.
    cotizados = {r["sku"] for r in renglones if r["estado"] == "cotizado"}
    paquetes_aplicados = []
    for q in catalogo.paquetes.values():
        if set(q["productos"]) <= cotizados:
            paquetes_aplicados.append({"id": q["id"], "nombre": q["nombre"], "pct": q["descuento_pct"]})
            for r in renglones:
                ya = any(d["concepto"].startswith("Paquete") for d in r["descuentos"])
                if r["sku"] in q["productos"] and r["mensual_lista"] and not ya and r["sku"] not in consumo["skus"]:
                    r["descuentos"].append({"concepto": f"Paquete {q['id']} {q['nombre']}", "pct": q["descuento_pct"]})
                    r["supuestos"].append("SUP-06")

    tope = par["descuento_max_sin_autorizacion_pct"]
    for r in renglones:
        if r["mensual_lista"] is not None:
            r["descuento_pct"] = sum(d["pct"] for d in r["descuentos"])
            r["requiere_autorizacion"] = r["descuento_pct"] > tope
            r["mensual_neto"] = r["mensual_lista"] * (1 - r["descuento_pct"] / 100) + r["variable_mensual"]
        if r["descuentos"]:
            r["supuestos"].append("SUP-03")
        if r["mensual_lista"] and r["descuentos"] and plazo != 12:
            r["supuestos"].append("SUP-14")
        r["supuestos"] = sorted(set(r["supuestos"]))
        for k in ("mensual_lista", "mensual_neto", "variable_mensual", "cargo_unico", "precio_unitario_mensual"):
            r[k] = _r(r[k])

    iva = par["iva_pct"] / 100
    mensual = sum(r["mensual_neto"] or 0 for r in renglones)
    unico = sum(r["cargo_unico"] or 0 for r in renglones)
    hoy = hoy or date.today()
    return {
        "plazo_meses": plazo,
        "renglones": renglones,
        "paquetes_aplicados": paquetes_aplicados,
        "mensual": {"subtotal": _r(mensual), "iva": _r(mensual * iva), "total": _r(mensual * (1 + iva))},
        "cargos_unicos": {"subtotal": _r(unico), "iva": _r(unico * iva), "total": _r(unico * (1 + iva)),
                          "opcion_3_mensualidades": _r(unico * (1 + iva) / 3)},
        "total_contrato": {"subtotal": _r(mensual * plazo + unico), "total": _r((mensual * plazo + unico) * (1 + iva))},
        "iva_pct": par["iva_pct"],
        "requiere_autorizacion_gerente": any(r["requiere_autorizacion"] for r in renglones),
        "descuento_max_pct": max([r["descuento_pct"] for r in renglones] or [0]),
        "renglones_por_definir": [r["sku"] for r in renglones if r["estado"] == "por definir"],
        "renglones_pendientes_arquitecto": [r["sku"] for r in renglones if r["estado"] == "pendiente de arquitecto"],
        "fecha": hoy.isoformat(),
        "vigencia_hasta": (hoy + timedelta(days=par["vigencia_dias"])).isoformat(),
        "aviso": catalogo.aviso,
    }
