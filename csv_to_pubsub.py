import argparse
import csv
import json
import logging

import apache_beam as beam
from apache_beam.io.gcp.pubsub import PubsubMessage
from apache_beam.options.pipeline_options import PipelineOptions
from apache_beam.options.pipeline_options import SetupOptions
from google.cloud import storage

def get_headers_from_gcs(gcs_uri):
    """Fetches the first line of the GCS file to extract dynamic headers."""
    # Split the gs:// URI to get bucket and blob names
    # Example: gs://my-bucket/data/file.csv
    parts = gcs_uri.replace("gs://", "").split("/")
    bucket_name = parts[0]
    blob_name = "/".join(parts[1:])

    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    
    # Download just the first 1024 bytes to ensure we get the first line 
    # without downloading a massive file into memory
    first_bytes = blob.download_as_bytes(start=0, end=1024)
    first_line = first_bytes.decode('utf-8').split('\n')[0]
    
    # Use csv module to correctly parse commas inside quotes, etc.
    reader = csv.reader([first_line])
    headers = next(reader)
    return headers

def parse_static_fields(raw):
    """Parses and validates the --static_fields JSON, failing at launch rather than per-row.

    Anything wrong here would otherwise surface as millions of malformed messages, so this is
    deliberately strict: it must be a JSON object of scalar values.
    """
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"--static_fields is not valid JSON: {exc}") from exc

    if not isinstance(parsed, dict):
        raise ValueError("--static_fields must be a JSON object, e.g. {\"campaign_id\": \"abc\"}")

    for key, value in parsed.items():
        if isinstance(value, (dict, list)):
            raise ValueError(
                f"--static_fields values must be scalars; '{key}' is {type(value).__name__}"
            )

    return parsed


class CsvToJsonDoFn(beam.DoFn):
    """A DoFn that converts a CSV line to a JSON string using provided headers."""
    def __init__(self, headers, static_fields=None):
        self.headers = headers
        self.static_fields = static_fields or {}

    def process(self, element):
        # element is a raw string (a single line from the CSV)
        reader = csv.reader([element])
        # csv.reader yields [] for a blank line rather than raising, so a trailing newline in the
        # file would otherwise publish a message built from an empty row — one carrying valid
        # static fields but no recipient. Skip anything with no usable values.
        row = next(reader, None)
        if not row or not any(field.strip() for field in row):
            return

        try:
            # Create a dictionary mapping headers to the row values
            row_dict = dict(zip(self.headers, row))

            # Static fields are applied last so they win over a same-named CSV column. They carry
            # run-scoped truth supplied by the caller (e.g. campaign_id), which a per-row value
            # from a user-supplied file must not be able to override.
            row_dict.update(self.static_fields)

            json_str = json.dumps(row_dict)
            yield PubsubMessage(
                data=json_str.encode('utf-8'),
                attributes={'send_pn': 'true'}
            )
        except (ValueError, TypeError):
            logging.warning(f"Skipping unparseable CSV row: {element[:120]!r}")

def run(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--input',
        dest='input',
        required=True,
        help='Input GCS file path (e.g., gs://my-bucket/data.csv)')
    parser.add_argument(
        '--topic',
        dest='topic',
        required=True,
        help='Output Pub/Sub topic (e.g., projects/my-project/topics/my-topic)')
    parser.add_argument(
        '--static_fields',
        dest='static_fields',
        default='{}',
        help='JSON object merged into every published message, for values that belong to the '
             'run rather than the row (e.g. {"campaign_id": "...", "occurrence_id": "..."}). '
             'Per-recipient data belongs in CSV columns instead.')
        
    # Parse our custom args, and pass the rest to Beam's standard PipelineOptions
    known_args, pipeline_args = parser.parse_known_args(argv)

    # 1. Validate static fields before doing anything expensive, so a malformed value fails the
    #    launch instead of producing millions of malformed messages.
    static_fields = parse_static_fields(known_args.static_fields)
    if static_fields:
        logging.info(f"Static fields applied to every message: {sorted(static_fields)}")

    # 2. Fetch headers dynamically before starting the Beam pipeline
    logging.info(f"Fetching headers from {known_args.input}...")
    headers = get_headers_from_gcs(known_args.input)
    logging.info(f"Found headers: {headers}")

    collisions = sorted(set(static_fields) & set(headers))
    if collisions:
        logging.warning(
            f"CSV columns {collisions} are overridden by --static_fields for every row"
        )

    # 3. Setup Pipeline Options
    pipeline_options = PipelineOptions(pipeline_args)
    # save_main_session prevents issues with global imports in distributed workers
    pipeline_options.view_as(SetupOptions).save_main_session = True

    # 4. Build and run the pipeline
    with beam.Pipeline(options=pipeline_options) as p:
        (
            p 
            # Read the file, safely skipping the first line (headers)
            | "Read CSV from GCS" >> beam.io.ReadFromText(known_args.input, skip_header_lines=1)
            # Pass our dynamically fetched headers to the workers
            | "Convert to JSON" >> beam.ParDo(CsvToJsonDoFn(headers, static_fields))
            # Publish to Pub/Sub
            | "Write to Pub/Sub" >> beam.io.WriteToPubSub(topic=known_args.topic, with_attributes=True)
        )

if __name__ == '__main__':
    logging.getLogger().setLevel(logging.INFO)
    run()
