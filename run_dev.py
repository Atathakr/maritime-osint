"""Dev server launcher — loads .env then starts Flask on port 5001."""
import os
import sys

# Ensure CWD is project root so python-dotenv finds .env
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv(override=True)  # override=True ensures .env values win over any empty vars in parent env

# Validate required env vars before importing app
if not os.environ.get("SECRET_KEY"):
    print("SECRET_KEY is required. Set it in your environment or .env file.")
    sys.exit(1)

from app import app  # noqa: E402

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5001, debug=True)
