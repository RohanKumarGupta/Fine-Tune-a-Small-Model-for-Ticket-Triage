"""Audit and repair the labelled training rows using SCHEMA.md."""

import csv
import json
import re
from collections import Counter
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parent
TRAIN_PATH = ROOT / "data" / "train.jsonl"
LOG_PATH = ROOT / "cleaning_log.csv"
KEYS = {
    "category",
    "priority",
    "amount_paise",
    "txn_date",
    "txn_id",
    "channel",
    "language",
    "needs_human",
}
NON_TRANSACTION_CATEGORIES = {"account_access", "kyc", "other"}
LEGAL_THREAT = re.compile(
    r"\b(?:RBI|ombudsman|consumer court|lawyer|legal notice|legal action)\b",
    re.IGNORECASE,
)
PRIOR_CONTACT = re.compile(
    r"\b(?:"
    r"already (?:contacted|written|complained|raised|reported)"
    r"|(?:contacted|written to|complained to) (?:support|you|them) (?:about (?:this )?(?:issue )?)?(?:before|earlier)"
    r"|(?:second|third|fourth|multiple) time"
    r"|(?:2nd|3rd|4th|\d+(?:st|nd|rd|th)) time"
    r"|(?:second|third|fourth) complaint (?:on|about) (?:the )?same issue"
    r"|(?:\d+|two|three|four) times (?:about|regarding|for) this"
    r"|again and again|baar baar|(?:doosri|dusri|teesri|chauthi) baar"
    r"|pehle bhi (?:complaint|complain|contact|report)"
    r"|pehele bhi (?:complaint|complain|contact|report)"
    r")\b",
    re.IGNORECASE,
)


def expected_priority(label, ticket):
    category = label.get("category")
    amount = label.get("amount_paise")
    if category == "fraud" or (isinstance(amount, int) and not isinstance(amount, bool) and amount >= 5_000_000) or LEGAL_THREAT.search(ticket):
        return "P1"
    if category == "account_access" or (
        category in {"payment_failed", "refund"}
        and isinstance(amount, int)
        and not isinstance(amount, bool)
        and amount >= 500_000
    ):
        return "P2"
    return "P3"


def expected_needs_human(priority, ticket):
    return priority == "P1" or bool(PRIOR_CONTACT.search(ticket))


def normalize_date(value):
    if not isinstance(value, str):
        return value
    if re.fullmatch(r"\d{2}/\d{2}/\d{4}", value):
        day, month, year = value.split("/")
        try:
            return date(int(year), int(month), int(day)).isoformat()
        except ValueError:
            return value
    return value


def normalize_txn_id(value):
    if not isinstance(value, str):
        return value
    candidate = re.sub(r"[\s-]", "", value).upper()
    return candidate if re.fullmatch(r"NP\d{10}", candidate) else value


def clean_rows(rows):
    cleaned = []
    log = []
    dropped = 0
    for row in rows:
        row_id = row.get("id", "")
        messages = row.get("messages", [])
        ticket = next(
            (message.get("content", "") for message in messages if message.get("role") == "user"),
            "",
        )
        assistant = next(
            (message.get("content", "") for message in messages if message.get("role") == "assistant"),
            "",
        )
        try:
            label = json.loads(assistant)
        except (json.JSONDecodeError, TypeError):
            log.append((row_id, "drop", "Assistant label is truncated or invalid JSON and cannot be recovered reliably."))
            dropped += 1
            continue

        reasons = []
        if not isinstance(label, dict):
            log.append((row_id, "drop", "Assistant label is not a JSON object."))
            dropped += 1
            continue

        if "priority" not in label and "prio" in label:
            label["priority"] = label.pop("prio")
            reasons.append("Renamed corrupted prio key; priority is recomputed from SCHEMA.md.")
        elif "prio" in label:
            label.pop("prio")
            reasons.append("Removed unexpected prio key.")

        for key in KEYS - set(label):
            if key == "priority":
                continue
            label[key] = None
            reasons.append(f"Added missing {key} field as null.")

        if label.get("txn_date") is not None:
            normalized = normalize_date(label["txn_date"])
            if normalized != label["txn_date"]:
                label["txn_date"] = normalized
                reasons.append("Normalized transaction date from DD/MM/YYYY to YYYY-MM-DD.")

        if label.get("txn_id") is not None:
            normalized = normalize_txn_id(label["txn_id"])
            if normalized != label["txn_id"]:
                label["txn_id"] = normalized
                reasons.append("Normalized NimbusPay transaction ID to uppercase NP plus 10 digits.")

        if label.get("category") in NON_TRANSACTION_CATEGORIES:
            for key in ("amount_paise", "txn_date", "txn_id", "channel"):
                if label.get(key) is not None:
                    label[key] = None
                    reasons.append(f"Cleared {key}; {label['category']} tickets have no transaction fields.")

        priority = expected_priority(label, ticket)
        if label.get("priority") != priority:
            label["priority"] = priority
            reasons.append("Corrected priority using the ordered rules in SCHEMA.md.")

        needs_human = expected_needs_human(priority, ticket)
        if label.get("needs_human") is not needs_human:
            label["needs_human"] = needs_human
            reasons.append("Corrected needs_human from P1 priority and explicit prior-contact wording.")

        ordered_label = {key: label.get(key) for key in (
            "category",
            "priority",
            "amount_paise",
            "txn_date",
            "txn_id",
            "channel",
            "language",
            "needs_human",
        )}
        new_row = dict(row)
        new_messages = list(messages)
        assistant_index = next(i for i, message in enumerate(messages) if message.get("role") == "assistant")
        new_messages[assistant_index] = dict(messages[assistant_index], content=json.dumps(ordered_label, ensure_ascii=False))
        new_row["messages"] = new_messages
        cleaned.append(new_row)
        if reasons:
            log.append((row_id, "fix", " ".join(reasons)))

    return cleaned, log, {"input_rows": len(rows), "kept_rows": len(cleaned), "dropped_rows": dropped, "logged_rows": len(log)}


def main():
    rows = [json.loads(line) for line in TRAIN_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    cleaned, log, stats = clean_rows(rows)
    with LOG_PATH.open("w", newline="", encoding="utf-8") as output:
        writer = csv.writer(output)
        writer.writerow(["id", "action", "reason"])
        writer.writerows(log)

    actions = Counter(action for _, action, _ in log)
    print(json.dumps({**stats, "actions": dict(actions)}, indent=2))

    remaining = []
    for row in cleaned:
        label = json.loads(row["messages"][-1]["content"])
        if set(label) != KEYS:
            remaining.append((row["id"], "key set"))
        if label["priority"] != expected_priority(label, row["messages"][1]["content"]):
            remaining.append((row["id"], "priority"))
        if label["needs_human"] is not expected_needs_human(label["priority"], row["messages"][1]["content"]):
            remaining.append((row["id"], "needs_human"))
        if label["txn_date"] is not None and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", label["txn_date"]):
            remaining.append((row["id"], "date"))
        if label["txn_id"] is not None and not re.fullmatch(r"NP\d{10}", label["txn_id"]):
            remaining.append((row["id"], "txn_id"))
    print(f"post-clean validation issues: {len(remaining)}")
    if remaining:
        print(remaining[:20])


if __name__ == "__main__":
    main()
