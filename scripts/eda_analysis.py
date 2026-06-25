"""
=============================================================
Script: eda_analysis.py
Mô tả: EDA + xuất 4 biểu đồ PNG vào data/charts/
=============================================================
"""

import os
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import seaborn as sns
from sqlalchemy import create_engine

DB_HOST = os.getenv("POSTGRES_HOST", "localhost")
DB_USER = os.getenv("POSTGRES_USER", "analyst")
DB_PASS = os.getenv("POSTGRES_PASSWORD", "analyst123")
DB_NAME = os.getenv("POSTGRES_DB", "crm_db")
engine  = create_engine(f"postgresql+psycopg2://{DB_USER}:{DB_PASS}@{DB_HOST}:5432/{DB_NAME}")

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR  = os.path.join(_SCRIPT_DIR, "..", "data", "charts")
os.makedirs(OUTPUT_DIR, exist_ok=True)

sns.set_theme(style="whitegrid", palette="muted")
COLORS = ["#2E75B6", "#ED7D31", "#70AD47", "#FFC000", "#7030A0"]


def q(sql): return pd.read_sql(sql, engine)


def plot_monthly_trend():
    df = q("SELECT * FROM vw_monthly_kpi ORDER BY month")
    df["month"] = pd.to_datetime(df["month"])

    fig, ax1 = plt.subplots(figsize=(14, 5))
    ax2 = ax1.twinx()
    ax1.bar(df["month"], df["total_revenue"], width=20, color=COLORS[0], alpha=0.7, label="Revenue ($)")
    ax2.plot(df["month"], df["profit_margin_pct"], color=COLORS[1], linewidth=2.5, marker="o", label="Profit Margin (%)")
    ax1.yaxis.set_major_formatter(mtick.FuncFormatter(lambda x, _: f"${x:,.0f}"))
    ax2.yaxis.set_major_formatter(mtick.FuncFormatter(lambda x, _: f"{x:.1f}%"))
    ax1.set_ylabel("Revenue ($)", color=COLORS[0])
    ax2.set_ylabel("Profit Margin (%)", color=COLORS[1])
    lines = ax1.get_legend_handles_labels()[0] + ax2.get_legend_handles_labels()[0]
    labels = ax1.get_legend_handles_labels()[1] + ax2.get_legend_handles_labels()[1]
    ax1.legend(lines, labels, loc="upper left")
    plt.title("Monthly Revenue & Profit Margin Trend", fontsize=14, fontweight="bold")
    plt.tight_layout()
    path = os.path.join(OUTPUT_DIR, "01_monthly_trend.png")
    plt.savefig(path, dpi=150); plt.close()
    print(f"  ✅ Saved: {path}")


def plot_region_category_heatmap():
    df    = q("SELECT * FROM vw_revenue_by_region_category")
    pivot = df.pivot_table(index="region", columns="category", values="revenue", aggfunc="sum")
    fig, ax = plt.subplots(figsize=(9, 5))
    sns.heatmap(pivot, annot=True, fmt=",.0f", cmap="Blues", linewidths=0.5, ax=ax)
    ax.set_title("Revenue by Region & Category", fontsize=14, fontweight="bold")
    plt.tight_layout()
    path = os.path.join(OUTPUT_DIR, "02_region_category_heatmap.png")
    plt.savefig(path, dpi=150); plt.close()
    print(f"  ✅ Saved: {path}")


def plot_top_customers():
    df  = q("SELECT * FROM vw_top_customers")
    fig, ax = plt.subplots(figsize=(11, 6))
    bars = ax.barh(df["customer_name"], df["total_revenue"], color=COLORS[0], alpha=0.85)
    ax.bar_label(bars, labels=[f"${v:,.0f}" for v in df["total_revenue"]], padding=5, fontsize=9)
    ax.set_xlabel("Total Revenue ($)")
    ax.set_title("Top 10 Customers by Revenue", fontsize=14, fontweight="bold")
    ax.invert_yaxis()
    plt.tight_layout()
    path = os.path.join(OUTPUT_DIR, "03_top_customers.png")
    plt.savefig(path, dpi=150); plt.close()
    print(f"  ✅ Saved: {path}")


def plot_anomaly_detection():
    df = q("""
        SELECT profit, discount,
               CASE WHEN profit < -50 OR discount > 0.4
                    THEN 'Anomaly' ELSE 'Normal' END AS status
        FROM fact_orders
    """)
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    color_map = {"Normal": COLORS[0], "Anomaly": "#E74C3C"}
    for status, grp in df.groupby("status"):
        axes[0].hist(grp["profit"], bins=60, alpha=0.7, label=status, color=color_map[status])
        axes[1].scatter(grp["discount"], grp["profit"], alpha=0.4, s=15, label=status, color=color_map[status])
    axes[0].set_title("Profit Distribution — Normal vs Anomaly", fontweight="bold")
    axes[0].set_xlabel("Profit ($)"); axes[0].legend()
    axes[1].set_title("Profit vs Discount (Anomaly Detection)", fontweight="bold")
    axes[1].set_xlabel("Discount Rate"); axes[1].set_ylabel("Profit ($)"); axes[1].legend()
    plt.tight_layout()
    path = os.path.join(OUTPUT_DIR, "04_anomaly_detection.png")
    plt.savefig(path, dpi=150); plt.close()
    print(f"  ✅ Saved: {path}")


def print_kpi_summary():
    row = q("""
        SELECT COUNT(DISTINCT order_id)    AS orders,
               COUNT(DISTINCT customer_id) AS customers,
               ROUND(SUM(sales)::NUMERIC,2)  AS revenue,
               ROUND(SUM(profit)::NUMERIC,2) AS profit,
               ROUND((SUM(profit)/NULLIF(SUM(sales),0)*100)::NUMERIC,2) AS margin
        FROM fact_orders
    """).iloc[0]
    print("\n📊 KPI SUMMARY")
    print("=" * 40)
    print(f"  Orders    : {row.orders:,}")
    print(f"  Customers : {row.customers:,}")
    print(f"  Revenue   : ${row.revenue:,.2f}")
    print(f"  Profit    : ${row.profit:,.2f}")
    print(f"  Margin    : {row.margin:.2f}%")
    print("=" * 40)


if __name__ == "__main__":
    print("🎨 Tạo EDA charts...")
    print_kpi_summary()
    plot_monthly_trend()
    plot_region_category_heatmap()
    plot_top_customers()
    plot_anomaly_detection()
    print("\n✅ Tất cả charts đã lưu vào data/charts/")
