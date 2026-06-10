#!/bin/bash
echo "Syncing to Windows..."
rsync -av --delete \
  --exclude='.git' \
  --exclude='build' \
  --exclude='.dart_tool' \
  ~/JamAi/jam_ai_app/ \
  /mnt/c/Users/shsal/jam_ai_app/

echo "Done! Now run in PowerShell:"
echo "cd C:\Users\shsal\jam_ai_app && flutter run -d chrome"
