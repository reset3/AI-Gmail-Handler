import re
import groq_llm
import google_api
import os

COUNTER_FILE = 'email_counter.txt'

def load_counter(): # Load the counter from the file. If the file doesn't exist, start from 1.
    if os.path.exists(COUNTER_FILE):
        with open(COUNTER_FILE, 'r') as file:
            try:
                return int(file.read().strip())
            except ValueError:
                return 1  # If the file is empty or corrupted, start from 1
    else:
        return 1

def save_counter(counter): # Save the current counter value to the file.
    with open(COUNTER_FILE, 'w', encoding='utf-8') as file:  # Use utf-8 encoding
        file.write(str(counter))
        
def sanitize_filename(filename): # Replace invalid characters (<>:"/\|?*) for Windows file names
    return re.sub(r'[<>:"/\\|?*]', '_', filename)

def get_user_email_settings():
    label = 0
    query = input("\nInput here the query you want to apply in the search for the email (e.g. is:unread from:example@gmail.com): ")
    
    apply_label = input("\nDo you want to apply a label to the emails handled by the program? (yes/no): ").lower()
    if apply_label.strip() == "y" or  apply_label.strip() == "yes":
        label = input("Input here the label to apply (e.g. Read by AI): ")
    
    delete_label = input("\nDo you want to delete a label? (yes/no): ").lower()
    if delete_label.strip() == "y" or  delete_label.strip() == "yes":
        label = input("Input here the label to delete (e.g. Read by AI): ") 
        delete_label = 1
    else:
        delete_label = 0
        
    download = input("\nDo you want to download email attachments? (yes/no): ").lower()
    if download.strip() == "y" or  download.strip() == "yes":
        download = 1
    else:
        download = 0
    
    print(f"\nGathering emails using query: {query}\n")
    return query, label, delete_label, download

def get_user_llm_request():
    request = "This is the body of an email.\nPlease summarise what it is about by main topic/subject/reason.\n"
    change_request = input("Do you want to change the prompt given to the LLM? (yes/no): ").lower()
    
    if change_request.strip() == "y" or  change_request.strip() == "yes":
        request = input("Input the prompt (e.g. Summarize the email content): ")
        
    return request

def main():
    # Load the persistent email counter
    counter = int(load_counter())

    service = google_api.create_gmail_service()
    query, label, delete_label, download = get_user_email_settings()
    emails = google_api.get_emails(service, query, label, download)
    
    print(f"\nGathered {len(emails)} emails.\n")
    
    request = get_user_llm_request()
    
    if delete_label:
        google_api.delete_label(service, label)
    
    for email in emails:
        body, e = groq_llm.limit_body_length(request, email['body']) # limit prompt length to 32k chars
        if e:
            email['sender'] = email['sender']+"-truncated"
            
        response = groq_llm.llm_response(request + body)

        # Store response
        safe_sender = sanitize_filename(email['sender'])
        # Use the persistent counter to ensure unique filenames
        try:
            with open(f"Inbox/[{counter}-{safe_sender}.txt", "w", encoding="utf-8") as f:  # Using utf-8 encoding for file
                f.write(f"{email['subject']}\nResponse:\n" + response)
        except UnicodeEncodeError as ue:
            print(f"Error writing file: {ue}")
        
        # Increment the counter for each email processed
        print(counter)
        counter += 1

    # Save the updated counter to the file after processing all emails
    save_counter(counter)

main()