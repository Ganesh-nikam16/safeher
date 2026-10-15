# SafeHer – Women Safety Software

## Features
1. Registration + login (hashed passwords, sessions)
2. Emergency contacts (add / remove)
3. Fake call (custom caller name + delay, ringtone, call timer)
4. Siren
5. Safe route detector (DBSCAN crime hotspots + risk-scored routes)
6. Live friends map (consent-based), nearby-friend detector (1 km), friend SOS alerts
7. Live location tracking link sent by SMS to emergency contacts (opens without login)
Extras: voice SOS (say "help", "save", "bachao": 10-second countdown with cancel, then location + SMS sent), 3-second SOS cancel window, report unsafe spot

## Run
    python -m venv venv && source venv/bin/activate     (Windows: venv\Scripts\activate)
    pip install -r requirements.txt
    python app.py          # http://localhost:5000

Test the friends feature: register two accounts (normal + private window), add each other by phone, accept.

## Real SMS (Twilio)
    export TWILIO_SID=... TWILIO_TOKEN=... TWILIO_FROM=+1...
    export SECRET_KEY=any-long-random-string
Without Twilio, SMS prints in the terminal (dev-mode). Contact numbers need country code (+91...).

## Use on phones
GPS + mic need HTTPS. Use `ngrok http 5000`, or deploy to Render/PythonAnywhere. Then open the link on phones.
Browser tracking works while the page is open; a native app is needed for background tracking.

## To improve
- Replace seed incidents in init() with a real crime CSV
- OSRM demo server uses car roads; use OpenRouteService for walking
- Add login rate-limiting, HTTPS-only cookies, and PostgreSQL for production

## Install as a phone app (PWA)
Deploy over HTTPS (Render / PythonAnywhere / ngrok), open the link in Chrome on Android -> menu -> "Install app" / "Add to Home screen".
iPhone: Safari -> Share -> Add to Home Screen. Opens full-screen with the SafeHer icon.
Android APK: paste the deployed URL into pwabuilder.com and download the Android package.

## Real calls + SMS
SOS sends an SMS and a Twilio voice call to every emergency contact (see send_call in app.py).

## Enhanced emergency features
- SOS SMS/call notifications are sent to **emergency contacts and accepted SafeHer friends** from the server, so recipients do not need SafeHer open.
- Voice SOS now requires **"help" three times within 10 seconds** before the countdown starts.
- Explicit **Camera Share** lets the user grant camera permission and sends periodic encrypted-in-transit JPEG snapshots to a tokenized viewer link; the link is sent to contacts and accepted friends.
- Important browser limitation: a normal PWA/browser cannot reliably detect the physical power button twice, and cannot keep microphone/GPS/camera running after the browser is fully killed. A native Android companion is required for true device-level power-button handling/background SOS.
