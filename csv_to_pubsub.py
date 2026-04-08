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

class CsvToJsonDoFn(beam.DoFn):
    """A DoFn that converts a CSV line to a JSON string using provided headers."""
    def __init__(self, headers):
        self.headers = headers

    def process(self, element):
        # element is a raw string (a single line from the CSV)
        reader = csv.reader([element])
        try:
            row = next(reader)
            # Create a dictionary mapping headers to the row values
            row_dict = dict(zip(self.headers, row))
            
            json_str = json.dumps(row_dict)
            yield PubsubMessage(
                data=json_str.encode('utf-8'),
                attributes={'send_pn': 'true'}
            )
        except StopIteration:
            # Handle empty lines gracefully
            pass

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
        
    # Parse our custom args, and pass the rest to Beam's standard PipelineOptions
    known_args, pipeline_args = parser.parse_known_args(argv)

    # 1. Fetch headers dynamically before starting the Beam pipeline
    logging.info(f"Fetching headers from {known_args.input}...")
    headers = get_headers_from_gcs(known_args.input)
    logging.info(f"Found headers: {headers}")

    # 2. Setup Pipeline Options
    pipeline_options = PipelineOptions(pipeline_args)
    # save_main_session prevents issues with global imports in distributed workers
    pipeline_options.view_as(SetupOptions).save_main_session = True

    # 3. Build and run the pipeline
    with beam.Pipeline(options=pipeline_options) as p:
        (
            p 
            # Read the file, safely skipping the first line (headers)
            | "Read CSV from GCS" >> beam.io.ReadFromText(known_args.input, skip_header_lines=1)
            # Pass our dynamically fetched headers to the workers
            | "Convert to JSON" >> beam.ParDo(CsvToJsonDoFn(headers))
            # Publish to Pub/Sub
            | "Write to Pub/Sub" >> beam.io.WriteToPubSub(topic=known_args.topic, with_attributes=True)
        )

if __name__ == '__main__':
    logging.getLogger().setLevel(logging.INFO)
    run()
