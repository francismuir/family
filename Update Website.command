#!/bin/zsh
# Double-click this file in Finder to rebuild the Muir Family Tree website (docs/)
# and all data/GEDCOM exports (exports/) from your edits in exports/muir_family_tree.xlsx.

cd "$(dirname "$0")" || exit 1

echo "============================================================"
echo "  Updating The Muir Family Tree Website & GEDCOM Exports"
echo "============================================================"
echo ""

if [ -f "exports/~\$muir_family_tree.xlsx" ]; then
  echo "Note: exports/muir_family_tree.xlsx is currently open in Excel."
  echo "Make sure you have pressed Cmd+S (Save) in Excel so your latest changes are included!"
  echo ""
fi

python3 scripts/generate_website.py

if [ $? -eq 0 ]; then
  echo ""
  echo "✅ Success! Your website (docs/index.html) and exports (exports/muir_family_tree.ged, .xlsx, .csv, .xml, .json) are now up to date."
else
  echo ""
  echo "❌ An error occurred while updating the website."
fi

echo ""
read -k 1 "?Press any key to close this window..."
echo ""

