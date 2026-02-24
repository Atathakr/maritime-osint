git clone https://github.com/Atathakr/maritime-osint.git
cd maritime-osint
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
# paste .env with DATABASE_URL, APP_PASSWORD, AISSTREAM_API_KEY
python app.py
# then hit Fetch OFAC + Fetch OpenSanctions + Reconcile in the browser
