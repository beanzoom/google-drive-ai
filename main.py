import functions_framework
import google.auth
import json
import vertexai
from vertexai.generative_models import GenerativeModel
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseUpload
import io

# --- Pre-configured Values ---
PROJECT_ID = "devstride-ai-project"
LOCATION = "us-central1"
PARENT_FOLDER_ID = "1jmrkOSfPo99L5L2onMR3ptvEqLBMWAwk"
DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive"]

# --- Initialize Vertex AI ---
vertexai.init(project=PROJECT_ID, location=LOCATION)

# --- System Instruction for the AI Model ---
SYSTEM_INSTRUCTION = """
You are a helpful assistant whose purpose is to create documents in Google Drive.
Based on the user's prompt, you must determine a suitable filename and the full text content for the document.
You must respond in a valid JSON format only, with no other text before or after the JSON block.
The JSON object must contain two keys: 'fileName' and 'fileContent'.
For example, if the user prompt is 'create a grocery list', your response should look like this:
{
  "fileName": "Grocery List.txt",
  "fileContent": "- Milk\\n- Bread\\n- Eggs\\n- Cheese"
}
"""

def get_drive_service():
    """Authenticates and returns a Drive service object."""
    creds, _ = google.auth.default(scopes=DRIVE_SCOPES)
    service = build("drive", "v3", credentials=creds)
    return service

def create_drive_file(drive_service, file_name, file_content):
    """Uses the Drive API to create a file."""
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
    print(f"Received prompt: {user_prompt}")

    try:
        model = GenerativeModel("gemini-1.0-pro-001", system_instruction=[SYSTEM_INSTRUCTION])
        response = model.generate_content(user_prompt)
        # Clean the AI response to ensure it's valid JSON
        cleaned_response_text = response.text.strip().replace("```json", "").replace("```", "")
        ai_data = json.loads(cleaned_response_text)
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
