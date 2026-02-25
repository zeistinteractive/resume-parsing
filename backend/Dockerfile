FROM python:3.11-slim

WORKDIR /app

# Install pip dependencies in a cached layer before copying source
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

# Ensure uploads directory exists (overridden by volume mount at runtime)
RUN mkdir -p uploads

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
