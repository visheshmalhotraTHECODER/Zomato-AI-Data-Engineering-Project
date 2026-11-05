
FROM apache/airflow:3.0.3

USER airflow

RUN pip install --no-cache-dir \
    apache-airflow-providers-snowflake \
    apache-airflow-providers-fab \
    openai \
    python-dotenv

USER airflow

RUN python -m venv /opt/airflow/dbt_venv && \
    /opt/airflow/dbt_venv/bin/pip install --no-cache-dir "dbt-snowflake==1.8.*"
