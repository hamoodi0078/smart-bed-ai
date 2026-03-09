import os
from dotenv import load_dotenv

# Load .env from project root
load_dotenv()

print("SENDGRID_API_KEY:", os.getenv("SENDGRID_API_KEY"))
print("EMAIL_FROM:", os.getenv("EMAIL_FROM"))
