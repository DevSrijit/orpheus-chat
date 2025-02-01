import os
from openai import AzureOpenAI
from pymongo import MongoClient
import numpy as np
from tqdm import tqdm
import tiktoken  # Make sure you have this installed: pip install tiktoken

# Azure OpenAI Config
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
API_VERSION = "2024-06-01"

# Initialize Azure OpenAI Client
azure_client = AzureOpenAI(
    azure_endpoint=AZURE_OPENAI_ENDPOINT,
    api_version=API_VERSION,
    api_key=AZURE_OPENAI_API_KEY,
    azure_deployment="2023-05-15"
)

# MongoDB Atlas Config
MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = "orpheus-bot"
COLLECTION_NAME = "Embeddings"

# Initialize MongoDB Connection
mongo_client = MongoClient(MONGO_URI)
db = mongo_client[DB_NAME]
collection = db[COLLECTION_NAME]

# Helper function to truncate text based on token count
def truncate_text(text, max_tokens=8192):
    """
    Truncates the input text to a maximum number of tokens using tiktoken.
    """
    # You might need to adjust the encoding name based on your model.
    encoding = tiktoken.get_encoding("cl100k_base")
    tokens = encoding.encode(text)
    if len(tokens) > max_tokens:
        tokens = tokens[:max_tokens]
        text = encoding.decode(tokens)
    return text

# Function to Generate Embeddings
def generate_embedding(text):
    response = azure_client.embeddings.create(
        input=text,
        model="text-embedding-3-large"
    )
    return response.data[0].embedding

# Process Each Document
for doc in tqdm(collection.find()):
    if "embedding" in doc:
        continue  # Skip if embedding already exists

    text = doc.get("content", "")
    if not text:
        continue

    # Truncate text to ensure it does not exceed the model's maximum context length
    text = truncate_text(text, max_tokens=8192)

    embedding = generate_embedding(text)

    collection.update_one(
        {"_id": doc["_id"]},
        {"$set": {"embedding": embedding}}
    )

print("Embeddings generated and stored successfully!")
