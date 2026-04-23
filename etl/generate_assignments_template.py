import os
from pathlib import Path

from normalize_movements import normalize_csv


def main() -> None:
    csv_path = os.getenv("CSV_SOURCE_PATH", "/data/input/conciliador_movimientos_pdf_enero_febrero.csv")
    output_dir = Path(os.getenv("ETL_OUTPUT_DIR", "/data/output"))
    output_dir.mkdir(parents=True, exist_ok=True)

    statements, _ = normalize_csv(csv_path)
    template = (
        statements[["filial", "bank", "account_number"]]
        .drop_duplicates()
        .sort_values(["filial", "bank", "account_number"])
        .assign(owner_name="", area="", email="")
    )

    destination = output_dir / "assignments_template.csv"
    template.to_csv(destination, index=False)
    print(destination)


if __name__ == "__main__":
    main()
