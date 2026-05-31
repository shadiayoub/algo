FROM python:3.9-slim

WORKDIR /app

# Copy requirements first (for better caching)
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of your application
COPY . .

# Run the bot
CMD ["python", "-u", "alertPivotRsi.py"]
