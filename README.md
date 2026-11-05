# Zomato AI Data Engineering — End-to-End Project

An end-to-end batch data engineering project that transforms Zomato-style food delivery data into analytics-ready datasets and AI-powered insights.

**Pipeline:**
Zomato Dataset → Amazon S3 → Snowflake → dbt → Apache Airflow → OpenAI

> 🎥 **Video walkthrough:** [Watch the project on YouTube](https://youtu.be/kYwaNMQ3XT8?si=Ge8ilVxkmGQS6iIg)

> 📂 **Dataset and project slides:** [Google Drive folder](https://drive.google.com/drive/folders/1FEnGWMHhHzzTUCZOw1-YnH2v3DMuM-rs?usp=sharing)

![Architecture](docs/architecture.png)

## Project Overview

This project implements a batch data pipeline for processing large-scale food delivery data.

Data is uploaded to Amazon S3 and loaded into Snowflake using a storage integration. dbt transforms raw data into staging and analytics models following the medallion architecture.

Apache Airflow orchestrates the pipeline, while the AI layer adds three capabilities:

- **LLM Review Enrichment:** Extract sentiment, topics, and key issues from customer reviews.
- **RAG Chat:** Ask natural-language questions about customer reviews.
- **Text-to-SQL:** Convert natural-language questions into SQL queries against analytics tables.

Streamlit provides the interface for the AI applications.

## Architecture & Data Layers

| Layer | Technology | Purpose |
|---|---|---|
| Source | CSV files | Food delivery datasets |
| Data Lake | Amazon S3 | Raw data storage |
| Bronze | Snowflake RAW | Load source data using COPY INTO |
| Silver | dbt STAGING | Clean, standardize, and transform data |
| Gold | dbt MARTS | Business-ready dimensions, facts, and analytics |
| AI | OpenAI + Snowflake | Review enrichment, RAG, and text-to-SQL |
| Orchestration | Apache Airflow | Schedule and coordinate pipeline tasks |

The dataset includes 10M orders, approximately 23M order items, and 300K customer reviews, alongside dimension datasets.

## Tech Stack

- **Languages:** Python, SQL
- **Cloud:** Amazon S3
- **Data Warehouse:** Snowflake
- **Transformation:** dbt Core, dbt-snowflake
- **Orchestration:** Apache Airflow 3
- **AI:** OpenAI API, GPT-4o-mini, text-embedding-3-small
- **Applications:** Streamlit
- **Infrastructure:** Docker Compose

## Repository Structure

```text
├── ai/
│   ├── enrich_reviews.py
│   ├── rag_chat.py
│   ├── text_to_sql.py
│   └── example.env
│
├── airflow/
│   ├── dags/
│   │   └── zomato_batch.py
│   ├── Dockerfile
│   ├── docker-compose.yaml
│   └── example.env
│
├── aws/
│   └── iam/
│
├── docs/
│   └── architecture.png
│
├── snowflake/
│   ├── 01_setup.sql
│   ├── 02_storage_integration.sql
│   ├── 03_stage_and_formats.sql
│   ├── 04_raw_tables.sql
│   └── 05_copy_into.sql
│
└── zomato/
    ├── dbt_project.yml
    ├── models/
    │   ├── staging/
    │   └── marts/
    └── macros/
```

Large datasets, generated logs, local credentials, and dbt artifacts are intentionally excluded from version control.

## How the Pipeline Works

### 1. Data Ingestion — Amazon S3

The source CSV files are uploaded to S3 using separate folders for each dataset:

```text
s3://<BUCKET>/raw/restaurants/
s3://<BUCKET>/raw/users/
s3://<BUCKET>/raw/food/
s3://<BUCKET>/raw/menu/
s3://<BUCKET>/raw/orders/
s3://<BUCKET>/raw/order_items/
s3://<BUCKET>/raw/reviews/
```

### 2. Snowflake Data Loading

Snowflake accesses S3 through an IAM role and storage integration instead of storing AWS access keys.

The Snowflake setup scripts define the warehouse, database, schemas, integration, external stage, file formats, and raw tables.

Run the SQL scripts in order:

1. `snowflake/01_setup.sql`
2. `snowflake/02_storage_integration.sql`
3. `snowflake/03_stage_and_formats.sql`
4. `snowflake/04_raw_tables.sql`
5. `snowflake/05_copy_into.sql`

AWS IAM policy and trust configuration files are available under `aws/iam/`.

### 3. Data Transformation — dbt

The dbt project follows a medallion architecture.

- **Staging:** Clean and standardize source data.
- **Dimensions:** Build analytical dimensions such as restaurants, customers, food, and dates.
- **Facts:** Build order and order-item fact tables using incremental models.
- **Marts:** Create business-focused datasets for revenue, restaurant performance, delivery SLAs, and review insights.

Data quality tests include uniqueness, not-null, relationships, accepted values, and reconciliation checks.

### 4. Workflow Orchestration — Airflow

The Airflow DAG coordinates the pipeline through four main tasks:

```text
reload_raw
    ↓
dbt_build_core
    ↓
enrich_reviews
    ↓
dbt_build_ai
```

The workflow loads raw data, runs core dbt transformations, enriches customer reviews using OpenAI, and builds AI-related analytics models.

### 5. AI Applications

**Review Enrichment — `ai/enrich_reviews.py`**

Uses GPT-4o-mini to classify customer reviews and extract structured information such as sentiment, topic, sentiment score, and key issue. Results are stored in Snowflake.

The `SAMPLE_N` environment variable controls the number of reviews processed per execution. Previously enriched reviews are excluded from subsequent selections.

**RAG Chat — `ai/rag_chat.py`**

Uses embeddings to retrieve semantically relevant customer reviews and generate context-grounded responses. Retrieved reviews can be inspected in the Streamlit interface.

**Text-to-SQL — `ai/text_to_sql.py`**

Generates SQL from natural-language questions using the analytics schema as context. SQLGlot-based AST validation restricts generated queries to a single SELECT statement and allowlisted tables.

For defense in depth, configure the Snowflake execution role with read-only permissions. Query validation alone is not a replacement for database permissions.

## Getting Started

### Prerequisites

- Python
- Docker Desktop
- Snowflake account
- AWS account with S3 access
- OpenAI API key
- dbt Core with the Snowflake adapter

### 1. Clone the repository

```bash
git clone https://github.com/visheshmalhotraTHECODER/Zomato-AI-Data-Engineering-Project.git
cd Zomato-AI-Data-Engineering-Project
```

### 2. Configure Snowflake

Run the SQL setup scripts under `snowflake/` in the documented order.

Configure the S3 storage integration and IAM permissions using the files under `aws/iam/`.

### 3. Configure dbt

Create a local `zomato/profiles.yml` file. Do not commit this file or store real credentials in Git.

Example configuration:

```yaml
zomato:
  target: dev
  outputs:
    dev:
      type: snowflake
      account: "{{ env_var('SNOWFLAKE_ACCOUNT') }}"
      user: "{{ env_var('SNOWFLAKE_USER') }}"
      password: "{{ env_var('SNOWFLAKE_PASSWORD') }}"
      role: DBT_ROLE
      database: ZOMATO
      warehouse: "{{ env_var('SNOWFLAKE_WAREHOUSE') }}"
      schema: RAW
      threads: 4
```

Set the required Snowflake environment variables before running dbt.

```bash
cd zomato
dbt debug
dbt build --exclude tag:ai
```

### 4. Configure and start Airflow

From the `airflow/` directory:

```bash
cp example.env .env
```

Fill in the required Snowflake credentials, OpenAI API key, and sample limit in `.env`.

Build and start the services:

```bash
docker compose build
docker compose up -d
```

Open `http://localhost:8080`, access the Airflow interface, and trigger the `zomato_batch` DAG after configuring the required connections and infrastructure.

### 5. Run the AI applications

Install the required Python dependencies for the AI applications in your Python environment, then configure the required environment variables.

```bash
python ai/enrich_reviews.py

streamlit run ai/rag_chat.py

streamlit run ai/text_to_sql.py
```

Run these commands from the repository root. Ensure Snowflake and OpenAI credentials are configured before execution.

## Configuration & Security

- Never commit `.env`, `profiles.yml`, API keys, or database passwords.
- Use `airflow/example.env` as the environment configuration template.
- Keep local credentials separate from source code.
- Use appropriately restricted Snowflake roles for application queries.
- Monitor Snowflake warehouse usage and OpenAI API consumption.

## Validation Status

Python syntax compilation, YAML parsing, and Git whitespace checks have been performed during development.

A complete Docker build, Airflow runtime validation, Snowflake integration test, and end-to-end pipeline execution remain pending.

---

**Built with Python, SQL, Snowflake, dbt, Airflow, AWS, and OpenAI.**