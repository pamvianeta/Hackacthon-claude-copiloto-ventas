"""Muestra en pantalla el triaje y la cotización de un caso de ejemplo (sin IA).

Uso:  py -m app.demo_motor CASO-02
"""
import json
import sys

from app import config
from app.motor import evaluar


def _m(x):
    return "—" if x is None else f"${x:,.2f}"


def main(caso: str):
    with open(config.RAIZ / "guiones" / "requerimientos_ejemplo.json", encoding="utf-8") as f:
        ejemplos = json.load(f)
    if caso not in ejemplos:
        print(f"Casos disponibles: {', '.join(k for k in ejemplos if not k.startswith('_'))}")
        return
    res = evaluar(ejemplos[caso])
    t, c = res["triaje"], res["cotizacion"]
    print(f"\n{caso} · TRIAJE: {t['etiqueta'].upper()} ({t['estado']})")
    for a in t["reglas_activadas"]:
        print(f"  • {a['regla']}: {a['texto']}\n      cita: «{a['cita']}»  [{a['detalle'] or ''}]")
    for f in t["faltantes"]:
        print(f"  ? {'(obligatoria) ' if f['bloquea'] else ''}{f['pregunta']}")
    for x in t["fuera_de_catalogo"]:
        print(f"  ✗ NO PROMETER: {x['que_pide']} — «{x['cita']}»")
    print(f"\nCOTIZACIÓN · plazo {c['plazo_meses']} meses · vigencia hasta {c['vigencia_hasta']}")
    for r in c["renglones"]:
        desc = ", ".join(f"{d['concepto']} −{d['pct']}%" for d in r["descuentos"])
        print(f"  {r['sku']:12} {r['nombre'][:38]:38} x{r['cantidad'] if r['cantidad'] is not None else '?':<5}"
              f" mensual {_m(r['mensual_neto']):>12}  único {_m(r['cargo_unico']):>12}  [{r['estado']}]")
        if desc:
            print(f"      descuentos: {desc}{'  ⚠ requiere gerente' if r['requiere_autorizacion'] else ''}")
        for n in r["notas"]:
            print(f"      nota: {n}")
        if r["supuestos"]:
            print(f"      supuestos: {', '.join(r['supuestos'])}")
    m, u = c["mensual"], c["cargos_unicos"]
    print(f"\n  Mensual:       subtotal {_m(m['subtotal'])}  IVA {_m(m['iva'])}  total {_m(m['total'])}")
    print(f"  Cargos únicos: subtotal {_m(u['subtotal'])}  IVA {_m(u['iva'])}  total {_m(u['total'])}"
          f"  (o 3 pagos de {_m(u['opcion_3_mensualidades'])})")
    print(f"\n  {c['aviso']}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main(sys.argv[1] if len(sys.argv) > 1 else "")
