import functions_framework
import google.auth
import json
import anthropic
from google.cloud import secretmanager
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseUpload
import io
import os

# --- Configuration ---
PROJECT_ID = "devstride-ai-project"
PARENT_FOLDER_ID = "1jmrkOSfPo99L5L2onMR3ptvEqLBMWAwk"
DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive"]

# --- Function to get the secret API key ---
def get_anthropic_api_key():
    client = secretmanager.SecretManagerServiceClient()
    secret_name = f"projects/{PROJECT_ID}/secrets/anthropic-api-key/versions/latest"
    response = client.access_secret_version(request={"name": secret_name})
    return response.payload.data.decode("UTF-8")

# --- Initialize Anthropic Client ---
anthropic_client = anthropic.Anthropic(api_key=get_anthropic_api_key())

# --- System Instruction for the AI Model ---
SYSTEM_INSTRUCTION = """
You are a helpful assistant whose purpose is to create documents in Google Drive.
Based on the user's prompt, you must determine a suitable filename and the full text content for the document.
You must respond in a valid JSON format only, with no other text before or after the JSON block.
The JSON object must contain two keys: 'fileName' and 'fileContent'.
"""

def get_drive_service():
    creds, _ = google.auth.default(scopes=DRIVE_SCOPES)
    service = build("drive", "v3", credentials=creds)
    return service

def create_drive_file(drive_service, file_name, file_content):
    file_metadata = {"name": file_name, "parents": [PARENT_FOLDER_ID]}
    fh = io.BytesIO(file_content.encode('utf-8'))
    media = MediaIoBaseUpload(fh, mimetype='text/plain')
    file = drive_service.files().create(body=file_metadata, media_body=media, fields="id, name").execute()
    return f"Success! Created file '{file.get('name')}' in Google Drive."

@functions_framework.http
def drive_action_handler(request):
    """The main AI-powered function."""
    request_json = request.get_json(silent=True)
    if not request_json or "prompt" not in request_json:
        return ("Request body must be JSON with a 'prompt' key.", 400)

    user_prompt = request_json["prompt"]
    
    try:
        message = anthropic_client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=2048,
            system=SYSTEM_INSTRUCTION,
            messages=[{"role": "user", "content": user_prompt}]
        )
        ai_response_text = message.content[0].text

        # --- NEW DETAILED DIAGNOSTIC LOGGING ---
        print("--- START DIAGNOSTIC LOG ---")
        print(f"RAW RESPONSE TEXT: {ai_response_text}")
        print(f"RAW RESPONSE REPRESENTATION: {repr(ai_response_text)}")
        char_codes = [ord(c) for c in ai_response_text]
        print(f"CHARACTER CODES: {char_codes}")
        print("--- END DIAGNOSTIC LOG ---")
        
        # We will now try to clean and parse it
        json_substring = ai_response_text[ai_response_text.find('{'):ai_response_text.rfind('}')+1]
        ai_data = json.loads(json_substring)
        
        file_name = ai_data.get("fileName")
        file_content = ai_data.get("fileContent")
        if not file_name or file_content is None:
             return ("AI response was missing fileName or fileContent.", 500)
             
    except Exception as e:
        # This error is expected, we want to see the logs that came before it.
        print(f"PARSING FAILED WITH ERROR: {e}")
        return (f"Error processing prompt with AI: {e}", 500)
    
    # This part will likely not be reached
    try:
        drive_service = get_drive_service()
        result = create_drive_file(drive_service, file_name, file_content)
        print(result)
        return (result, 200)
    except Exception as e:
        print(f"Error creating Drive file: {e}")
        return (f"Failed to create file: {e}", 500)
