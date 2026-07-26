import os
from dotenv import load_dotenv

load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
MONGODB_DB = os.getenv("MONGODB_DB", "roskyro_healthcare_os")

# This sandbox has no outbound access to MongoDB's binary distribution
# servers, so there is no real `mongod` to install here. USE_MOCK_DB=true
# swaps the Motor client for mongomock-motor's in-process, wire-compatible
# stand-in so the app can actually run and be verified in this session.
# Every query in this codebase is written against the real Motor/PyMongo
# async API — set USE_MOCK_DB=false (or unset it) and point MONGODB_URI at
# a real MongoDB (local `mongod` or Atlas) on a machine that can reach it,
# and nothing else needs to change.
USE_MOCK_DB = os.getenv("USE_MOCK_DB", "false").lower() == "true"

JWT_SECRET = os.getenv("JWT_SECRET", "change_this_secret_in_production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRES_DAYS = int(os.getenv("JWT_EXPIRES_DAYS", "7"))

CLIENT_ORIGIN = os.getenv("CLIENT_ORIGIN", "http://localhost:3000")

# Super-admin login -- read from env so production credentials live in
# Railway's Variables tab, not in seed data or source code. Same pattern
# the original app used (ADMIN_USERNAME / ADMIN_PASSWORD in server.py's
# startup). Defaults match the demo seed data so local/dev behaviour is
# unchanged if these aren't set -- but ALWAYS override ADMIN_PASSWORD in
# production, same as JWT_SECRET above.
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@roskyro.com")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "Roskyro@123")

# How patient-facing WhatsApp messages actually go out -- see
# app/utils/whatsapp_sender.py for the full explanation. "queue" (default)
# is the free, no-API-contract approach: messages queue up centrally and a
# ROSKYRO ops user dispatches them by hand via a pre-filled wa.me
# click-to-chat link, from ONE shared WhatsApp Web/Business session --
# solves the "one WhatsApp login can't run on every business's own
# computer" problem without paying for the official API. Set
# WHATSAPP_MODE=api once a real WhatsApp Business/Cloud API integration is
# wired up in that module's `_send_via_official_api` -- no calling code
# (referrals.py, whatsapp.py) needs to change either way.
WHATSAPP_MODE = os.getenv("WHATSAPP_MODE", "queue")
# Placeholders for that future official-API integration -- intentionally
# unset today. Per the standing rule for this project, real values for
# these belong ONLY in the hosting platform's environment-variable UI
# (Railway's Variables tab), never committed to source or seed data.
WHATSAPP_API_TOKEN = os.getenv("WHATSAPP_API_TOKEN")
WHATSAPP_API_PHONE_NUMBER_ID = os.getenv("WHATSAPP_API_PHONE_NUMBER_ID")
