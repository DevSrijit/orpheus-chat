from slack_bolt import App
import os
from dotenv import load_dotenv

load_dotenv()

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
app = App(token=SLACK_BOT_TOKEN)

# Get emoji list and filter for orpheus
response = app.client.emoji_list()
orpheus_emojis = {name: url for name, url in response['emoji'].items() if 'orpheus' in name.lower()}

# Print results
print("\nOrpheus Emojis Found:")
for name, url in orpheus_emojis.items():
    print(f":{name}:")
print(f"\nTotal: {len(orpheus_emojis)} orpheus emojis")