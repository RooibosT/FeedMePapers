FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt pyproject.toml ./
COPY src/ ./src/
COPY main.py ./
RUN pip install --no-cache-dir -r requirements.txt
RUN mkdir -p /app/results
ENTRYPOINT ["python", "main.py"]
