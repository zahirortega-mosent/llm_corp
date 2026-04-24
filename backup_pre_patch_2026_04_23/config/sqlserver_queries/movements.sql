WITH movimientos_base AS (
    SELECT
        TRY_CONVERT(date, FechaFin) AS movement_date,
        TRY_CONVERT(varchar(100), FolioFin) AS folio,
        TRY_CONVERT(int, NumMovto) AS num_movto,
        TRY_CONVERT(varchar(50), CodCtaMayorFin) AS cod_cta_mayor,
        TRY_CONVERT(varchar(255), NomCtaMayor) AS nom_cta_mayor,
        TRY_CONVERT(varchar(100), CodigoCuentaFin) AS codigo_cuenta_fin,
        TRY_CONVERT(varchar(255), NombreCuentaFin) AS nombre_cuenta_fin,
        TRY_CONVERT(varchar(500), ReferenciaFin) AS reference,
        TRY_CONVERT(varchar(1000), ConceptoMovimiento) AS concept,
        TRY_CONVERT(varchar(1000), ConceptoPolizaFin) AS description,
        TRY_CONVERT(decimal(18,2), Cargos) AS withdrawal,
        TRY_CONVERT(decimal(18,2), Abonos) AS deposit,
        TRY_CONVERT(decimal(18,2), ImporteNeto) AS importe_neto,
        TRY_CONVERT(varchar(255), Cliente) AS cliente,
        TRY_CONVERT(varchar(255), PlazaFin) AS plaza_fin,
        TRY_CONVERT(varchar(255), GrupoFin) AS grupo_fin,
        TRY_CONVERT(varchar(255), DiarioFin) AS diario_fin,
        TRY_CONVERT(varchar(255), TipoPolizaFin) AS tipo_poliza_fin,
        TRY_CONVERT(varchar(255), Usuario) AS usuario,
        TRY_CONVERT(varchar(255), move_name) AS move_name,
        CONCAT(
            TRY_CONVERT(varchar(100), FolioFin),
            '-',
            TRY_CONVERT(varchar(20), NumMovto),
            '-',
            CONVERT(varchar(10), TRY_CONVERT(date, FechaFin), 23)
        ) AS source_movement_key
    FROM dbo.MovimientosFinancieros_Corporativo
    WHERE TRY_CONVERT(int, CodCtaMayorFin) = 101
),
movimientos_parseados AS (
    SELECT
        mb.*,
        CASE
            WHEN mb.nom_cta_mayor LIKE '%Santander%' THEN 'SANTANDER'
            WHEN mb.nom_cta_mayor LIKE '%Scotia%' OR mb.nom_cta_mayor LIKE '%SCOTIA%' THEN 'SCOTIABANK'
            WHEN mb.nom_cta_mayor LIKE '%Bajio%' OR mb.nom_cta_mayor LIKE '%BAJIO%' THEN 'BANBAJIO'
            WHEN mb.nom_cta_mayor LIKE '%Banamex%' OR mb.nom_cta_mayor LIKE '%BANAMEX%' THEN 'BANAMEX'
            ELSE NULL
        END AS bank_inferred,
        REVERSE(LEFT(REVERSE(mb.nom_cta_mayor), PATINDEX('%[^0-9]%', REVERSE(mb.nom_cta_mayor) + 'X') - 1)) AS trailing_digits_nom,
        REVERSE(LEFT(REVERSE(mb.nombre_cuenta_fin), PATINDEX('%[^0-9]%', REVERSE(mb.nombre_cuenta_fin) + 'X') - 1)) AS trailing_digits_name
    FROM movimientos_base mb
),
movimientos_con_cuenta AS (
    SELECT
        mp.*,
        CASE
            WHEN LEN(NULLIF(mp.trailing_digits_nom, '')) >= 4 THEN mp.trailing_digits_nom
            WHEN LEN(NULLIF(mp.trailing_digits_name, '')) >= 4 THEN mp.trailing_digits_name
            ELSE NULL
        END AS account_number_extracted
    FROM movimientos_parseados mp
),
matches AS (
    SELECT
        c.id AS source_statement_id,
        c.hash_archivo AS statement_uid,
        c.hash_archivo AS source_hash,
        c.nombre_archivo AS source_filename,
        c.no_cuenta AS account_number,
        c.clabe,
        c.razon_social AS entity_name,
        c.filial,
        UPPER(LTRIM(RTRIM(CAST(c.banco AS varchar(100))))) AS bank,
        CAST(DATEFROMPARTS(YEAR(c.fecha_final), MONTH(c.fecha_final), 1) AS date) AS period,
        mc.source_movement_key,
        mc.movement_date,
        mc.folio,
        mc.num_movto,
        mc.reference,
        mc.description,
        mc.concept,
        mc.deposit,
        mc.withdrawal,
        mc.importe_neto,
        mc.cliente,
        mc.plaza_fin,
        mc.grupo_fin,
        mc.diario_fin,
        mc.tipo_poliza_fin,
        mc.usuario,
        mc.move_name,
        mc.account_number_extracted,
        ROW_NUMBER() OVER (
            PARTITION BY mc.source_movement_key
            ORDER BY
                CASE
                    WHEN mc.account_number_extracted = c.no_cuenta THEN 1
                    WHEN RIGHT(c.no_cuenta, 4) = RIGHT(mc.account_number_extracted, 4) THEN 2
                    ELSE 99
                END,
                c.fecha_final DESC,
                c.id DESC
        ) AS rn
    FROM dbo.ConciliacionBancaria c
    INNER JOIN movimientos_con_cuenta mc
        ON mc.movement_date >= CAST(c.fecha_inicial AS date)
       AND mc.movement_date <= CAST(c.fecha_final AS date)
       AND (
            mc.account_number_extracted = c.no_cuenta
            OR (
                LEN(ISNULL(mc.account_number_extracted, '')) >= 4
                AND RIGHT(c.no_cuenta, 4) = RIGHT(mc.account_number_extracted, 4)
            )
       )
       AND (
            mc.bank_inferred IS NULL
            OR mc.bank_inferred = UPPER(LTRIM(RTRIM(CAST(c.banco AS varchar(100)))))
       )
),
movimientos_finales AS (
    SELECT
        TRY_CONVERT(bigint, ABS(CHECKSUM(source_movement_key))) AS source_movement_id,
        TRY_CONVERT(bigint, source_statement_id) AS source_statement_id,
        CAST(statement_uid AS varchar(255)) AS statement_uid,
        NULL AS bank_transaction_id,
        CAST(bank AS varchar(100)) AS bank,
        CAST(filial AS varchar(255)) AS filial,
        CAST(account_number AS varchar(100)) AS account_number,
        CAST(clabe AS varchar(100)) AS clabe,
        CAST(entity_name AS varchar(255)) AS entity_name,
        CAST(period AS date) AS period,
        CAST(movement_date AS date) AS movement_date,
        CAST(movement_date AS date) AS settlement_date,
        CAST(reference AS varchar(500)) AS reference,
        CAST(folio AS varchar(100)) AS folio,
        CAST(description AS varchar(1000)) AS description,
        CAST(concept AS varchar(1000)) AS concept,
        CAST(
            CASE
                WHEN ISNULL(deposit, 0) > 0 AND ISNULL(withdrawal, 0) = 0 THEN 'deposit'
                WHEN ISNULL(withdrawal, 0) > 0 AND ISNULL(deposit, 0) = 0 THEN 'withdrawal'
                WHEN ISNULL(importe_neto, 0) >= 0 THEN 'deposit'
                ELSE 'withdrawal'
            END
            AS varchar(50)
        ) AS movement_type,
        CAST(
            CASE
                WHEN ISNULL(deposit, 0) > 0 THEN deposit
                WHEN ISNULL(withdrawal, 0) > 0 THEN withdrawal
                ELSE ABS(ISNULL(importe_neto, 0))
            END
            AS decimal(18,2)
        ) AS amount,
        CAST(ISNULL(deposit, 0) AS decimal(18,2)) AS deposit,
        CAST(ISNULL(withdrawal, 0) AS decimal(18,2)) AS withdrawal,
        NULL AS balance,
        NULL AS liquidation_balance,
        NULL AS currency,
        CAST(NULL AS bit) AS reconciled,
        CAST(source_filename AS varchar(500)) AS source_filename,
        CAST(source_hash AS varchar(255)) AS source_hash,
        CAST(grupo_fin AS varchar(255)) AS source_group,
        CAST(NULL AS datetime) AS created_at_source,
        CAST(NULL AS datetime) AS updated_at_source
    FROM matches
    WHERE rn = 1
)
SELECT *
FROM movimientos_finales;