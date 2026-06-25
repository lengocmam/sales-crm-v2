"""
=============================================================
Module: data_quality.py
Mô tả: Kiểm tra chất lượng dữ liệu trước khi load vào DB
=============================================================
"""

import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text
from datetime import datetime
import os

DB_HOST = os.getenv("POSTGRES_HOST", "localhost")
DB_USER = os.getenv("POSTGRES_USER", "analyst")
DB_PASS = os.getenv("POSTGRES_PASSWORD", "analyst123")
DB_NAME = os.getenv("POSTGRES_DB", "crm_db")
ENGINE  = create_engine(f"postgresql+psycopg2://{DB_USER}:{DB_PASS}@{DB_HOST}:5432/{DB_NAME}")


class DataQualityChecker:
    """Chạy các bước kiểm tra chất lượng dữ liệu và log kết quả."""

    def __init__(self, df: pd.DataFrame):
        self.df      = df
        self.results = []
        self.passed  = 0
        self.failed  = 0

    def _log(self, check_name: str, condition: pd.Series, message: str):
        """Ghi kết quả 1 check vào results."""
        rows_failed = int((~condition).sum())
        status      = "PASS" if rows_failed == 0 else "FAIL"

        self.results.append({
            "check_name":   check_name,
            "status":       status,
            "rows_checked": len(self.df),
            "rows_failed":  rows_failed,
            "message":      message,
        })

        icon = "✅" if status == "PASS" else "❌"
        print(f"  {icon} [{status}] {check_name}: {message} ({rows_failed} lỗi)")

        if status == "PASS":
            self.passed += 1
        else:
            self.failed += 1

    # ── Các check cụ thể ─────────────────────────────────────

    def check_no_null_keys(self):
        """Các cột khoá không được NULL."""
        key_cols = ["order_id", "customer_id", "product_id", "order_date"]
        for col in key_cols:
            if col not in self.df.columns:
                continue
            condition = self.df[col].notna()
            self._log(
                f"null_check_{col}",
                condition,
                f"Cột '{col}' không được chứa NULL"
            )

    def check_sales_positive(self):
        """Sales phải >= 0."""
        condition = self.df["sales"] >= 0
        self._log(
            "sales_non_negative",
            condition,
            "Sales không được âm"
        )

    def check_quantity_positive(self):
        """Quantity phải > 0."""
        condition = self.df["quantity"] > 0
        self._log(
            "quantity_positive",
            condition,
            "Quantity phải lớn hơn 0"
        )

    def check_discount_range(self):
        """Discount phải trong khoảng [0, 1]."""
        condition = self.df["discount"].between(0, 1)
        self._log(
            "discount_range",
            condition,
            "Discount phải trong khoảng 0.0 – 1.0"
        )

    def check_order_date_valid(self):
        """Order date không được trong tương lai."""
        today     = pd.Timestamp(datetime.today().date())
        condition = pd.to_datetime(self.df["order_date"], errors="coerce") <= today
        self._log(
            "order_date_not_future",
            condition,
            "Order date không được là ngày trong tương lai"
        )

    def check_ship_after_order(self):
        """Ship date phải >= order date."""
        order_dt = pd.to_datetime(self.df["order_date"], errors="coerce")
        ship_dt  = pd.to_datetime(self.df["ship_date"],  errors="coerce")
        condition = (ship_dt >= order_dt) | ship_dt.isna()
        self._log(
            "ship_after_order",
            condition,
            "Ship date phải >= Order date"
        )

    def check_no_duplicate_keys(self):
        """Không được có (order_id, product_id) trùng nhau."""
        duplicated = self.df.duplicated(subset=["order_id", "product_id"])
        condition  = ~duplicated
        self._log(
            "no_duplicate_order_product",
            condition,
            "Không được trùng cặp (order_id, product_id)"
        )

    def check_segment_values(self):
        """Segment chỉ được là 3 giá trị hợp lệ."""
        valid     = {"Consumer", "Corporate", "Home Office"}
        condition = self.df["segment"].isin(valid)
        self._log(
            "segment_valid_values",
            condition,
            f"Segment phải là một trong: {valid}"
        )

    def check_extreme_discount(self):
        """Cảnh báo nếu discount > 80% (có thể là lỗi nhập liệu)."""
        extreme   = self.df["discount"] > 0.8
        condition = ~extreme
        self._log(
            "discount_extreme_warning",
            condition,
            "Discount > 80% — kiểm tra lại dữ liệu"
        )

    # ── Chạy tất cả checks ───────────────────────────────────

    def run_all(self) -> bool:
        """Chạy toàn bộ checks. Trả về True nếu tất cả PASS."""
        print("\n📋 Bắt đầu Data Quality Checks...")
        print("-" * 55)

        self.check_no_null_keys()
        self.check_sales_positive()
        self.check_quantity_positive()
        self.check_discount_range()
        self.check_order_date_valid()
        self.check_ship_after_order()
        self.check_no_duplicate_keys()
        self.check_segment_values()
        self.check_extreme_discount()

        print("-" * 55)
        print(f"  Kết quả: {self.passed} PASS | {self.failed} FAIL")

        self._save_to_db()

        if self.failed > 0:
            print(f"\n⚠️  {self.failed} check(s) FAIL — xem bảng data_quality_log trong DB")
            return False

        print("\n✅ Tất cả checks PASS — dữ liệu sạch, sẵn sàng load!")
        return True

    def _save_to_db(self):
        """Lưu kết quả checks vào bảng data_quality_log."""
        try:
            with ENGINE.begin() as conn:
                for r in self.results:
                    conn.execute(text("""
                        INSERT INTO data_quality_log
                            (check_name, status, rows_checked, rows_failed, message)
                        VALUES
                            (:check_name, :status, :rows_checked, :rows_failed, :message)
                    """), r)
            print("  💾 Đã lưu kết quả vào bảng data_quality_log")
        except Exception as e:
            print(f"  ⚠️  Không thể lưu log: {e}")
