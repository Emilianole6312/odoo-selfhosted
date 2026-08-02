#!/usr/bin/env python3
"""Concatena varios CSV, ordena por código de barras y resuelve duplicados."""

import argparse
import csv
import sys
from pathlib import Path
from typing import List, Dict, Tuple

KNOWN_BARCODE_COLUMNS = {
    "codigo barras",
    "código barras",
    "codigo de barras",
    "código de barras",
    "barcode",
}

SUMMARY_COLUMNS = ["Nombre", "Presentacion", "Precio", "Costo", "Descripcion", "description"]


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Concatena CSV, ordena por la columna de código de barras (por índice) "
            "y resuelve duplicados interactivos."
        )
    )
    parser.add_argument(
        "csv_files",
        nargs="+",
        help="Archivos CSV de entrada a concatenar. Se requieren al menos dos.",
    )
    parser.add_argument(
        "--barcode-index",
        type=int,
        default=4,
        help=(
            "Índice 1-based de la columna que contiene el código de barras. "
            "Por defecto 4 (la cuarta columna)."
        ),
    )
    parser.add_argument(
        "--price-index",
        type=int,
        default=2,
        help=(
            "Índice 1-based de la columna de precio de venta. Por defecto 2."
        ),
    )
    parser.add_argument(
        "--cost-index",
        type=int,
        default=3,
        help=(
            "Índice 1-based de la columna de precio de compra/costo. Por defecto 3."
        ),
    )
    parser.add_argument(
        "--output-kept",
        default="concatenado_conservados.csv",
        help="Nombre del CSV de productos conservados.",
    )
    parser.add_argument(
        "--output-discarded",
        default="concatenado_descartados.csv",
        help="Nombre del CSV de productos descartados.",
    )
    parser.add_argument(
        "--keep-policy",
        choices=["first", "last"],
        default=None,
        help="Política automática para duplicados: conservar el primero o el último sin preguntar.",
    )
    parser.add_argument(
        "--no-sort",
        action="store_false",
        dest="sort",
        help="No ordenar el resultado por la columna de código de barras.",
    )
    return parser.parse_args()


def safe_read_csv(path: Path) -> Tuple[List[str], List[Dict[str, str]]]:
    try:
        with path.open(newline='', encoding='utf-8') as handle:
            reader = csv.DictReader(handle)
            fieldnames = reader.fieldnames or []
            columns = [str(col).strip() for col in fieldnames]
            rows = []
            for original in reader:
                row = {str(col).strip(): (original.get(col) or '').strip() for col in fieldnames}
                rows.append(row)
    except Exception as error:
        raise RuntimeError(f"Error leyendo '{path}': {error}") from error
    return columns, rows


def parse_number(value: str) -> float:
    try:
        s = str(value).strip()
        if not s:
            return 0.0
        # Keep digits and dot and comma
        s = s.replace(',', '.')
        # Remove everything except digits and dot and minus
        filtered = ''.join(ch for ch in s if (ch.isdigit() or ch in '.-'))
        if not filtered or filtered == '-' or filtered == '.' or filtered == '-.':
            return 0.0
        return float(filtered)
    except Exception:
        return 0.0


def build_summary_columns(columns: List[str], barcode_column: str) -> List[str]:
    selected = [barcode_column]
    for name in SUMMARY_COLUMNS:
        if name in columns and name != barcode_column:
            selected.append(name)
    for name in columns:
        if name not in selected and len(selected) < 6:
            selected.append(name)
    return selected


def print_table(rows: List[Dict[str, str]], columns: List[str], price_col: str, cost_col: str, source_col: str):
    # Columns to show: index, source, price, cost, then summary columns
    headers = ["#", "Fuente", price_col, cost_col] + [c for c in columns if c not in {price_col, cost_col, source_col}][:3]
    # compute widths
    widths = [max(len(h), 3) for h in headers]
    table_rows = []
    for idx, row in enumerate(rows, start=1):
        source = row.get(source_col, '')
        price = row.get(price_col, '')
        cost = row.get(cost_col, '')
        rest = [row.get(h, '') for h in headers[4:]]
        cells = [str(idx), source, price, cost] + rest
        table_rows.append(cells)
        for i, cell in enumerate(cells):
            widths[i] = max(widths[i], len(str(cell)))
    # print header
    sep = ' | '
    line = sep.join(h.ljust(widths[i]) for i, h in enumerate(headers))
    print(line)
    print('-' * len(line))
    for cells in table_rows:
        print(sep.join(str(c).ljust(widths[i]) for i, c in enumerate(cells)))


def choose_keep_from_rows(rows: List[Dict[str, str]], columns: List[str], barcode: str, price_col: str, cost_col: str, source_col: str) -> int:
    print(f"\nDuplicado detectado para el código de barras: {barcode}  ({len(rows)} registros)")
    print("Seleccione el registro que desea conservar:")
    print_table(rows, columns, price_col, cost_col, source_col)
    while True:
        answer = input(f"Número a conservar [1-{len(rows)}]: ").strip()
        if answer.isdigit():
            selected = int(answer)
            if 1 <= selected <= len(rows):
                return selected - 1
        print(f"Respuesta inválida. Ingrese un número entre 1 y {len(rows)}.")


def write_csv(path: Path, rows: List[Dict[str, str]], columns: List[str]):
    with path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction='ignore')
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, '') for col in columns})


def main():
    args = parse_args()

    if len(args.csv_files) < 2:
        print("Error: se requieren al menos dos archivos CSV de entrada.")
        return 1

    paths = [Path(path) for path in args.csv_files]
    for path in paths:
        if not path.is_file():
            print(f"Error: no se encontró '{path}'")
            return 1
        if path.suffix.lower() != ".csv":
            print(f"Error: '{path}' no es un archivo CSV")
            return 1

    all_columns: List[str] = []
    rows: List[Dict[str, str]] = []

    for path in paths:
        print(f"Cargando '{path}'...")
        file_columns, file_rows = safe_read_csv(path)
        file_columns = [col for col in file_columns if col]
        for col in file_columns:
            if col not in all_columns:
                all_columns.append(col)
        for row in file_rows:
            row['__source_file'] = path.name
            rows.append(row)

    if not all_columns:
        print("Error: no se encontraron columnas en los CSV de entrada.")
        return 1

    # Convert 1-based indices to 0-based and validate
    def idx_to_name(idx1: int, name: str) -> str:
        if idx1 < 1 or idx1 > len(all_columns):
            raise ValueError(f"{name} index {idx1} fuera de rango (1..{len(all_columns)})")
        return all_columns[idx1 - 1]

    try:
        barcode_col = idx_to_name(args.barcode_index, 'barcode')
        price_col = idx_to_name(args.price_index, 'price')
        cost_col = idx_to_name(args.cost_index, 'cost')
    except ValueError as e:
        print(f"Error: {e}")
        return 1

    print(f"Usando columna de código de barras (índice {args.barcode_index}): '{barcode_col}'")
    print(f"Usando columna de precio (índice {args.price_index}): '{price_col}'")
    print(f"Usando columna de costo (índice {args.cost_index}): '{cost_col}'")

    # normalize barcode values
    for row in rows:
        row[barcode_col] = str(row.get(barcode_col, '')).strip()

    if args.sort:
        rows.sort(key=lambda r: r.get(barcode_col, ''))

    duplicates = {}
    for row in rows:
        value = row.get(barcode_col, '')
        if value == '':
            continue
        duplicates.setdefault(value, []).append(row)

    duplicated_barcode_groups = {bar: gr for bar, gr in duplicates.items() if len(gr) > 1}

    kept: List[Dict[str, str]] = []
    discarded: List[Dict[str, str]] = []

    if not duplicated_barcode_groups:
        print("No se encontraron códigos de barras duplicados.")
        kept = rows[:]
        discarded = []
    else:
        print(f"Se encontraron {len(duplicated_barcode_groups)} códigos de barras duplicados.")
        for barcode, group_rows in duplicated_barcode_groups.items():
            # Auto-discard rows where price==0 or cost==0
            valid_rows = []
            auto_discarded = []
            for r in group_rows:
                price_val = parse_number(r.get(price_col, ''))
                cost_val = parse_number(r.get(cost_col, ''))
                if price_val == 0.0 or cost_val == 0.0:
                    auto_discarded.append(r)
                else:
                    valid_rows.append(r)

            if auto_discarded:
                print(f"\nPara barcode {barcode}: descartadas automáticamente {len(auto_discarded)} opción(es) con precio o costo = 0.")
                discarded.extend(auto_discarded)

            # Decide chosen row
            if args.keep_policy == 'first':
                chosen_row = valid_rows[0] if valid_rows else group_rows[0]
            elif args.keep_policy == 'last':
                chosen_row = valid_rows[-1] if valid_rows else group_rows[-1]
            else:
                if valid_rows:
                    if len(valid_rows) == 1:
                        chosen_row = valid_rows[0]
                        print(
                            f"  Solo queda una opción válida para {barcode}; se conserva automáticamente: "
                            f"Fuente={chosen_row.get('__source_file', '')} | Precio={chosen_row.get(price_col, '')} | Costo={chosen_row.get(cost_col, '')}"
                        )
                    else:
                        try:
                            sel = choose_keep_from_rows(valid_rows, all_columns, barcode, price_col, cost_col, '__source_file')
                            chosen_row = valid_rows[sel]
                        except (EOFError, KeyboardInterrupt):
                            print("\nProceso cancelado. No se generaron archivos.")
                            return 130
                else:
                    # No valid options remain after auto-discard; keep the first original row
                    print(f"  Ninguna opción válida (precio/costo > 0) para {barcode}; se conservará la primera fila por defecto.")
                    chosen_row = group_rows[0]

            # Add chosen to kept, rest to discarded (exclude previously auto_discarded which already in discarded)
            for r in group_rows:
                if r is chosen_row:
                    kept.append(r)
                else:
                    if r not in auto_discarded:
                        discarded.append(r)

        # add rows that had no duplicates
        for row in rows:
            barcode_value = row.get(barcode_col, '')
            if barcode_value == '' or barcode_value not in duplicated_barcode_groups:
                kept.append(row)

    output_columns = [col for col in all_columns if col != '__source_file']
    if '__source_file' in all_columns:
        output_columns.append('__source_file')

    write_csv(Path(args.output_kept), kept, output_columns)
    write_csv(Path(args.output_discarded), discarded, output_columns)

    print(f"\nArchivo de conservados: {args.output_kept} ({len(kept)} filas)")
    print(f"Archivo de descartados: {args.output_discarded} ({len(discarded)} filas)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
