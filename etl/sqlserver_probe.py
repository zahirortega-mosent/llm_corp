from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import pymssql

from extract_sqlserver import SourceConfigError

CANDIDATES = [
    'dbo.ConciliacionBancaria',
    'dbo.MovimientosFinancieros',
    'dbo.MovimientosFinancieros_Corporativo',
    'dbo.vwMovimientosFinancierosPABS',
    'curated.fact_account_move_line',
    'staging.odoo_account_move_line',
]


def connect():
    password = os.getenv('SQLSERVER_PASSWORD', '')
    if not password:
        raise SourceConfigError('Falta SQLSERVER_PASSWORD en .env')
    server = os.getenv('SQLSERVER_SERVER', r'192.168.0.10\POWERBI')
    port = os.getenv('SQLSERVER_PORT', '').strip()
    if port:
        server = f"{server}:{port}"
    return pymssql.connect(
        server=server,
        user=os.getenv('SQLSERVER_USERNAME', 'sa'),
        password=password,
        database=os.getenv('SQLSERVER_DATABASE', 'DataLake'),
        login_timeout=int(os.getenv('SQLSERVER_LOGIN_TIMEOUT_SECONDS', '15')),
        timeout=int(os.getenv('SQLSERVER_TIMEOUT_SECONDS', '120')),
        charset='UTF-8',
    )


def main() -> None:
    output_dir = Path(os.getenv('ETL_OUTPUT_DIR', '/data/output'))
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    with connect() as conn:
        for candidate in CANDIDATES:
            try:
                count = pd.read_sql(f'SELECT COUNT(*) AS total FROM {candidate}', conn).iloc[0]['total']
                sample = pd.read_sql(f'SELECT TOP 5 * FROM {candidate}', conn)
                sample_path = output_dir / f"probe_{candidate.replace('.', '_')}.csv"
                sample.to_csv(sample_path, index=False)
                rows.append({'object_name': candidate, 'total_rows': int(count), 'sample_csv': str(sample_path), 'error': ''})
                print(f'[OK] {candidate}: {count} filas')
            except Exception as exc:
                rows.append({'object_name': candidate, 'total_rows': None, 'sample_csv': '', 'error': str(exc)})
                print(f'[WARN] {candidate}: {exc}')
    pd.DataFrame(rows).to_csv(output_dir / 'sqlserver_probe_summary.csv', index=False)
    print(output_dir / 'sqlserver_probe_summary.csv')


if __name__ == '__main__':
    main()
