# Análisis inicial del CSV y del proyecto Conciliador

## CSV analizado

Archivo:
- `conciliador_movimientos_pdf_enero_febrero.csv`

### Hallazgos principales

- Estados de cuenta únicos: **193**
- Movimientos normalizados: **75384**
- Cuentas únicas: **125**
- Filiales presentes: **12**
- Periodos detectados:
  - 2026-01: **40,546** movimientos
  - 2026-02: **34,838** movimientos
- Movimientos conciliados: **3,957**
- Movimientos no conciliados: **71,427**
- Estados con descuadre de saldo: **4**
- Estados con cabecera sin movimientos hijos: **14**
- Movimientos sin referencia: **21,251**

## Bancos con mayor volumen

| bank       |   movimientos |   cuentas |   depositos |          retiros |
|:-----------|--------------:|----------:|------------:|-----------------:|
| SANTANDER  |         53886 |        90 | 3.77138e+08 |      3.95532e+08 |
| BANBAJIO   |         16112 |        12 | 2.24685e+07 |      2.11551e+07 |
| BANAMEX    |          4669 |         2 | 6.78104e+06 |      6.67515e+06 |
| BANREGIO   |           276 |         1 | 5.83302e+06 |      5.82492e+06 |
| SCOTIABANK |           190 |         4 | 1.54534e+06 | 974149           |
| BANORTE    |           186 |         5 | 6.64453e+07 |      7.1347e+07  |
| BBVA       |            65 |         3 | 2.04917e+06 |      1.89765e+06 |

## Filiales con mayor volumen

| filial       |   movimientos |   cuentas |
|:-------------|--------------:|----------:|
| Guadalajara  |         21422 |        40 |
| Toluca       |          9885 |        10 |
| Puebla       |          8593 |         8 |
| Tampico      |          8462 |         8 |
| Villahermosa |          7654 |         8 |
| Saltillo     |          5543 |         6 |
| Monclova     |          4325 |         7 |
| Cuernavaca   |          3669 |         7 |
| Acapulco     |          2744 |         6 |
| Cancun       |          1653 |         2 |

## Qué representa realmente este CSV

No es una tabla transaccional limpia.
Es un **join ancho** entre la cabecera del estado de cuenta y múltiples layouts bancarios hijos.

Por eso:
- hay columnas repetidas
- hay grupos de columnas nulas
- un layout cambia según banco
- la tabla requiere normalización antes de consultar con IA

## Qué confirma el código del Conciliador

Del proyecto Laravel revisado se observó lo siguiente:

- Existen macroprocesos separados para:
  - transacciones digitales
  - conciliación bancaria
  - depósitos
  - dispersiones
  - reportería
- La conciliación bancaria usa:
  - estados de cuenta PDF
  - estados de movimientos XLS/XLSX/CSV
  - Nextcloud/WebDAV
  - cruces contra Odoo y otros catálogos
- El flujo Santander entra principalmente por archivo y enriquecimiento con referencias.
- NetPay tiene doble fase de conciliación:
  - por invoice/transacción
  - por contrato para rezagos
- El sistema registra errores operativos asociados a:
  - archivo inexistente
  - nomenclatura incorrecta
  - carpeta incorrecta
  - hash ya procesado
  - reintento con menos movimientos
  - saldos inconsistentes

## Conclusión útil para el MVP

El MVP correcto no debe rehacer el conciliador.
Debe agregar una capa de:

- consulta mensual
- explicación
- priorización de revisión
- cotejo contra lo que el Conciliador ya hace
- trazabilidad por archivo / cuenta / filial / banco
