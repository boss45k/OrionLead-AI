# OrionLead AI — Mobile App (Expo + Supabase)

## Setup

### 1. Install dependencies
```bash
cd mobile
npm install
```

### 2. Configure Supabase
Edit `src/config/supabase.js` and replace:
```js
export const SUPABASE_URL = 'YOUR_SUPABASE_URL';
export const SUPABASE_ANON_KEY = 'YOUR_SUPABASE_ANON_KEY';
```
Get these from: https://supabase.com/dashboard → Project Settings → API

### 3. Set up Supabase database
Run the SQL in `supabase/schema.sql` in your Supabase SQL Editor.

### 4. Configure backend URL
Edit `src/services/api.js`:
```js
export const API_BASE_URL = 'http://YOUR_BACKEND_IP:5000';
```
> Use your machine's local IP (not localhost) for physical device testing.

### 5. Configure backend Supabase sync (optional)
Add to your backend `.env`:
```
SUPABASE_URL=your_supabase_url
SUPABASE_SERVICE_KEY=your_service_role_key
```

### 6. Run the app
```bash
npm start          # Expo dev server
npm run android    # Android emulator
npm run ios        # iOS simulator
```

## Build for Play Store
```bash
npm install -g eas-cli
eas login
eas build --platform android
```

## Architecture

```
Mobile App (Expo)
     │
     ├── Flask Backend (same as web)
     │     ├── /api/v1/auth      → Login, Register, Google OAuth
     │     ├── /api/v1/leads     → CRUD, Search, AI Qualify
     │     ├── /api/v1/ai        → Collection, Training
     │     ├── /api/v1/analytics → Charts data
     │     └── /api/v1/sync      → User/Lead sync endpoint
     │
     └── Supabase (secondary DB)
           ├── users_sync        → Mirror of Flask users
           ├── leads_cache       → Mirror of Flask leads (real-time)
           └── sync_log          → Sync operation history
```

## Sync Layer

| Event | What happens |
|-------|-------------|
| User logs in | Flask JWT issued → user pushed to `users_sync` in Supabase |
| Leads loaded | Latest leads synced to `leads_cache` in background |
| Lead created/updated | Single lead pushed to Supabase immediately |
| Manual sync (Settings) | Full leads sync from Flask → Supabase |
| Real-time | Supabase subscriptions push changes to all connected devices |
