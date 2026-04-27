import hashlib
import json
import os
import re
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

from catalogs import BUSINESS_RULES
from extract_sqlserver import SourceConfigError, read_normalized_frames
from load_knowledge import load_all_knowledge
from normalize_movements import normalize_csv, build_movement_uid


STATEMENT_PATH_PATTERN = re.compile(r"^EdoCuentaGrupoMosent/.+/20\d{2} \d{2} [A-Za-z]{3}.+\.pdf$", re.IGNORECASE)
TRANSFER_KEYWORDS = ["traspaso", "transferencia", "transfer", "spei", "tef"]
GROUP_MARKERS = [
    "mosent",
    "pabs",
    "latino",
    "latinoamericana",
    "percapita",
    "dire movil",
    "diremovil",
    "solarum",
    "zell",
    "cooperativa",
    "servicios a futuro",
]


def settings_from_env() -> dict:
    db = os.getenv("POSTGRES_DB", "conciliador_mvp")
    user = os.getenv("POSTGRES_USER", "conciliador")
    password = os.getenv("POSTGRES_PASSWORD", "conciliador_local_2026")
    host = os.getenv("POSTGRES_HOST", "db")
    port = os.getenv("POSTGRES_PORT", "5432")
    return {
        "database_url": f"postgresql+psycopg://{user}:{password}@{host}:{port}/{db}",
        "data_source_mode": os.getenv("DATA_SOURCE_MODE", "sqlserver").strip().lower(),
        "csv_source_path": os.getenv("CSV_SOURCE_PATH", "/data/input/conciliador_movimientos_pdf_enero_febrero.csv"),
        "pdf_source_path": os.getenv("PDF_SOURCE_PATH", "/data/input/Conciliador_zahir_1.1.pdf"),
        "source_code_path": os.getenv("SOURCE_CODE_PATH", "/data/input/conciliacion_mosent-main"),
        "source_code_paths": os.getenv("SOURCE_CODE_PATHS", "/data/input/codebases"),
        "assignments_path": os.getenv("ASSIGNMENTS_PATH", "/data/input/assignments.csv"),
        "etl_output_dir": os.getenv("ETL_OUTPUT_DIR", "/data/output"),
        "sqlserver_server": os.getenv("SQLSERVER_SERVER", r"192.168.0.10\POWERBI"),
        "sqlserver_database": os.getenv("SQLSERVER_DATABASE", "DataLake"),
        "sqlserver_username": os.getenv("SQLSERVER_USERNAME", "sa"),
        "sqlserver_password": os.getenv("SQLSERVER_PASSWORD", ""),
        "sqlserver_port": os.getenv("SQLSERVER_PORT", "").strip() or None,
        "sqlserver_statements_query_file": os.getenv("SQLSERVER_STATEMENTS_QUERY_FILE", "/app/config/sqlserver_queries/statements.sql"),
        "sqlserver_movements_query_file": os.getenv("SQLSERVER_MOVEMENTS_QUERY_FILE", "/app/config/sqlserver_queries/movements.sql"),
        "sqlserver_login_timeout_seconds": int(os.getenv("SQLSERVER_LOGIN_TIMEOUT_SECONDS", "15")),
        "sqlserver_timeout_seconds": int(os.getenv("SQLSERVER_TIMEOUT_SECONDS", "120")),
    }


def sha(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def normalize_text(value: str | None) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).lower()).strip()


def is_blank(value) -> bool:
    if pd.isna(value):
        return True
    return not str(value).strip()


def prepare_output_dir(path: str | Path) -> Path:
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_source_code_locations(cfg: dict) -> list[str]:
    locations = [item.strip() for item in str(cfg.get("source_code_paths") or "").split(",") if item.strip()]
    legacy = str(cfg.get("source_code_path") or "").strip()
    if legacy and legacy not in locations:
        locations.append(legacy)
    return locations


def coerce_statement_types(statements: pd.DataFrame, movements: pd.DataFrame) -> pd.DataFrame:
    statements = statements.copy()
    for column in ["period", "period_start", "period_end", "created_at_source", "updated_at_source"]:
        if column in statements.columns:
            statements[column] = pd.to_datetime(statements[column], errors="coerce")
    if "period" in statements.columns:
        statements["period"] = statements["period"].dt.date
    if "period_start" in statements.columns:
        statements["period_start"] = statements["period_start"].dt.date
    if "period_end" in statements.columns:
        statements["period_end"] = statements["period_end"].dt.date
    for column in ["opening_balance", "closing_balance", "total_deposits", "total_withdrawals", "reconciled_deposit_balance", "reconciled_withdrawal_balance"]:
        if column in statements.columns:
            statements[column] = pd.to_numeric(statements[column], errors="coerce")
    if "statement_balance_ok" in statements.columns:
        statements["statement_balance_ok"] = statements["statement_balance_ok"].map(lambda v: str(v).strip().lower() in {"1", "true", "t", "yes"} if pd.notna(v) else False)
    statements = statements.drop_duplicates(subset=["statement_uid"], keep="first")
    if "source_movement_id" in movements.columns and not movements.empty:
        counts = movements.assign(has_child=movements["source_movement_id"].notna()).groupby("statement_uid", as_index=False)["has_child"].max().rename(columns={"has_child": "has_child_movements"})
        statements = statements.merge(counts, on="statement_uid", how="left")
        statements["header_only"] = ~statements["has_child_movements"].fillna(False)
        statements = statements.drop(columns=["has_child_movements"])
    else:
        statements["header_only"] = True
    return statements


def coerce_movement_types(movements: pd.DataFrame) -> pd.DataFrame:
    movements = movements.copy()
    for column in ["period", "movement_date", "settlement_date", "created_at_source", "updated_at_source"]:
        if column in movements.columns:
            movements[column] = pd.to_datetime(movements[column], errors="coerce")
    if "period" in movements.columns:
        movements["period"] = movements["period"].dt.date
    if "movement_date" in movements.columns:
        movements["movement_date"] = movements["movement_date"].dt.date
    if "settlement_date" in movements.columns:
        movements["settlement_date"] = movements["settlement_date"].dt.date
    for column in ["amount", "deposit", "withdrawal", "balance", "liquidation_balance"]:
        if column in movements.columns:
            movements[column] = pd.to_numeric(movements[column], errors="coerce")
    if "reconciled" in movements.columns:
        movements["reconciled"] = movements["reconciled"].map(lambda v: str(v).strip().lower() in {"1", "true", "t", "yes"} if pd.notna(v) else False)
    if "movement_uid" not in movements.columns:
        movements["movement_uid"] = movements.apply(build_movement_uid, axis=1)
    return movements


def load_source_frames(cfg: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    mode = cfg["data_source_mode"]
    if mode == "csv":
        return normalize_csv(cfg["csv_source_path"])
    if mode == "sqlserver":
        class SettingsShim:
            pass
        settings = SettingsShim()
        for key, value in cfg.items():
            setattr(settings, key, value)
        statements, movements = read_normalized_frames(settings)
        movements = coerce_movement_types(movements)
        statements = coerce_statement_types(statements, movements)
        return statements, movements
    raise ValueError(f"DATA_SOURCE_MODE no soportado: {mode}")


def write_assignment_template(statements: pd.DataFrame, output_dir: Path) -> Path:
    template_path = output_dir / "assignments_template.csv"
    template = (
        statements[["filial", "bank", "account_number"]]
        .drop_duplicates()
        .sort_values(["filial", "bank", "account_number"])
        .assign(owner_name="", area="", email="")
    )
    template.to_csv(template_path, index=False)
    return template_path


def load_assignments(assignments_path: str | Path, output_dir: Path, statements: pd.DataFrame) -> pd.DataFrame:
    assignments_path = Path(assignments_path)
    template_path = write_assignment_template(statements, output_dir)
    if not assignments_path.exists():
        print(f"[WARN] No existe assignments.csv. Se generó plantilla en {template_path}")
        return pd.DataFrame(columns=["filial", "bank", "account_number", "owner_name", "area", "email"])

    frame = pd.read_csv(assignments_path, dtype=str).fillna("")
    rename_map = {
        "responsable": "owner_name",
        "correo": "email",
        "cuenta": "account_number",
        "no_cuenta": "account_number",
        "banco": "bank",
    }
    frame = frame.rename(columns=rename_map)
    required = ["filial", "bank", "account_number", "owner_name", "area", "email"]
    for column in required:
        if column not in frame.columns:
            frame[column] = ""
    frame = frame[required].copy()
    frame["bank"] = frame["bank"].str.upper().str.strip()
    frame["account_number"] = frame["account_number"].str.strip()
    frame["filial"] = frame["filial"].str.strip()
    frame = frame.drop_duplicates(subset=["filial", "bank", "account_number"])
    print(f"[OK] assignments.csv cargado con {len(frame)} filas. Plantilla base: {template_path}")
    return frame


def build_incidents(statements: pd.DataFrame, movements: pd.DataFrame, assignments: pd.DataFrame) -> pd.DataFrame:
    incidents = []

    statement_lookup = statements.set_index("statement_uid")[
        [
            "period",
            "period_start",
            "period_end",
            "bank",
            "filial",
            "account_number",
            "source_filename",
            "opening_balance",
            "closing_balance",
            "total_deposits",
            "total_withdrawals",
            "statement_balance_ok",
            "header_only",
        ]
    ].to_dict(orient="index")

    movement_counts = {}
    if not movements.empty and "statement_uid" in movements.columns:
        movement_counts = movements.groupby("statement_uid").size().to_dict()

    assignments_lookup = {}
    if not assignments.empty:
        assignments_lookup = {
            (row["filial"], row["bank"], row["account_number"]): row
            for _, row in assignments.iterrows()
        }

    def add_incident(
        rule_code: str,
        severity: str,
        title: str,
        description: str,
        period=None,
        bank=None,
        filial=None,
        account_number=None,
        statement_uid=None,
        movement_uid=None,
        source_filename=None,
        suggested_owner=None,
        evidence=None,
    ):
        incident_uid = sha(rule_code, str(statement_uid), str(movement_uid), str(source_filename), str(description))
        incidents.append(
            {
                "incident_uid": incident_uid,
                "rule_code": rule_code,
                "period": period,
                "bank": bank,
                "filial": filial,
                "account_number": account_number,
                "statement_uid": statement_uid,
                "movement_uid": movement_uid,
                "source_filename": source_filename,
                "severity": severity,
                "title": title,
                "description": description,
                "status": "abierta",
                "suggested_owner": suggested_owner,
                "evidence": evidence,
            }
        )

    for _, row in statements[statements["statement_balance_ok"] == False].iterrows():
        opening_balance = float(row.get("opening_balance") or 0)
        closing_balance = float(row.get("closing_balance") or 0)
        total_deposits = float(row.get("total_deposits") or 0)
        total_withdrawals = float(row.get("total_withdrawals") or 0)
        calculated_closing_balance = opening_balance + total_deposits - total_withdrawals
        difference_vs_declared = closing_balance - calculated_closing_balance
        evidence = {
            "statement_uid": row.get("statement_uid"),
            "period": str(row.get("period")) if pd.notna(row.get("period")) else None,
            "period_start": str(row.get("period_start")) if pd.notna(row.get("period_start")) else None,
            "period_end": str(row.get("period_end")) if pd.notna(row.get("period_end")) else None,
            "opening_balance": opening_balance,
            "closing_balance": closing_balance,
            "total_deposits": total_deposits,
            "total_withdrawals": total_withdrawals,
            "calculated_closing_balance": calculated_closing_balance,
            "difference_vs_declared": difference_vs_declared,
            "statement_balance_ok": bool(row.get("statement_balance_ok")),
            "movement_count_for_statement": int(movement_counts.get(row.get("statement_uid"), 0)),
        }
        add_incident(
            "STATEMENT_BALANCE_MISMATCH",
            "critica",
            "Descuadre de saldo en estado de cuenta",
            (
                f"El archivo {row['source_filename']} presenta descuadre de saldo. "
                f"Saldo inicial {opening_balance:,.2f}, depósitos {total_deposits:,.2f}, retiros {total_withdrawals:,.2f}, "
                f"saldo final declarado {closing_balance:,.2f} y saldo calculado {calculated_closing_balance:,.2f}."
            ),
            period=row["period"],
            bank=row["bank"],
            filial=row["filial"],
            account_number=row["account_number"],
            statement_uid=row["statement_uid"],
            source_filename=row["source_filename"],
            evidence=evidence,
        )

    for _, row in statements[statements["header_only"] == True].iterrows():
        evidence = {
            "statement_uid": row.get("statement_uid"),
            "period": str(row.get("period")) if pd.notna(row.get("period")) else None,
            "movement_count_for_statement": int(movement_counts.get(row.get("statement_uid"), 0)),
            "header_only": bool(row.get("header_only")),
        }
        add_incident(
            "HEADER_WITHOUT_MOVEMENTS",
            "alta",
            "Estado de cuenta sin movimientos hijos",
            (
                f"El archivo {row['source_filename']} se cargó como cabecera sin movimientos normalizados. "
                f"Movimientos asociados detectados: {int(movement_counts.get(row.get('statement_uid'), 0))}."
            ),
            period=row["period"],
            bank=row["bank"],
            filial=row["filial"],
            account_number=row["account_number"],
            statement_uid=row["statement_uid"],
            source_filename=row["source_filename"],
            evidence=evidence,
        )

    for _, row in statements[~statements["source_filename"].astype(str).str.match(STATEMENT_PATH_PATTERN, na=False)].iterrows():
        add_incident(
            "FILENAME_PATTERN_WARNING",
            "media",
            "Ruta o nomenclatura no homologada",
            f"La ruta/nombre {row['source_filename']} no coincide con el patrón esperado de estados de cuenta.",
            period=row["period"],
            bank=row["bank"],
            filial=row["filial"],
            account_number=row["account_number"],
            statement_uid=row["statement_uid"],
            source_filename=row["source_filename"],
        )

    movement_frame = movements.copy()
    movement_frame["description_norm"] = movement_frame["description"].fillna("").astype(str).str.lower().str.replace(r"\s+", " ", regex=True).str.strip()
    duplicate_mask = movement_frame.duplicated(
        subset=["bank", "account_number", "movement_date", "amount", "movement_type", "description_norm"],
        keep=False,
    )

    for _, row in movement_frame.iterrows():
        stmt = statement_lookup.get(row["statement_uid"], {})
        owner = assignments_lookup.get((row["filial"], row["bank"], row["account_number"]))
        owner_name = owner.get("owner_name") if isinstance(owner, dict) else None

        if pd.isna(row["movement_date"]):
            add_incident(
                "MISSING_MOVEMENT_DATE",
                "alta",
                "Movimiento sin fecha",
                "No se identificó fecha de movimiento en el registro normalizado.",
                period=row["period"],
                bank=row["bank"],
                filial=row["filial"],
                account_number=row["account_number"],
                statement_uid=row["statement_uid"],
                movement_uid=row["movement_uid"],
                source_filename=row["source_filename"],
                suggested_owner=owner_name,
            )

        if is_blank(row.get("description")):
            add_incident(
                "MISSING_DESCRIPTION",
                "media",
                "Movimiento sin descripción",
                "No se identificó descripción ni concepto para el movimiento.",
                period=row["period"],
                bank=row["bank"],
                filial=row["filial"],
                account_number=row["account_number"],
                statement_uid=row["statement_uid"],
                movement_uid=row["movement_uid"],
                source_filename=row["source_filename"],
                suggested_owner=owner_name,
            )

        if is_blank(row.get("reference")):
            add_incident(
                "MISSING_REFERENCE",
                "media",
                "Movimiento sin referencia",
                "No se identificó referencia, folio o equivalente para el movimiento.",
                period=row["period"],
                bank=row["bank"],
                filial=row["filial"],
                account_number=row["account_number"],
                statement_uid=row["statement_uid"],
                movement_uid=row["movement_uid"],
                source_filename=row["source_filename"],
                suggested_owner=owner_name,
            )

        if float(row.get("amount") or 0) == 0:
            add_incident(
                "ZERO_AMOUNT_MOVEMENT",
                "alta",
                "Movimiento sin importe",
                "El movimiento no tiene depósito ni retiro distinto de cero.",
                period=row["period"],
                bank=row["bank"],
                filial=row["filial"],
                account_number=row["account_number"],
                statement_uid=row["statement_uid"],
                movement_uid=row["movement_uid"],
                source_filename=row["source_filename"],
                suggested_owner=owner_name,
            )

        if float(row.get("deposit") or 0) > 0 and float(row.get("withdrawal") or 0) > 0:
            add_incident(
                "BOTH_DEPOSIT_AND_WITHDRAWAL",
                "alta",
                "Movimiento con depósito y retiro simultáneos",
                "El mismo registro trae monto en depósito y retiro.",
                period=row["period"],
                bank=row["bank"],
                filial=row["filial"],
                account_number=row["account_number"],
                statement_uid=row["statement_uid"],
                movement_uid=row["movement_uid"],
                source_filename=row["source_filename"],
                suggested_owner=owner_name,
            )

        if float(row.get("deposit") or 0) < 0 or float(row.get("withdrawal") or 0) < 0:
            add_incident(
                "NEGATIVE_SIGN_VALUE",
                "media",
                "Signo inconsistente en importe",
                "Se detectó un importe negativo en depósito o retiro.",
                period=row["period"],
                bank=row["bank"],
                filial=row["filial"],
                account_number=row["account_number"],
                statement_uid=row["statement_uid"],
                movement_uid=row["movement_uid"],
                source_filename=row["source_filename"],
                suggested_owner=owner_name,
            )

        period_start = stmt.get("period_start")
        period_end = stmt.get("period_end")
        movement_date = row.get("movement_date")
        if pd.notna(movement_date) and pd.notna(period_start) and movement_date < period_start:
            add_incident(
                "OUTSIDE_PERIOD_RANGE",
                "alta",
                "Movimiento anterior al periodo del estado de cuenta",
                f"La fecha {movement_date} es anterior al inicio {period_start}.",
                period=row["period"],
                bank=row["bank"],
                filial=row["filial"],
                account_number=row["account_number"],
                statement_uid=row["statement_uid"],
                movement_uid=row["movement_uid"],
                source_filename=row["source_filename"],
                suggested_owner=owner_name,
            )
        if pd.notna(movement_date) and pd.notna(period_end) and movement_date > period_end:
            add_incident(
                "OUTSIDE_PERIOD_RANGE",
                "alta",
                "Movimiento posterior al periodo del estado de cuenta",
                f"La fecha {movement_date} es posterior al cierre {period_end}.",
                period=row["period"],
                bank=row["bank"],
                filial=row["filial"],
                account_number=row["account_number"],
                statement_uid=row["statement_uid"],
                movement_uid=row["movement_uid"],
                source_filename=row["source_filename"],
                suggested_owner=owner_name,
            )

        if not bool(row.get("reconciled")):
            add_incident(
                "UNRECONCILED_MOVEMENT",
                "media",
                "Movimiento no conciliado",
                "El movimiento permanece sin conciliar en el dataset normalizado.",
                period=row["period"],
                bank=row["bank"],
                filial=row["filial"],
                account_number=row["account_number"],
                statement_uid=row["statement_uid"],
                movement_uid=row["movement_uid"],
                source_filename=row["source_filename"],
                suggested_owner=owner_name,
            )

        if duplicate_mask.loc[row.name]:
            add_incident(
                "DUPLICATE_HEURISTIC",
                "alta",
                "Posible movimiento duplicado",
                "El movimiento comparte banco, cuenta, fecha, importe, tipo y descripción con otros registros.",
                period=row["period"],
                bank=row["bank"],
                filial=row["filial"],
                account_number=row["account_number"],
                statement_uid=row["statement_uid"],
                movement_uid=row["movement_uid"],
                source_filename=row["source_filename"],
                suggested_owner=owner_name,
            )

        operation_text = normalize_text(f"{row.get('description', '')} {row.get('reference', '')}")
        if any(keyword in operation_text for keyword in TRANSFER_KEYWORDS) and any(marker in operation_text for marker in GROUP_MARKERS):
            add_incident(
                "POTENTIAL_INTERCOMPANY_TRANSFER",
                "alta",
                "Posible transferencia intercompañía",
                "El texto del movimiento sugiere traspaso/transferencia relacionado con entidades del grupo.",
                period=row["period"],
                bank=row["bank"],
                filial=row["filial"],
                account_number=row["account_number"],
                statement_uid=row["statement_uid"],
                movement_uid=row["movement_uid"],
                source_filename=row["source_filename"],
                suggested_owner=owner_name,
            )

        if assignments_lookup and owner is None:
            add_incident(
                "NO_RESPONSIBLE_ASSIGNED",
                "media",
                "Cuenta sin responsable asignado",
                "La cuenta no existe en el catálogo assignments.csv cargado para esta filial y banco.",
                period=row["period"],
                bank=row["bank"],
                filial=row["filial"],
                account_number=row["account_number"],
                statement_uid=row["statement_uid"],
                movement_uid=row["movement_uid"],
                source_filename=row["source_filename"],
                suggested_owner=None,
            )

    incidents_df = pd.DataFrame(incidents).drop_duplicates(subset=["incident_uid"])
    return incidents_df


def truncate_tables(engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                TRUNCATE TABLE
                    incidents,
                    bank_movements,
                    bank_statements,
                    knowledge_snippets,
                    business_rules,
                    assignments
                RESTART IDENTITY CASCADE
                """
            )
        )


def insert_rules(engine) -> None:
    sql = text(
        """
        INSERT INTO business_rules(
            rule_code, title, description, origin, severity, applies_to,
            auto_detectable, keywords, normative_basis, recommendation
        )
        VALUES (
            :rule_code, :title, :description, :origin, :severity, :applies_to,
            :auto_detectable, :keywords, :normative_basis, :recommendation
        )
        """
    )
    with engine.begin() as conn:
        conn.execute(sql, BUSINESS_RULES)


def insert_knowledge(engine, snippets: list[dict]) -> None:
    if not snippets:
        return

    sql = text(
        """
        INSERT INTO knowledge_snippets(
            snippet_uid, source_type, source_name, source_path, page_number, title, content, tags
        )
        VALUES (
            :snippet_uid, :source_type, :source_name, :source_path, :page_number, :title, :content, :tags
        )
        """
    )

    clean = []
    for item in snippets:
        row = dict(item)
        if "tags" in row and isinstance(row["tags"], (dict, list)):
            row["tags"] = json.dumps(row["tags"], ensure_ascii=False)
        clean.append(row)

    with engine.begin() as conn:
        conn.execute(sql, clean)


def insert_bank_movements(engine, movements: pd.DataFrame, chunksize: int = 500) -> None:
    cols = [
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
        "created_at_source",
        "updated_at_source",
    ]

    insert_sql = text(
        """
        INSERT INTO bank_movements (
            movement_uid,
            source_movement_id,
            source_statement_id,
            statement_uid,
            bank_transaction_id,
            bank,
            filial,
            account_number,
            clabe,
            entity_name,
            period,
            movement_date,
            settlement_date,
            reference,
            folio,
            description,
            concept,
            movement_type,
            amount,
            deposit,
            withdrawal,
            balance,
            liquidation_balance,
            currency,
            reconciled,
            source_filename,
            source_hash,
            source_group,
            raw_payload,
            created_at_source,
            updated_at_source
        ) VALUES (
            :movement_uid,
            :source_movement_id,
            :source_statement_id,
            :statement_uid,
            :bank_transaction_id,
            :bank,
            :filial,
            :account_number,
            :clabe,
            :entity_name,
            :period,
            :movement_date,
            :settlement_date,
            :reference,
            :folio,
            :description,
            :concept,
            :movement_type,
            :amount,
            :deposit,
            :withdrawal,
            :balance,
            :liquidation_balance,
            :currency,
            :reconciled,
            :source_filename,
            :source_hash,
            :source_group,
            CAST(:raw_payload AS jsonb),
            :created_at_source,
            :updated_at_source
        )
        """
    )

    frame = movements.copy()

    for col in cols:
        if col not in frame.columns:
            frame[col] = None

    frame = frame[cols].copy()
    frame = frame.where(pd.notna(frame), None)
    frame["raw_payload"] = None

    records = frame.to_dict(orient="records")

    with engine.begin() as conn:
        for i in range(0, len(records), chunksize):
            batch = records[i:i + chunksize]
            for row in batch:
                row["raw_payload"] = None
            conn.execute(insert_sql, batch)


def insert_incidents(engine, incidents: pd.DataFrame, chunksize: int = 500) -> None:
    cols = [
        "incident_uid",
        "rule_code",
        "period",
        "bank",
        "filial",
        "account_number",
        "statement_uid",
        "movement_uid",
        "source_filename",
        "severity",
        "title",
        "description",
        "status",
        "suggested_owner",
        "evidence",
    ]

    insert_sql = text(
        """
        INSERT INTO incidents (
            incident_uid,
            rule_code,
            period,
            bank,
            filial,
            account_number,
            statement_uid,
            movement_uid,
            source_filename,
            severity,
            title,
            description,
            status,
            suggested_owner,
            evidence
        ) VALUES (
            :incident_uid,
            :rule_code,
            :period,
            :bank,
            :filial,
            :account_number,
            :statement_uid,
            :movement_uid,
            :source_filename,
            :severity,
            :title,
            :description,
            :status,
            :suggested_owner,
            CAST(:evidence AS jsonb)
        )
        """
    )

    frame = incidents.copy()

    for col in cols:
        if col not in frame.columns:
            frame[col] = None

    frame = frame[cols].copy()
    frame = frame.where(pd.notna(frame), None)

    records = frame.to_dict(orient="records")

    with engine.begin() as conn:
        for i in range(0, len(records), chunksize):
            batch = records[i:i + chunksize]
            for row in batch:
                if row.get("evidence") is not None:
                    row["evidence"] = json.dumps(row["evidence"], ensure_ascii=False, default=str)
            conn.execute(insert_sql, batch)


def main() -> None:
    cfg = settings_from_env()
    output_dir = prepare_output_dir(cfg["etl_output_dir"])
    engine = create_engine(cfg["database_url"], future=True)

    print(f"[1/6] Cargando fuente de datos ({cfg['data_source_mode']})...")
    try:
        statements, movements = load_source_frames(cfg)
    except SourceConfigError as exc:
        raise SystemExit(f"[ERROR] {exc}")
    statements.to_csv(output_dir / "bank_statements_normalized.csv", index=False)
    movements.to_csv(output_dir / "bank_movements_normalized.csv", index=False)

    print("[2/6] Cargando catálogo de responsables...")
    assignments = load_assignments(cfg["assignments_path"], output_dir, statements)
    if not assignments.empty:
        assignments.to_csv(output_dir / "assignments_loaded.csv", index=False)

    print("[3/6] Detectando incidencias...")
    incidents = build_incidents(statements, movements, assignments)
    incidents.to_csv(output_dir / "incidents_detected.csv", index=False)

    print("[4/6] Ingestando conocimiento interno (PDF + código)...")
    knowledge = load_all_knowledge(cfg["pdf_source_path"], get_source_code_locations(cfg), Path(cfg["etl_output_dir"]) / "_source_code_extracted")

    print("[5/6] Reiniciando tablas y cargando datos...")
    truncate_tables(engine)
    insert_rules(engine)

    if not assignments.empty:
        assignments = assignments.copy()
        assignments["active"] = True
        assignments.to_sql("assignments", engine, if_exists="append", index=False, method="multi", chunksize=1000)

    statements.to_sql("bank_statements", engine, if_exists="append", index=False, method="multi", chunksize=1000)
    insert_bank_movements(engine, movements, chunksize=500)
    insert_incidents(engine, incidents, chunksize=500)

    try:
        insert_knowledge(engine, knowledge)
    except Exception as e:
        print(f"[WARN] No se pudo insertar knowledge_snippets: {e}")

    print("[6/6] Resumen final")
    print(f"    bank_statements: {len(statements):,}")
    print(f"    bank_movements: {len(movements):,}")
    print(f"    incidents: {len(incidents):,}")
    print(f"    knowledge_snippets: {len(knowledge):,}")
    print(f"    output_dir: {output_dir}")


if __name__ == "__main__":
    main()