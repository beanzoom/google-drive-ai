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

def sanitize_for_json(s):
    """Removes invalid control characters that crash json.loads()."""
    # Rebuilds the string, allowing only printable characters and standard whitespace
    return "".join(char for char in s if char.isprintable() or char in ('\n', '\r', '\t'))

@functions_framework.http
def drive_action_handler(request):
    """The main AI-powered function."""
    request_json = request.get_json(silent=True)
    if not request_json or "prompt" not in request_json:
        return ("Request body must be JSON with a 'prompt' key.", 400)

    user_prompt = request_json["prompt"]
    print(f"Received prompt: {user_prompt}")

    try:
        # Call the AI Brain (Anthropic Claude)
        message = anthropic_client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=2048,
            system=SYSTEM_INSTRUCTION,
            messages=[{"role": "user", "content": user_prompt}]
        )
        ai_response_text = message.content[0].text
        print(f"Received raw AI response: {repr(ai_response_text)}")

        # --- FINAL, AGGRESSIVE SANITIZATION ---
        sanitized_text = sanitize_for_json(ai_response_text)
        
        ai_data = json.loads(sanitized_text)
        
        file_name = ai_data.get("fileName")
        file_content = ai_data.get("fileContent")
        if not file_name or file_content is None:
             return ("AI response was missing fileName or fileContent.", 500)
             
    except Exception as e:
        print(f"Error calling AI model or parsing response: {e}")
        return (f"Error processing prompt with AI: {e}", 500)
    
    try:
        drive_service = get_drive_service()
        result = create_drive_file(drive_service, file_name, file_content)
        print(result)
        return (result, 200)
    except Exception as e:
        print(f"Error creating Drive file: {e}")
        return (f"Failed to create file: {e}", 500)
