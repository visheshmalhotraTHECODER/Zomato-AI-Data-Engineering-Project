
import os
import json
import math

import snowflake.connector
from openai import OpenAI
from dotenv import load_dotenv


# Load environment variables
load_dotenv()

# Configuration
MODEL = "gpt-4o-mini"
SAMPLE_N = int(os.getenv("SAMPLE_N", "5"))

TOPICS = [
    "food quality",
    "delivery",
    "pricing",
    "service",
    "packaging",
    "other",
]

if SAMPLE_N <= 0:
    raise ValueError("SAMPLE_N must be greater than zero")

# Initialize OpenAI client
api_key = os.getenv("OPENAI_API_KEY")

if not api_key:
    raise ValueError("OPENAI_API_KEY environment variable is missing")

client = OpenAI(api_key=api_key)


SYSTEM_PROMPT = """
You classify customer reviews for a food delivery app.

For every review, return a JSON object with exactly these fields:

1. sentiment_label: positive, negative, or neutral
2. sentiment_score: a number between -1 and 1
3. topic: one of food quality, delivery, pricing, service, packaging, other
4. key_issue: a short phrase of 6 words or fewer, or null

Rules:
- Return valid JSON only.
- Do not include markdown or explanations.
- Do not invent information that is not present in the review.
- Use neutral sentiment when the review does not express a clear opinion.
"""


def get_connection():
    """Create a Snowflake connection using environment variables."""

    required_vars = [
        "SNOWFLAKE_ACCOUNT",
        "SNOWFLAKE_USER",
        "SNOWFLAKE_PASSWORD",
        "SNOWFLAKE_WAREHOUSE",
        "SNOWFLAKE_DATABASE",
        "SNOWFLAKE_SCHEMA",
    ]

    missing_vars = [
        variable
        for variable in required_vars
        if not os.getenv(variable)
    ]

    if missing_vars:
        raise ValueError(
            f"Missing Snowflake environment variables: {', '.join(missing_vars)}"
        )

    return snowflake.connector.connect(
        user=os.getenv("SNOWFLAKE_USER"),
        password=os.getenv("SNOWFLAKE_PASSWORD"),
        account=os.getenv("SNOWFLAKE_ACCOUNT"),
        warehouse=os.getenv("SNOWFLAKE_WAREHOUSE"),
        database=os.getenv("SNOWFLAKE_DATABASE"),
        schema=os.getenv("SNOWFLAKE_SCHEMA"),
    )


def create_output_table(cursor):
    """Create the AI enrichment schema and output table if required."""

    cursor.execute("CREATE SCHEMA IF NOT EXISTS ZOMATO.AI")

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS ZOMATO.AI.REVIEW_ENRICHED (
            REVIEW_ID VARCHAR,
            SENTIMENT_LABEL VARCHAR,
            SENTIMENT_SCORE FLOAT,
            TOPIC VARCHAR,
            KEY_ISSUE VARCHAR,
            MODEL VARCHAR,
            CREATED_AT TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
        )
        """
    )


def get_reviews_to_enrich(cursor):
    """Fetch a limited number of reviews that have not been enriched."""

    cursor.execute(
        """
        SELECT r.REVIEW_ID, r.COMMENT
        FROM ZOMATO.RAW.REVIEWS AS r
        WHERE r.REVIEW_ID IS NOT NULL
          AND r.COMMENT IS NOT NULL
          AND NOT EXISTS (
              SELECT 1
              FROM ZOMATO.AI.REVIEW_ENRICHED AS e
              WHERE e.REVIEW_ID = r.REVIEW_ID
          )
        LIMIT %s
        """,
        (SAMPLE_N,),
    )

    return cursor.fetchall()


def classify_review(comment):
    """Classify one review using OpenAI and validate the response."""

    if not isinstance(comment, str) or not comment.strip():
        raise ValueError("Review comment must be a non-empty string")

    response = client.chat.completions.create(
        model=MODEL,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": comment,
            },
        ],
    )

    answer = response.choices[0].message.content

    if not answer:
        raise ValueError("OpenAI returned an empty response")

    labels = json.loads(answer)

    required_fields = {
        "sentiment_label",
        "sentiment_score",
        "topic",
        "key_issue",
    }

    if not isinstance(labels, dict):
        raise ValueError("OpenAI response must be a JSON object")

    if not required_fields.issubset(labels.keys()):
        raise ValueError("OpenAI response is missing required fields")

    sentiment = labels["sentiment_label"]
    score = labels["sentiment_score"]
    topic = labels["topic"]
    key_issue = labels["key_issue"]

    if sentiment not in ["positive", "negative", "neutral"]:
        raise ValueError("Invalid sentiment label")

    if (
        not isinstance(score, (int, float))
        or isinstance(score, bool)
        or not math.isfinite(score)
        or not -1 <= score <= 1
    ):
        raise ValueError("Invalid sentiment score")

    if topic not in TOPICS:
        raise ValueError("Invalid topic")

    if key_issue is not None:
        if (
            not isinstance(key_issue, str)
            or len(key_issue.split()) > 6
        ):
            raise ValueError("Invalid key issue")

    return labels


def save_results(cursor, results):
    """Insert successfully enriched reviews into Snowflake."""

    cursor.executemany(
        """
        INSERT INTO ZOMATO.AI.REVIEW_ENRICHED (
            REVIEW_ID,
            SENTIMENT_LABEL,
            SENTIMENT_SCORE,
            TOPIC,
            KEY_ISSUE,
            MODEL
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        results,
    )


def main():
    """Run the review enrichment pipeline."""

    conn = None
    cursor = None

    try:
        print("Connecting to Snowflake...")

        conn = get_connection()
        cursor = conn.cursor()

        print("Checking AI output table...")
        create_output_table(cursor)

        print("Fetching reviews...")
        reviews = get_reviews_to_enrich(cursor)

        if not reviews:
            print("No new reviews to enrich.")
            conn.commit()
            return

        print(f"Found {len(reviews)} reviews to enrich.")

        results = []

        for review_id, comment in reviews:
            try:
                labels = classify_review(comment)

                results.append(
                    (
                        review_id,
                        labels["sentiment_label"],
                        labels["sentiment_score"],
                        labels["topic"],
                        labels["key_issue"],
                        MODEL,
                    )
                )

                print(f"Successfully enriched review: {review_id}")

            except Exception as error:
                print(
                    f"Failed to enrich review {review_id}: {error}"
                )

        if results:
            print(f"Saving {len(results)} enriched reviews...")

            save_results(cursor, results)
            conn.commit()

            print(
                f"Successfully saved {len(results)} enriched reviews."
            )

        else:
            print("No reviews were successfully enriched.")
            conn.commit()

    except Exception:
        if conn is not None:
            conn.rollback()

        raise

    finally:
        if cursor is not None:
            cursor.close()

        if conn is not None:
            conn.close()

        print("Snowflake connection closed.")


if __name__ == "__main__":
    main()
