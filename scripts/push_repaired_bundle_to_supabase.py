from __future__ import annotations

import argparse
import csv
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


TABLE_CONFIG = {
    "song_versions": {
        "key": "id",
        "columns": [
            "id",
            "song_id",
            "display_key",
            "detected_key_raw",
            "detected_key_relative_major",
            "normalized_chords_full",
        ],
    },
    "section_occurrences": {
        "key": "id",
        "columns": [
            "id",
            "song_version_id",
            "name_raw",
            "normalized_chords",
            "nashville",
            "nashville_relative_major",
        ],
    },
}


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def build_changed_rows(
    original_path: Path,
    repaired_path: Path,
    key: str,
    columns: list[str],
) -> list[dict[str, str]]:
    original_rows = {row[key]: row for row in read_csv_rows(original_path)}
    repaired_rows = {row[key]: row for row in read_csv_rows(repaired_path)}

    changed: list[dict[str, str]] = []
    for row_id, repaired_row in repaired_rows.items():
        original_row = original_rows.get(row_id)
        if original_row is None:
            continue
        if original_row == repaired_row:
            continue

        payload = {column: repaired_row.get(column, "") for column in columns}
        changed.append(payload)

    changed.sort(key=lambda row: int(row[key]))
    return changed


def chunk_rows(rows: list[dict[str, str]], batch_size: int) -> list[list[dict[str, str]]]:
    return [rows[index : index + batch_size] for index in range(0, len(rows), batch_size)]


def postgrest_upsert(
    base_url: str,
    service_role_key: str,
    table_name: str,
    rows: list[dict[str, str]],
    retries: int = 3,
) -> None:
    if not rows:
        return

    url = (
        f"{base_url.rstrip('/')}/rest/v1/{table_name}?"
        + urllib.parse.urlencode({"on_conflict": "id"})
    )
    payload = json.dumps(rows).encode("utf-8")
    headers = {
        "apikey": service_role_key,
        "Authorization": f"Bearer {service_role_key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }

    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        request = urllib.request.Request(url, data=payload, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                if response.status < 200 or response.status >= 300:
                    raise RuntimeError(f"{table_name} upsert failed with HTTP {response.status}")
                return
        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8", errors="replace")
            last_error = RuntimeError(f"HTTP {error.code}: {body}")
            if attempt == retries:
                break
            time.sleep(attempt * 2)
        except (urllib.error.URLError, RuntimeError) as error:
            last_error = error
            if attempt == retries:
                break
            time.sleep(attempt * 2)

    raise RuntimeError(f"Failed to upsert {table_name} batch after {retries} attempts: {last_error}")


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Push repaired Supabase bundle deltas to the live Supabase project.")
    parser.add_argument(
        "--original-bundle",
        default=str(project_root / "data" / "processed" / "supabase_import_bundle"),
        help="Path to the original Supabase import bundle.",
    )
    parser.add_argument(
        "--repaired-bundle",
        default=str(project_root / "data" / "processed" / "supabase_import_bundle_repaired"),
        help="Path to the repaired Supabase import bundle.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=250,
        help="Rows per upsert request.",
    )
    parser.add_argument(
        "--supabase-url",
        default=os.getenv("SUPABASE_URL", ""),
        help="Supabase project URL. Defaults to SUPABASE_URL.",
    )
    parser.add_argument(
        "--service-role-key",
        default=os.getenv("SUPABASE_SERVICE_ROLE_KEY", ""),
        help="Supabase service role key. Defaults to SUPABASE_SERVICE_ROLE_KEY.",
    )
    args = parser.parse_args()

    if not args.supabase_url:
        raise SystemExit("Missing Supabase URL. Set --supabase-url or SUPABASE_URL.")
    if not args.service_role_key:
        raise SystemExit("Missing Supabase service role key. Set --service-role-key or SUPABASE_SERVICE_ROLE_KEY.")

    original_bundle = Path(args.original_bundle)
    repaired_bundle = Path(args.repaired_bundle)

    for table_name, config in TABLE_CONFIG.items():
        rows = build_changed_rows(
            original_path=original_bundle / f"{table_name}.csv",
            repaired_path=repaired_bundle / f"{table_name}.csv",
            key=config["key"],
            columns=config["columns"],
        )
        batches = chunk_rows(rows, args.batch_size)
        print(f"{table_name}: {len(rows)} changed rows across {len(batches)} batches")

        for index, batch in enumerate(batches, start=1):
            postgrest_upsert(
                base_url=args.supabase_url,
                service_role_key=args.service_role_key,
                table_name=table_name,
                rows=batch,
            )
            print(f"  pushed batch {index}/{len(batches)} ({len(batch)} rows)")


if __name__ == "__main__":
    main()
