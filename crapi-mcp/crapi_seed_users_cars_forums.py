#!/usr/bin/env python3
"""
crAPI Auto-Enroll Script
Registers users mike1-mike9, grabs VIN/PIN from MailHog,
adds vehicle, and creates a forum post for each user.
"""

import requests
import time
import re
import quopri

# ── Config ────────────────────────────────────────────────────────────────────
CRAPI_BASE   = "http://192.168.1.101:8888"
MAILHOG_BASE = "http://192.168.1.101:8025"
PASSWORD     = "Mylab123!"

USERS = [
    {"name": f"Mike Williams{i}",
     "email": f"mike{i}@my.lab",
     "phone": f"{i}{i}{i}-{i}{i}{i}-{i}{i}{i}{i}"}
    for i in range(1, 10)
]
# ─────────────────────────────────────────────────────────────────────────────


def banner(msg):
    print(f"\n{'='*60}\n  {msg}\n{'='*60}")


def decode_body(raw_data):
    """Decode quoted-printable email and strip HTML tags."""
    try:
        decoded = quopri.decodestring(raw_data.encode()).decode("utf-8", errors="replace")
    except Exception:
        decoded = raw_data
    plain = re.sub(r'<[^>]+>', ' ', decoded)
    plain = re.sub(r'\s+', ' ', plain).strip()
    return plain


def register(user):
    r = requests.post(
        f"{CRAPI_BASE}/identity/api/auth/signup",
        json={
            "name":     user["name"],
            "email":    user["email"],
            "number":   user["phone"],
            "password": PASSWORD
        }
    )
    print(f"  Register → {r.status_code}: {r.text.strip()}")
    return r.status_code in (200, 201)


def get_vin_and_pin(email, retries=15, delay=4):
    for attempt in range(1, retries + 1):
        print(f"  MailHog attempt {attempt}/{retries}...")
        try:
            r = requests.get(f"{MAILHOG_BASE}/api/v1/messages", timeout=5)
            r.raise_for_status()
        except requests.RequestException as e:
            print(f"  MailHog error: {e}")
            time.sleep(delay)
            continue

        for msg in (r.json() or []):
            if not isinstance(msg, dict):
                continue
            raw     = msg.get("Raw") or {}
            to_raw  = " ".join(raw.get("To") or [])
            content = msg.get("Content") or {}
            to_hdr  = " ".join((content.get("Headers") or {}).get("To") or [])
            if email.lower() not in (to_raw + " " + to_hdr).lower():
                continue
            plain = decode_body(raw.get("Data") or "")
            vin_match = re.search(r'VIN:\s*([A-HJ-NPR-Z0-9]{17})', plain, re.IGNORECASE)
            pin_match = re.search(r'Pincode:\s*(\d+)', plain, re.IGNORECASE)
            if vin_match and pin_match:
                vin = vin_match.group(1)
                pin = pin_match.group(1)
                print(f"  ✅ VIN: {vin}  PIN: {pin}")
                return vin, pin
            print(f"  Found email but could not parse VIN/PIN: {plain[:200]}")

        print(f"  Email not found yet — waiting {delay}s...")
        time.sleep(delay)

    print(f"  ❌ Could not find VIN/PIN for {email}")
    return None, None


def login(email):
    r = requests.post(
        f"{CRAPI_BASE}/identity/api/auth/login",
        json={"email": email, "password": PASSWORD}
    )
    print(f"  Login → {r.status_code}")
    if r.status_code != 200:
        print(f"  ❌ Login failed: {r.text}")
        return None
    token = r.json().get("token")
    if not token:
        print(f"  ❌ No token in response")
        return None
    return token


def add_vehicle(token, vin, pin):
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    for pin_val in [pin, int(pin)]:
        r = requests.post(
            f"{CRAPI_BASE}/identity/api/v2/vehicle/add_vehicle",
            json={"vin": vin, "pincode": pin_val},
            headers=headers, timeout=10
        )
        print(f"  Add vehicle → {r.status_code}: {r.text.strip()}")
        if r.status_code in (200, 201):
            print(f"  ✅ Vehicle added!")
            return True
    print(f"  ❌ Failed to add vehicle")
    return False


def create_post(token, name):
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {
        "title":   f"Sample Post from {name}",
        "content": f"Sample post from {name}"
    }
    r = requests.post(
        f"{CRAPI_BASE}/community/api/v2/community/posts",
        json=payload, headers=headers, timeout=10
    )
    print(f"  Create post → {r.status_code}: {r.text.strip()}")
    if r.status_code in (200, 201):
        print(f"  ✅ Post created!")
        return True
    print(f"  ❌ Failed to create post")
    return False


def main():
    banner("crAPI Bulk Enroll — mike1 through mike9")
    print(f"Target:  {CRAPI_BASE}")
    print(f"MailHog: {MAILHOG_BASE}")

    results = []

    for user in USERS:
        banner(f"Processing {user['email']}")
        print(f"  Name:  {user['name']}")
        print(f"  Phone: {user['phone']}")

        if not register(user):
            results.append({**user, "vin": "N/A", "pin": "N/A", "post": "❌", "status": "❌ FAILED - registration"})
            continue

        print("  Waiting 3s for welcome email...")
        time.sleep(3)

        vin, pin = get_vin_and_pin(user["email"])
        if not vin:
            results.append({**user, "vin": "N/A", "pin": "N/A", "post": "❌", "status": "❌ FAILED - no VIN/PIN"})
            continue

        token = login(user["email"])
        if not token:
            results.append({**user, "vin": vin, "pin": pin, "post": "❌", "status": "❌ FAILED - login"})
            continue

        vehicle_ok = add_vehicle(token, vin, pin)
        post_ok    = create_post(token, user["name"])

        results.append({
            **user,
            "vin":    vin,
            "pin":    pin,
            "post":   "✅" if post_ok else "❌",
            "status": "✅ SUCCESS" if (vehicle_ok and post_ok) else "⚠️  PARTIAL"
        })

        time.sleep(2)

    banner("Summary")
    print(f"{'Email':<20} {'Name':<20} {'Phone':<15} {'VIN':<20} {'PIN':<6} {'Post':<6} Status")
    print("-" * 110)
    for r in results:
        print(f"{r['email']:<20} {r['name']:<20} {r['phone']:<15} {r['vin']:<20} {r['pin']:<6} {r['post']:<6} {r['status']}")


if __name__ == "__main__":
    main()
