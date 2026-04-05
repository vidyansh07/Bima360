"""
PostgreSQL → BigQuery incremental sync Lambda.
Runs on a schedule; syncs rows modified in the last 24 hours from key tables.
"""
import json
import logging
import os
from datetime import datetime, timedelta, timezone

import psycopg2
from google.cloud import bigquery
from google.oauth2 import service_account

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# ── Configuration (injected via Lambda env vars) ─────────────────────────────
PG_HOST     = os.environ["PG_HOST"]
PG_PORT     = int(os.environ.get("PG_PORT", "5432"))
PG_DB       = os.environ["PG_DB"]
PG_USER     = os.environ["PG_USER"]
PG_PASSWORD = os.environ["PG_PASSWORD"]

GCP_PROJECT      = os.environ["GCP_PROJECT"]
BQ_DATASET       = os.environ.get("BQ_DATASET", "bima360_analytics")
GCP_CREDENTIALS  = json.loads(os.environ["GCP_SA_JSON"])

# Tables to sync with their incremental column
SYNC_CONFIG = {
    "users":    {"columns": ["id", "phone", "district", "state", "kyc_status", "created_at", "updated_at"], "ts_col": "updated_at"},
    "agents":   {"columns": ["id", "name", "phone", "district", "state", "created_at", "updated_at"],       "ts_col": "updated_at"},
    "policies": {"columns": ["id", "user_id", "agent_id", "product_id", "status", "premium_paid", "coverage_amount", "start_date", "end_date", "fabric_tx_id", "created_at", "updated_at"], "ts_col": "updated_at"},
    "claims":   {"columns": ["id", "policy_id", "status", "claimed_amount", "ai_confidence", "fabric_tx_id", "created_at", "updated_at"], "ts_col": "updated_at"},
    "payments": {"columns": ["id", "policy_id", "amount", "method", "status", "razorpay_payment_id", "created_at"], "ts_col": "created_at"},
}


def get_bq_client() -> bigquery.Client:
    credentials = service_account.Credentials.from_service_account_info(
        GCP_CREDENTIALS,
        scopes=["https://www.googleapis.com/auth/bigquery"],
    )
    return bigquery.Client(project=GCP_PROJECT, credentials=credentials)


def get_pg_conn():
    return psycopg2.connect(
        host=PG_HOST, port=PG_PORT, dbname=PG_DB,
        user=PG_USER, password=PG_PASSWORD,
        connect_timeout=10,
    )


def sync_table(
    pg_conn,
    bq_client: bigquery.Client,
    table: str,
    columns: list[str],
    ts_col: str,
    since: datetime,
) -> int:
    col_list = ", ".join(columns)
    with pg_conn.cursor() as cur:
        cur.execute(
            f"SELECT {col_list} FROM {table} WHERE {ts_col} >= %s ORDER BY {ts_col}",
            (since,),
        )
        rows = cur.fetchall()

    if not rows:
        logger.info("Table %s: no rows since %s", table, since.isoformat())
        return 0

    bq_table_id = f"{GCP_PROJECT}.{BQ_DATASET}.{table}"
    records = [dict(zip(columns, row)) for row in rows]

    # Stringify datetimes for BQ JSON ingestion
    for rec in records:
        for k, v in rec.items():
            if isinstance(v, datetime):
                rec[k] = v.isoformat()

    errors = bq_client.insert_rows_json(bq_table_id, records)
    if errors:
        logger.error("BQ insert errors for %s: %s", table, errors)
        raise RuntimeError(f"BigQuery insert failed for {table}: {errors}")

    logger.info("Table %s: synced %d rows", table, len(rows))
    return len(rows)


def handler(event, context):
    """Lambda entrypoint."""
    lookback_hours = int(event.get("lookback_hours", 24))
    since = datetime.now(tz=timezone.utc) - timedelta(hours=lookback_hours)

    pg_conn = get_pg_conn()
    bq_client = get_bq_client()
    total = 0

    try:
        for table, cfg in SYNC_CONFIG.items():
            total += sync_table(
                pg_conn, bq_client,
                table, cfg["columns"], cfg["ts_col"], since,
            )
    finally:
        pg_conn.close()

    logger.info("Sync complete. Total rows: %d", total)
    return {"statusCode": 200, "rows_synced": total}
