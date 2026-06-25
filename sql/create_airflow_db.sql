-- Tạo database riêng cho Airflow metadata
CREATE DATABASE airflow_db;
GRANT ALL PRIVILEGES ON DATABASE airflow_db TO analyst;
