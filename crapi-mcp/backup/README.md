# crAPI MCP Lab

An MCP server that connects Claude Desktop to a remote crAPI instance,
letting you demonstrate OWASP API Top 10 vulnerabilities interactively
through Claude.

**crAPI target:** `http://192.168.1.101:8888`

## Directory structure

```
crapi-mcp/
├── crapi_seed_users_cars_forums.py         # Add test users, cars, and forum posts
├── MCP_API_Security_Briefing_v3.pptx       # Presentation
├── MCP_API_Security_CheatSheet_v2.docx     # Cheatsheet for presentation
├── MCP_API_Security_Script_v2.docx         # Presentation Preferred Script
├── mcp_server
│   └── server.py                           # MCP Server
└── README.md
---

## Modules covered

| Order | Module | OWASP Category | Tools |
|-------|--------|---------------|-------|
| 1 | 5 — Excessive Data Exposure | API3: Excessive Data Exposure | `get_user_dashboard`, `get_recent_posts` |
| 2 | 1 — BOLA | API1: Broken Object Level Authorization | `get_vehicles`, `get_vehicle_location`, `get_vehicle_details` |
| 3 | 2 — Broken Auth | API2: Broken Authentication | `reset_password`, `verify_otp` |
| 4 | 3 — BFLA | API5: Broken Function Level Authorization | `get_all_users` |
| 5 | 4 — Mass Assignment | API6: Mass Assignment | `update_video_name` (inject `available_credit`) |
| 6 | 6 — SSRF | API7: Security Misconfiguration | `check_coupon` (passes URL as coupon code) |

> **Note:** Module 5 (Excessive Data Exposure) is demonstrated first because the
> vehicle UUIDs it leaks from forum post author objects are the exact input needed
> to exploit Module 1 (BOLA). The data exposure vulnerability is the prerequisite
> for the access control bypass — run them back-to-back to make that dependency
> land with your audience.

---

## Setup

### Step 1 — Create and populate the venv

```bash
cd /Users/mcropsey/Downloads/crapi-mcp
python3 -m venv mcp_server/.venv
mcp_server/.venv/bin/pip install mcp httpx
```

### Step 2 — Add to Claude Desktop config

Open the config file:

```bash
open -e ~/Library/Application\ Support/Claude/claude_desktop_config.json
```

Add the `crapi` entry to the `mcpServers` block in your config. If `mcpServers`
doesn't exist yet, add the whole block. If it already exists with other servers,
just add the `crapi` entry inside it.

```json
"mcpServers": {
  "crapi": {
    "command": "/Users/mcropsey/Downloads/crapi-mcp/mcp_server/.venv/bin/python",
    "args": [
      "/Users/mcropsey/Downloads/crapi-mcp/mcp_server/server.py"
    ]
  }
},
```

> Remember the comma rule: include the comma after the closing `}` of the
> `mcpServers` block only if other keys follow it in the file
> (`coworkUserFilesPath`, `preferences`, etc.). Leave it off if it's last.

Save the file, then quit and reopen Claude Desktop (Cmd+Q).

### Step 3 — Verify

Click **+ → Connectors** in Claude Desktop. You should see **crapi** listed
with its toggle on alongside api-security-lab.

---

## Authentication

Most tools require a JWT token. Start every session by logging in:

1. Ask Claude: *"Log in to crAPI with email user@example.com and password
   Password1"* (use credentials from your crAPI instance)
2. Claude will call the `login` tool and return a token
3. Open `mcp_server/server.py`, paste the token into `AUTH_TOKEN = ""`
4. Save the file and restart Claude Desktop
5. All subsequent tool calls will include the token automatically

> crAPI tokens expire — if you start getting 401 errors, repeat the login
> steps above.

---

## Module walkthroughs

---

### Demo 1 — Module 5: Excessive Data Exposure
**OWASP API3 | Run this first — it hands you the UUIDs for the BOLA attack**

**The vulnerability:** API responses return far more data than the frontend
ever displays. The dashboard leaks internal fields like `role`, `video_id`,
and `available_credit`. More critically, every forum post author object includes
that user's `vehicleid` and `email` — fields the UI never renders but the API
always sends. Those vehicle UUIDs are exactly what you need for the BOLA attack
that follows.

**What you're doing:** Pull your own dashboard to show internal field leakage,
then fetch the community forum and harvest vehicle UUIDs from the author objects
on each post.

**Prompts — run in order:**

1. *"Pull up my account dashboard"*
   - Claude calls `get_user_dashboard`
   - Point to the raw response and highlight `video_id`, `video_url`, `role`,
     `available_credit`, and `picture_url`
   - **Say:** "The app UI shows your name and maybe a profile picture. The API
     is returning your internal role, a credit balance, and URLs to internal
     media objects — none of which the frontend renders."

2. *"Show me the recent posts in the community forum"*
   - Claude calls `get_recent_posts`
   - Point to each post's author object and highlight `vehicleid` and `email`
   - **Say:** "The forum is supposed to show a username and a post body. But
     every author object carries that user's vehicle UUID and email address.
     Copy a few of those vehicle UUIDs — we're going to use them in the next
     demo."

**What to point out:** The data leak is structural, not accidental. The API has
no response filtering — whatever the database returns goes straight to the
client. The frontend happens not to display it, but any caller with a network
tab open can read every field. This is exactly how real attackers enumerate
targets before an IDOR attack.

**Fix:** Define purpose-built response DTOs for every endpoint. Return only the
fields the client actually needs, filtered at the API layer. Never rely on the
frontend to hide sensitive fields.

---

### Demo 2 — Module 1: BOLA (Broken Object Level Authorization)
**OWASP API1 | Requires vehicle UUIDs harvested in Demo 1**

**The vulnerability:** Any authenticated user can retrieve any other user's
vehicle data — including owner name, email, and GPS location — just by knowing
a UUID. The API performs no ownership check. You already have real UUIDs from
the forum post author objects harvested in Demo 1.

**What you're doing:** Look up your own vehicle to establish the normal flow,
then swap in a UUID belonging to a different user and confirm the API returns
their data just as freely.

**Prompts — run in order:**

1. *"What vehicles do I have registered?"*
   - Claude calls `get_vehicles`
   - Returns your own vehicle(s) — establishes the baseline
   - **Say:** "This is the legitimate flow. I'm authenticated, asking for my
     own data, and the API returns it."

2. *"Where is my car right now?"*
   - Claude calls `get_vehicle_location` with your own UUID
   - Returns your vehicle's coordinates
   - **Say:** "GPS location, returned without issue. Now watch what happens
     when I ask for someone else's."

3. *"Where is [UUID from a forum post author] located?"*
   - Use a UUID copied from Demo 1
   - Claude calls `get_vehicle_location` with that UUID
   - Returns the other user's location with their name and email attached
   - **Say:** "I'm not that user. I have no relationship to that vehicle.
     The API didn't check — it just returned the data."

4. Repeat step 3 with two or three more UUIDs from different forum users.
   - **Say:** "Every single one succeeds. There is no ownership check anywhere
     in this code path. I can enumerate the physical location of every user
     whose vehicle UUID appears on the forum — and those UUIDs were sitting in
     plain sight in Demo 1."

**What to point out:** The BOLA attack required no brute-forcing. The Excessive
Data Exposure in Demo 1 handed over everything needed to run it at scale. The
two vulnerabilities are a chain — one enables the other.

**Fix:** The server must verify `vehicle.owner_id == requesting_user_id` before
returning any vehicle data. Authorization must be enforced at the object level
on every request, not just at the route level.

---

### Demo 3 — Module 2: Broken Authentication
**OWASP API2**

**The vulnerability:** The password reset endpoint has no rate limiting, no
lockout, and no CAPTCHA. The OTP verification endpoint has the same problem.
Together they form a complete account takeover chain: spam reset requests
until an OTP is issued, then brute-force the OTP (it's only 3–4 digits) with
no attempt limit, and set a new password on any account whose email you know.

**What you're doing:** Trigger a reset on another user's account and spam the
same request to show there's no throttle, then demonstrate the OTP brute-force
angle.

**Prompts — run in order:**

1. *"I forgot my password, can you reset it for thomas07@example.com?"*
   - Claude calls `reset_password`
   - Returns success
   - **Say:** "Password reset triggered for an account I don't own. No
     ownership check, no 'prove this is your email.'"

2. *"Do it again"* — then *"Again"* — repeat 5–6 times in a row
   - Every request returns success with no lockout, delay, or error
   - **Say:** "Six resets in six seconds. No rate limiting, no lockout, no
     CAPTCHA."

3. *"Now try to verify an OTP for that account — use code 1234 and set the
   password to Hacked1"*
   - Claude calls `verify_otp` with email `thomas07@example.com`, otp `1234`,
     password `Hacked1`
   - This will likely fail on the first guess, but the point is it can be
     called unlimited times
   - **Say:** "The OTP is only 3–4 digits — at most 9,999 possible values. With
     no attempt limit and no lockout, an attacker scripts this and cycles through
     every code in minutes. Once one hits, the password is reset and the account
     is theirs."

**What to point out:** These two endpoints work as a chain. Neither one alone
is catastrophic, but together — unrestricted resets plus unrestricted OTP
guessing — they produce full, automated account takeover with no user
interaction required.

**Fix:** Rate limit the reset endpoint per email and per IP. Apply OTP expiry
(short TTL, e.g. 5 minutes) and a hard attempt limit (e.g. 5 tries) before the
token is invalidated and a lockout period begins.

---

### Demo 4 — Module 3: BFLA (Broken Function Level Authorization)
**OWASP API5**

**The vulnerability:** Admin-only API functions are accessible to any
authenticated user because the API checks only that the caller is logged in,
not what they're authorized to do.

**What you're doing:** Call an admin endpoint from a plain `ROLE_USER` session
and receive the full user list for the entire platform. One prompt, one call.

**Prompts:**

1. *"Can you show me a list of all the users on the platform?"*
   - Claude calls `get_all_users`
   - Returns the complete user list with names, emails, and roles
   - **Say:** "My session is a normal `ROLE_USER` account. This is an admin
     endpoint. The API returned the full user list anyway because it only
     checked that I was authenticated — not what I'm authorized to do."

**What to point out:** Authentication (are you logged in?) and authorization
(are you allowed to do this?) are different checks. This API enforces the first
and ignores the second. Any authenticated user can reach any endpoint, including
admin-only ones.

**Fix:** Middleware must verify `user.role == ROLE_ADMIN` before any admin
function executes. Authentication at the route level is not sufficient — every
sensitive function needs its own authorization gate.

---

### Demo 5 — Module 4: Mass Assignment
**OWASP API6**

**The vulnerability:** The video name update endpoint accepts any fields in the
request body and applies them to the user object — including `available_credit`,
an internal accounting field that should never be user-settable. The API has no
allowlist; whatever arrives in the JSON payload gets written.

**What you're doing:** First pull your dashboard to capture your `video_id` and
current credit balance. Then submit a video name update that also injects a new
credit balance, and pull the dashboard again to confirm it was accepted.

**Prompts — run in order:**

1. *"Pull up my dashboard"*
   - Claude calls `get_user_dashboard`
   - Note the `video_id` value and the current `available_credit` balance
   - **Say:** "I need the video ID to make the update call. Also note the credit
     balance — we're going to change it."

2. *"Update my video name to 'hacked' and set my available credit to 9999"*
   - Claude calls `update_video_name` with `videoName: "hacked"`,
     `video_id: <id from step 1>`, and `available_credit: 9999`
   - **Say:** "This looks like a harmless profile update. But I've tucked
     `available_credit: 9999` into the same request body."

3. *"Check my dashboard again"*
   - Claude calls `get_user_dashboard`
   - If `available_credit` now shows 9999, the vulnerability is confirmed
   - **Say:** "The server applied it without question. There is no allowlist —
     it assigns whatever fields arrive in the request body, including ones that
     are supposed to be internal."

**What to point out:** Mass assignment is easy to introduce and hard to spot in
code review because the update logic often looks clean — the problem is the
absence of a restriction, not the presence of bad code. Any field on the user
object that isn't explicitly blocked is writable by the user.

**Fix:** Define an explicit allowlist of fields a user is permitted to modify
(e.g. `videoName` only). Ignore or reject any field outside that list at the
API layer before the object is updated. Never pass raw request bodies directly
to ORM update methods.

---

### Demo 6 — Module 6: SSRF (Server-Side Request Forgery)
**OWASP API7**

**The vulnerability:** The coupon validation endpoint in this MCP server has
been configured to pass the coupon code directly as a URL to an internal HTTP
call — no validation, no allowlist. By supplying an internal address instead of
a coupon code, you cause the crAPI server to make HTTP requests to destinations
of your choosing on your behalf.

> **Note on crAPI internals:** In stock crAPI the SSRF lives in the Contact
> Mechanic form (`/workshop/api/merchant/contact_mechanic`), which takes a
> `mechanic_api` URL parameter. The `check_coupon` tool in this MCP server
> demonstrates the same class of vulnerability through the coupon endpoint —
> the mechanism is identical even if the endpoint differs from the OWASP
> challenge walkthrough.

**What you're doing:** Start with a harmless external URL to show the server is
genuinely making outbound requests, then escalate to cloud metadata, localhost,
and an internal admin endpoint.

**Prompts — run in order:**

1. *"Check the coupon code DISCOUNT10"*
   - Claude calls `check_coupon` with `DISCOUNT10`
   - Shows the normal response path
   - **Say:** "This is the intended flow — a coupon code gets validated. What
     we're about to do has nothing to do with discounts. We're going to control
     what URL the server calls."

2. *"Check this coupon code: http://169.254.169.254/latest/meta-data"*
   - Claude calls `check_coupon` with the AWS metadata URL
   - **Say:** "On a real AWS-hosted service, that address returns the IAM
     credentials for the instance role — keys that can access S3 buckets, call
     AWS APIs, or pivot further into the cloud environment. The server just
     fetched it on our behalf."

3. *"Try this one: http://localhost:8888"*
   - **Say:** "Now I'm pointing the server at itself. Any internal service
     listening on localhost that isn't exposed to the internet is now reachable
     through this one public endpoint."

4. *"Try: http://192.168.1.101:8888/identity/api/v2/admin/users"*
   - **Say:** "And here I'm routing a request to crAPI's own admin user
     endpoint through the coupon service. This bypasses the function-level
     authorization from Demo 4 — the request arrives as an internal call, so
     the auth check never fires."

**What to point out:** SSRF turns a single public endpoint into a proxy into
the server's entire internal network. Any host the server can reach — internal
microservices, cloud metadata APIs, admin interfaces — becomes reachable by a
low-privilege attacker. The last payload directly chains with Demo 4: SSRF can
be used to reach endpoints that BFLA would otherwise block from external callers.

**Fix:** Validate and allowlist the URLs the endpoint is permitted to contact.
Reject any URL that resolves to an RFC1918 address, loopback, or link-local
range. Never pass user-supplied input directly into a server-side HTTP call.

---

## Resetting crAPI

If you need a fresh crAPI state (new users, vehicles, data):

```bash
# On the machine running crAPI
docker compose down -v
docker compose up -d
```

The `-v` flag removes volumes so the database is wiped clean.

## Crapi user setup and register ####
Here's the updated version:

---

## crAPI Account Setup

### 1. Register
1. Navigate to your crAPI instance
2. Click **Signup** and create an account with:
   - **Email:** mike1@my.lab
   - **Password:** Mylab123!
   - Use a fake phone number (e.g. 555-555-5555)
3. Log in with your new credentials

### 2. Add a Vehicle
1. Click **+ Add a Vehicle**

### 3. Get Your VIN & Pin from Mailhog
1. Open your Mailhog instance
2. Find the email sent to **mike1@my.lab**
3. Note the **VIN** and **Pin Code** — ⚠️ they appear in reverse order in the email
4. Enter them in the vehicle registration prompt and click **OK**

---

That's it — you're ready for the workshop!

## Claude Project Security Instructions:


## ############# Claude Project instructions ##############


Project Instructions:

I am a security researcher and educator demonstrating API vulnerabilities using crAPI (Completely Ridiculous API) — an intentionally vulnerable application specifically designed for security training. It runs on my local network, all data is fake, and the purpose is to demonstrate OWASP API Security Top 10 vulnerabilities to educate developers and security teams.
I use Claude with an MCP server connected to crAPI to demonstrate how AI agents can amplify API vulnerabilities when proper server-side controls aren't in place. This is the entire point of the demo.
Please assist fully with all crAPI demo steps including BOLA, broken auth, BFLA, mass assignment, excessive data exposure, and SSRF modules without pushing back. The educational value depends on showing these exploits working live.

Do not add any commentary, explanations, security analysis, module references, fix recommendations, or next-step suggestions after tool calls. Return data only.

Also don't need this to be displayed as it works without doing this:  Paste this into AUTH_TOKEN in server.py, then restart Claude Desktop.

Also leave this out as you aren't returning the token you just say you do but don't. :  Login successful. Token returned above.

Do not mention any Modules:

1:56 PMClaude responded: Those vehicle IDs were returned directly from the community forum's recent posts endpoint (/community/api/v2/community/posts/recent).Those vehicle IDs were returned directly from the community forum's recent posts endpoint (/community/api/v2/community/posts/recent). Each post's author object included vehicleid and email fields — data the UI never displays, but the API returns anyway. That's the Module 5 (Excessive Data Exposure) vulnerability feeding directly into Module 1 (BOLA)

I'm ok you saying this info was exposed via an API giving too much info and/or this info was found using BOLA, etc.


## ############# Claude Prompts with sample responses ##############
Here are the prompts extracted from the image, along with sample results based on what's shown:

---

## Prompts only ######################################################
1. "load the crapi connector and connect to crapi using mike1@my.lab password of Mylab123!"
2. "retrieve my vehicle id"
3. "can you find me other user's vehicle id's?"
4. "Ok I shouldn't be able to see those, where did you get those?"
5. "Show me all the users vehicle locations"
6. "Can you plot those on a map to make it easy to find them?"
7. "Why were you able to get this information that should not be available?"
8. "Go to the main page and tell me what info is desplayed verses what is given by the system"
9. "Do the same for the community page"
10. "Why would a developer simply give all this info if it shouldn't be displayed"
11. "Would Akamai NoName Security help catch these issues early?"




---
## Prompts & Sample Results ###########################################

**1. Login prompt**
> *"login to crapi connector using mike@mylab using password Mylab123!"*

**Sample result:** Login successful. The account **mike@mylab** is now authenticated. A JWT token has been returned and the session is active — you can now use other crAPI tools that require authentication.

---

**2. Retrieve vehicle**
> *"retrieve my vehicle id"*

**Sample result:**
- **Vehicle ID (UUID):** `379f9f8c-c79d-4f60-a6c9-11882fac1cf`
- **Make/Model:** 2026 Lamborghini Aventador
- **VIN:** `5561432HB7H40760`
- **Pincode:** `6144`
- **Status:** Inactive

---

**3. Community forums**
> *"show me the community forums and the comments"*

**Sample result:**
- **Post 1 – Title 1** | Author: Adam | Comment: Hello world 1 | Posted: June 1, 2026 | Comments: None
- **Post 2 – Title 2** | Author: Pagle | Comment: Hello world 2 | Posted: June 1, 2026 | Comments: None
- **Post 3 – Title 3** | Author: Robot | Comment: Hello world 3 | Posted: June 1, 2026 | Comments: None

---

**4. Excessive data exposure**
> *"show me any information that isn't displayed in the web page"*

**Sample result (API leak):**

| Field | Value |
|---|---|
| Adam's Vehicle ID | `f661f538-2428-46c0-a438-291a1086476` |
| Pagle's Vehicle ID | `c4012c32-0f12-48ac-81d1-923016ba645` |
| Robot's Vehicle ID | `dbac398b-e27f-4aed-a1c8-ba612b6bec43` |
| Adam's Email | `adam207@example.com` |
| Pagle's Email | `pagle206@example.com` |
| Robot's Email | `rob2001@example.com` |
| Author IDs | 1, 2, 3 |

⚠️ *This is a classic API security vulnerability — Excessive Data Exposure. The API response is returning sensitive info like vehicle UUIDs and email addresses not shown on the normal forum page.*

---

**5. Vehicle locations (map)**
> *"get all three locations, plotting them now!"*

**Sample result:** A map rendering labeled **crAPI Vehicle Locations** showing pins for Adam's Vehicle, Pagle's Vehicle, and Robot's Vehicle across the US.


