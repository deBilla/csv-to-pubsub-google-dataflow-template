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

Step 1 — build the Docker image via Cloud Build (produces a linux/amd64 image):

```bash
gcloud builds submit \
  --tag "$IMAGE_REPO/csv-to-pubsub:latest" \
  --project "$PROJECT_ID"
```

Step 2 — upload the template spec to GCS:

```bash
gcloud dataflow flex-template build "$TEMPLATE_BUCKET/templates/csv-to-pubsub.json" \
  --image "$IMAGE_REPO/csv-to-pubsub:latest" \
  --sdk-language "PYTHON" \
  --metadata-file "metadata.json" \
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

## Launch from Node.js (Dataflow API)

Install the dependency:

```bash
npm install @google-cloud/dataflow
```

```javascript
const { FlexTemplatesServiceClient } = require('@google-cloud/dataflow').v1beta3;

const client = new FlexTemplatesServiceClient();

async function launchDataflowJob({ inputCsv, topic, campaignId }) {
  const [response] = await client.launchFlexTemplate({
    projectId: process.env.PROJECT_ID,
    location: process.env.REGION,
    launchParameter: {
      jobName: `csv-to-pubsub-${campaignId}-${Date.now()}`,
      containerSpecGcsPath: `${process.env.TEMPLATE_BUCKET}/templates/csv-to-pubsub.json`,
      parameters: {
        input: inputCsv,
        topic: topic,
      },
      environment: {
        tempLocation: `${process.env.STAGING_BUCKET}/temp`,
      },
    },
  });

  console.log('Job launched:', response.job.id);
  return response.job;
}
```
