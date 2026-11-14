#!/usr/bin/env python3
"""Convierte un CSV de inventario a un CSV importable en Odoo.

Pasos (en este orden):
  1. Normaliza y valida códigos de barras (UPC-A -> EAN-13; no corrige dígitos).
  2. Resuelve códigos de barras duplicados (interactivo o con --keep-policy).
  3. Resuelve productos con precio doble '$paquete($pieza)' conservando una
     sola versión (interactivo o con --variant-policy).
  4. Exporta el CSV de Odoo y los reportes de revisión.
"""

import argparse
import re
import sys
from pathlib import Path

import pandas as pd

COLUMNAS_REQUERIDAS = ["Codigo barras", "Nombre", "Presentacion", "Precio", "Costo"]
COLUMNAS_ODOO = [
    "name", "sale_price", "standard_price", "barcode",
    "uom_id", "type", "available_in_pos", "active",
]

# '$24.00($6.00)' -> (exterior=paquete, interior=pieza)
PRECIO_DOBLE = re.compile(r"\$\s*([\d.,]+)\s*\(\s*\$\s*([\d.,]+)\s*\)")
PRECIO_KG = re.compile(r"\$\s*\d+(\.\d+)?\s*/\s*kg\b", re.IGNORECASE)
PRIMER_NUMERO = re.compile(r"\d[\d,]*(?:\.\d+)?|\.\d+")

OPCIONES_VARIANTE = {
    "1": ("unidad", "conservar la unidad (precio dentro del paréntesis)"),
    "2": ("paquete", "conservar el paquete (precio fuera del paréntesis)"),
    "3": ("eliminar", "eliminar el producto"),
}

MOTIVOS_BARCODE = {
    "vacio": "sin código de barras",
    "invalido": "formato o largo no reconocido",
}


# ── Utilidades de precio ───────────────────────────────────────────────
def a_numero(texto):
    try:
        return float(str(texto).replace(",", ""))
    except ValueError:
        return 0.0


def precio_doble(valor):
    """Devuelve (exterior, interior) o None si no tiene formato doble."""
    coincidencia = PRECIO_DOBLE.search(str(valor))
    if not coincidencia:
        return None
    return a_numero(coincidencia.group(1)), a_numero(coincidencia.group(2))


def limpiar_precio(valor):
    """Primer número del texto: '$30.00/kg' -> 30.0; '$24.00($6.00)' -> 24.0."""
    coincidencia = PRIMER_NUMERO.search(str(valor))
    return a_numero(coincidencia.group(0)) if coincidencia else 0.0


def es_cero(valor):
    """True si el precio/costo es 0 (en formato doble, si cualquiera es 0)."""
    doble = precio_doble(valor)
    if doble is not None:
        return 0.0 in doble
    return limpiar_precio(valor) == 0.0


def inferir_uom(precio):
    """'$30.00/kg' -> 'kg'. Todo lo demás -> 'Unidades'."""
    return "kg" if PRECIO_KG.search(str(precio)) else "Unidades"


# ── Códigos de barras ──────────────────────────────────────────────────
def validar_barcode(barcode):
    """Valida sin corregir. Devuelve (codigo, tipo, es_valido).

    - EAN-13 / EAN-8: se valida el dígito verificador tal cual viene.
    - UPC-A (12 dígitos): se normaliza a EAN-13 con un 0 al inicio.
    - Código interno de 4 dígitos: se acepta sin validar.
    - Vacío u otro formato/largo: se marca para revisión sin modificar.
    """
    b = str(barcode).strip()

    if not b:
        return "", "vacio", False
    if not b.isdigit():
        return b, "invalido", False

    if len(b) == 13:
        suma = sum(int(d) * (1 if i % 2 == 0 else 3) for i, d in enumerate(b[:12]))
        return b, "ean13", (10 - suma % 10) % 10 == int(b[12])

    if len(b) == 12:
        normalizado = "0" + b
        suma = sum(int(d) * (1 if i % 2 == 0 else 3) for i, d in enumerate(normalizado[:12]))
        return normalizado, "upc-a", (10 - suma % 10) % 10 == int(normalizado[12])

    if len(b) == 8:
        suma = sum(int(d) * (3 if i % 2 == 0 else 1) for i, d in enumerate(b[:7]))
        return b, "ean8", (10 - suma % 10) % 10 == int(b[7])

    if len(b) == 4:
        return b, "interno", True

    return b, "invalido", False


# ── Interacción ────────────────────────────────────────────────────────
def imprimir_tabla(encabezados, filas):
    filas = [[str(c) for c in fila] for fila in filas]
    anchos = [max(len(c) for c in col) for col in zip(encabezados, *filas)]
    linea = " | ".join(h.ljust(anchos[i]) for i, h in enumerate(encabezados))
    print(linea)
    print("-" * len(linea))
    for fila in filas:
        print(" | ".join(c.ljust(anchos[i]) for i, c in enumerate(fila)))


def elegir_duplicado(grupo, barcode):
    print(f"\nDuplicado detectado para el código de barras: {barcode}  ({len(grupo)} registros)")
    print("Seleccione el registro que desea conservar:")
    imprimir_tabla(
        ["#", "Fila", "Nombre", "Presentacion", "Precio", "Costo"],
        [[i, f["_fila"], f["Nombre"], f["Presentacion"], f["Precio"], f["Costo"]]
         for i, f in enumerate(grupo, start=1)],
    )
    while True:
        respuesta = input(f"Número a conservar [1-{len(grupo)}]: ").strip()
        if respuesta.isdigit() and 1 <= int(respuesta) <= len(grupo):
            return grupo[int(respuesta) - 1]
        print(f"Respuesta inválida. Ingrese un número entre 1 y {len(grupo)}.")


def elegir_variante(fila):
    exterior, interior = precio_doble(fila["Precio"])
    print(f"\nProducto con precio doble (fila {fila['_fila']}): "
          f"{fila['Nombre']} ({fila['Presentacion']})")
    print(f"  Precio: paquete ${exterior:.2f} | unidad ${interior:.2f}")
    costo = precio_doble(fila["Costo"])
    if costo is not None:
        print(f"  Costo:  paquete ${costo[0]:.2f} | unidad ${costo[1]:.2f}")
    else:
        print(f"  Costo:  {fila['Costo']}")
    for numero, (_, descripcion) in OPCIONES_VARIANTE.items():
        print(f"  {numero}) {descripcion}")
    while True:
        respuesta = input("Seleccione una opción [1-3]: ").strip()
        if respuesta in OPCIONES_VARIANTE:
            return OPCIONES_VARIANTE[respuesta][0]
        print("Opción inválida. Escriba 1, 2 o 3.")


def decidir_variante(fila, politica):
    """Aplica --variant-policy; si los precios son iguales no pregunta."""
    if politica:
        return politica
    exterior, interior = precio_doble(fila["Precio"])
    costo = precio_doble(fila["Costo"])
    if exterior == interior and (costo is None or costo[0] == costo[1]):
        print(f"\nFila {fila['_fila']}: {fila['Nombre']} ({fila['Presentacion']}): "
              f"paquete y unidad cuestan lo mismo (${exterior:.2f}); "
              "se conserva sin preguntar.")
        return "unidad"
    return elegir_variante(fila)


# ── Lógica principal ───────────────────────────────────────────────────
def resolver_duplicados(filas, politica):
    """Devuelve la lista de (fila, motivo) descartadas por barcode duplicado."""
    grupos = {}
    for f in filas:
        if f["_barcode"]:
            grupos.setdefault(f["_barcode"], []).append(f)
    duplicados = {b: g for b, g in grupos.items() if len(g) > 1}

    descartadas = []
    if not duplicados:
        print("No se encontraron códigos de barras duplicados.")
        return descartadas

    print(f"Se encontraron {len(duplicados)} códigos de barras duplicados.")
    for barcode, grupo in duplicados.items():
        con_cero = {f["_fila"] for f in grupo if es_cero(f["Precio"]) or es_cero(f["Costo"])}
        validas = [f for f in grupo if f["_fila"] not in con_cero]

        if con_cero:
            print(f"\nPara barcode {barcode}: descartadas automáticamente "
                  f"{len(con_cero)} opción(es) con precio o costo = 0.")

        if politica == "first":
            elegido = (validas or grupo)[0]
        elif politica == "last":
            elegido = (validas or grupo)[-1]
        elif len(validas) == 1:
            elegido = validas[0]
            print(f"  Solo queda una opción válida para {barcode}; se conserva "
                  f"automáticamente: fila {elegido['_fila']} | "
                  f"Precio={elegido['Precio']} | Costo={elegido['Costo']}")
        elif validas:
            elegido = elegir_duplicado(validas, barcode)
        else:
            print(f"  Ninguna opción válida (precio/costo > 0) para {barcode}; "
                  "se conservará la primera fila por defecto.")
            elegido = grupo[0]

        for f in grupo:
            if f is elegido:
                continue
            motivo = ("duplicado: precio o costo = 0" if f["_fila"] in con_cero
                      else "duplicado: versión no elegida")
            descartadas.append((f, motivo))
    return descartadas


def costo_para(fila, opcion):
    doble = precio_doble(fila["Costo"])
    if doble is not None:
        return doble[1] if opcion == "unidad" else doble[0]
    return limpiar_precio(fila["Costo"])


def crear_producto(fila, precio, costo):
    return {
        "name": f"{fila['Nombre']} {fila['Presentacion']}".strip(),
        "sale_price": f"{precio:.2f}",
        "standard_price": f"{costo:.2f}",
        "barcode": fila["_barcode"],  # se importa aunque el dígito sea inválido
        "uom_id": inferir_uom(fila["Precio"]),
        "type": "consu",
        "available_in_pos": "true",
        "active": "true",
    }


def parse_args():
    parser = argparse.ArgumentParser(
        description="Convierte un CSV de inventario a formato importable en Odoo."
    )
    parser.add_argument("csv", help="Archivo CSV de inventario.")
    parser.add_argument(
        "--keep-policy", choices=["first", "last"], default=None,
        help="Duplicados de barcode: conservar el primero o el último sin preguntar.",
    )
    parser.add_argument(
        "--variant-policy", choices=["eliminar", "unidad", "paquete"], default=None,
        help="Productos con precio doble: aplicar esta opción a todos sin preguntar.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    archivo = Path(args.csv)

    if not archivo.is_file():
        print(f"Error: no se encontró el archivo '{archivo}'")
        return 1
    if archivo.suffix.lower() != ".csv":
        print("Error: el archivo debe ser un CSV")
        return 1

    print(f"\n→ Cargando {archivo}...")
    try:
        df = pd.read_csv(archivo, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError, pd.errors.ParserError, pd.errors.EmptyDataError) as error:
        print(f"Error al leer el CSV: {error}")
        return 1

    df.columns = df.columns.str.strip()
    faltantes = [c for c in COLUMNAS_REQUERIDAS if c not in df.columns]
    if faltantes:
        print(f"Error: faltan columnas requeridas: {', '.join(faltantes)}")
        return 1

    df = df.apply(lambda col: col.str.strip())
    df = df[(df != "").any(axis=1)]  # descarta filas totalmente vacías
    columnas_originales = list(df.columns)

    # 1. Normalizar y validar barcodes
    filas = df.to_dict("records")
    for f in filas:
        f["_fila"] = None
    for numero, f in zip(df.index, filas):
        f["_fila"] = int(numero) + 2  # línea del CSV (1 = encabezado)
        f["_barcode"], f["_tipo"], f["_valido"] = validar_barcode(f["Codigo barras"])

    def registro_descartado(f, motivo):
        registro = {c: f[c] for c in columnas_originales}
        registro["fila"] = f["_fila"]
        registro["motivo"] = motivo
        return registro

    try:
        # 2. Duplicados
        dup_descartadas = resolver_duplicados(filas, args.keep_policy)
        descartadas = [registro_descartado(f, m) for f, m in dup_descartadas]
        ids_descartados = {f["_fila"] for f, _ in dup_descartadas}
        restantes = [f for f in filas if f["_fila"] not in ids_descartados]

        # 3. Variantes (precio doble) y construcción del catálogo
        productos, finales = [], []
        n_variantes = {"eliminar": 0, "unidad": 0, "paquete": 0}
        for f in restantes:
            if precio_doble(f["Precio"]) is None:
                productos.append(crear_producto(f, limpiar_precio(f["Precio"]),
                                                limpiar_precio(f["Costo"])))
                finales.append(f)
                continue

            opcion = decidir_variante(f, args.variant_policy)
            n_variantes[opcion] += 1
            if opcion == "eliminar":
                descartadas.append(registro_descartado(f, "eliminado por el usuario (precio doble)"))
                continue
            exterior, interior = precio_doble(f["Precio"])
            precio = interior if opcion == "unidad" else exterior
            productos.append(crear_producto(f, precio, costo_para(f, opcion)))
            finales.append(f)
    except (EOFError, KeyboardInterrupt):
        print("\nProceso cancelado; no se generaron archivos.")
        return 130

    # 4. Reportes
    sospechosos = [
        {
            "nombre": p["name"],
            "barcode": f["_barcode"],
            "tipo_detectado": f["_tipo"],
            "motivo": MOTIVOS_BARCODE.get(f["_tipo"], "dígito verificador no coincide"),
            "fila": f["_fila"],
        }
        for f, p in zip(finales, productos)
        if not f["_valido"]
    ]

    salida = archivo.with_name(f"{archivo.stem}_odoo.csv")
    salida_sospechosos = archivo.with_name(f"{archivo.stem}_barcodes_a_revisar.csv")
    salida_descartados = archivo.with_name(f"{archivo.stem}_descartados.csv")

    pd.DataFrame(productos, columns=COLUMNAS_ODOO).to_csv(salida, index=False)
    pd.DataFrame(
        sospechosos, columns=["nombre", "barcode", "tipo_detectado", "motivo", "fila"]
    ).to_csv(salida_sospechosos, index=False)
    pd.DataFrame(
        descartadas, columns=columnas_originales + ["fila", "motivo"]
    ).to_csv(salida_descartados, index=False)

    print(f"\n{'─' * 58}")
    print(f"  Filas leídas:                      {len(filas)}")
    print(f"  Descartadas por duplicado:         {len(dup_descartadas)}")
    print(f"  Productos con precio doble:        {sum(n_variantes.values())}"
          f"  (unidad: {n_variantes['unidad']}, paquete: {n_variantes['paquete']},"
          f" eliminados: {n_variantes['eliminar']})")
    print(f"  Productos en el CSV de Odoo:       {len(productos)}")
    print(f"  Barcodes a revisar:                {len(sospechosos)}")
    if sospechosos:
        print("\n  Detalle de barcodes a revisar:")
        for s in sospechosos:
            print(f"    {s['barcode']:<16} [{s['tipo_detectado']:<8}] {s['nombre']}")
    print(f"{'─' * 58}")
    print(f"\n→ {salida}")
    print(f"→ {salida_sospechosos}  (revisar contra producto físico)")
    print(f"→ {salida_descartados}  (filas descartadas y motivo)\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
