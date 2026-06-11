#!/bin/bash
# Helper script to run live editing workflow test

echo "=========================================="
echo "Marcedit Live Editing Workflow Test"
echo "=========================================="
echo ""
echo "SETUP INSTRUCTIONS:"
echo "1. Make sure Marcedit is running"
echo "2. Open a PDF document in Marcedit"
echo "3. Make sure the PDF is visible in the main view"
echo ""
echo "Press ENTER when ready to start the test..."
read

echo ""
echo "Starting test in 3 seconds..."
sleep 3

cd /Users/mhm/Documents/Dev/Marcedit
python3 -m tests.gui_harness.live_editing_test

echo ""
echo "Test complete! Check the report that just opened."
