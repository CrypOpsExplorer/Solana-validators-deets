import tkinter as tk
from tkinter import messagebox, scrolledtext, filedialog
from datetime import datetime
import requests
import csv
import time

# Constants
API_TOKEN = "YOUR_VALIDATORS_APP_API_TOKEN"  # Replace with your Validators.app API token
BASE_URL = "https://www.validators.app/api/v1"
HEADERS = {"Token": API_TOKEN}

# Resolve input (stake account or vote account) to a vote account
def resolve_vote_account(input_key):
    # Try treating input as a stake account
    params = {"stake_pubkey": input_key}
    resp = requests.get(
        f"{BASE_URL}/stake-explorer/mainnet.json",
        headers=HEADERS,
        params=params
    )
    data = resp.json()
    recs = data.get("explorer_stake_accounts", [])
    if recs:
        return recs[0].get("delegated_vote_account_address")
    # Fallback: assume input_key is a vote account
    return input_key

# Fetch validator details from Validators.app
def fetch_validator_details(vote_account, with_history=False):
    params = {}
    if with_history:
        params["with_history"] = "true"
    resp = requests.get(
        f"{BASE_URL}/validators/mainnet/{vote_account}.json",
        headers=HEADERS,
        params=params
    )
    return resp.json()

# Fetch list of epochs
def get_epochs():
    epochs = []
    page, per = 1, 50
    while True:
        resp = requests.get(
            f"{BASE_URL}/epochs/mainnet.json",
            headers=HEADERS,
            params={"per": per, "page": page}
        )
        data = resp.json()
        batch = data.get("epochs", [])
        if not batch:
            break
        for e in batch:
            epochs.append({"epoch": e["epoch"], "date": e["created_at"]})
        if len(epochs) >= data.get("epochs_count", 0):
            break
        page += 1
        time.sleep(0.5)
    return epochs

# Filter epochs by a date range
def filter_epochs_by_date(start_date_str, end_date_str):
    start_dt = datetime.strptime(start_date_str, "%Y-%m-%d").date()
    end_dt = datetime.strptime(end_date_str, "%Y-%m-%d").date()
    epochs = get_epochs()
    return [e["epoch"] for e in epochs
            if start_dt <= datetime.fromisoformat(e["date"].replace("Z", "+00:00")).date() <= end_dt]

# Fetch all stake snapshots for a validator vote account
def fetch_stake_records(vote_account):
    records = []
    page, per = 1, 999
    while True:
        params = {"vote_account": vote_account, "per": per, "page": page}
        resp = requests.get(
            f"{BASE_URL}/stake-explorer/mainnet.json",
            headers=HEADERS,
            params=params
        )
        data = resp.json()
        recs = data.get("explorer_stake_accounts", [])
        records.extend(recs)
        total = data.get("total_count", 0)
        if len(records) >= total:
            break
        page += 1
        time.sleep(1)
    return records

# Main calculation logic
def calculate(pubkeys, mode, start_val, end_val, output_box):
    try:
        output_box.delete("1.0", tk.END)
        for raw in pubkeys:
            if not raw.strip():
                continue
            input_key = raw.strip()
            vote_account = resolve_vote_account(input_key)
            # Fetch validator details (basic)
            details = fetch_validator_details(vote_account)
            output_box.insert(tk.END, f"\nValidator: {details.get('name')} ({vote_account})\n")
            output_box.insert(tk.END, f"  Commission: {details.get('commission')}%\n")
            output_box.insert(tk.END, f"  Active Stake: {round(details.get('active_stake',0)/1e9,2)} SOL\n")
            output_box.insert(tk.END, f"  Description: {details.get('details')}\n")
            if mode == 'live':
                continue  # live mode only shows current details

            # Determine epoch list
            if mode == 'date':
                epochs = filter_epochs_by_date(start_val, end_val)
            else:  # epoch range
                start_e, end_e = int(start_val), int(end_val)
                epochs = list(range(start_e, end_e + 1))

            output_box.insert(
                tk.END,
                f"\nEpochs ({mode}): {epochs}\n"
            )
            output_box.insert(tk.END, "Epoch-wise Stakes:\n")

            # Fetch historical stake snapshots
            records = fetch_stake_records(vote_account)
            stake_by_epoch = {}
            for rec in records:
                ep = rec.get('epoch')
                lam = rec.get('active_stake', 0)
                stake_by_epoch[ep] = stake_by_epoch.get(ep, 0) + lam

            # Display each epoch
            for ep in epochs:
                lam = stake_by_epoch.get(ep, 0)
                sol = lam / 1e9
                output_box.insert(
                    tk.END,
                    f"  Epoch {ep}: {sol:.2f} SOL\n"
                )
    except Exception as e:
        output_box.insert(tk.END, f"\n❌ ERROR: {e}\n")

# GUI Setup

def create_gui():
    window = tk.Tk()
    window.title("Validators.app Stake & Details Explorer")
    window.geometry("750x650")

    # Input area
    tk.Label(window, text="Enter Validator Pubkeys or Stake Account Pubkeys (comma/newline separated):").pack(pady=5)
    pub_text = tk.Text(window, height=4, width=90)
    pub_text.pack()

    # Mode selection
    mode_var = tk.StringVar(value='date')
    mode_frame = tk.Frame(window)
    tk.Radiobutton(mode_frame, text="Date Range", variable=mode_var, value='date').pack(side='left')
    tk.Radiobutton(mode_frame, text="Epoch Range", variable=mode_var, value='epoch').pack(side='left')
    tk.Radiobutton(mode_frame, text="Live Data", variable=mode_var, value='live').pack(side='left')
    mode_frame.pack(pady=5)

    # Date inputs
    date_frame = tk.Frame(window)
    tk.Label(date_frame, text="Start Date (YYYY-MM-DD):").pack(side='left')
    date_start = tk.Entry(date_frame, width=15)
    date_start.pack(side='left', padx=5)
    tk.Label(date_frame, text="End Date (YYYY-MM-DD):").pack(side='left')
    date_end = tk.Entry(date_frame, width=15)
    date_end.pack(side='left', padx=5)
    date_frame.pack(pady=5)

    # Epoch inputs
    epoch_frame = tk.Frame(window)
    tk.Label(epoch_frame, text="Start Epoch:").pack(side='left')
    epoch_start = tk.Entry(epoch_frame, width=10)
    epoch_start.pack(side='left', padx=5)
    tk.Label(epoch_frame, text="End Epoch:").pack(side='left')
    epoch_end = tk.Entry(epoch_frame, width=10)
    epoch_end.pack(side='left', padx=5)
    epoch_frame.pack(pady=5)

    # Output box
    output_box = scrolledtext.ScrolledText(window, width=95, height=25)
    output_box.pack(pady=10)

    def on_run():
        texts = pub_text.get("1.0", tk.END).replace(',', '\n').splitlines()
        mode = mode_var.get()
        start_val = date_start.get().strip() if mode=='date' else epoch_start.get().strip()
        end_val = date_end.get().strip() if mode=='date' else epoch_end.get().strip()
        if mode != 'live' and (not start_val or not end_val):
            messagebox.showwarning("Missing Inputs", "Please provide both start and end values for the selected mode.")
            return
        calculate(texts, mode, start_val, end_val, output_box)

    tk.Button(window, text="Fetch Data", command=on_run).pack(pady=5)

    window.mainloop()

if __name__ == "__main__":
    create_gui()
