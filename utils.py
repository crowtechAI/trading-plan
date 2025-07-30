import os
import pandas as pd

# The single, predictable filename we will use.
# It will be saved in the root of your project folder.
OUTPUT_FILENAME = "latest_forex_data.csv"

def save_csv(data, month, year):
    """
    Saves the provided data to a CSV file with a constant name.
    The month and year arguments are now ignored but kept for compatibility.
    """
    if not data:
        print("No data provided to save. Creating an empty file.")
        # Create an empty file to signal completion and avoid errors
        pd.DataFrame([]).to_csv(OUTPUT_FILENAME, index=False)
        return

    df = pd.DataFrame(data)
    # Save to the consistent, top-level filename
    df.to_csv(OUTPUT_FILENAME, index=False)
    print(f"✅ Data successfully saved to {OUTPUT_FILENAME}")