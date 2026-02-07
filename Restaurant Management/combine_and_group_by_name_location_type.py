import pandas as pd
import os
import re

# Load employee names from both Excel files
user_files = [
    "/Users/arnoldoramirezjr/Desktop/users-export.xls",
    "/Users/arnoldoramirezjr/Desktop/users-export (1).xls"
]
employee_names = set()
for user_file in user_files:
    user_df = pd.read_excel(user_file)
    # Assume the first column contains the names
    for col in user_df.columns:
        employee_names.update(user_df[col].dropna().astype(str).str.strip())

# Business keywords for heuristic
BUSINESS_KEYWORDS = [
    "inc", "llc", "corp", "company", "co", "ltd", "services", "store",
    "enterprises", "group", "partners", "pllc", "pc", "plc", "associates"
]

def is_business(name):
    name_lower = name.lower()
    if any(keyword in name_lower for keyword in BUSINESS_KEYWORDS):
        return True
    if re.search(r"[^a-zA-Z\s\-'.]", name):
        return True
    if len(name.split()) > 3:
        return True
    return False

def is_person(name):
    # Check if name is in employee_names (case-insensitive)
    return name.strip().lower() in {n.lower() for n in employee_names}

def classify_name(name):
    if is_person(name):
        return "Employee"
    elif is_business(name):
        return "Business"
    else:
        # Heuristic: 2-3 words, no business keywords, no numbers
        words = name.split()
        if 1 < len(words) <= 3:
            return "Likely Person"
        return "Unknown"

# File paths for data
files = [
    "/Users/arnoldoramirezjr/Desktop/Kingsville.csv",
    "/Users/arnoldoramirezjr/Desktop/Alice.csv"
]
dfs = []
for file in files:
    location = os.path.splitext(os.path.basename(file))[0].capitalize()
    df = pd.read_csv(file)
    df['Location'] = location
    dfs.append(df)

combined_df = pd.concat(dfs, ignore_index=True)
combined_df['Name'] = combined_df['Name'].astype(str).str.strip()

# Classify each name
type_list = []
for name in combined_df['Name']:
    type_list.append(classify_name(name))
combined_df['Type'] = type_list

# Group by Name, Location, and Type, sum numeric columns
grouped = combined_df.groupby(['Name', 'Location', 'Type'], as_index=False).sum(numeric_only=True)

output_path = "/Users/arnoldoramirezjr/Desktop/combined_grouped_by_name_location_type.csv"
grouped.to_csv(output_path, index=False)
print(f"Grouped data saved to {output_path}")
