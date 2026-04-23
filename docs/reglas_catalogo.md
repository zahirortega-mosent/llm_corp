# Catálogo de reglas propuesto

## STATEMENT_BALANCE_MISMATCH
- Título: Descuadre entre saldo inicial, depósitos, retiros y saldo final
- Origen: sistema_origen
- Severidad: critica
- Aplica a: estado_cuenta
- Auto detectable: sí
- Base normativa / operativa: Control operativo del conciliador y validación bancaria básica
- Descripción: Se activa cuando el estado de cuenta no cumple la igualdad saldo inicial + depósitos - retiros = saldo final o cuando el propio origen marca saldo incorrecto.
- Acción sugerida: Revisar archivo fuente, parser bancario, movimientos faltantes o duplicados y recalcular saldos.

## HEADER_WITHOUT_MOVEMENTS
- Título: Estado de cuenta cargado sin movimientos hijos
- Origen: sistema_origen
- Severidad: alta
- Aplica a: estado_cuenta
- Auto detectable: sí
- Base normativa / operativa: Control de integridad de carga
- Descripción: Existe cabecera de estado de cuenta pero no quedaron movimientos normalizados asociados.
- Acción sugerida: Validar nomenclatura, carpeta de origen, archivo dañado o extractor bancario.

## MISSING_MOVEMENT_DATE
- Título: Movimiento sin fecha
- Origen: operativa
- Severidad: alta
- Aplica a: movimiento
- Auto detectable: sí
- Base normativa / operativa: Trazabilidad mínima para conciliación y corte
- Descripción: El movimiento no tiene fecha de operación identificable.
- Acción sugerida: Revisar parser del banco y archivo fuente; no conciliar hasta tener fecha válida.

## MISSING_DESCRIPTION
- Título: Movimiento sin descripción o concepto
- Origen: operativa
- Severidad: media
- Aplica a: movimiento
- Auto detectable: sí
- Base normativa / operativa: Trazabilidad operativa
- Descripción: El movimiento carece de descripción/concepto suficiente para rastreo operativo.
- Acción sugerida: Complementar evidencia con referencia, folio, archivo fuente u origen operativo.

## MISSING_REFERENCE
- Título: Movimiento sin referencia o folio
- Origen: operativa
- Severidad: media
- Aplica a: movimiento
- Auto detectable: sí
- Base normativa / operativa: Trazabilidad para conciliación entre fuentes
- Descripción: No existe referencia, folio o campo equivalente para cruzar el movimiento con otras fuentes.
- Acción sugerida: Complementar con sistema de referencias, Odoo, Ecobro o fuente operativa aplicable.

## UNRECONCILED_MOVEMENT
- Título: Movimiento no conciliado
- Origen: operativa
- Severidad: media
- Aplica a: movimiento
- Auto detectable: sí
- Base normativa / operativa: Estado operativo de conciliación
- Descripción: El movimiento aparece en el dataset como no conciliado.
- Acción sugerida: Priorizar por monto, antigüedad y relación con estados de cuenta con descuadre.

## ZERO_AMOUNT_MOVEMENT
- Título: Movimiento sin importe
- Origen: operativa
- Severidad: alta
- Aplica a: movimiento
- Auto detectable: sí
- Base normativa / operativa: Integridad de transacción bancaria
- Descripción: El movimiento no trae depósito ni retiro, o ambos están en cero.
- Acción sugerida: Revisar si es fila vacía, totalizador o error de parseo.

## BOTH_DEPOSIT_AND_WITHDRAWAL
- Título: Movimiento con depósito y retiro simultáneos
- Origen: operativa
- Severidad: alta
- Aplica a: movimiento
- Auto detectable: sí
- Base normativa / operativa: Integridad de estructura bancaria
- Descripción: Un mismo registro trae importes de depósito y retiro mayores a cero.
- Acción sugerida: Confirmar layout del banco y si el parser mezcló columnas.

## NEGATIVE_SIGN_VALUE
- Título: Importe con signo inconsistente
- Origen: operativa
- Severidad: media
- Aplica a: movimiento
- Auto detectable: sí
- Base normativa / operativa: Normalización de layout bancario
- Descripción: Hay importes negativos en campos que deberían llegar como magnitud positiva por columna.
- Acción sugerida: Homologar signo y tipo de movimiento antes de conciliar.

## OUTSIDE_PERIOD_RANGE
- Título: Movimiento fuera del rango del estado de cuenta
- Origen: operativa
- Severidad: alta
- Aplica a: movimiento
- Auto detectable: sí
- Base normativa / operativa: Corte y congruencia documental
- Descripción: La fecha del movimiento cae fuera del periodo del estado de cuenta al que está asociado.
- Acción sugerida: Revisar si el movimiento fue asignado al archivo equivocado o si el banco incluyó arrastres.

## DUPLICATE_HEURISTIC
- Título: Posible duplicidad de movimiento
- Origen: operativa
- Severidad: alta
- Aplica a: movimiento
- Auto detectable: sí
- Base normativa / operativa: Prevención de doble conciliación y doble contabilización
- Descripción: Se detectan movimientos repetidos por banco, cuenta, fecha, tipo, importe y descripción normalizada.
- Acción sugerida: Confirmar si son pagos legítimos recurrentes o si hubo duplicidad de ingestión/consulta.

## FILENAME_PATTERN_WARNING
- Título: Ruta o nomenclatura de archivo no homologada
- Origen: sistema_origen
- Severidad: media
- Aplica a: archivo
- Auto detectable: sí
- Base normativa / operativa: Control de carga documental y homologación operativa
- Descripción: La ruta o el nombre del archivo no siguen el patrón operativo esperado para estados de cuenta.
- Acción sugerida: Corregir carpeta, nombre y homologación antes de reprocesar.

## POTENTIAL_INTERCOMPANY_TRANSFER
- Título: Posible transferencia intercompañía o entre cuentas del grupo
- Origen: propuesta_contable
- Severidad: alta
- Aplica a: movimiento
- Auto detectable: sí
- Base normativa / operativa: NIF B-8 / IFRS 10: eliminación de transacciones intragrupo en estados financieros consolidados
- Descripción: El texto del movimiento sugiere traspaso entre entidades del grupo, por lo que debe ser conciliable por empresa pero no ingreso consolidado.
- Acción sugerida: Clasificar como transferencia entre entidades/cuentas del grupo y evitar doble reconocimiento de ingreso.

## NO_RESPONSIBLE_ASSIGNED
- Título: Cuenta sin responsable asignado
- Origen: operativa
- Severidad: media
- Aplica a: cuenta
- Auto detectable: sí
- Base normativa / operativa: Control operativo y segregación de responsabilidades
- Descripción: La cuenta no tiene responsable asociado en el catálogo operativo de la filial.
- Acción sugerida: Completar assignments.csv para poder enrutar incidencias y revisión.

## INTERCOMPANY_NOT_REVENUE
- Título: Las operaciones intragrupo no son ingreso consolidado
- Origen: propuesta_contable
- Severidad: critica
- Aplica a: contabilidad
- Auto detectable: no
- Base normativa / operativa: NIF B-8 / IFRS 10
- Descripción: Las transferencias entre filiales o cuentas del mismo grupo pueden ser conciliables por entidad, pero deben eliminarse al consolidar para evitar duplicidad de ingresos.
- Acción sugerida: Etiquetar estas operaciones y excluirlas del reconocimiento de ingreso consolidado.

## CASHFLOW_CLASSIFICATION
- Título: Clasificación de flujos de efectivo
- Origen: propuesta_contable
- Severidad: media
- Aplica a: contabilidad
- Auto detectable: no
- Base normativa / operativa: NIF B-2 / IAS 7
- Descripción: Los movimientos de efectivo deben clasificarse adecuadamente y no compensarse indebidamente entre sí.
- Acción sugerida: Separar operación, inversión y financiamiento cuando aplique; no netear movimientos sin sustento normativo.

## REVENUE_GROSS_NET_COMMISSIONS
- Título: Ingreso bruto vs comisiones y retenciones
- Origen: propuesta_contable
- Severidad: alta
- Aplica a: contabilidad
- Auto detectable: no
- Base normativa / operativa: NIF D-1 / IFRS 15
- Descripción: Cuando existan depósitos netos de comisiones de proveedores, debe evaluarse la presentación bruta o neta y la comisión no debe ocultar el ingreso real sin análisis de principal/agente.
- Acción sugerida: Separar el ingreso del gasto/comisión y documentar el criterio contable aplicado.

## NO_OFFSETTING_PRESENTATION
- Título: No compensar activos, pasivos, ingresos o gastos sin base expresa
- Origen: propuesta_contable
- Severidad: alta
- Aplica a: contabilidad
- Auto detectable: no
- Base normativa / operativa: NIF A-7 / IAS 1
- Descripción: La compensación contable o de presentación sin soporte puede ocultar diferencias y distorsionar reportes.
- Acción sugerida: Presentar de forma separada y solo compensar cuando una norma lo permita expresamente.

## ACCRUAL_AND_CUTOFF
- Título: Devengación y corte del periodo
- Origen: propuesta_contable
- Severidad: alta
- Aplica a: contabilidad
- Auto detectable: no
- Base normativa / operativa: NIF A-6
- Descripción: Los movimientos deben reconocerse y explicarse en el periodo correcto, evitando arrastres o cortes operativos incorrectos.
- Acción sugerida: Revisar fecha valor, fecha operación y política de corte para evitar conciliaciones cruzadas entre meses.

## RESTRICTED_CASH_PRESENTATION
- Título: Presentación de efectivo restringido
- Origen: propuesta_contable
- Severidad: media
- Aplica a: contabilidad
- Auto detectable: no
- Base normativa / operativa: NIF C-1, NIF A-7
- Descripción: Cuando existan restricciones sobre cuentas o saldos, debe evaluarse su presentación separada del efectivo disponible.
- Acción sugerida: Identificar restricciones y separar presentación de efectivo disponible vs restringido.
