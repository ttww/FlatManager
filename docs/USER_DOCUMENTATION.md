# FlatManager User Documentation (Admin + Guest)

This guide explains the normal day-to-day workflow for both:

- Admin users (`http://localhost:8080`)
- Guest users (`http://localhost:8081`)

It is written as a step-by-step quick guide with screenshots.

## 1. Admin Guide

### 1.1 Login to Admin UI

1. Open `http://localhost:8080`.
2. Enter your admin token.
3. Click **Continue**.

![Admin Login](./screenshots/admin-01-login.png)

Notes:
- The token comes from your backend environment (`ADMIN_TOKEN` in `api/.env`).
- If login fails, verify API is running and token is correct.

### 1.2 Create an Access Code

1. Open **Access Codes** in the left menu.
2. Fill in:
   - Apartment ID
   - Numeric Code
   - Valid From / Valid Until
   - Optional booking reference and guest name
3. Click **Create Code**.
4. Confirm the new row appears in the code table.

![Admin Access Codes](./screenshots/admin-02-codes.png)

Tips:
- Use a future **Valid Until** time.
- If guest access is denied, check if the code is active and in validity range.

### 1.3 Manage Devices

1. Open **Devices**.
2. Confirm at least one device exists for the apartment.
3. Check status is **online**.
4. Use **Rotate Token** only when re-provisioning a device.

![Admin Devices](./screenshots/admin-03-devices.png)

Why this matters:
- Guest access can only trigger a door command when a device is registered for the apartment.

### 1.4 Check Command History

1. Open **Commands**.
2. Look for rows with status changes (`pending` -> `delivered` -> `done`).
3. Use this page to confirm whether an open request reached the device.

![Admin Commands](./screenshots/admin-04-commands.png)

### 1.5 Check Access Logs

1. Open **Access Logs**.
2. Use this page to audit each attempt:
   - `success`
   - `denied`
   - reason text (for example `accepted`, `validation_failed`)

![Admin Access Logs](./screenshots/admin-05-logs.png)

### 1.6 Trigger Manual Open (Support)

1. Open **Support**.
2. Enter apartment ID.
3. Click **Trigger Manual Open**.
4. Verify result in **Commands** and **Access Logs**.

![Admin Support](./screenshots/admin-06-support.png)

Use this only for verified support cases.

---

## 2. Guest Guide

### 2.1 Open Door Request (Normal Flow)

1. Open `http://localhost:8081`.
2. Enter apartment ID.
3. Enter access code.
4. Click **Open Door**.

![Guest Open Form](./screenshots/guest-01-open-form.png)

### 2.2 Successful Request

If the request is valid, the user sees a success message (language depends on selected locale).

![Guest Success](./screenshots/guest-02-success.png)

### 2.3 Failed Request

If code is wrong/expired/inactive, the user sees a denial message.

![Guest Denied](./screenshots/guest-03-denied.png)

---

## 3. Quick Troubleshooting Checklist

If guests cannot open the door:

1. In Admin **Access Codes**, verify code exists, is active, and valid now.
2. In Admin **Devices**, verify apartment has a registered online device.
3. In Admin **Commands**, verify command is created and reaches `done`.
4. In Admin **Access Logs**, inspect `result` and `reason`.
5. Use **Support -> Trigger Manual Open** for fallback.

---

## 4. URL Overview

- Admin UI: `http://localhost:8080`
- Guest UI: `http://localhost:8081`
- API base: `http://localhost:8000`
