"""
=============================================================
DAG: crm_etl_pipeline
Mô tả: Tự động chạy ETL pipeline mỗi ngày lúc 6:00 sáng
=============================================================
"""

from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator
from airflow.utils.dates import days_ago
import sys
import os

sys.path.insert(0, "/opt/airflow/scripts")

# ── Cấu hình mặc định ────────────────────────────────────────
DEFAULT_ARGS = {
    "owner":            "data_analyst",
    "depends_on_past":  False,
    "email_on_failure": False,
    "email_on_retry":   False,
    "retries":          1,
    "retry_delay":      timedelta(minutes=5),
}


# ── Task functions ────────────────────────────────────────────

def task_extract(**context):
    """Task 1: Extract dữ liệu từ CSV."""
    from etl_pipeline import extract
    df = extract()
    # Lưu thông tin vào XCom để task sau dùng
    context["ti"].xcom_push(key="row_count", value=len(df))
    return f"Extracted {len(df):,} rows"


def task_quality_check(**context):
    """Task 2: Kiểm tra chất lượng dữ liệu."""
    import pandas as pd
    from etl_pipeline import extract
    from data_quality import DataQualityChecker

    df = extract()
    # Chuẩn hoá tên cột
    df.columns = (
        df.columns.str.strip().str.lower()
        .str.replace(" ", "_").str.replace("-", "_")
    )
    df["order_date"] = pd.to_datetime(df["order_date"], dayfirst=True, errors="coerce")
    df["ship_date"]  = pd.to_datetime(df["ship_date"],  dayfirst=True, errors="coerce")
    df["sales"]      = pd.to_numeric(df["sales"],    errors="coerce").fillna(0)
    df["profit"]     = pd.to_numeric(df["profit"],   errors="coerce").fillna(0)
    df["discount"]   = pd.to_numeric(df["discount"], errors="coerce").fillna(0)
    df["quantity"]   = pd.to_numeric(df["quantity"], errors="coerce").fillna(0).astype(int)

    checker = DataQualityChecker(df)
    passed = checker.run_all()

    if not passed:
        # Không dừng pipeline, chỉ log warning
        print(f"⚠️ {checker.failed} data quality check(s) failed — tiếp tục ETL")

    return f"Quality check: {checker.passed} PASS, {checker.failed} FAIL"


def task_transform_load(**context):
    """Task 3: Transform + Load vào PostgreSQL."""
    from etl_pipeline import extract, quality_check, transform, load
    raw_df   = extract()
    clean_df = quality_check(raw_df)
    tables   = transform(clean_df)
    load(tables)
    return "Transform & Load hoàn tất"


def task_generate_charts(**context):
    """Task 4: Tạo EDA charts."""
    import subprocess
    result = subprocess.run(
        ["python", "/opt/airflow/scripts/eda_analysis.py"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        raise Exception(f"EDA script lỗi:\n{result.stderr}")
    print(result.stdout)
    return "Charts đã được tạo trong data/charts/"


# ── Định nghĩa DAG ───────────────────────────────────────────
with DAG(
    dag_id="crm_etl_pipeline",
    description="CRM Sales ETL Pipeline — chạy tự động mỗi ngày 6:00 SA",
    default_args=DEFAULT_ARGS,
    start_date=days_ago(1),
    schedule_interval="0 6 * * *",   # Mỗi ngày lúc 6:00 sáng
    catchup=False,
    tags=["crm", "etl", "analytics"],
) as dag:

    # Task 1: Extract
    t1_extract = PythonOperator(
        task_id="extract_data",
        python_callable=task_extract,
        provide_context=True,
    )

    # Task 2: Data Quality Check
    t2_quality = PythonOperator(
        task_id="data_quality_check",
        python_callable=task_quality_check,
        provide_context=True,
    )

    # Task 3: Transform + Load
    t3_transform_load = PythonOperator(
        task_id="transform_and_load",
        python_callable=task_transform_load,
        provide_context=True,
    )

    # Task 4: Generate Charts
    t4_charts = PythonOperator(
        task_id="generate_charts",
        python_callable=task_generate_charts,
        provide_context=True,
    )

    # Task 5: Log hoàn thành
    t5_done = BashOperator(
        task_id="pipeline_complete",
        bash_command='echo "✅ CRM ETL Pipeline hoàn tất lúc $(date)"',
    )

    # ── Thứ tự chạy ──────────────────────────────────────────
    # extract → quality_check → transform_load → charts → done
    t1_extract >> t2_quality >> t3_transform_load >> t4_charts >> t5_done
