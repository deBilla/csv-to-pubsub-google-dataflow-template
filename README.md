# CSV to Pub/Sub Dataflow Flex Template

Reads a CSV from GCS, dynamically extracts headers, and publishes each row as a JSON payload to a Pub/Sub topic.

## Setup

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

Load the variables before running any commands:

```bash
source .env
```

## One-time: Create Artifact Registry repository

```bash
gcloud artifacts repositories create dataflow-templates-repo \
    --project=$PROJECT_ID \
    --repository-format=docker \
    --location=$REGION \
    --description="Repository for Dataflow Flex Template images"
```

## Build the Flex Template

```bash
gcloud dataflow flex-template build $TEMPLATE_BUCKET/templates/csv-to-pubsub.json \
  --image-gcr-path "$IMAGE_REPO/csv-to-pubsub:latest" \
  --sdk-language "PYTHON" \
  --flex-template-base-image "PYTHON3" \
  --metadata-file "metadata.json" \
  --py-path "." \
  --env "FLEX_TEMPLATE_PYTHON_PY_FILE=csv_to_pubsub.py" \
  --env "FLEX_TEMPLATE_PYTHON_REQUIREMENTS_FILE=requirements.txt" \
  --project "$PROJECT_ID"
```

## Run the Dataflow job

```bash
gcloud dataflow flex-template run "csv-to-pubsub-$(date +%Y%m%d-%H%M%S)" \
  --template-file-gcs-location "$TEMPLATE_BUCKET/templates/csv-to-pubsub.json" \
  --parameters input="$INPUT_CSV" \
  --parameters topic="$PUBSUB_TOPIC" \
  --region "$REGION" \
  --temp-location "$STAGING_BUCKET/temp" \
  --project "$PROJECT_ID"
```

## Run locally (direct runner)

```bash
python3 csv_to_pubsub.py \
    --input "$INPUT_CSV" \
    --topic "$PUBSUB_TOPIC" \
    --project "$PROJECT_ID" \
    --region "$REGION" \
    --temp_location "$STAGING_BUCKET/temp" \
    --runner DataflowRunner
```
# csv-to-pubsub-google-dataflow-template
