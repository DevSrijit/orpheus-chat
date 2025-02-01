# Use an official Python runtime as a parent image
FROM python:3.10-slim

# Prevents Python from writing pyc files to disc (equivalent to -B)
ENV PYTHONDONTWRITEBYTECODE=1
# Prevents Python from buffering stdout and stderr.
ENV PYTHONUNBUFFERED=1

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy the rest of the working directory contents into the container at /app
COPY . .


# EXPOSE 3000

# Define environment variable defaults
ENV SLACK_BOT_TOKEN=
ENV SLACK_APP_TOKEN=
ENV PINECONE_API_KEY=

# Run app.py when the container launches
CMD ["python", "slack_bot.py"]
