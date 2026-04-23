SELECT
    TRY_CONVERT(BIGINT, id) AS source_statement_id,

    CAST(
        COALESCE(
            NULLIF(LTRIM(RTRIM(CAST(hash_archivo AS VARCHAR(255)))), ''),
            CONVERT(VARCHAR(64), HASHBYTES(
                'SHA2_256',
                CONCAT(
                    ISNULL(CAST(id AS VARCHAR(50)), ''),
                    '|', ISNULL(CAST(no_cuenta AS VARCHAR(100)), ''),
                    '|', ISNULL(CAST(clabe AS VARCHAR(100)), ''),
                    '|', ISNULL(CAST(banco AS VARCHAR(100)), ''),
                    '|', ISNULL(CONVERT(VARCHAR(10), CAST(fecha_inicial AS DATE), 23), ''),
                    '|', ISNULL(CONVERT(VARCHAR(10), CAST(fecha_final AS DATE), 23), ''),
                    '|', ISNULL(CAST(nombre_archivo AS VARCHAR(500)), '')
                )
            ), 2)
        ) AS VARCHAR(255)
    ) AS statement_uid,

    CAST(
        COALESCE(
            NULLIF(LTRIM(RTRIM(CAST(hash_archivo AS VARCHAR(255)))), ''),
            CONVERT(VARCHAR(64), HASHBYTES(
                'SHA2_256',
                CONCAT(
                    ISNULL(CAST(id AS VARCHAR(50)), ''),
                    '|', ISNULL(CAST(no_cuenta AS VARCHAR(100)), ''),
                    '|', ISNULL(CAST(clabe AS VARCHAR(100)), ''),
                    '|', ISNULL(CAST(banco AS VARCHAR(100)), ''),
                    '|', ISNULL(CONVERT(VARCHAR(10), CAST(fecha_inicial AS DATE), 23), ''),
                    '|', ISNULL(CONVERT(VARCHAR(10), CAST(fecha_final AS DATE), 23), ''),
                    '|', ISNULL(CAST(nombre_archivo AS VARCHAR(500)), '')
                )
            ), 2)
        ) AS VARCHAR(255)
    ) AS source_hash,

    CAST(nombre_archivo AS VARCHAR(500)) AS source_filename,
    CAST(no_cuenta AS VARCHAR(100)) AS account_number,
    CAST(clabe AS VARCHAR(100)) AS clabe,
    CAST(razon_social AS VARCHAR(255)) AS entity_name,
    CAST(filial AS VARCHAR(255)) AS filial,
    UPPER(LTRIM(RTRIM(CAST(banco AS VARCHAR(100))))) AS bank,
    NULL AS currency,
    CAST(DATEFROMPARTS(YEAR(fecha_final), MONTH(fecha_final), 1) AS DATE) AS period,
    CAST(fecha_inicial AS DATE) AS period_start,
    CAST(fecha_final AS DATE) AS period_end,
    TRY_CONVERT(DECIMAL(18,2), saldo_inicial) AS opening_balance,
    TRY_CONVERT(DECIMAL(18,2), saldo_final) AS closing_balance,
    TRY_CONVERT(DECIMAL(18,2), depositos) AS total_deposits,
    TRY_CONVERT(DECIMAL(18,2), retiros) AS total_withdrawals,
    TRY_CONVERT(DECIMAL(18,2), saldo_deposito_conciliado) AS reconciled_deposit_balance,
    TRY_CONVERT(DECIMAL(18,2), saldo_retiro_conciliado) AS reconciled_withdrawal_balance,
    TRY_CONVERT(BIT, saldo_correcto) AS statement_balance_ok,
    CAST(created_at AS DATETIME) AS created_at_source,
    CAST(updated_at AS DATETIME) AS updated_at_source
FROM dbo.ConciliacionBancaria;