#!/bin/sh
cd "$(dirname "$0")"
if command -v python3 >/dev/null; then
    python3 patch.py
else
    echo "Python 3 is not installed. Get it here: https://www.python.org/downloads/"
fi
echo
printf "Press Enter to close"
read _
