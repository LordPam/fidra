# Fidra Cloud Server Setup Guide

This guide explains how to set up a Supabase cloud backend for Fidra, enabling multi-user access and cloud-hosted data storage.

## Overview

Fidra supports two storage backends:
- **SQLite** (default): Local file storage, single-user
- **Cloud (Supabase)**: PostgreSQL database with cloud storage for attachments, multi-user support

---

## Part 1: Supabase Project Setup

### 1.1 Create a Supabase Project

1. Go to [supabase.com](https://supabase.com) and sign in
2. Click **New Project**
3. Enter a project name (e.g., "Fidra Finance")
4. Set a **database password** - save this, you'll need it later
5. Select a region close to your users
6. Click **Create new project**

Wait for the project to be provisioned (usually 1-2 minutes).

---

## Part 2: Database Schema

### 2.1 Create the Database Tables

1. In your Supabase dashboard, go to **SQL Editor**
2. Click **New query**
3. Paste the following SQL and click **Run**:

```sql
-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Transactions table
CREATE TABLE transactions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    date DATE NOT NULL,
    description TEXT NOT NULL,
    amount NUMERIC(15, 2) NOT NULL CHECK (amount > 0),
    type TEXT NOT NULL CHECK (type IN ('income', 'expense')),
    status TEXT NOT NULL CHECK (status IN ('--', 'pending', 'approved', 'rejected', 'planned')),
    sheet TEXT NOT NULL,
    category TEXT,
    party TEXT,
    notes TEXT,
    reference TEXT,
    activity TEXT,
    version INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    modified_at TIMESTAMPTZ,
    modified_by TEXT
);

CREATE INDEX idx_transactions_date ON transactions(date DESC);
CREATE INDEX idx_transactions_sheet ON transactions(sheet);
CREATE INDEX idx_transactions_type ON transactions(type);
CREATE INDEX idx_transactions_status ON transactions(status);

-- Planned templates table
CREATE TABLE planned_templates (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    start_date DATE NOT NULL,
    description TEXT NOT NULL,
    amount NUMERIC(15, 2) NOT NULL CHECK (amount > 0),
    type TEXT NOT NULL CHECK (type IN ('income', 'expense')),
    frequency TEXT NOT NULL CHECK (frequency IN ('once', 'weekly', 'biweekly', 'monthly', 'quarterly', 'yearly')),
    target_sheet TEXT NOT NULL,
    category TEXT,
    party TEXT,
    activity TEXT,
    end_date DATE,
    occurrence_count INTEGER,
    skipped_dates JSONB DEFAULT '[]'::jsonb,
    fulfilled_dates JSONB DEFAULT '[]'::jsonb,
    version INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_planned_start ON planned_templates(start_date);
CREATE INDEX idx_planned_target ON planned_templates(target_sheet);

-- Sheets table
CREATE TABLE sheets (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name TEXT UNIQUE NOT NULL,
    is_virtual BOOLEAN DEFAULT FALSE,
    is_planned BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_sheets_name ON sheets(name);

-- Attachments table (metadata only - files stored in Supabase Storage)
CREATE TABLE attachments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    transaction_id UUID NOT NULL REFERENCES transactions(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    stored_name TEXT NOT NULL,
    mime_type TEXT,
    file_size BIGINT DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_attachments_transaction ON attachments(transaction_id);

-- Audit log table
CREATE TABLE audit_log (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    action TEXT NOT NULL CHECK (action IN ('create', 'update', 'delete')),
    entity_type TEXT NOT NULL,
    entity_id UUID NOT NULL,
    "user" TEXT NOT NULL,
    summary TEXT NOT NULL,
    details TEXT
);

CREATE INDEX idx_audit_timestamp ON audit_log(timestamp DESC);
CREATE INDEX idx_audit_entity ON audit_log(entity_type, entity_id);

-- Categories table
CREATE TABLE categories (
    id SERIAL PRIMARY KEY,
    type TEXT NOT NULL CHECK (type IN ('income', 'expense')),
    name TEXT NOT NULL,
    sort_order INTEGER DEFAULT 0,
    UNIQUE(type, name)
);

CREATE INDEX idx_categories_type ON categories(type);

-- Row Level Security (enable for multi-user)
ALTER TABLE transactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE planned_templates ENABLE ROW LEVEL SECURITY;
ALTER TABLE sheets ENABLE ROW LEVEL SECURITY;
ALTER TABLE attachments ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE categories ENABLE ROW LEVEL SECURITY;

-- Policies: Allow all authenticated users full access
-- (Adjust these if you need more granular permissions)
CREATE POLICY "Full access" ON transactions FOR ALL USING (true);
CREATE POLICY "Full access" ON planned_templates FOR ALL USING (true);
CREATE POLICY "Full access" ON sheets FOR ALL USING (true);
CREATE POLICY "Full access" ON attachments FOR ALL USING (true);
CREATE POLICY "Full access" ON audit_log FOR ALL USING (true);
CREATE POLICY "Full access" ON categories FOR ALL USING (true);
```

---

## Part 3: Storage Bucket Setup

Fidra stores receipt attachments in Supabase Storage.

### 3.1 Create the Attachments Bucket

1. In your Supabase dashboard, go to **Storage** (left sidebar)
2. Click **New bucket**
3. Enter the name: `attachments`
4. Leave "Public bucket" **unchecked** (private bucket)
5. Click **Create bucket**

### 3.2 Configure Bucket Policies

The bucket needs policies to allow uploads, downloads, and deletes.

1. Click on the **attachments** bucket
2. Go to the **Policies** tab
3. Create three policies:

#### Policy 1: Allow Uploads (INSERT)

1. Click **New policy**
2. Select **For full customization**
3. Fill in:
   - **Policy name**: `Allow uploads`
   - **Allowed operation**: `INSERT`
   - **Target roles**: `anon`
   - **Policy definition**: `true`
4. Click **Review** then **Save policy**

#### Policy 2: Allow Downloads (SELECT)

1. Click **New policy**
2. Select **For full customization**
3. Fill in:
   - **Policy name**: `Allow downloads`
   - **Allowed operation**: `SELECT`
   - **Target roles**: `anon`
   - **Policy definition**: `true`
4. Click **Review** then **Save policy**

#### Policy 3: Allow Deletes (DELETE)

1. Click **New policy**
2. Select **For full customization**
3. Fill in:
   - **Policy name**: `Allow deletes`
   - **Allowed operation**: `DELETE`
   - **Target roles**: `anon`
   - **Policy definition**: `true`
4. Click **Review** then **Save policy**

> **Note**: When creating the DELETE policy, Supabase may require you to also select SELECT. This is fine - it will create two policies under the same name.

Your final policies should look like:
```sql
CREATE POLICY "Allow uploads" ON storage.objects FOR INSERT TO anon WITH CHECK (true);
CREATE POLICY "Allow downloads" ON storage.objects FOR SELECT TO anon USING (true);
CREATE POLICY "Allow deletes" ON storage.objects FOR DELETE TO anon USING (true);
```

---

## Part 4: Connecting Fidra to Supabase

### 4.1 Gather Connection Details

You'll need three pieces of information from Supabase:

#### Database Connection String

1. In Supabase dashboard, click the **Connect** button (top navigation bar)
2. Go to the **Connection string** tab
3. Set the following options:
   - **Type**: `URI`
   - **Source**: `Primary Database`
   - **Method**: `Transaction Pooler`
4. Copy the connection string
5. Replace `[YOUR-PASSWORD]` with your **database password** (the one you set when creating the project)

The connection string looks like:
```
postgresql://postgres.xxxxxxxxxxxx:[YOUR-PASSWORD]@aws-0-xx-xxxx.pooler.supabase.com:6543/postgres
```

#### Project URL and API Key

1. Go to **Project Settings** (gear icon, bottom of left sidebar)
2. Click **API** in the settings menu
3. Copy:
   - **Project URL**: e.g., `https://xxxxxxxxxxxx.supabase.co`
   - **anon public** key (under "Project API keys")

### 4.2 Configure in Fidra

#### First-Time Setup (Setup Wizard)

1. Launch Fidra
2. On the database selection screen, click **Configure Server...**
3. Fill in:
   - **Server Name**: A friendly name (e.g., "Club Finances")
   - **Project URL**: Paste the Project URL from Supabase
   - **Anon Key**: Paste the anon public key
   - **Database Connection String**: Paste the connection string (with password filled in)
4. Click **Test Connection** to verify
5. Click **Save**

#### Adding a Server Later (Returning Users)

1. Launch Fidra
2. On the welcome screen, click **Connect to Different Server...**
3. Click **+ Configure New Server...**
4. Fill in the same details as above
5. Click **Test Connection** then **Save**

#### From Within the App

1. Go to **Settings menu** (gear icon)
2. Click **Cloud Servers...**
3. Click **Add Server**
4. Fill in the connection details
5. Click **Test Connection** then **Save**
6. Select the server and click **Connect**

---

## Part 5: How Sync Works

Once connected, Fidra uses an offline-first architecture:

### Local Cache
All data is cached locally in a SQLite database (`cloud_cache.db`). Reads always come from the local cache for instant response, even when offline.

### Pushing Changes (Local to Cloud)
When you create, edit, or delete a transaction, the change is:
1. Applied to the local cache immediately
2. Queued in a persistent sync queue (survives app restarts)
3. Pushed to PostgreSQL in the background within ~1 second

If the network is down, changes accumulate in the queue and sync automatically when connectivity returns.

### Receiving Changes (Cloud to Local)
Fidra installs PostgreSQL LISTEN/NOTIFY triggers on the synced tables. When another device makes changes, Fidra receives a notification within seconds, refreshes the affected caches, and updates the UI.

The triggers are installed automatically on first connection (idempotent, safe to run repeatedly).

### Connection Recovery
- **Health checks** run every 30 seconds when connected
- If the connection is lost, Fidra attempts reconnection with exponential backoff (up to 5 attempts)
- Once offline, recovery checks run every 5 seconds
- When network returns, the app reconnects automatically (no restart needed)
- The status bar indicator shows current connection state (green/yellow/red) with a manual Reconnect button

---

## Upgrading an Existing Database

If you set up your Supabase database before the `reference` and `activity` columns were added, you need to add them manually. Open the **SQL Editor** in your Supabase dashboard and run:

```sql
-- Add reference column (for bank statement matching)
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS reference TEXT;

-- Add activity column (for project/activity tagging)
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS activity TEXT;

-- Add activity column to planned templates
ALTER TABLE planned_templates ADD COLUMN IF NOT EXISTS activity TEXT;
```

These columns are optional (`TEXT`, nullable) so existing data is unaffected.

---

## Troubleshooting

### "Bucket not found" error
- Verify the bucket is named exactly `attachments`
- Check that storage policies are configured

### "400 Bad Request" when uploading attachments
- Verify the INSERT policy exists on the storage bucket
- Check that the anon key is correct

### Connection timeout
- Verify the connection string is correct
- Check that you're using "Transaction Pooler" method
- Ensure your database password is correct (no `[YOUR-PASSWORD]` placeholder)

### "Permission denied" errors
- Verify RLS policies are created on all tables
- Check that the anon key has the correct permissions

---

## Security Considerations

The default setup uses permissive policies (`true`) which allow any authenticated request full access. For production use with multiple organisations, consider:

1. **Row-Level Security**: Add user/organisation columns and filter by authenticated user
2. **Service Role Key**: Use for server-side operations only, never expose in client apps
3. **Custom Policies**: Restrict access based on user roles or organisation membership

For a single organisation with trusted users, the default policies are sufficient.
