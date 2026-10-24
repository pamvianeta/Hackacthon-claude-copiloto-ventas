# Catálogo simulado · Hackathon Claude

> **Aviso:** estos son datos SIMULADOS para el Hackathon Claude. No son productos, precios ni condiciones oficiales de Alestra. Tienen el mismo tipo de información que usa el equipo comercial, para que construyas y pruebes tu solución.

## Qué hay aquí

| Archivo | Para qué sirve |
|---|---|
| `catalogo-simulado.xlsx` | Para leerlo y explorarlo, con una hoja por tabla. |
| `catalogo-simulado.db` | Base de datos SQLite lista para consultar con SQL. |
| `catalogo-simulado.json` | Todo en un solo archivo. Es el más fácil de pasarle a Claude o de leer desde código. |
| `csv/` | Una tabla por archivo, para importarla donde quieras. |

## Tablas

- **familias**: las 7 familias de soluciones: Data Center, Microsoft 365, Backup inmutable, AWS, Azure, OCI y Agentes de IA.
- **productos**: 45 productos. Cada uno trae:
  - precio mensual y cargo único;
  - para quién es;
  - qué productos necesita antes (`requiere_alguno_de`);
  - con qué se recomienda;
  - qué dice un cliente que lo necesita (`senal_del_cliente`);
  - qué preguntar (`preguntas_clave`);
  - cuándo hace falta un arquitecto.
- **paquetes**: combinaciones frecuentes con descuento.
- **condiciones_comerciales**: plazos, descuentos, IVA y vigencia de la propuesta.
- **reglas_escalamiento**: cuándo un caso deja de ser estándar y necesita un arquitecto de soluciones.
- **casos_clientes**: 10 clientes ficticios con su primer mensaje, la información que falta preguntar y el tipo de caso (estándar, mixto o a la medida). Úsalos para probar tu demo.

## Tipos de producto

- **estándar**: precio fijo; el vendedor lo puede cotizar solo.
- **configurable**: precio fijo por unidad, pero hay que dimensionar cuántos usuarios, servidores o TB.
- **a la medida**: no tiene precio de lista; lo diseña un arquitecto.

## Notas

- Precios en pesos mexicanos, **sin IVA**.
- En CSV, SQLite y Excel, las listas van separadas con `|` (en Excel, con saltos de línea). En el JSON ya vienen como listas.
- En la base SQLite, la vista `v_productos` muestra cada producto con el nombre de su familia. La tabla `paquete_productos` dice qué productos tiene cada paquete.

Ejemplo de consulta SQL:

```sql
SELECT sku, nombre, precio_mensual_mxn
FROM v_productos
WHERE familia_nombre = 'Backup inmutable' AND tipo = 'estándar';
```
