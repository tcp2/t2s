import re

def clean_text(text):
    cleaned_text = re.sub(r'[^\w\s.,!?]', '', text)
    cleaned_text = re.sub(r'\s+', ' ', cleaned_text).strip()
    return cleaned_text

with open('input.txt', 'r') as f:
    dirty_text = f.read()
    cleaned = clean_text(dirty_text)

with open('clean.txt', 'w') as f:
    f.write(cleaned)