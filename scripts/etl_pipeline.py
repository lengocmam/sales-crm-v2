"""
=============================================================
Script: etl_pipeline.py
Mô tả: ETL pipeline hoàn chỉnh với Data Quality Check
       Extract → Quality Check → Transform → Load
=============================================================
"""

import os
import sys
import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text
import warnings
warnings.filterwarnings("ignore")

# Import module kiểm tra chất lượng
sys.path.append(os.path.dirname(__file__))
from data_quality import DataQualityChecker

# ── Cấu hình ─────────────────────────────────────────────────
DB_HOST = os.getenv("POSTGRES_HOST", "localhost")
DB_USER = os.getenv("POSTGRES_USER", "analyst")
DB_PASS = os.getenv("POSTGRES_PASSWORD", "analyst123")
DB_NAME = os.getenv("POSTGRES_DB", "crm_db")
ENGINE  = create_engine(f"postgresql+psycopg2://{DB_USER}:{DB_PASS}@{DB_HOST}:5432/{DB_NAME}")

# Tìm file data dù chạy từ đâu
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH   = os.path.join(_SCRIPT_DIR, "..", "data", "superstore.csv")


# ── 1. EXTRACT ───────────────────────────────────────────────
def extract() -> pd.DataFrame:
    print("[EXTRACT] Đọc file CSV...")
    if not os.path.exists(DATA_PATH):
        raise FileNotFoundError(
            f"Không tìm thấy file: {DATA_PATH}\n"
            "👉 Tải dataset từ Kaggle và đặt vào thư mục data/"
        )
    df = pd.read_csv(DATA_PATH, encoding="latin-1")
    print(f"[EXTRACT] ✅ Đọc xong — {len(df):,} dòng, {len(df.columns)} cột")
    return df


# ── 2. QUALITY CHECK ─────────────────────────────────────────
def quality_check(df: pd.DataFrame) -> pd.DataFrame:
    """Chuẩn hoá tên cột → chạy checks → trả về df đã chuẩn hoá."""

    # Chuẩn hoá tên cột trước khi check
    df.columns = (
        df.columns.str.strip().str.lower()
        .str.replace(" ", "_").str.replace("-", "_")
    )

    # Ép kiểu cơ bản để checker dùng được
    df["order_date"] = pd.to_datetime(df["order_date"], dayfirst=False, errors="coerce")
    df["ship_date"]  = pd.to_datetime(df["ship_date"],  dayfirst=False, errors="coerce")
    df["sales"]      = pd.to_numeric(df["sales"],    errors="coerce").fillna(0)
    df["profit"]     = pd.to_numeric(df["profit"],   errors="coerce").fillna(0)
    df["discount"]   = pd.to_numeric(df["discount"], errors="coerce").fillna(0)
    df["quantity"]   = pd.to_numeric(df["quantity"], errors="coerce").fillna(0).astype(int)

    checker = DataQualityChecker(df)
    all_passed = checker.run_all()

    if not all_passed:
        print("\n⚠️  Vẫn tiếp tục ETL với dữ liệu đã lọc lỗi...")

    return df


# ── 3. TRANSFORM ─────────────────────────────────────────────
def transform(df: pd.DataFrame) -> dict:
    print("\n[TRANSFORM] Làm sạch và chuẩn bị dữ liệu...")

    # Xoá duplicate
    before = len(df)
    df = df.drop_duplicates(subset=["order_id", "product_id"])
    print(f"[TRANSFORM] Loại bỏ {before - len(df)} duplicate rows")

    # Anomaly detection bằng IQR
    q1, q3 = df["profit"].quantile(0.25), df["profit"].quantile(0.75)
    iqr = q3 - q1
    anomalies = df[df["profit"] < (q1 - 1.5 * iqr)]
    print(f"[TRANSFORM] Phát hiện {len(anomalies)} anomaly records (IQR method)")

    # ── Bảng DIM ─────────────────────────────────────────────
    dim_customers = df[[
        "customer_id", "customer_name", "segment",
        "city", "state", "region", "country"
    ]].drop_duplicates("customer_id").reset_index(drop=True)

    dim_products = df[[
        "product_id", "product_name", "category", "sub_category"
    ]].drop_duplicates("product_id").reset_index(drop=True)

    all_dates = pd.concat([df["order_date"], df["ship_date"]]).dropna().unique()
    date_series = pd.Series(sorted(all_dates))
    dim_date = pd.DataFrame({
        "date_key":    date_series,
        "year":        date_series.dt.year,
        "quarter":     date_series.dt.quarter,
        "month":       date_series.dt.month,
        "month_name":  date_series.dt.strftime("%B"),
        "week":        date_series.dt.isocalendar().week.values,
        "day_of_week": date_series.dt.strftime("%A"),
    })

    # ── Bảng FACT ────────────────────────────────────────────
    fact_orders = df[[
        "order_id", "order_date", "ship_date", "ship_mode",
        "customer_id", "product_id",
        "sales", "quantity", "discount", "profit"
    ]].copy()

    print(f"[TRANSFORM] ✅ Hoàn tất:")
    print(f"  dim_customers : {len(dim_customers):,} rows")
    print(f"  dim_products  : {len(dim_products):,} rows")
    print(f"  dim_date      : {len(dim_date):,} rows")
    print(f"  fact_orders   : {len(fact_orders):,} rows")

    return {
        "dim_customers": dim_customers,
        "dim_products":  dim_products,
        "dim_date":      dim_date,
        "fact_orders":   fact_orders,
    }


# ── 4. LOAD ──────────────────────────────────────────────────
def load(tables: dict) -> None:
    print("\n[LOAD] Nạp dữ liệu vào PostgreSQL...")
    order = ["dim_customers", "dim_products", "dim_date", "fact_orders"]

    with ENGINE.begin() as conn:
        for tbl in reversed(order):
            conn.execute(text(f"TRUNCATE TABLE {tbl} CASCADE"))

    for tbl in order:
        tables[tbl].to_sql(
            tbl, ENGINE,
            if_exists="append", index=False,
            method="multi", chunksize=500
        )
        print(f"  ✅ {tbl}: {len(tables[tbl]):,} rows")

    print("[LOAD] ✅ Hoàn tất!")


# ── Main ─────────────────────────────────────────────────────
def run_pipeline():
    print("=" * 55)
    print("  Sales CRM Analytics — ETL Pipeline v2")
    print("=" * 55)

    raw_df = extract()
    clean_df = quality_check(raw_df)
    tables = transform(clean_df)
    load(tables)

    print("\n" + "=" * 55)
    print("  ✅ Pipeline hoàn tất!")
    print("  → Mở Power BI và kết nối PostgreSQL để visualize")
    print("=" * 55)


if __name__ == "__main__":
    run_pipeline()
