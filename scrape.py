import aiohttp
import asyncio
import json
import uuid
import yaml
import glob
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import tldextract
from pymongo import MongoClient
import os
import socket

# Configuration
SHORTLINK_DOMAIN = "hack.af"
FINE_TUNE_FILE = "hackclub_finetune.jsonl"
EMBEDDINGS_FILE = "hackclub_embeddings.json"
MAX_CONCURRENT_REQUESTS = 100  # Adjust based on server capacity
RATE_LIMIT_DELAY = 0  # Delay between requests in seconds

# MongoDB Atlas Connection
MONGO_URI = os.getenv("MONGO_URI")
print(MONGO_URI)
DB_NAME = "orpheus-bot"
COLLECTION_NAME = "Embeddings"

# Initialize MongoDB connection
try:
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)  # 5-second timeout
    client.server_info()  # Test connection
    db = client[DB_NAME]
    collection = db[COLLECTION_NAME]
    print("Connected to MongoDB successfully!")
except Exception as e:
    print(f"Error connecting to MongoDB: {e}")
    collection = None  # Disable MongoDB if connection fails

visited_urls = set()
allowed_domains = set()

async def expand_shortlink(session, url):
    try:
        async with session.head(url, allow_redirects=True, timeout=10) as response:
            return str(response.url) if response.status == 200 else None
    except Exception as e:
        print(f"Error expanding {url}: {e}")
        return None

def get_subdomains_from_yaml(yaml_files):
    subdomains = set()
    for yaml_file in yaml_files:
        domain = yaml_file[:-5]  # Remove .yaml extension
        with open(yaml_file, 'r') as f:
            try:
                data = yaml.safe_load(f)
                if not data:
                    continue
                for key in data:
                    if key == '*':
                        continue
                    if key == '':
                        sub = domain
                    else:
                        sub = f"{key}.{domain}"
                    subdomains.add(sub)
            except yaml.YAMLError as e:
                print(f"Error parsing {yaml_file}: {e}")
    return subdomains

async def extract_data(session, url):
    try:
        # Skip SSL verification for misconfigured domains
        async with session.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"}, ssl=False) as response:
            if response.status != 200:
                print(f"Error: {url} returned status code {response.status}")
                return None

            html = await response.text()
            soup = BeautifulSoup(html, "lxml")  # Use lxml for faster parsing
            title = soup.title.string.strip() if soup.title else "No Title"
            headings = [h.get_text(strip=True) for h in soup.find_all(["h1", "h2", "h3"])]
            paragraphs = [p.get_text(strip=True) for p in soup.find_all("p")]
            metadata = {meta["name"]: meta["content"] for meta in soup.find_all("meta", attrs={"name": True, "content": True})}

            content = "\n".join(paragraphs)
            return {
                "id": str(uuid.uuid4()),
                "url": url,
                "title": title,
                "content": content,
                "metadata": {
                    "headings": headings,
                    "keywords": metadata.get("keywords", "").split(", ")
                }
            }
    except Exception as e:
        print(f"Error scraping {url}: {e}")
        return None

def generate_fine_tune_entry(data):
    return {
        "messages": [
            {"role": "system", "content": f"You are an expert in Hack Club topics related to {', '.join(data['metadata']['headings'][:2])}."},
            {"role": "user", "content": f"Tell me about {data['title']}"},
            {"role": "assistant", "content": data["content"]}
        ]
    }

def save_to_mongodb(data):
    if collection is None:
        print("MongoDB not connected. Skipping save.")
        return
    try:
        collection.insert_one(data)
        print(f"Saved to MongoDB: {data['url']}")
    except Exception as e:
        print(f"Error saving to MongoDB: {e}")

async def crawl_url(session, url, discovered_links):
    if url in visited_urls:
        return
    visited_urls.add(url)

    print(f"Crawling: {url}")
    
    parsed_url = urlparse(url)
    if parsed_url.netloc == SHORTLINK_DOMAIN:
        expanded_url = await expand_shortlink(session, url)
        if expanded_url and expanded_url not in visited_urls:
            url = expanded_url
            print(f"Expanded shortlink: {url}")

    data = await extract_data(session, url)
    if not data:
        return

    with open(FINE_TUNE_FILE, "a", encoding="utf-8") as f:
        json.dump(generate_fine_tune_entry(data), f)
        f.write("\n")

    with open(EMBEDDINGS_FILE, "a", encoding="utf-8") as f:
        json.dump(data, f)
        f.write("\n")

    save_to_mongodb(data)

    try:
        async with session.get(url, timeout=10, ssl=False) as response:
            html = await response.text()
            soup = BeautifulSoup(html, "lxml")
            for link in soup.find_all("a", href=True):
                full_link = urljoin(url, link["href"])
                if is_valid_link(full_link):
                    discovered_links.add(full_link)
    except Exception as e:
        print(f"Error processing links for {url}: {e}")

def is_valid_link(link):
    parsed = urlparse(link)
    domain = tldextract.extract(link).registered_domain
    return parsed.scheme in ["http", "https"] and domain in allowed_domains and link not in visited_urls

async def process_batch(session, batch):
    tasks = [crawl_url(session, url, set()) for url in batch]
    await asyncio.gather(*tasks)

async def main():
    global allowed_domains
    yaml_files = glob.glob("*.yaml")
    yaml_domains = [filename[:-5] for filename in yaml_files]
    allowed_domains = set(yaml_domains + [SHORTLINK_DOMAIN])
    
    subdomains = get_subdomains_from_yaml(yaml_files)
    print(f"Discovered subdomains from YAML: {subdomains}")
    
    start_urls = [f"https://{sub}" for sub in subdomains]
    discovered_links = set(start_urls)

    # Skip invalid domains
    valid_urls = [url for url in discovered_links if is_valid_link(url)]
    print(f"Valid URLs to crawl: {len(valid_urls)}")

    connector = aiohttp.TCPConnector(limit=MAX_CONCURRENT_REQUESTS, ssl=False)
    async with aiohttp.ClientSession(connector=connector) as session:
        while valid_urls:
            batch = [valid_urls.pop() for _ in range(min(MAX_CONCURRENT_REQUESTS, len(valid_urls)))]
            await process_batch(session, batch)
            await asyncio.sleep(RATE_LIMIT_DELAY)  # Rate limiting

if __name__ == "__main__":
    asyncio.run(main())