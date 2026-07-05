#!/usr/bin/env bash
# One-shot setup: creates a private Python environment (.venv), installs
# dependencies into it, installs the Chromium browser Playwright drives, and
# creates .env for proxy credentials (prompting for them once, interactively).
# Safe to re-run — later runs are fast no-ops.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 isn't installed on this machine."
  echo "Install it from https://www.python.org/downloads/ and then run this again."
  exit 1
fi

if [ ! -d .venv ]; then
  echo "==> Creating a private Python environment (.venv)"
  python3 -m venv .venv
fi

PY=.venv/bin/python
PIP=.venv/bin/pip

echo "==> Installing Python dependencies"
"$PIP" install --quiet --upgrade pip
"$PIP" install --quiet -r requirements.txt

echo "==> Installing Chromium for Playwright (first run only; can take a few minutes)"
"$PY" -m playwright install chromium

if [ ! -f .env ]; then
  cp .env.example .env
fi

# Ask for proxy credentials once, interactively, only if none are set yet.
# Non-technical users shouldn't have to open and edit a text file.
if ! grep -q "^PROXY_SERVER=..*" .env 2>/dev/null; then
  echo
  echo "Optional: if you have a residential proxy, enter it now (needed for Myntra;"
  echo "Flipkart/Amazon/Meesho work fine without one)."
  read -r -p "Proxy server, e.g. http://gate.provider.com:8000 (Enter to skip): " proxy_server
  if [ -n "$proxy_server" ]; then
    read -r -p "Proxy username (Enter to skip): " proxy_username
    read -r -s -p "Proxy password (Enter to skip): " proxy_password
    echo
    {
      echo "PROXY_SERVER=$proxy_server"
      echo "PROXY_USERNAME=$proxy_username"
      echo "PROXY_PASSWORD=$proxy_password"
      echo "PROXY_BYPASS="
    } > .env
    echo "Saved proxy settings to .env."
  fi
fi

echo
echo "Setup complete."
