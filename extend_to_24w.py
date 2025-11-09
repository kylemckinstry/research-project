"""Extend shift data from 12 weeks to 24 weeks"""
from datetime import datetime, timedelta
import csv

# Generate shiftWeeks_24w.csv
start_date = datetime(2025, 9, 1)
shift_weeks = []

for day_offset in range(168):  # 24 weeks * 7 days
    current_date = start_date + timedelta(days=day_offset)
    shift_id = 1000 + day_offset
    date_str = current_date.strftime('%Y-%m-%d')
    week_str = current_date.strftime('%Y-W%V')
    
    shift_weeks.append({
        'id': shift_id,
        'date': date_str,
        'week_id': week_str
    })

with open('data/shiftWeeks_24w.csv', 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=['id', 'date', 'week_id'])
    writer.writeheader()
    writer.writerows(shift_weeks)

print(f"Created shiftWeeks_24w.csv with {len(shift_weeks)} days")
print(f"Start: {shift_weeks[0]['date']} ({shift_weeks[0]['week_id']})")
print(f"End: {shift_weeks[-1]['date']} ({shift_weeks[-1]['week_id']})")

# Generate shiftDetails_24w.csv by extending the pattern
# Pattern: 4 employees per weekday, 5-6 employees on weekends
# Employee IDs: 1001-1008 (2 managers, 6 staff)
# Managers: 1001, 1002 (empty ratings, 8h shifts)
# Staff: 1003-1008 (various ratings, 7-8.5h shifts)

shift_details = []

# Define weekly rotation pattern (simplified)
weekday_pattern = [
    # 4 people: 2 managers + 2 staff
    [1001, 1003, 1006, 1007],  # Monday
    [1002, 1004, 1005, 1008],  # Tuesday
    [1001, 1003, 1006, 1007],  # Wednesday
    [1002, 1004, 1005, 1008],  # Thursday
    [1001, 1003, 1006, 1007],  # Friday
    [1001, 1002, 1003, 1004, 1005, 1008],  # Saturday (6 people)
    [1001, 1002, 1003, 1004, 1005, 1007],  # Sunday (6 people)
]

import random
random.seed(42)  # For consistent random ratings

for day_offset in range(168):
    current_date = start_date + timedelta(days=day_offset)
    shift_id = 1000 + day_offset
    date_str = current_date.strftime('%Y-%m-%d')
    day_of_week = current_date.weekday()  # 0=Monday, 6=Sunday
    
    employees = weekday_pattern[day_of_week]
    
    for emp_id in employees:
        # Managers (1001, 1002) work 8h with no skill ratings
        if emp_id in [1001, 1002]:
            start_time = f"{date_str}T07:00:00"
            end_time = f"{date_str}T15:00:00"
            coffee = sandwich = service = speed = ""
        
        # Staff members have varied schedules
        else:
            # Different shifts for variety
            if day_of_week in [5, 6]:  # Weekend
                if emp_id in [1003]:  # Short shift
                    start_time = f"{date_str}T11:00:00"
                    end_time = f"{date_str}T15:00:00"
                elif emp_id in [1007, 1008]:  # Early + extended
                    start_time = f"{date_str}T05:00:00"
                    end_time = f"{date_str}T13:30:00"
                else:  # Short shift
                    start_time = f"{date_str}T07:00:00"
                    end_time = f"{date_str}T12:00:00"
            else:  # Weekday
                if emp_id in [1007, 1008]:  # Early shift
                    start_time = f"{date_str}T05:00:00"
                    end_time = f"{date_str}T12:00:00"
                else:
                    start_time = f"{date_str}T07:00:00"
                    end_time = f"{date_str}T15:00:00"
            
            # Generate skill ratings
            # Sandwich specialists: 1007, 1008
            if emp_id in [1007, 1008]:
                coffee = ""
                sandwich = random.randint(70, 99)
                service = ""
                speed = ""
            # Baristas: 1003, 1006
            elif emp_id in [1003, 1006]:
                coffee = random.randint(33, 95)
                sandwich = ""
                service = random.randint(45, 79)
                speed = random.randint(50, 88)
            # Waiters: 1004, 1005
            else:
                coffee = random.randint(45, 78)
                sandwich = ""
                service = random.randint(64, 79)
                speed = random.randint(60, 91)
        
        shift_details.append({
            'shift_id': shift_id,
            'emp_id': emp_id,
            'start_time': start_time,
            'end_time': end_time,
            'coffee_rating': coffee,
            'sandwich_rating': sandwich,
            'customer_service_rating': service,
            'speed_rating': speed,
            'present': 'True'
        })

with open('data/shiftDetails_24w.csv', 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=[
        'shift_id', 'emp_id', 'start_time', 'end_time',
        'coffee_rating', 'sandwich_rating', 'customer_service_rating',
        'speed_rating', 'present'
    ])
    writer.writeheader()
    writer.writerows(shift_details)

print(f"Created shiftDetails_24w.csv with {len(shift_details)} shift assignments")
