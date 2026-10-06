import os
from dotenv import load_dotenv

load_dotenv()


BUSINESS_NAME = "Emmason Laundry Services"
BUSINESS_ADDRESS = "23 Adu Street behind Bradford Hotel, Merit Junction, Lagos State"
BUSINESS_PHONE = "080 6348 7679"
FOOTER_NOTE = "Thank you for your patronage. Items not collected within 30 days are not our responsibility."




SECRET_KEY = os.getenv("BIZAPP_SECRET")
if not SECRET_KEY:
    raise RuntimeError("BIZAPP_SECRET is not set. Add it to the .env file.")

TOKEN_HOURS = 12          # how long a login lasts
BACKUP_DIR = "backups"
BACKUP_KEEP = 14          # number of backups to keep