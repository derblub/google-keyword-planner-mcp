#!/usr/bin/env python3
"""Einmalige Einrichtung: holt den OAuth2-Refresh-Token und schreibt local/.env.

Aufruf:
    ./setup.py                       # fragt Client-ID und Client-Secret ab
    ./setup.py client_secret_*.json  # liest beides aus der Google-JSON-Datei
"""

import getpass
import http.server
import json
import os
import secrets
import subprocess
import sys
import urllib.parse
import urllib.request

PORT = 9876
REDIRECT_URI = f"http://localhost:{PORT}"
SCOPE = "https://www.googleapis.com/auth/adwords"
ENV_PATH = os.path.join(os.path.dirname(os.path.realpath(__file__)), ".env")


def read_client(argv):
    if len(argv) > 1:
        with open(argv[1]) as f:
            data = json.load(f)
        client = data.get("installed") or data.get("web")
        if not client:
            sys.exit("JSON-Datei enthält weder 'installed' noch 'web'.")
        if "installed" not in data:
            print("Hinweis: Das ist kein Desktop-App-Client; die Weiterleitung "
                  f"{REDIRECT_URI} muss dort eingetragen sein.")
        return client["client_id"], client["client_secret"]
    client_id = input("Client-ID: ").strip()
    client_secret = getpass.getpass("Client-Secret (Eingabe unsichtbar): ").strip()
    return client_id, client_secret


def wait_for_code(state):
    result = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            result.update({k: v[0] for k, v in params.items()})
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write("Fertig. Dieser Tab kann geschlossen werden.".encode())

        def log_message(self, *args):
            pass

    with http.server.HTTPServer(("127.0.0.1", PORT), Handler) as server:
        while "code" not in result and "error" not in result:
            server.handle_request()

    if "error" in result:
        sys.exit(f"Google hat die Anmeldung abgelehnt: {result['error']}")
    if result.get("state") != state:
        sys.exit("State stimmt nicht überein, Abbruch.")
    return result["code"]


def exchange(client_id, client_secret, code):
    body = urllib.parse.urlencode({
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": REDIRECT_URI,
    }).encode()
    try:
        with urllib.request.urlopen("https://oauth2.googleapis.com/token", body) as resp:
            tokens = json.load(resp)
    except urllib.error.HTTPError as e:
        sys.exit(f"Token-Tausch fehlgeschlagen: {e.read().decode()}")
    if "refresh_token" not in tokens:
        sys.exit("Antwort enthält keinen Refresh-Token.")
    return tokens["refresh_token"]


def main():
    client_id, client_secret = read_client(sys.argv)
    customer_id = input("Google-Ads-Kundennummer (10-stellig): ").strip().replace("-", "")
    login_customer_id = input(
        "Manager-Kontonummer (leer lassen, wenn kein Manager-Konto): "
    ).strip().replace("-", "")

    state = secrets.token_urlsafe(16)
    auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode({
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    })
    print("\nBrowser öffnet sich. Falls nicht, diese Adresse aufrufen:\n" + auth_url + "\n")
    subprocess.Popen(["xdg-open", auth_url],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    refresh_token = exchange(client_id, client_secret, wait_for_code(state))

    # Google ignoriert den developer-token-Header seit September 2026,
    # der Server verlangt aber einen nicht leeren Wert.
    lines = [
        "GOOGLE_ADS_DEVELOPER_TOKEN=unused",
        f"GOOGLE_ADS_CLIENT_ID={client_id}",
        f"GOOGLE_ADS_CLIENT_SECRET={client_secret}",
        f"GOOGLE_ADS_REFRESH_TOKEN={refresh_token}",
        f"GOOGLE_ADS_CUSTOMER_ID={customer_id}",
    ]
    if login_customer_id:
        lines.append(f"GOOGLE_ADS_LOGIN_CUSTOMER_ID={login_customer_id}")

    fd = os.open(ENV_PATH, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write("\n".join(lines) + "\n")
    os.chmod(ENV_PATH, 0o600)
    print(f"Gespeichert in {ENV_PATH}")


if __name__ == "__main__":
    main()
