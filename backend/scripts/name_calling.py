import os
import re
import pickle
import csv
import glob
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
import pandas as pd
import requests

# Dynamically resolve path to the 'assets' folder
ASSETS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "assets")
)
DEFAULT_DB_PATH = os.path.join(ASSETS_DIR, "stocks_registry.pkl")


@dataclass(slots=True)
class StockRecord:
    symbol: str
    company: str
    callname: str


def compute_callname(company_name: str) -> str:
    """
    Applies transformation rules to generate CALLNAME from COMPANY name.

    Rules:
    1. If name has only two words keep it as is.
    2. If the word 'limited' (or 'ltd') appears anywhere after the 2nd word, remove it.
    3. Remove anything inside parenthesis.
    4. Remove numbers/digits (EXCEPT if the number is in the very first word).
    """
    if not isinstance(company_name, str) or not company_name.strip():
        return ""

    # Rule 3: Remove text inside parenthesis
    name = re.sub(r"\(.*?\)", "", company_name)

    # Split into words before removing numbers to isolate the first word
    raw_words = name.split()
    if not raw_words:
        return ""

    words = []
    for i, word in enumerate(raw_words):
        if i == 0:
            # First word: Keep it exactly as is (preserves starting numbers)
            words.append(word)
        else:
            # Rule 4: Remove numbers/digits from all subsequent words
            cleaned_word = re.sub(r"\d+", "", word)
            if cleaned_word.strip():
                words.append(cleaned_word.strip())

    # Rule 1: If 2 or fewer words, keep as is
    if len(words) <= 2:
        return " ".join(words)

    # Rule 2: Keep the first two words, then filter out 'limited' or 'ltd' from the rest
    new_words = words[:2]

    for word in words[2:]:
        # Check case-insensitive and strip punctuation
        if word.lower().strip(".,") not in ["limited", "ltd"]:
            new_words.append(word)

    return " ".join(new_words)


class StockRegistry:
    """In-memory Pythonic registry optimized for O(1) lookups and atomic local persistence."""

    def __init__(self, filepath: str = DEFAULT_DB_PATH):
        self.filepath = filepath
        os.makedirs(os.path.dirname(self.filepath), exist_ok=True)
        self.records: dict[str, StockRecord] = self._load()

    def _load(self) -> dict[str, StockRecord]:
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "rb") as f:
                    return pickle.load(f)
            except Exception as e:
                print(f"Warning: Could not load persistence file ({e}). Starting fresh.")
        return {}

    def sync_dataframe(self, df: pd.DataFrame):
        added, updated, unchanged = 0, 0, 0

        for _, row in df.iterrows():
            symbol = str(row["SYMBOL"]).strip()
            company = str(row["COMPANY"]).strip()

            if not symbol or not company or symbol.lower() == "nan":
                continue

            callname = compute_callname(company)

            if symbol not in self.records:
                self.records[symbol] = StockRecord(
                    symbol=symbol, company=company, callname=callname
                )
                added += 1
            elif self.records[symbol].company != company:
                self.records[symbol] = StockRecord(
                    symbol=symbol, company=company, callname=callname
                )
                updated += 1
            else:
                unchanged += 1

        print(
            f"Sync Complete -> Added: {added} | Updated: {updated} | Unchanged: {unchanged}"
        )
        self.save_atomic()

    def save_atomic(self):
        temp_path = f"{self.filepath}.tmp"
        with open(temp_path, "wb") as f:
            pickle.dump(self.records, f, protocol=pickle.HIGHEST_PROTOCOL)
        os.replace(temp_path, self.filepath)

    def generate_audit_csv(self):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        audit_filename = f"audit_report_{timestamp}.csv"
        audit_filepath = os.path.join(os.path.dirname(self.filepath), audit_filename)

        with open(audit_filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=["symbol", "company", "callname"])
            writer.writeheader()
            for record in self.records.values():
                writer.writerow(asdict(record))

        print(f"Audit CSV generated: {audit_filepath}")

    def get(self, symbol: str) -> StockRecord | None:
        return self.records.get(symbol.strip())


def get_callname(company_or_symbol: str, db_file: str = DEFAULT_DB_PATH) -> str:
    """Return a stored callname for a symbol/company, or compute a safe fallback."""
    query = company_or_symbol.strip()
    if not query:
        return ""

    registry = StockRegistry(filepath=db_file)
    symbol_match = registry.get(query)
    if symbol_match:
        return symbol_match.callname

    normalized_query = query.casefold()
    for record in registry.records.values():
        if record.company.casefold() == normalized_query:
            return record.callname

    return compute_callname(query)


def cleanup_old_files(current_file_path: str):
    """Deletes older PSX history .xls files from the assets directory."""
    search_pattern = os.path.join(ASSETS_DIR, "indhist_*.xls")
    existing_files = glob.glob(search_pattern)

    removed_count = 0
    for file_path in existing_files:
        if file_path != current_file_path:
            try:
                os.remove(file_path)
                removed_count += 1
            except OSError as e:
                print(f"Failed to remove {file_path}: {e}")

    if removed_count > 0:
        print(f"Cleaned up {removed_count} older history file(s).")


def run_daily_writer(target_date: str = None, db_file: str = DEFAULT_DB_PATH):
    """Fetches daily PSX data, syncs the persistent store, and cleans old files."""

    # 1. Determine Date and URL
    if not target_date:
        # Default to yesterday (current date - 1 day)
        target_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    file_url = f"https://dps.psx.com.pk/download/indhist/{target_date}.xls"
    xls_filename = f"indhist_{target_date}.xls"
    xls_filepath = os.path.join(ASSETS_DIR, xls_filename)

    os.makedirs(ASSETS_DIR, exist_ok=True)

    # 2. Download File
    print(f"Downloading daily file from: {file_url}")
    try:
        response = requests.get(
            file_url,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=30,
        )
        response.raise_for_status()
    except requests.exceptions.HTTPError as e:
        print(f"HTTP Error: Could not fetch data for {target_date}. (Is it a weekend/holiday?)")
        print(f"Details: {e}")
        return None

    # Save to assets directory
    with open(xls_filepath, "wb") as f:
        f.write(response.content)
    print(f"Saved daily file to: {xls_filepath}")

    # 3. Read & Sync Data
    df = pd.read_excel(xls_filepath, usecols=["SYMBOL", "COMPANY"])

    print(f"Syncing data to: {db_file}")
    registry = StockRegistry(filepath=db_file)
    registry.sync_dataframe(df)

    # 4. Generate Audit & Cleanup
    registry.generate_audit_csv()
    cleanup_old_files(current_file_path=xls_filepath)

    return registry


if __name__ == "__main__":
    # You can now run this directly without providing a manual test date,
    # as it will automatically pull yesterday's file.

    print("--- Running Daily Sync ---")
    run_daily_writer()

    print("\n--- Verifying Database ---")
    registry = StockRegistry()

    # Checking our newly adjusted rule
    match = registry.get("786")

    if match:
        print(f"Success! Found: {match.symbol} -> {match.company}")
        print(f"Computed Callname: {match.callname}")
    else:
        print("Test failed: Symbol not found.")
