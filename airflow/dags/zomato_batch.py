
"""
Zomato batch data pipeline.

Pipeline:
1. Load raw data from Snowflake stages.
2. Build core dbt models.
3. Enrich customer reviews using OpenAI.
4. Build AI dbt models.
"""

from datetime import datetime, timedelta

from airflow import DAG
from airflow.providers.common.sql.operators.sql import SQLExecuteQueryOperator
from airflow.providers.standard.operators.bash import BashOperator


DBT = "/opt/airflow/dbt_venv/bin/dbt"
DBT_PROJECT = "/opt/airflow/dbt/zomato"

DEFAULT_ARGS = {
    "owner": "zomato-data-engineering",
    "depends_on_past": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}

COPY_RAW_SQL = """
USE WAREHOUSE ZOMATO_WH;

COPY INTO ZOMATO.RAW.restaurants
FROM @ZOMATO.RAW.ZOMATO_RAW_STAGE/restaurants/;

COPY INTO ZOMATO.RAW.users
FROM @ZOMATO.RAW.ZOMATO_RAW_STAGE/users/;

COPY INTO ZOMATO.RAW.food
FROM @ZOMATO.RAW.ZOMATO_RAW_STAGE/food/;

COPY INTO ZOMATO.RAW.menu
FROM @ZOMATO.RAW.ZOMATO_RAW_STAGE/menu/;

COPY INTO ZOMATO.RAW.orders
FROM @ZOMATO.RAW.ZOMATO_RAW_STAGE/orders/;

COPY INTO ZOMATO.RAW.order_items
FROM @ZOMATO.RAW.ZOMATO_RAW_STAGE/order_items/;

COPY INTO ZOMATO.RAW.reviews
FROM @ZOMATO.RAW.ZOMATO_RAW_STAGE/reviews/;
"""


with DAG(
    dag_id="zomato_batch",
    description="Daily Zomato ELT and AI review enrichment pipeline",
    default_args=DEFAULT_ARGS,
    start_date=datetime(2024, 1, 1),
    schedule="@daily",
    catchup=False,
    max_active_runs=1,
    tags=["zomato", "snowflake", "dbt", "ai"],
    doc_md=__doc__,
) as dag:

    # Step 1: Load source data into Snowflake RAW tables
    reload_raw = SQLExecuteQueryOperator(
        task_id="reload_raw",
        conn_id="snowflake_default",
        sql=COPY_RAW_SQL,
        split_statements=True,
        autocommit=True,
    )

    # Step 2: Build core dbt models
    dbt_build_core = BashOperator(
        task_id="dbt_build_core",
        bash_command=(
            f"set -euo pipefail && "
            f"{DBT} build "
            f"--exclude tag:ai "
            f"--project-dir {DBT_PROJECT} "
            f"--profiles-dir {DBT_PROJECT}"
        ),
    )

    # Step 3: Enrich customer reviews using OpenAI
    enrich_reviews = BashOperator(
        task_id="enrich_reviews",
        bash_command=(
            "set -euo pipefail && "
            "python /opt/airflow/ai/enrich_reviews.py"
        ),
    )

    # Step 4: Build AI dbt models
    dbt_build_ai = BashOperator(
        task_id="dbt_build_ai",
        bash_command=(
            f"set -euo pipefail && "
            f"{DBT} build "
            f"--select tag:ai "
            f"--project-dir {DBT_PROJECT} "
            f"--profiles-dir {DBT_PROJECT}"
        ),
    )

    # Pipeline dependencies
    (
        reload_raw
        >> dbt_build_core
        >> enrich_reviews
        >> dbt_build_ai
    )
