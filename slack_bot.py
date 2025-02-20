import os
import logging
import yaml
import requests
import tempfile
import time
import re
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from pinecone import Pinecone
from pinecone_plugins.assistant.models.chat import Message
from dotenv import load_dotenv
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.units import inch

load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Load credentials
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_APP_TOKEN = os.getenv("SLACK_APP_TOKEN")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
YAML_URL = "https://raw.githubusercontent.com/hackclub/YSWS-Catalog/main/data.yml"

# New constant for embeddings URL
EMBEDDINGS_URL = "https://raw.githubusercontent.com/DevSrijit/orpheus-chat/refs/heads/main/hackclub_embeddings_cron.json"

# Constants for user context scraping
CONTEXT_CHANNEL_ID = "C05B6DBN802"
CONTEXT_USER_ID = "U07BU2HS17Z"
LOUNGE_CHANNEL_ID = "C0266FRGV"

# Initialize Pinecone
pc = Pinecone(api_key=PINECONE_API_KEY)
assistant = pc.assistant.Assistant(assistant_name="orpheus")

# Initialize Slack app
app = App(token=SLACK_BOT_TOKEN)

def yaml_to_pdf(yaml_data, output_path):
    """Convert YAML data to a formatted PDF document"""
    doc = SimpleDocTemplate(
        output_path,
        pagesize=letter,
        rightMargin=72,
        leftMargin=72,
        topMargin=72,
        bottomMargin=72
    )
    
    styles = getSampleStyleSheet()
    story = []
    
    # Add header
    header_style = ParagraphStyle(
        'CustomHeader',
        parent=styles['Heading1'],
        fontSize=24,
        spaceAfter=30
    )
    story.append(Paragraph("Hack Club YSWS Catalog", header_style))
    story.append(Paragraph(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", styles['Normal']))
    story.append(Spacer(1, 20))
    
    # Add metadata section
    story.append(Paragraph("Dataset Information", styles['Heading2']))
    story.append(Spacer(1, 10))
    
    # Process each section of the YAML data
    for section_name, section_data in yaml_data.items():
        story.append(Paragraph(section_name.title(), styles['Heading2']))
        story.append(Spacer(1, 10))
        
        if isinstance(section_data, list):
            # Handle list of items
            for item in section_data:
                if isinstance(item, dict):
                    # Create a table for each dictionary item
                    table_data = [[Paragraph(k, styles['Heading4']), 
                                   Paragraph(str(v), styles['Normal'])] 
                                  for k, v in item.items()]
                    table = Table(table_data, colWidths=[2*inch, 4*inch])
                    table.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
                        ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
                        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                        ('FONTSIZE', (0, 0), (-1, 0), 12),
                        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
                        ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
                        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                        ('FONTSIZE', (0, 1), (-1, -1), 10),
                        ('GRID', (0, 0), (-1, -1), 1, colors.black)
                    ]))
                    story.append(table)
                    story.append(Spacer(1, 20))
                else:
                    story.append(Paragraph(str(item), styles['Normal']))
                    story.append(Spacer(1, 10))
        elif isinstance(section_data, dict):
            # Handle dictionary data
            table_data = [[Paragraph(k, styles['Heading4']), 
                           Paragraph(str(v), styles['Normal'])] 
                          for k, v in section_data.items()]
            table = Table(table_data, colWidths=[2*inch, 4*inch])
            table.setStyle(TableStyle([
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
                ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 12)
            ]))
            story.append(table)
            story.append(Spacer(1, 20))
    
    # Build the PDF
    doc.build(story)

def fetch_yaml_data():
    """Fetch YAML data from GitHub and convert to PDF"""
    try:
        response = requests.get(YAML_URL)
        response.raise_for_status()
        yaml_data = yaml.safe_load(response.content)
        
        # Create temporary PDF file
        pdf_path = tempfile.mktemp(prefix='ysws-data-', suffix='.pdf')
        yaml_to_pdf(yaml_data, pdf_path)
        
        return {
            "file_path": pdf_path,
            "metadata": {
                "source_url": YAML_URL,
                "converted_at": datetime.utcnow().isoformat(),
                "original_format": "yml",
                "document_type": "YSWS Catalog"
            }
        }
    except Exception as e:
        logger.error(f"Error processing YAML data: {e}")
        return None

def wait_for_file_processing(file_id, timeout=5000, interval=10):
    """Wait for file processing to complete with status checks"""
    start_time = datetime.now()
    while (datetime.now() - start_time).seconds < timeout:
        try:
            file_status = assistant.describe_file(file_id=file_id)
            logger.debug(f"File {file_id} status: {file_status['status']} ({file_status['percent_done']}%)")
            
            if file_status['status'] == 'Available':
                logger.info(f"File {file_id} processed successfully")
                return True
            elif file_status['status'] in ['ProcessingFailed', 'Deleting']:
                logger.error(f"File processing failed: {file_status.get('error_message', 'Unknown error')}")
                return False
            
            time.sleep(interval)
        except Exception as e:
            logger.error(f"Error checking file status: {e}")
            return False
    logger.error("File processing timed out")
    return False

def update_knowledge_base():
    """Update Pinecone knowledge base with PDF document"""
    logger.info("Starting knowledge base update")
    
    data = fetch_yaml_data()
    if not data:
        logger.error("Failed to fetch and process YAML data")
        return

    # Delete previous files
    try:
        filter = {
            "source_url": YAML_URL
        }
        files = assistant.list_files(filter=filter)
        for file in files:
            if file['status'] not in ['Deleting', 'ProcessingFailed'] and file['name'].startswith('ysws-data-'):
                logger.info(f"Deleting file {file['id']} (Status: {file['status']})")
                assistant.delete_file(file_id=file['id'])
                while True:
                    try:
                        assistant.describe_file(file_id=file['id'])
                        time.sleep(1)
                    except Exception:
                        break
    except Exception as e:
        logger.error(f"Error in file cleanup: {e}")

    # Upload and verify new file
    try:
        file_info = assistant.upload_file(
            file_path=data['file_path'],
            metadata=data['metadata']
        )
        logger.info(f"Uploaded new file: {file_info['id']}")
        
        if wait_for_file_processing(file_info['id']):
            logger.info("New file successfully processed and available")
        else:
            raise Exception("File processing failed")
            
    except Exception as e:
        logger.error(f"Knowledge base update failed: {e}")
    finally:
        # Clean up temporary PDF file
        try:
            os.remove(data['file_path'])
        except Exception as e:
            logger.error(f"Error cleaning up temporary file: {e}")

def update_embeddings():
    """Update Pinecone knowledge base with embeddings data"""
    logger.info("Starting embeddings update")
    
    try:
        # Fetch new embeddings file
        response = requests.get(EMBEDDINGS_URL)
        response.raise_for_status()
        
        # Create temporary file for embeddings data
        temp_path = tempfile.mktemp(prefix='embeddings-', suffix='.json')
        with open(temp_path, 'wb') as f:
            f.write(response.content)
        
        # Delete previous embeddings file(s)
        try:
            filter = {
                "source_url": EMBEDDINGS_URL
            }
            files = assistant.list_files(filter=filter)
            for file in files:
                if file['status'] not in ['Deleting', 'ProcessingFailed']:
                    logger.info(f"Deleting embeddings file {file['id']} (Status: {file['status']})")
                    assistant.delete_file(file_id=file['id'])
                    while True:
                        try:
                            assistant.describe_file(file_id=file['id'])
                            time.sleep(1)
                        except Exception:
                            break
        except Exception as e:
            logger.error(f"Error in embeddings file cleanup: {e}")

        # Upload new embeddings file
        file_info = assistant.upload_file(
            file_path=temp_path,
            metadata={
                "source_url": EMBEDDINGS_URL,
                "converted_at": datetime.utcnow().isoformat(),
                "original_format": "json",
                "document_type": "Hack Club Embeddings"
            }
        )
        logger.info(f"Uploaded new embeddings file: {file_info['id']}")
        
        if wait_for_file_processing(file_info['id']):
            logger.info("New embeddings file successfully processed and available")
        else:
            raise Exception("Embeddings file processing failed")
            
    except Exception as e:
        logger.error(f"Embeddings update failed: {e}")
    finally:
        # Clean up temporary embeddings file
        try:
            os.remove(temp_path)
        except Exception as e:
            logger.error(f"Error cleaning up temporary embeddings file: {e}")

def update_user_context(message_text):
    """
    Update the assistant's context with the latest message text from a specific user.
    Deletes any previous context file so that only the latest message is stored.
    Uploads the context as a .txt file.
    """
    logger.info("Updating user context for assistant")
    # Delete previous context files
    try:
        context_filter = {
            "document_type": "User Context",
            "source_id": CONTEXT_USER_ID
        }
        files = assistant.list_files(filter=context_filter)
        for file in files:
            if file['status'] not in ['Deleting', 'ProcessingFailed']:
                logger.info(f"Deleting previous context file {file['id']} (Status: {file['status']})")
                assistant.delete_file(file_id=file['id'])
                while True:
                    try:
                        assistant.describe_file(file_id=file['id'])
                        time.sleep(1)
                    except Exception:
                        break
    except Exception as e:
        logger.error(f"Error during previous context file cleanup: {e}")

    # Write the new context to a temporary .txt file
    try:
        temp_context_path = tempfile.mktemp(prefix='user-context-', suffix='.txt')
        with open(temp_context_path, 'w', encoding='utf-8') as f:
            f.write(message_text)
    except Exception as e:
        logger.error(f"Error writing context file: {e}")
        return

    # Upload the new context file
    try:
        file_info = assistant.upload_file(
            file_path=temp_context_path,
            metadata={
                "source_id": CONTEXT_USER_ID,
                "converted_at": datetime.utcnow().isoformat(),
                "original_format": "txt",
                "document_type": "User Context"
            }
        )
        logger.info(f"Uploaded new user context file: {file_info['id']}")
        
        if wait_for_file_processing(file_info['id']):
            logger.info("User context file successfully processed and available")
        else:
            raise Exception("User context file processing failed")
    except Exception as e:
        logger.error(f"User context update failed: {e}")
    finally:
        try:
            os.remove(temp_context_path)
        except Exception as e:
            logger.error(f"Error cleaning up temporary context file: {e}")

# Lakera Guard API will be used for comprehensive content moderation.

def moderate_with_lakera(prompt_text):
    """
    Call the Lakera Guard API's moderation endpoint to flag and detect any AI security risks.
    Returns a json where 'flagged' is True if any risk is detected.
    """
    try:
        api_key = os.getenv("LAKERA_GUARD_API_KEY")
        if not api_key:
            logger.error("LAKERA_GUARD_API_KEY not set.")
            return False, None
        url = "https://api.lakera.ai/v2/guard"
        payload = {"messages": [{"content": prompt_text, "role": "user"}], "metadata": {"project_id": "project-6267211438"}}
        headers = {"Authorization": f"Bearer {api_key}"}
        response = requests.post(url, json=payload, headers=headers, timeout=5)
        response.raise_for_status()
        result = response.json()
        flagged = result.get("flagged", False)
        return flagged, result
    except Exception as e:
        logger.error(f"Error during Lakera Guard moderation: {e}")
        return False, None

def sanitize_mentions(text):
    """
    Sanitize the text to prevent actual Slack pings.
    Replace user/channel mentions such as <@U12345> or <!channel> with a harmless format.
    """
    # Replace user mentions: <@U12345> -> @/U12345
    text = re.sub(r"<@([A-Z0-9]+)>", r"@/\1", text)
    # Replace special mentions like <@channel>, <@here>, <@everyone>
    text = re.sub(r"@((?:channel|here|everyone)[^>]*)", r"@/\1", text)
    return text

# Scheduler for periodic updates
scheduler = BackgroundScheduler()
scheduler.add_job(update_knowledge_base, 'cron', hour=0)
scheduler.add_job(update_embeddings, 'cron', hour=0, minute=30)
scheduler.start()

@app.event("app_mention")
def handle_app_mention_events(body, say):
    event = body.get("event", {})
    channel_id = event.get("channel")
    message_ts = event.get("ts")
    
    # Extract the text and remove the bot mention
    try:
        bot_id = app.client.auth_test()["user_id"]
    except Exception as e:
        logger.error(f"Error fetching bot user id: {e}")
        bot_id = ""
    text = event.get("text", "").replace(f"<@{bot_id}>", "").strip()
    
    # --- Use Lakera Guard API for comprehensive moderation ---
    flagged, guard_response = moderate_with_lakera(text)
    if flagged:
        flagged_message = ("🚫 Oi, I think you're trying to trick me!\n"
                           "As an AI, I may produce content which may be harmful to this community (and then Srijit will pull the plug on me). In order to prevent this (and stay alive), I'm going to ignore you this time.")
        sanitized = sanitize_mentions(flagged_message)
        say({
            "text": sanitized,
            "mrkdwn": True,
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": sanitized
                    }
                }
            ]
        })
        return

    # FD Moderation: Restrict processing in lounge channel
    if channel_id == LOUNGE_CHANNEL_ID:
        lounge_message = ("⚠️ I can't answer questions in #lounge, "
                          "this is to combat bot spam & inaccurate information in #lounge. "
                          "Please ask your question in #orpheus-irl.")
        sanitized = sanitize_mentions(lounge_message)
        say({
            "text": sanitized,
            "mrkdwn": True,
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": sanitized
                    }
                }
            ]
        })
        return

    # Normal stuff
    try:
        try:
            app.client.reactions_add(channel=channel_id, timestamp=message_ts, name="loading-dots")
        except Exception as e:
            logger.error(f"Failed to add loading reaction: {e}")
        
        msg = Message(content=text)
        response = assistant.chat(messages=[msg])
        
        # Format the message content for Slack and sanitize mentions
        message_content = response["message"]["content"]
        message_content = sanitize_mentions(message_content)
        
        # Send message with proper Slack markdown formatting
        say({
            "text": message_content,
            "mrkdwn": True,
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": message_content
                    }
                }
            ]
        })
        
        try:
            app.client.reactions_add(channel=channel_id, timestamp=message_ts, name="white_check_mark")
        except Exception as e:
            logger.error(f"Failed to add white_check_mark reaction: {e}")
    except Exception as e:
        logger.exception("Error handling message:")
        error_message = "⚠️ An error occurred while processing your request"
        say({
            "text": error_message,
            "mrkdwn": True,
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": error_message
                    }
                }
            ]
        })
        try:
            app.client.reactions_add(channel=channel_id, timestamp=message_ts, name="x")
        except Exception as e:
            logger.error(f"Failed to add error reaction: {e}")
    finally:
        try:
            app.client.reactions_remove(channel=channel_id, timestamp=message_ts, name="loading-dots")
        except Exception as e:
            logger.error(f"Failed to remove loading reaction: {e}")

# New event handler to capture messages from a specific user in a specific channel
@app.event("message")
def handle_user_context_messages(event, logger):
    # Check that the event comes from the designated channel and user,
    # and ignore messages with a subtype (like bot messages or message edits)
    if (event.get("channel") == CONTEXT_CHANNEL_ID and
        event.get("user") == CONTEXT_USER_ID and
        not event.get("subtype")):
        text = event.get("text", "").strip()
        if text:
            logger.info(f"New context message received from {CONTEXT_USER_ID} in channel {CONTEXT_CHANNEL_ID}")
            update_user_context(text)

if __name__ == "__main__":
    logger.info("Starting application with scheduled updates")
    update_knowledge_base()
    update_embeddings()
    handler = SocketModeHandler(app, SLACK_APP_TOKEN)
    handler.start()