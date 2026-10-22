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

COUNTRY_CODE = "234"   # Nigeria. Local numbers like 0801... become 234801...

# Placeholders: {name} {business} {invoice} {total} {paid} {balance}
#               {balance_line} {amount} {items} {due}
WHATSAPP_TEMPLATES = {
    "received": (
        "Hello {name}, we have received your laundry ({items}) at {business}. "
        "Order {invoice}, total {total}. Expected ready: {due}. Thank you!"
    ),
    "ready": (
        "Hello {name}, your laundry order {invoice} is ready for pickup at {business}. "
        "{balance_line} Thank you!"
    ),
    "receipt": (
        "Hello {name}, we received your payment of {amount} for order {invoice}. "
        "{balance_line} Thank you for choosing {business}!"
    ),
    "balance": (
        "Hello {name}, a friendly reminder from {business}: {balance} is outstanding "
        "on order {invoice} (total {total}). Kindly pay at your earliest convenience. Thank you."
    ),
    "delayed": (
        "Hello {name}, we are sorry your order {invoice} is not ready yet. "
        "We will let you know as soon as it is. Thank you for your patience. - {business}"
    ),
}
PRODUCTION = os.getenv("BIZAPP_ENV", "").lower() == "production"