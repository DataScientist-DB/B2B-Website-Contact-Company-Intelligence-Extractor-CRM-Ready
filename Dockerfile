# Use Apify’s official Python base image
FROM apify/actor-python:3.11

# Copy only what we need
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy the source code
COPY src ./src
COPY INPUT_SCHEMA.json ./
COPY OUTPUT_SCHEMA.json ./

# Apify runs: python -m src
CMD ["python", "-m", "src"]
