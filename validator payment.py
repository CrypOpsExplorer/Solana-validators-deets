import tkinter as tk
from tkinter import messagebox, scrolledtext, filedialog
from datetime import datetime
from solana.rpc.api import Client
import csv
import time

# Constants
RPC_URL = "https://api.mainnet-beta.solana.com"
client = Client(RPC_URL)
PAYOUT_RATE_PER_10K = 2.97  # USD per 10,000 SOL per epoch

# Retry-safe block time fetcher with exponential backoff and handling None
def get_block_time(slot, retries=7):
    delay = 3
    for attempt in range(retries):
        try:
            result = client.get_block_time(slot)
            if result.value is not None:
                return result.value
            else:
                # No block time for this slot, treat as skipped and return None
                return None
        except Exception as e:
            print(f"Warning: attempt {attempt+1} failed for slot {slot} with error: {e}")
        time.sleep(delay)
        delay = min(delay * 2, 10)  # exponential backoff capped at 10 sec
    raise Exception(f"❌ Could not get block time for slot {slot} after {retries} retries.")

# Get slot for timestamp using binary search, skip slots with no block time
def get_slot_for_time(target_time):
    current_slot = client.get_slot().value
    low, high = 0, current_slot

    while low <= high:
        mid = (low + high) // 2
        ts = get_block_time(mid)
        if ts is None:
            # Skip missing block time slots by moving upward
            mid += 1
            if mid > high:
                break
            continue
        if ts < target_time:
            low = mid + 1
        else:
            high = mid - 1
        time.sleep(3)  # delay to avoid rate limiting
    return low

def get_epoch_schedule():
    return client.get_epoch_schedule().value

def get_epoch_from_slot(slot, schedule):
    slots_per_epoch = schedule.slots_per_epoch
    first_normal_slot = schedule.first_normal_slot
    first_normal_epoch = schedule.first_normal_epoch

    if slot < first_normal_slot:
        return slot // schedule.leader_schedule_slot_offset
    return first_normal_epoch + (slot - first_normal_slot) // slots_per_epoch

def get_stake_for_validator(pubkey):
    vote_accounts = client.get_vote_accounts().value
    for validator in vote_accounts["current"] + vote_accounts["delinquent"]:
        if validator["votePubkey"] == pubkey:
            return float(validator["activatedStake"]) / 1e9  # lamports to SOL
    return 0

def calculate_payout(pubkeys, start_date, end_date, output_box):
    try:
        output_box.delete("1.0", tk.END)
        output_box.insert(tk.END, f"Getting slots for dates... please wait\n")

        start_ts = int(datetime.strptime(start_date, "%Y-%m-%d").timestamp())
        end_ts = int(datetime.strptime(end_date, "%Y-%m-%d").timestamp())

        start_slot = get_slot_for_time(start_ts)
        end_slot = get_slot_for_time(end_ts)

        schedule = get_epoch_schedule()
        start_epoch = get_epoch_from_slot(start_slot, schedule)
        end_epoch = get_epoch_from_slot(end_slot, schedule)

        output_box.insert(tk.END, f"Epoch range: {start_epoch} to {end_epoch}\n\n")

        csv_rows = [("Pubkey", "Epoch", "Stake (SOL)", "Payout (USD)")]

        for pubkey in pubkeys:
            pubkey = pubkey.strip()
            if not pubkey:
                continue
            total_stake, total_payout, epoch_count = 0, 0, 0
            output_box.insert(tk.END, f"Results for {pubkey}:\n")

            for epoch in range(start_epoch, end_epoch + 1):
                stake = get_stake_for_validator(pubkey)
                payout = (stake / 10_000) * PAYOUT_RATE_PER_10K
                csv_rows.append((pubkey, epoch, round(stake, 2), round(payout, 2)))
                output_box.insert(tk.END, f"  Epoch {epoch}: Stake = {stake:.2f} SOL → Payout = ${payout:.2f}\n")
                total_stake += stake
                total_payout += payout
                epoch_count += 1
                time.sleep(1)  # pause to avoid rate-limiting

            avg_stake = total_stake / epoch_count if epoch_count else 0
            output_box.insert(tk.END, f"  ➤ Average Stake: {avg_stake:.2f} SOL\n")
            output_box.insert(tk.END, f"  ➤ Total Payout: ${total_payout:.2f}\n\n")

        file_path = filedialog.asksaveasfilename(defaultextension=".csv", title="Save CSV As", filetypes=[("CSV files", "*.csv")])
        if file_path:
            with open(file_path, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerows(csv_rows)
            output_box.insert(tk.END, f"\n✅ Results saved to: {file_path}\n")
        else:
            output_box.insert(tk.END, "\n❌ CSV export cancelled.\n")

    except Exception as e:
        output_box.insert(tk.END, f"\n❌ ERROR: {str(e)}\n")

# GUI Setup
def create_gui():
    window = tk.Tk()
    window.title("Solana Validator Payout Calculator")
    window.geometry("700x600")

    tk.Label(window, text="Validator Pubkeys (comma or newline separated):").pack()
    pubkey_text = tk.Text(window, height=5, width=80)
    pubkey_text.pack()

    tk.Label(window, text="Start Date (YYYY-MM-DD):").pack()
    start_entry = tk.Entry(window, width=20)
    start_entry.pack()

    tk.Label(window, text="End Date (YYYY-MM-DD):").pack()
    end_entry = tk.Entry(window, width=20)
    end_entry.pack()

    output_box = scrolledtext.ScrolledText(window, width=85, height=20)
    output_box.pack(pady=10)

    def on_calculate():
        raw_pubkeys = pubkey_text.get("1.0", tk.END)
        pubkeys = [p.strip() for p in raw_pubkeys.replace(",", "\n").splitlines()]
        start = start_entry.get().strip()
        end = end_entry.get().strip()
        if not pubkeys or not start or not end:
            messagebox.showwarning("Input Missing", "Please fill in all fields.")
            return
        calculate_payout(pubkeys, start, end, output_box)

    tk.Button(window, text="Calculate and Export CSV", command=on_calculate).pack(pady=5)

    window.mainloop()

if __name__ == "__main__":
    create_gui()
