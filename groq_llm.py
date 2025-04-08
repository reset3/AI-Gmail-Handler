import os
from groq import Groq

def limit_body_length(request, body):
        if len(request+body) > 32000:
            body = (body[:(32000-len(request))]) 
            print("An email body was truncated to fit in the context window")
            return body, 1
        return body, 0

def llm_response(string):
    client = Groq( api_key = os.environ.get("GROQ_API_KEY"),)
    chat_completion = client.chat.completions.create(
        messages=[
            {
                "role": "user",
                "content": f"{string}",
            }
        ],
        model="llama3-8b-8192",
        temperature=0.4
    )
    return chat_completion.choices[0].message.content