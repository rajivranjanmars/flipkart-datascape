#!/usr/bin/env bash
# Double-click this file in Finder to set up (first run only) and launch the
# scraper. No Terminal typing required.
cd "$(dirname "${BASH_SOURCE[0]}")"

clear
echo "Datascape — marketplace scraper"
echo "================================"
echo

if ! ./setup.sh; then
  echo
  echo "Setup failed — see the messages above for what went wrong."
  read -r -p "Press Enter to close this window..."
  exit 1
fi

echo
echo "Starting the scraper..."
echo
.venv/bin/python -m scraper

echo
read -r -p "Press Enter to close this window..."
