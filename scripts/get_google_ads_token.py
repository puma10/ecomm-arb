#!/usr/bin/env python3
"""Generate a new Google Ads refresh token.

Run this script to get a fresh refresh token that matches your client credentials.
It will open a browser window for you to authenticate.

Usage:
    python scripts/get_google_ads_token.py
"""

import os
from pathlib import Path

# Load .env file
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())

client_id = os.environ.get("GOOGLE_ADS_CLIENT_ID")
client_secret = os.environ.get("GOOGLE_ADS_CLIENT_SECRET")

if not client_id or not client_secret:
    print("❌ Missing GOOGLE_ADS_CLIENT_ID or GOOGLE_ADS_CLIENT_SECRET in .env")
    exit(1)

print(f"Using client ID: {client_id[:20]}...{client_id[-20:]}")

try:
    from google_auth_oauthlib.flow import InstalledAppFlow
except ImportError:
    print("❌ Missing google-auth-oauthlib. Installing...")
    import subprocess
    subprocess.run(["pip", "install", "google-auth-oauthlib"], check=True)
    from google_auth_oauthlib.flow import InstalledAppFlow

client_config = {
    "installed": {
        "client_id": client_id,
        "client_secret": client_secret,
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": ["http://localhost:8080/"],
    }
}

print("\n🔐 Opening browser for Google authentication...")
print("   (Make sure to log in with the account that has Google Ads access)\n")

flow = InstalledAppFlow.from_client_config(
    client_config,
    scopes=["https://www.googleapis.com/auth/adwords"]
)

credentials = flow.run_local_server(port=8080, prompt="consent")

print("\n" + "=" * 60)
print("✅ SUCCESS! Here's your new refresh token:")
print("=" * 60)
print(f"\n{credentials.refresh_token}\n")
print("=" * 60)
print("\nUpdate your .env file:")
print(f"GOOGLE_ADS_REFRESH_TOKEN={credentials.refresh_token}")
print("\nThen restart the backend.")
