# Running OrionLead AI on your own machine (no dependency on the developer's computer)

This runs the backend + web app entirely on your machine. The included mobile app
also has a **Server Settings** option on the login screen, so once you have the
backend running on your own computer (steps below), you can point the already-installed
APK at it directly — no rebuild needed. See "Using the mobile app on your own network" below.

## Prerequisites

- **Python 3.10 or 3.11** — https://www.python.org/downloads/
- **MySQL Server 8.x** — https://dev.mysql.com/downloads/mysql/ (remember the root password you set)
- **Node.js 18+** — https://nodejs.org/ (only needed if you also want the web UI, not just the API)

## 1. Create the database

Open a MySQL client (MySQL Workbench, or the `mysql` command line) and run:

```sql
CREATE DATABASE ai_lead_db;
```

## 2. Set up the backend

```bash
cd backend
python -m venv venv
venv\Scripts\activate          # on Windows
# source venv/bin/activate     # on macOS/Linux

pip install -r requirements.txt
```

## 3. Configure environment variables

```bash
cd ..
copy .env.example .env         # Windows
# cp .env.example .env         # macOS/Linux
```

Open `.env` and set at minimum:

```
DATABASE_URL=mysql+pymysql://root:YOUR_MYSQL_PASSWORD@localhost:3306/ai_lead_db
```

Everything else in `.env` (Gemini/Groq keys, Supabase, email, social APIs, etc.) is
**optional** — the app runs fine without them, just with AI scoring falling back to
rule-based logic and cloud sync disabled. `SECRET_KEY`/`JWT_SECRET_KEY` already have
safe development defaults, so you only strictly need `DATABASE_URL` to get the server
running.

## 4. Run the backend

```bash
cd backend
python run.py
```

The database tables are created automatically on first run. You should see the server
come up on `http://localhost:5000`. Leave this terminal running.

Verify it's alive by opening `http://localhost:5000/api/v1/ai/health` in a browser —
you should get a JSON response.

## 5. (Optional) Run the web app against it

In a **new** terminal:

```bash
cd web
npm install
npm start
```

This opens `http://localhost:3000` in your browser and automatically talks to the
backend on `localhost:5000` — no extra configuration needed. Register a new account
or log in to use the full system (leads, AI engine, analytics, admin panel).

## Using the mobile app on your own network

The provided `.apk` defaults to the developer's Wi-Fi IP address, but you don't need
a rebuild to change that. Once your backend is running (step 4 above):

1. Find your computer's LAN IP: `ipconfig` (Windows) → look for "IPv4 Address" under
   your active Wi-Fi/Ethernet adapter (e.g. `192.168.1.10`).
2. Install `mobile-app-apk/OrionLead-AI.apk` on your Android phone.
3. Open the app → on the login screen, tap **"Server Settings"** at the bottom.
4. Enter `http://YOUR_COMPUTER_LAN_IP:5000`, tap **Test Connection** to confirm it
   reaches your backend, then **Save**.
5. Make sure your phone is on the **same Wi-Fi network** as your computer, then log in.

This works entirely on your own network — no dependency on the developer's laptop.
The setting is remembered, so you only need to do this once.

If you'd rather not use the phone/network setup at all, the web app (step 5 above) is
the simplest way to try the full system on one machine.
