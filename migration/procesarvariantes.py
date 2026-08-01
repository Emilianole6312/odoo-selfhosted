#!/usr/bin/env python3
"""Procesa productos con precio de paquete y de pieza para importarlos en Odoo."""

import re
import sys
from pathlib import Path

import pandas as pd


PRECIO_DOBLE = re.compile(r"\$([\d.]+)\s*\(\s*\$([\d.]+)\s*\)")
OPCIONES = {
    "a": "eliminar el producto",
    "b": "conservar el precio de dentro de los parentesis (unidad)",
    "c": "conservar el precio de fuera de los parentesis (paquete)",
    "d": "conservar ambas presentaciones",
}


def precio_doble(valor):
    """Devuelve (precio_exterior, precio_interior), o None si no hay dos precios."""
    coincidencia = PRECIO_DOBLE.search(str(valor))
    if not coincidencia:
        return None
    return float(coincidencia.group(1)), float(coincidencia.group(2))


def limpiar_precio(valor):
    """Convierte un precio del CSV a número."""
    if pd.isna(valor):
        return 0.0
    numero = re.sub(r"[^\d.]", "", str(valor))
    return float(numero) if numero else 0.0


def validar_barcode(barcode):
    """Normaliza UPC-A y valida EAN-13/EAN-8, igual que importarodoo.py."""
    codigo = str(barcode).strip()
    if not codigo.isdigit():
        return codigo, False
    if len(codigo) == 12:
        codigo = "0" + codigo
    if len(codigo) == 13:
        suma = sum(int(digito) * (1 if indice % 2 == 0 else 3)
                   for indice, digito in enumerate(codigo[:12]))
        return codigo, (10 - suma % 10) % 10 == int(codigo[12])
    if len(codigo) == 8:
        suma = sum(int(digito) * (3 if indice % 2 == 0 else 1)
                   for indice, digito in enumerate(codigo[:7]))
        return codigo, (10 - suma % 10) % 10 == int(codigo[7])
    return codigo, len(codigo) == 4


def digito_verificador(base):
    suma = sum(int(digito) * (3 if indice % 2 else 1)
               for indice, digito in enumerate(reversed(base)))
    return str((10 - suma % 10) % 10)


def generar_barcode(usados, consecutivo):
    """Genera un EAN-13 válido y evita códigos ya presentes en el catálogo."""
    while True:
        base = f"200{consecutivo:09d}"
        codigo = base + digito_verificador(base)
        consecutivo += 1
        if codigo not in usados:
            usados.add(codigo)
            return codigo, consecutivo


def pedir_opcion(fila_numero, fila):
    nombre = str(fila["Nombre"]).strip()
    presentacion = str(fila["Presentacion"]).strip()
    precios = precio_doble(fila["Precio"])
    exterior, interior = precios

    print(f"\nProducto {fila_numero}: {nombre} ({presentacion})")
    print(f"  Precio exterior: ${exterior:.2f} | Precio interior: ${interior:.2f}")
    for opcion, descripcion in OPCIONES.items():
        print(f"  {opcion}) {descripcion}")
    while True:
        opcion = input("Seleccione una opción [a-d]: ").strip().lower()
        if opcion in OPCIONES:
            break
        print("Opción inválida. Escriba a, b, c o d.")

    barcode_presentacion = None
    if opcion == "d":
        while barcode_presentacion not in {"dentro", "fuera"}:
            barcode_presentacion = input(
                "¿Qué precio conservará el código original? [dentro/fuera]: "
            ).strip().lower()
            if barcode_presentacion not in {"dentro", "fuera"}:
                print("Respuesta inválida. Escriba dentro o fuera.")
    return opcion, barcode_presentacion


def crear_producto(fila, precio, uom, barcode):
    nombre = f"{str(fila['Nombre']).strip()} {uom}".strip()
    return {
        "name": nombre,
        "sale_price": f"{precio:.2f}",
        "standard_price": f"{limpiar_precio(fila['Costo']):.2f}",
        "barcode": barcode,
        "uom_id": uom,
        "type": "consu",
        "available_in_pos": "true",
        "active": "true",
    }


def main():
    if len(sys.argv) != 2:
        print(f"Uso: {Path(sys.argv[0]).name} <archivo.csv>")
        return 1

    archivo = Path(sys.argv[1])
    if not archivo.is_file():
        print(f"Error: no se encontró el archivo '{archivo}'")
        return 1
    if archivo.suffix.lower() != ".csv":
        print("Error: el archivo debe ser un CSV")
        return 1

    try:
        df = pd.read_csv(archivo, dtype=str, keep_default_na=False)
    except (OSError, pd.errors.ParserError) as error:
        print(f"Error al leer el CSV: {error}")
        return 1

    requeridas = {"Codigo barras", "Nombre", "Presentacion", "Precio", "Costo"}
    faltantes = requeridas - set(df.columns)
    if faltantes:
        print(f"Error: faltan columnas requeridas: {', '.join(sorted(faltantes))}")
        return 1

    usados = set()
    for barcode in df["Codigo barras"]:
        normalizado, _ = validar_barcode(barcode)
        if normalizado:
            usados.add(normalizado)

    productos = []
    generados = []
    eliminados = 0
    consecutivo = 1

    try:
        for indice, (_, fila) in enumerate(df.iterrows(), start=1):
            precios = precio_doble(fila["Precio"])
            if precios is None:
                print(
                    f"Error: la fila {indice} no tiene formato "
                    "'$exterior($interior)'."
                )
                return 1

            opcion, barcode_presentacion = pedir_opcion(indice, fila)
            exterior, interior = precios
            barcode_original, _ = validar_barcode(fila["Codigo barras"])

            if opcion == "a":
                eliminados += 1
                continue
            if opcion == "b":
                productos.append(crear_producto(fila, interior, "Unidades",
                                                barcode_original))
                continue
            if opcion == "c":
                productos.append(crear_producto(fila, exterior, "Paquetes",
                                                barcode_original))
                continue

            if barcode_presentacion == "dentro":
                productos.append(crear_producto(fila, interior, "Unidades",
                                                barcode_original))
                barcode_generado, consecutivo = generar_barcode(usados, consecutivo)
                productos.append(crear_producto(fila, exterior, "Paquetes",
                                                barcode_generado))
                generados.append((fila["Nombre"], "Paquetes", barcode_generado))
            else:
                productos.append(crear_producto(fila, exterior, "Paquetes",
                                                barcode_original))
                barcode_generado, consecutivo = generar_barcode(usados, consecutivo)
                productos.append(crear_producto(fila, interior, "Unidades",
                                                barcode_generado))
                generados.append((fila["Nombre"], "Unidades", barcode_generado))
    except (EOFError, KeyboardInterrupt):
        print("\nProceso cancelado; no se generaron archivos.")
        return 130

    salida = archivo.with_name(f"{archivo.stem}_odoo.csv")
    reporte = archivo.with_name(f"{archivo.stem}_barcodes_generados.csv")
    pd.DataFrame(productos, columns=[
        "name", "sale_price", "standard_price", "barcode", "uom_id",
        "type", "available_in_pos", "active",
    ]).to_csv(salida, index=False)
    pd.DataFrame(generados, columns=["nombre", "presentacion", "barcode"]).to_csv(
        reporte, index=False
    )

    print(f"\nProductos conservados: {len(productos)}")
    print(f"Productos eliminados: {eliminados}")
    print(f"Códigos generados: {len(generados)}")
    print(f"→ {salida}")
    print(f"→ {reporte}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
