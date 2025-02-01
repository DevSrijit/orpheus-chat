# Orpheus Chat: Behind the Scenes

Orpheus Chat is an AI-powered Slack bot that brings Hack Club's knowledge base to life. Let me walk you through how I built it. You can start talking with Orpheus by pinging `@Orpheus AI` at Slack.

## The Journey

I wanted to create a bot that could truly understand and respond to questions about Hack Club's diverse community. I started by researching existing bots and AI models, but I quickly realized that none of them were tailored to my specific needs.

So, I set out to build my own.

### Building the Knowledge Base

First, I needed to give the bot deep knowledge about Hack Club. I wrote a Python scraper that collected data from the HackClub/dns repository to find all domains, then I scraped all the sites, gathering information about various projects, initiatives, and community resources. This raw data was then transformed into a structured JSON format (`hackclub_finetune.jsonl`), making it perfect for AI consumption.

### Making the Bot Smart

To give the bot real understanding, I used advanced AI techniques:

- Generated semantic embeddings from the processed data
- Stored these embeddings in Pinecone's vector database
- Integrated Pinecone's assistant feature for intelligent responses

### Real-time Communication

The bot comes alive through Slack integration:

- Built using the Slack Bolt Framework for robust event handling
- Implemented Socket Mode for secure, real-time communication
- Added comprehensive error handling and logging
- Hosted on nest

### Technical Stack

- Python for the core implementation
- Slack Bolt for the messaging interface
- Pinecone for AI capabilities and vector storage
- MongoDB for structured data management

The result? A smart, context-aware assistant that helps Hack Club community members get the information they need, when they need it. This bot is hosted on nest ! Feel free to ping `@Orpheus AI` to start a chat or ask a question.
