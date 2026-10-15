# SafeHer – Women Safety Software

## Features
1. Registration and login with hashed passwords and sessions.
2. Emergency contacts: add and remove contacts.
3. Fake call with a custom caller name, delay, ringtone, and call timer.
4. Emergency siren.
5. Safe-route detector using DBSCAN crime hotspots and risk-scored routes.
6. Consent-based live friends map, nearby-friend detection (1 km), and friend SOS alerts.
7. Live location tracking link sent by SMS to emergency contacts; recipients can open the link without logging in.
8. Voice SOS: recognized keywords trigger a countdown with a cancellation option.
9. Report unsafe locations.
10. Camera Share, where supported and explicitly permitted by the user.

## Run Locally

Create and activate a virtual environment, then install dependencies.

**Windows PowerShell:**
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

Open `http://localhost:5000` in your browser.

To test the friends feature, register two accounts in separate browser sessions, add each other by phone number, and accept the friend requests.

## Configure SMS and Calls with Twilio

Set these environment variables in your deployment environment:

- `TWILIO_SID`
- `TWILIO_TOKEN`
- `TWILIO_FROM`
- `SECRET_KEY`

Use valid Twilio credentials and a long, random secret key. Never commit credentials to GitHub. Without Twilio configuration, messaging and calling may be unavailable or use development-mode behavior, depending on the implementation.

Emergency contact numbers should include the country code, such as `+91...`.

## Use on Phones

GPS, microphone, and camera features generally require HTTPS and explicit browser permissions. Deploy the application over HTTPS before testing these features on a phone.

Browser-based tracking generally works only while the relevant page and browser capabilities remain active. A normal PWA cannot reliably detect physical power-button presses or guarantee background tracking after the browser is closed.

## Install as a Phone App (PWA)

After deploying over HTTPS:

- **Android:** Open the site in Chrome and select the install option or "Add to Home screen."
- **iPhone:** Open the site in Safari, select Share, then "Add to Home Screen."

A packaged Android application can be explored using a PWA packaging tool, but device-level capabilities may require native Android development.

## Production Improvements

- Replace sample incident records with verified, appropriately sourced crime data.
- Evaluate a routing service suitable for walking routes.
- Add login rate limiting and secure cookie settings.
- Use PostgreSQL or another persistent database for production.
- Configure persistent storage and backups for user accounts and emergency data.
- Test SMS, voice calls, location sharing, camera permissions, and authorization flows before real-world use.

## Important Safety and Privacy Notes

SOS notifications, calls, SMS, friend alerts, and camera sharing depend on the actual implementation and configuration. Test these features before relying on them in an emergency. Share location or camera access only with trusted recipients and with explicit consent.