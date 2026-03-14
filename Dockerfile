FROM gcr.io/dataflow-templates-base/python3-template-launcher-base

ARG WORKDIR=/dataflow/template
RUN mkdir -p ${WORKDIR}
WORKDIR ${WORKDIR}

# Copy the requirements and install them
COPY requirements.txt .
RUN pip install --no-cache-dir -U -r requirements.txt

# Copy your script
COPY csv_to_pubsub.py .

# Set the entrypoint to your script
ENV FLEX_TEMPLATE_PYTHON_PY_FILE="${WORKDIR}/csv_to_pubsub.py"
# Dependencies are pre-installed in the image; no runtime installation needed.