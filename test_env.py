from dotenv import load_dotenv
import os

load_dotenv()

print("API_TOKEN =", os.getenv("API_TOKEN"))
