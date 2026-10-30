
#This reads the sightings data from json file and prints how many signting are in it.

import json
from collections import Counter
from datetime import datetime



# 1. load the records in.
with open ("scratch/sightings.json", encoding="utc-8") as file:
	sightings = json.load(file)

print ("Numbers of signtings:", len(records))

#2. count the duplicate IDs, excluding missing or blank IDs.
ids = [
	record["id"]
	for record in records
	if isinstance(record.get("id"), str) and record ["id"].strip()
]

print ("Duplicate IDs:", len(ids) - len(set(ids)))

#3. count missing or blank values for each field.
fields = ("id","data","location","species","latinName")
missing_counts = {field: 0 for field in fields}

for record in records:
	for field in fields:
		value = record.get(field)
		if value is None or (isinstance(value, str) and not value.strip()):
			missing_counts[field] += 1
			
   
#4. count the sightings by location and species.   
print("Missing values:")
for field, count in missing_counts.items():
	print(f"{field}: {count}")

print("Sightings by location:", Counter(
    record.get("location") for record in records
).most_common())

print("Sightings by specices:", Counter(
    record.get("location") for record in records
).most_common())


#5. fidn the earlist and latest valid dates.
valid_dates = []
invaild_date_count = 0

for record in records:
    try:
        valid_dates.append(datetime.fromisoformat(record.get("date")))
    except (TypeError, ValueError):
        invaild_date_count += 1
        
print("Invalid dates:", invalid_date_count)
if valid_dates:
    print("Date range:", min(valid_dates), "to", max(valid_dates))
else:
    print("Date range: no valid dates found")
