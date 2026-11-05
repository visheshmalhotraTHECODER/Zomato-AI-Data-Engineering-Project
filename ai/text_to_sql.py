
import os
import json

import pandas as pd
import streamlit as st
import snowflake.connector
import sqlglot
from sqlglot import exp
from openai import OpenAI
from dotenv import load_dotenv


load_dotenv()

MODEL = "gpt-4o-mini"
MAX_ROWS = 100

EXAMPLE_QUESTIONS = [
    "Top 10 cities by GMV",
    "Which cuisine has the most orders?",
    "Average delivery time by city, worst first",
    "Cancel rate by payment method",
]

ALLOWED_TABLES = {
    "FCT_ORDERS",
    "DIM_RESTAURANT",
    "DIM_CUSTOMER",
    "MART_DAILY_CITY_REVENUNE",
    "MART_RESTAURANT_PERFORMANCE",
    "MART_DELIVERY_SLA",
}

SCHEMA = """
Available Snowflake tables:

FCT_ORDERS(
    order_id, order_date, customer_id, restaurant_id, city, cuisine,
    payment_method, order_status, is_delivered, sales_amount, discount,
    delivery_fee, gst, customer_rating, delivery_time_min
)

DIM_RESTAURANT(
    restaurant_id, restaurant_name, city, cuisine, rating, cost_for_two
)

DIM_CUSTOMER(
    customer_id, customer_name, age, age_segment, gender, city
)

MART_DAILY_CITY_REVENUNE(
    order_date, city, orders, cancel_rate, gmv, aov
)

MART_RESTAURANT_PERFORMANCE(
    restaurant_id, restaurant_name, city, cuisine,
    orders, revenue, avg_customer_rating, cancel_rate
)

MART_DELIVERY_SLA(
    city, order_hour, delivered_orders, p50_delivery_min, late_rate
)

Use MART tables whenever they answer the question.
Use bare table names without database/schema prefixes.
"""

SYSTEM_PROMPT = f"""
You are a Snowflake SQL expert.

Generate exactly ONE read-only SELECT query to answer the user's question.

Rules:
- SELECT queries only.
- Never generate INSERT, UPDATE, DELETE, DROP, CREATE or other modifications.
- Use only the tables and columns listed below.
- Use bare table names without database/schema prefixes.
- Add LIMIT 100 or less unless the query returns a single aggregate result.
- Do not generate multiple SQL statements.
- Return valid JSON only in this format:
  {{"sql": "SELECT ..."}}

{SCHEMA}
"""


# Validate configuration
required_vars = [
    "OPENAI_API_KEY",
    "SNOWFLAKE_ACCOUNT",
    "SNOWFLAKE_USER",
    "SNOWFLAKE_PASSWORD",
    "SNOWFLAKE_WAREHOUSE",
    "SNOWFLAKE_DATABASE",
]

missing_vars = [
    name for name in required_vars if not os.getenv(name)
]

st.set_page_config(page_title="Zomato SQL Assistant", page_icon="🍽️")
st.title("Chat with your Zomato Data")
st.caption(f"Ask questions in English. {MODEL} generates SQL.")

if missing_vars:
    st.error("Missing environment variables: " + ", ".join(missing_vars))
    st.stop()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


@st.cache_resource
def get_connection():
    """Create a Snowflake connection."""

    return snowflake.connector.connect(
        account=os.getenv("SNOWFLAKE_ACCOUNT"),
        user=os.getenv("SNOWFLAKE_USER"),
        password=os.getenv("SNOWFLAKE_PASSWORD"),
        warehouse=os.getenv("SNOWFLAKE_WAREHOUSE"),
        database=os.getenv("SNOWFLAKE_DATABASE"),
        schema="MARTS",
        role=os.getenv("SNOWFLAKE_READONLY_ROLE", "DBT_ROLE"),
    )


def generate_sql(question):
    """Generate SQL from a natural-language question."""

    response = client.chat.completions.create(
        model=MODEL,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ],
    )

    answer = response.choices[0].message.content

    if not answer:
        raise ValueError("The AI returned an empty response.")

    result = json.loads(answer)

    sql = result.get("sql")

    if not isinstance(sql, str) or not sql.strip():
        raise ValueError("The AI did not return a valid SQL query.")

    return sql.strip()


def is_safe(sql):
    """
    Parse and validate a single read-only SELECT statement.

    This is an application-level guard, not a replacement
    for a read-only Snowflake database role.
    """

    if not isinstance(sql, str) or not sql.strip():
        return False

    try:
        statements = sqlglot.parse(sql, read="snowflake")

        if len(statements) != 1 or statements[0] is None:
            return False

        parsed = statements[0]

        # Only SELECT statements are allowed.
        if not isinstance(parsed, exp.Select):
            return False

        # Reject modifying or administrative operations.
        blocked_nodes = {
            "INSERT",
            "UPDATE",
            "DELETE",
            "DROP",
            "CREATE",
            "ALTER",
            "TRUNCATE",
            "MERGE",
            "COMMAND",
            "COPY",
            "GRANT",
            "REVOKE",
        }

        for node in parsed.walk():
            if node.key.upper() in blocked_nodes:
                return False

        # Allow listed source tables and CTE names only.
        cte_names = {
            cte.alias_or_name.upper()
            for cte in parsed.find_all(exp.CTE)
        }

        for table in parsed.find_all(exp.Table):
            table_name = table.name.upper()

            if table_name not in ALLOWED_TABLES and table_name not in cte_names:
                return False

            # No database or schema-qualified table references.
            if table.db or table.catalog:
                return False

        return True

    except Exception:
        return False


def run_query(sql):
    """Execute validated SQL and always close the cursor."""

    conn = get_connection()
    cursor = None

    try:
        cursor = conn.cursor()
        cursor.execute(sql)
        return cursor.fetch_pandas_all()

    finally:
        if cursor is not None:
            cursor.close()


# Sidebar examples
with st.sidebar:
    st.header("Example Questions")

    for question in EXAMPLE_QUESTIONS:
        st.markdown(f"- {question}")


# Main application
question = st.text_input(
    "Enter your question:",
    placeholder="e.g. Top 10 restaurants by revenue in Bangalore",
)

if question and question.strip():

    try:
        with st.spinner("Generating and validating SQL..."):
            sql = generate_sql(question.strip())

        st.subheader("Generated SQL")
        st.code(sql, language="sql")

        if not is_safe(sql):
            st.error(
                "Query rejected. Only one SELECT query using approved "
                "tables is allowed."
            )

        else:
            with st.spinner("Executing query in Snowflake..."):
                df = run_query(sql)

            st.success(f"{len(df)} rows returned.")
            st.dataframe(df, hide_index=True)

            if (
                len(df.columns) == 2
                and pd.api.types.is_numeric_dtype(df.iloc[:, 1])
            ):
                st.subheader("Result Visualization")
                st.bar_chart(
                    df,
                    x=df.columns[0],
                    y=df.columns[1],
                )

    except Exception as error:
        st.error(f"Query execution failed: {error}")
