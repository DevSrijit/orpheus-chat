import os
import logging
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from pinecone import Pinecone
from pinecone_plugins.assistant.models.chat import Message
from dotenv import load_dotenv

load_dotenv()

# Configure logging to output detailed debug information
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Load credentials from environment variables
SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
SLACK_APP_TOKEN = os.environ.get("SLACK_APP_TOKEN")
PINECONE_API_KEY = os.environ.get("PINECONE_API_KEY")

if not SLACK_BOT_TOKEN or not SLACK_APP_TOKEN or not PINECONE_API_KEY:
    logger.error("Missing one or more required environment variables: SLACK_BOT_TOKEN, SLACK_APP_TOKEN, or PINECONE_API_KEY.")
    exit(1)

# Initialize Pinecone assistant
logger.debug("Initializing Pinecone assistant...")
pc = Pinecone(api_key=PINECONE_API_KEY)
assistant = pc.assistant.Assistant(assistant_name="orpheus")

# Initialize the Slack app
app = App(token=SLACK_BOT_TOKEN)

@app.event("app_mention")
def handle_app_mention_events(body, say):
    logger.debug(f"Received app_mention event: {body}")
    try:
        event = body.get("event", {})
        user = event.get("user")
        text = event.get("text", "")
        logger.info(f"Message from user {user}: {text}")
        
        # Optionally, remove the bot mention from the text if needed.
        # For example, if the bot's user ID is "<@U12345>", you might do:
        # text = text.replace(f"<@{app.client.auth_test()['user_id']}>", "").strip()
        
        # Create a Message object for the Pinecone assistant
        msg = Message(content=text)
        logger.debug(f"Sending message to Pinecone assistant: {msg.content}")
        
        # Query the Pinecone assistant (non-streaming example)
        response = assistant.chat(messages=[msg])
        reply_text = response["message"]["content"]
        logger.info(f"Received response from assistant: {reply_text}")
        
        # Send the reply back in Slack
        say(reply_text)
        
    except Exception as e:
        logger.exception("Error handling app_mention event:")
        say("Sorry, something went wrong while processing your request.")

if __name__ == "__main__":
    logger.info("Starting Slack bot in Socket Mode...")
    # Use Socket Mode to connect your app to Slack
    handler = SocketModeHandler(app, SLACK_APP_TOKEN)
    handler.start()
