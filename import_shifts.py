"""Import shift data from CSV to Firestore."""
from scheduler.domain.db import get_firestore
from scheduler.io.import_csv import import_shifts_csv
from pathlib import Path

# Get Firestore client
client = get_firestore()

# Import shifts
csv_path = Path("data/shiftWeeks_12w.csv")
if csv_path.exists():
    # Import all shifts (no week filter)
    count = import_shifts_csv(client, csv_path, week_id=None)
    print(f"\n✓ Successfully imported {count} shifts to Firestore!")
    print("\nYou can now:")
    print("  1. Check the Firestore console: https://console.firebase.google.com/project/rostretto-fb/firestore")
    print("  2. Test scheduling via the API")
else:
    print(f"CSV file not found: {csv_path}")
