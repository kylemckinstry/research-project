"""Import employee data from CSV to Firestore."""
from scheduler.domain.db import get_firestore
from scheduler.io.import_csv import import_employees_csv
from pathlib import Path

# Get Firestore client
client = get_firestore()

# Import employees
csv_path = Path("data/employees_id.csv")
if csv_path.exists():
    count = import_employees_csv(client, csv_path)
    print(f"\n✓ Successfully imported {count} employees to Firestore!")
    print("\nYou can now:")
    print("  1. Check the Firestore console: https://console.firebase.google.com/project/rostretto-fb/firestore")
    print("  2. Test the API: curl https://rostretto-scheduler-127031505005.australia-southeast1.run.app/employees")
else:
    print(f"CSV file not found: {csv_path}")
