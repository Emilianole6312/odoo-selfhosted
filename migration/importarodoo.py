#!/usr/bin/env python3
import pandas as pd
import re
import sys
from pathlib import Path

# ── Argumentos ─────────────────────────────────────────────────────────
if len(sys.argv) != 2:
    print("Uso: ./importarodoo.py <archivo.csv>")
    sys.exit(1)

archivo = Path(sys.argv[1])

if not archivo.exists():
    print(f"Error: no se encontró el archivo '{archivo}'")
    sys.exit(1)

if archivo.suffix.lower() != '.csv':
    print(f"Error: el archivo debe ser un CSV")
    sys.exit(1)

# ── Carga ──────────────────────────────────────────────────────────────
print(f"\n→ Cargando {archivo}...")
df = pd.read_csv(archivo, dtype=str)
df.columns = df.columns.str.strip()

# ── Helpers ────────────────────────────────────────────────────────────
def es_precio_doble(valor):
    """Detecta formato $24.00($6.00)"""
    if pd.isna(valor):
        return False
    return bool(re.search(r'\$[\d.]+\(\$[\d.]+\)', str(valor)))

def limpiar_precio(valor):
    """Elimina símbolo $ y convierte a float."""
    if pd.isna(valor):
        return 0.0
    return float(re.sub(r'[^\d.]', '', str(valor)))

def limpiar_existencias(valor):
    """Extrae solo el número, ignora texto como 'paq'."""
    if pd.isna(valor):
        return 0
    numero = re.sub(r'[^\d-]', '', str(valor))
    return int(numero) if numero and numero != '-' else 0

def validar_barcode(barcode):
    """
    Valida un código de barras sin corregirlo.
    Devuelve: (codigo, tipo, es_valido)
    - EAN-13: se valida el dígito verificador tal cual viene
    - UPC-A (12 dígitos): se normaliza a EAN-13 agregando 0 (regla segura del estándar)
    - EAN-8: se valida el dígito verificador tal cual viene
    - Código interno (4 dígitos): se acepta sin validación de dígito verificador
    - Cualquier otro largo: se marca como inválido sin modificar
    """
    b = str(barcode).strip()

    if not b or not b.isdigit():
        return b, 'invalido', False

    if len(b) == 13:
        suma = sum(int(d) * (1 if i % 2 == 0 else 3) for i, d in enumerate(b[:12]))
        es_valido = (10 - (suma % 10)) % 10 == int(b[12])
        return b, 'ean13', es_valido

    if len(b) == 12:
        # Normalización UPC-A → EAN-13 (segura, no es una corrección de dígito)
        normalizado = '0' + b
        suma = sum(int(d) * (1 if i % 2 == 0 else 3) for i, d in enumerate(normalizado[:12]))
        es_valido = (10 - (suma % 10)) % 10 == int(normalizado[12])
        return normalizado, 'upc-a', es_valido

    if len(b) == 8:
        suma = sum(int(d) * (3 if i % 2 == 0 else 1) for i, d in enumerate(b[:7]))
        es_valido = (10 - (suma % 10)) % 10 == int(b[7])
        return b, 'ean8', es_valido

    if len(b) == 4:
        # Código interno propio, sin estándar EAN que validar
        return b, 'interno', True

    return b, 'invalido', False

def inferir_uom(presentacion):
    """Gramaje, granel y kg → kg. Todo lo demás → Unit(s)"""
    if pd.isna(presentacion):
        return 'Unit(s)'
    p = str(presentacion).lower()
    if any(u in p for u in ['kg', 'g ', 'gr', 'gramos', 'granel', 'gramaje']):
        return 'kg'
    return 'Unit(s)'

# ── Separar filas con precio doble (pieza/paquete) ─────────────────────
mask_doble   = df['Precio'].apply(es_precio_doble)
df_variantes = df[mask_doble].copy()
df_simple    = df[~mask_doble].copy()

# ── Procesar catálogo simple ───────────────────────────────────────────
df_simple['sale_price']  = df_simple['Precio'].apply(limpiar_precio)
df_simple['cost_price']  = df_simple['Costo'].apply(limpiar_precio)
df_simple['existencias'] = df_simple['Existencias'].apply(limpiar_existencias)
df_simple['uom_id']      = df_simple['Presentacion'].apply(inferir_uom)

resultado_barcode = df_simple['Codigo barras'].apply(validar_barcode)
df_simple['barcode']        = [r[0] for r in resultado_barcode]
df_simple['barcode_tipo']   = [r[1] for r in resultado_barcode]
df_simple['barcode_valido'] = [r[2] for r in resultado_barcode]

odoo_simple = pd.DataFrame({
    'name': (
        df_simple['Nombre'].str.strip() + ' ' +
        df_simple['Presentacion'].fillna('').str.strip()
    ).str.strip(),    
    'sale_price':       df_simple['sale_price'],
    'standard_price':   df_simple['cost_price'],
    'barcode':          df_simple['barcode'],   # se importa aunque el dígito sea inválido
    'uom_id':           df_simple['uom_id'],
    'type':             'consu',
    'available_in_pos': 'true',
    'active':           'true',
})

# ── Reporte de barcodes a revisar (no se excluyen de la importación) ───
sospechosos = df_simple[~df_simple['barcode_valido']][
    ['Nombre', 'barcode', 'barcode_tipo']
].rename(columns={'Nombre': 'nombre', 'barcode_tipo': 'tipo_detectado'})

# ── Reporte por consola ─────────────────────────────────────────────────
exist_negativas = (df_simple['existencias'] < 0).sum()

print(f"\n{'─'*55}")
print(f"  Productos simples procesados:   {len(odoo_simple)}")
print(f"  Separados para revisión manual: {len(df_variantes)}  (precio pieza/paquete)")
print(f"  Barcodes a revisar:             {len(sospechosos)}  (dígito verificador no coincide)")
print(f"  Existencias negativas:          {exist_negativas}  (ignoradas, tipo=consu)")

if not sospechosos.empty:
    print(f"\n  Detalle de barcodes a revisar:")
    for _, row in sospechosos.iterrows():
        print(f"    {row['barcode']:<16} [{row['tipo_detectado']:<8}] {row['nombre']}")

print(f"{'─'*55}")

# ── Exportar ───────────────────────────────────────────────────────────
salida_simple      = archivo.stem + '_odoo.csv'
salida_variantes   = archivo.stem + '_variantes.csv'
salida_sospechosos = archivo.stem + '_barcodes_a_revisar.csv'

odoo_simple.to_csv(salida_simple, index=False)
df_variantes.to_csv(salida_variantes, index=False)
sospechosos.to_csv(salida_sospechosos, index=False)

print(f"\n→ {salida_simple}")
print(f"→ {salida_variantes}        (requiere procesamiento manual)")
print(f"→ {salida_sospechosos}  (revisar contra producto físico)\n")