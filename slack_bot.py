import os
import logging
import yaml
import requests
import tempfile
import time
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
        files = assistant.list_files(filter=f"source_url = '{YAML_URL}'")
        for file in files.get('files', []):
            if file['status'] not in ['Deleting', 'ProcessingFailed']:
                logger.info(f"Deleting file {file['id']} (Status: {file['status']})")
                assistant.files.delete(file_id=file['id'])
                while True:
                    try:
                        assistant.files.get(file_id=file['id'])
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

# Configure scheduler
scheduler = BackgroundScheduler()
scheduler.add_job(update_knowledge_base, 'cron', hour=0)
scheduler.start()

@app.event("app_mention")
def handle_app_mention_events(body, say):
    event = body.get("event", {})
    channel_id = event.get("channel")
    message_ts = event.get("ts")
    
    try:
        app.client.reactions_add(channel=channel_id, timestamp=message_ts, name="loading-dots")
    except Exception as e:
        logger.error(f"Failed to add loading reaction: {e}")

    try:
        text = event.get("text", "").replace(f"<@{app.client.auth_test()['user_id']}>", "").strip()
        msg = Message(content=text)
        response = assistant.chat(messages=[msg])
        
        # Format the message content for Slack
        message_content = response["message"]["content"]
        
        # Send message with proper Slack formatting
        say({
            "text": message_content,
            "mrkdwn": True,  # Enable Slack markdown parsing
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
        
        app.client.reactions_add(channel=channel_id, timestamp=message_ts, name="white_check_mark")
    except Exception as e:
        logger.exception("Error handling message:")
        say("⚠️ An error occurred while processing your request")
        app.client.reactions_add(channel=channel_id, timestamp=message_ts, name="x")
    finally:
        try:
            app.client.reactions_remove(channel=channel_id, timestamp=message_ts, name="loading-dots")
        except Exception as e:
            logger.error(f"Failed to remove loading reaction: {e}")

if __name__ == "__main__":
    logger.info("Starting application with scheduled updates")
    update_knowledge_base()
    handler = SocketModeHandler(app, SLACK_APP_TOKEN)
    handler.start()