import base64
import os
import re
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.errors import HttpError
from bs4 import BeautifulSoup


# If modifying these SCOPES, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/gmail.modify',
          'https://www.googleapis.com/auth/spreadsheets']

def create_gmail_service(): # Authenticate and create a service to access Gmail API.
    creds = None
    # Check if token.json exists for previous login session
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    # If there are no (valid) credentials available, log in
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=51230)
        # Save the credentials for the next run
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    
    # Return the Gmail service
    return build('gmail', 'v1', credentials=creds)

def clean_html_email_body(html_content): # Cleans some HTML email content, removing unnecessary formatting and extracting plain text.
    # Parse the HTML content with BeautifulSoup
    soup = BeautifulSoup(html_content, 'html.parser')

    # Remove <style> and <script> tags and their content
    for element in soup(['style', 'script']):
        element.extract()

    # Extract text from the parsed HTML, which strips away all tags
    clean_text = soup.get_text()

    # Use regex to remove excessive whitespaces, newlines, and tabs
    clean_text = re.sub(r'\s+', ' ', clean_text)  # Collapses multiple spaces into one

    # Optionally, further strip specific unwanted sections based on content patterns
    # e.g., clean_text = re.sub(r"UnwantedTextPattern", "", clean_text)

    return clean_text.strip()  # Clean up leading/trailing spaces

def extract_body_and_attachments(payload): # Extracts the body and attachments from a Gmail message payload.
    body = ""
    number_of_attachments = 0
    attachment_names = []
    
    if 'parts' in payload:
        for part in payload['parts']:
            # Check if the part is text/plain or text/html
            if part['mimeType'] == 'text/plain':
                body = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')
            elif part['mimeType'] == 'text/html' and not body:
                # If no plain text body is found, fallback to HTML
                body = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')
            # Handle attachments
            elif 'filename' in part and part['filename']:
                attachment_names.append(part['filename'])
                number_of_attachments += 1

            # Check for nested parts
            if 'parts' in part:
                nested_body, nested_attachments, nested_attachment_names = extract_body_and_attachments(part)
                if nested_body:
                    body = nested_body
                number_of_attachments += nested_attachments
                attachment_names.extend(nested_attachment_names)
    else:
        # Single-part message
        if 'data' in payload['body']:
            body = base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8')
    #Returns: body (string): The decoded email body (plain text or HTML), number_of_attachments (int) / attachment_names (list)
    return clean_html_email_body(body), number_of_attachments, attachment_names

def get_emails(service, query, label, download):  
    try:
        # Retrieve emails from the user's inbox
        results = service.users().messages().list(userId='me', labelIds=['INBOX'], q=query).execute()
        messages = results.get('messages', [])
        
        email_contents = []

        if not messages:
            print('No new messages.')
            return email_contents
        
        # Process each message
        for message in messages:
            msg = service.users().messages().get(userId='me', id=message['id'], format="full").execute()
            headers = msg['payload']['headers']

            # Extract subject and sender
            subject = next((header['value'] for header in headers if header['name'] == 'Subject'), None)
            sender = next((header['value'] for header in headers if header['name'] == 'From'), None)
            
            # Initialize body and attachment-related variables
            body = None
            number_of_attachments = 0
            attachment_names = []

            # Extract body and attachments
            body, number_of_attachments, attachment_names = extract_body_and_attachments(msg['payload'])

            # If attachments are found, append that info to the body
            if number_of_attachments > 0:
                attachment_list = ', '.join(attachment_names)
                body = f"This email has {number_of_attachments} attachment(s): {attachment_list}\n\n{body}"
            
            # Append the email data
            email_contents.append({
                'subject': subject,
                'sender': sender,
                'body': body if body else "(No body content)"
            })

            # Apply label if provided
            if label:
                apply_label(service, message['id'], label)

            # Download if requested
            if download:
                get_attachments(service, message['id'])

    except HttpError as error:
        print(f'An error occurred: {error}')

    return email_contents

def delete_label(service, label_name): # Delete the label by its name.
    # Get the label list and check for the specified label
    label_list = service.users().labels().list(userId='me').execute()
    labels = label_list.get('labels', [])
    
    label_id = None
    for label in labels:
        if label['name'] == label_name:
            label_id = label['id']
            break
    
    if label_id: # Step 2: Delete the label if it exists
        service.users().labels().delete(userId='me', id=label_id).execute()
        print(f"Label '{label_name}' deleted.")
    else:
        print(f"Label '{label_name}' not found. Nothing to delete.")


def get_or_create_label(service, label_name): # Get the label by name. If it doesn't exist, create the label. return label id
    
    label_list = service.users().labels().list(userId='me').execute() # Check if the label exists
    labels = label_list.get('labels', [])
    
    for label in labels:
        if label['name'] == label_name:
            return label['id']  # Return existing label ID

    label_body = {'name': label_name, 'labelListVisibility': 'labelShow', 'messageListVisibility': 'show'}  # Create the label if it doesn't exist
    label = service.users().labels().create(userId='me', body=label_body).execute()   
     
    return label['id']  # Return the new label ID

def apply_label(service, email_id, label_name):         # Apply the label to an email. If the label doesn't exist, create it.
    
    label_id = get_or_create_label(service, label_name) # Get or create the label
    service.users().messages().modify(userId='me', id=email_id, body={'addLabelIds': [label_id]} ).execute() # Apply the label to the email
    
def get_attachments(service, msg_id):  # Removed store_dir parameter
    try:
        # Get the message with the given ID
        message = service.users().messages().get(userId='me', id=msg_id).execute()
        parts = [message['payload']]
        
        # Define the directory for storing attachments
        store_dir = os.path.join(os.getcwd(), 'Inbox')  # Create 'Inbox' folder in current directory
        
        while parts:
            part = parts.pop()
            
            # Check for nested parts in the message payload
            if part.get('parts'):
                parts.extend(part['parts'])
            
            # If there's an attachment
            if part.get('filename'):
                if 'data' in part['body']:
                    # Handle attachments encoded directly in the message body
                    file_data = base64.urlsafe_b64decode(part['body']['data'].encode('UTF-8'))
                elif 'attachmentId' in part['body']:
                    # Retrieve the attachment using attachmentId
                    attachment = service.users().messages().attachments().get(
                        userId='me', messageId=msg_id, id=part['body']['attachmentId']
                    ).execute()
                    file_data = base64.urlsafe_b64decode(attachment['data'].encode('UTF-8'))
                else:
                    file_data = None
                
                if file_data:
                    # Create the 'Inbox' directory if it doesn't exist
                    if not os.path.exists(store_dir):
                        os.makedirs(store_dir)
                    
                    # Create a unique file name
                    file_path = os.path.join(store_dir, part['filename'])
                    base_name, extension = os.path.splitext(part['filename'])
                    count = 1
                    
                    # Increment the filename if it already exists
                    while os.path.exists(file_path):
                        file_path = os.path.join(store_dir, f"{base_name}_{count}{extension}")
                        count += 1
                    
                    # Save the attachment
                    with open(file_path, 'wb') as f:
                        f.write(file_data)
    
    except HttpError as error:
        print(f'An error occurred: {error}')