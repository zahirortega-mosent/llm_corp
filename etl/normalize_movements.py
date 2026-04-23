import hashlib
from pathlib import Path
from typing import Tuple

import numpy as np
import pandas as pd


GROUP_MAP = {
    "id.1": "layout_1_banamex_banbajio",
    "id.2": "layout_2_banbajio",
    "id.3": "layout_3_banorte",
    "id.4": "layout_4_banregio",
    "id.5": "layout_5_bbva",
    "id.6": "layout_6_santander",
    "id.7": "layout_7_scotiabank",
    "id.8": "layout_8_generic",
}


def coalesce(frame: pd.DataFrame, columns: list[str]) -> pd.Series:
    existing = [column for column in columns if column in frame.columns]
    if not existing:
        return pd.Series([pd.NA] * len(frame), index=frame.index, dtype="object")
    subset = frame[existing]
    return subset.bfill(axis=1).iloc[:, 0]


def to_numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def to_bool(series: pd.Series) -> pd.Series:
    def parse(value):
        if pd.isna(value):
            return False
        normalized = str(value).strip().lower()
        return normalized in {"1", "1.0", "true", "t", "yes", "si", "sí"}
    return series.map(parse)


def detect_source_group(frame: pd.DataFrame) -> pd.Series:
    result = pd.Series(["header_only"] * len(frame), index=frame.index, dtype="object")
    for group_id_column, group_name in GROUP_MAP.items():
        if group_id_column in frame.columns:
            mask = frame[group_id_column].notna()
            result.loc[mask] = group_name
    return result


def build_movement_uid(row: pd.Series) -> str:
    material = "|".join(
        [
            str(row.get("statement_uid") or ""),
            str(row.get("source_group") or ""),
            str(row.get("source_movement_id") or ""),
            str(row.get("movement_date") or ""),
            str(row.get("movement_type") or ""),
            f"{float(row.get('amount') or 0):.2f}",
            str(row.get("reference") or ""),
            str(row.get("description") or ""),
        ]
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def normalize_csv(csv_path: str | Path) -> Tuple[pd.DataFrame, pd.DataFrame]:
    csv_path = Path(csv_path)
    if not csv_path.exists():
        raise FileNotFoundError(f"No existe el CSV de origen: {csv_path}")

    frame = pd.read_csv(csv_path, low_memory=False)

    bank = frame["banco"].astype(str).str.upper().str.strip()
    source_group = detect_source_group(frame)

    statements = pd.DataFrame(
        {
            "source_statement_id": frame["id"],
            "statement_uid": frame["hash_archivo"],
            "source_hash": frame["hash_archivo"],
            "source_filename": frame["nombre_archivo"],
            "account_number": frame["no_cuenta"].astype(str).str.replace(r"\.0$", "", regex=True),
            "clabe": frame["clabe"].astype(str).replace("nan", pd.NA).str.replace(r"\.0$", "", regex=True),
            "entity_name": frame["razon_social"],
            "filial": frame["filial"],
            "bank": bank,
            "currency": frame["tipo_moneda"],
            "period": pd.to_datetime(frame["fecha_final"], errors="coerce").dt.to_period("M").dt.to_timestamp().dt.date,
            "period_start": pd.to_datetime(frame["fecha_inicial"], errors="coerce").dt.date,
            "period_end": pd.to_datetime(frame["fecha_final"], errors="coerce").dt.date,
            "opening_balance": to_numeric(frame["saldo_inicial"]),
            "closing_balance": to_numeric(frame["saldo_final"]),
            "total_deposits": to_numeric(frame["total_depositos"]),
            "total_withdrawals": to_numeric(frame["total_retiros"]),
            "reconciled_deposit_balance": to_numeric(frame["saldo_deposito_conciliado"]),
            "reconciled_withdrawal_balance": to_numeric(frame["saldo_retiro_conciliado"]),
            "statement_balance_ok": to_bool(frame["saldo_correcto"]),
            "created_at_source": pd.to_datetime(frame["created_at"], errors="coerce"),
            "updated_at_source": pd.to_datetime(frame["updated_at"], errors="coerce"),
        }
    ).drop_duplicates(subset=["statement_uid"], keep="first")

    movements = pd.DataFrame(
        {
            "source_movement_id": coalesce(frame, ["id.1", "id.2", "id.3", "id.4", "id.5", "id.6", "id.7", "id.8"]),
            "source_statement_id": frame["id"],
            "statement_uid": frame["hash_archivo"],
            "bank_transaction_id": coalesce(
                frame,
                [
                    "banco_transaccion_id",
                    "banco_transaccion_id.1",
                    "banco_transaccion_id.2",
                    "banco_transaccion_id.3",
                    "banco_transaccion_id.4",
                    "banco_transaccion_id.5",
                    "banco_transaccion_id.6",
                    "banco_transaccion_id.7",
                ],
            ),
            "bank": bank,
            "filial": frame["filial"],
            "account_number": frame["no_cuenta"].astype(str).str.replace(r"\.0$", "", regex=True),
            "clabe": frame["clabe"].astype(str).replace("nan", pd.NA).str.replace(r"\.0$", "", regex=True),
            "entity_name": frame["razon_social"],
            "period": pd.to_datetime(frame["fecha_final"], errors="coerce").dt.to_period("M").dt.to_timestamp().dt.date,
            "movement_date": pd.to_datetime(
                coalesce(frame, ["fecha", "fecha.1", "fecha.2", "fecha.3", "fecha.4", "fecha.5", "fecha.6", "fecha.7"]),
                errors="coerce",
            ).dt.date,
            "settlement_date": pd.to_datetime(frame["fecha_liquidacion"], errors="coerce").dt.date,
            "reference": coalesce(frame, ["referencia", "referencia.1", "folio"]),
            "folio": frame.get("folio"),
            "description": coalesce(
                frame,
                ["descripcion", "descripcion.1", "descripcion.2", "descripcion.3", "descripcion.4", "concepto", "concepto.1", "concepto.2"],
            ),
            "concept": coalesce(frame, ["concepto", "concepto.1", "concepto.2"]),
            "deposit": to_numeric(coalesce(frame, ["deposito", "deposito.1", "deposito.2", "deposito.3", "deposito.4", "deposito.5", "deposito.6", "deposito.7"])).fillna(0),
            "withdrawal": to_numeric(coalesce(frame, ["retiro", "retiro.1", "retiro.2", "retiro.3", "retiro.4", "retiro.5", "retiro.6", "retiro.7"])).fillna(0),
            "balance": to_numeric(coalesce(frame, ["saldo", "saldo.1", "saldo.2", "saldo.3", "saldo.4", "saldo.5", "saldo.6", "saldo.7"])),
            "liquidation_balance": to_numeric(frame["saldo_liquidacion"]),
            "currency": coalesce(frame, ["tipo_moneda.1", "tipo_moneda"]),
            "reconciled": to_bool(
                coalesce(frame, ["conciliado", "conciliado.1", "conciliado.2", "conciliado.3", "conciliado.4", "conciliado.5", "conciliado.6"])
            ),
            "source_filename": frame["nombre_archivo"],
            "source_hash": frame["hash_archivo"],
            "source_group": source_group,
            "raw_payload": None,
            "created_at_source": pd.to_datetime(
                coalesce(frame, ["created_at.1", "created_at.2", "created_at.3", "created_at.4", "created_at.5", "created_at.6", "created_at.7", "created_at.8"]),
                errors="coerce",
            ),
            "updated_at_source": pd.to_datetime(
                coalesce(frame, ["updated_at.1", "updated_at.2", "updated_at.3", "updated_at.4", "updated_at.5", "updated_at.6", "updated_at.7", "updated_at.8"]),
                errors="coerce",
            ),
        }
    )

    movements["movement_type"] = np.where(
        movements["deposit"].fillna(0) > 0,
        "deposit",
        np.where(movements["withdrawal"].fillna(0) > 0, "withdrawal", "unknown"),
    )
    movements["amount"] = np.where(
        movements["deposit"].fillna(0) > 0,
        movements["deposit"].fillna(0),
        np.where(movements["withdrawal"].fillna(0) > 0, movements["withdrawal"].fillna(0), 0),
    )

    movements = movements[
        [
            "source_movement_id",
            "source_statement_id",
            "statement_uid",
            "bank_transaction_id",
            "bank",
            "filial",
            "account_number",
            "clabe",
            "entity_name",
            "period",
            "movement_date",
            "settlement_date",
            "reference",
            "folio",
            "description",
            "concept",
            "movement_type",
            "amount",
            "deposit",
            "withdrawal",
            "balance",
            "liquidation_balance",
            "currency",
            "reconciled",
            "source_filename",
            "source_hash",
            "source_group",
            "raw_payload",
            "created_at_source",
            "updated_at_source",
        ]
    ]

    movements["movement_uid"] = movements.apply(build_movement_uid, axis=1)
    movements = movements[movements["source_movement_id"].notna()].copy()
    movements = movements[
        [
            "movement_uid",
            "source_movement_id",
            "source_statement_id",
            "statement_uid",
            "bank_transaction_id",
            "bank",
            "filial",
            "account_number",
            "clabe",
            "entity_name",
            "period",
            "movement_date",
            "settlement_date",
            "reference",
            "folio",
            "description",
            "concept",
            "movement_type",
            "amount",
            "deposit",
            "withdrawal",
            "balance",
            "liquidation_balance",
            "currency",
            "reconciled",
            "source_filename",
            "source_hash",
            "source_group",
            "raw_payload",
            "created_at_source",
            "updated_at_source",
        ]
    ]

    movement_counts = (
        movements.assign(has_child=movements["source_movement_id"].notna())
        .groupby("statement_uid", as_index=False)["has_child"]
        .max()
        .rename(columns={"has_child": "has_child_movements"})
    )
    statements = statements.merge(movement_counts, on="statement_uid", how="left")
    statements["header_only"] = ~statements["has_child_movements"].fillna(False)
    statements = statements.drop(columns=["has_child_movements"])

    return statements, movements
