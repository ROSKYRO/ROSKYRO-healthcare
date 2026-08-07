"""Stores referral report files (a partner's PDF/image lab or diagnostic
report) in a private Backblaze B2 bucket, and hands back short-lived signed
download links -- rather than storing raw files in MongoDB, or on this
server's own disk (Railway's filesystem is wiped on every redeploy, so
anything saved there would silently vanish the next time code ships).

Backblaze B2 exposes an S3-compatible API, so the standard boto3 S3 client
works against it unmodified once pointed at B2's endpoint -- this avoids
hand-rolling B2's native b2_get_download_authorization token dance and
gives us `generate_presigned_url` for free. That's what actually builds
the link that goes out in the patient's WhatsApp message (see
routers/referrals.py's `_notify_patient_whatsapp`) and the "Download
Report" link shown in-app to the referring business/partner.

Configured entirely via env vars (B2_KEY_ID / B2_APPLICATION_KEY /
B2_BUCKET_NAME / B2_ENDPOINT, see app/config.py) -- real values live only
in Railway's Variables tab, never in source or seed data, same rule as
every other credential in this codebase.
"""
import boto3
from botocore.client import Config as BotoConfig
from botocore.exceptions import BotoCoreError, ClientError

from app.config import (
    B2_KEY_ID, B2_APPLICATION_KEY, B2_BUCKET_NAME, B2_ENDPOINT,
    B2_REPORT_LINK_VALID_SECONDS,
)
from app.utils.ids import new_id


def is_configured() -> bool:
    return bool(B2_KEY_ID and B2_APPLICATION_KEY and B2_BUCKET_NAME and B2_ENDPOINT)


def _client():
    if not is_configured():
        raise RuntimeError(
            "Report storage isn't configured -- set B2_KEY_ID, B2_APPLICATION_KEY, "
            "B2_BUCKET_NAME and B2_ENDPOINT (Railway Variables tab) to enable report uploads."
        )
    return boto3.client(
        "s3",
        endpoint_url=f"https://{B2_ENDPOINT}",
        aws_access_key_id=B2_KEY_ID,
        aws_secret_access_key=B2_APPLICATION_KEY,
        # B2's S3-compatible endpoint requires SigV4 -- boto3 defaults to
        # it for most regions already, but pinned explicitly here since a
        # wrong default silently produces "SignatureDoesNotMatch" errors
        # that are painful to debug from a stack trace alone.
        config=BotoConfig(signature_version="s3v4"),
    )


def upload_report(*, referral_id: str, filename: str, content: bytes, content_type: str | None) -> str:
    """Uploads one report file for a referral. Returns the B2 object key
    (NOT a URL -- the bucket is private, so the key alone grants no
    access; see build_download_link for the actual access mechanism).
    Namespaced under the referral's own id so every report for a referral
    lives together and the eventual lifecycle-rule / manual cleanup can
    target a referral's files by prefix if needed."""
    ext = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""
    key = f"referrals/{referral_id}/{new_id()}{ext}"
    try:
        _client().put_object(
            Bucket=B2_BUCKET_NAME, Key=key, Body=content,
            ContentType=content_type or "application/octet-stream",
        )
    except (BotoCoreError, ClientError) as exc:
        raise RuntimeError(f"Could not upload report to storage: {exc}") from exc
    return key


def build_download_link(object_key: str, valid_seconds: int | None = None) -> str:
    """A time-limited, signed download URL for a private-bucket object --
    safe to put straight into a patient-facing WhatsApp message or show as
    an in-app "Download Report" link, since it stops working after
    `valid_seconds` (default: B2_REPORT_LINK_VALID_SECONDS, 7 days) with
    no ROSKYRO login or app needed to open it."""
    return _client().generate_presigned_url(
        "get_object",
        Params={"Bucket": B2_BUCKET_NAME, "Key": object_key},
        ExpiresIn=valid_seconds if valid_seconds is not None else B2_REPORT_LINK_VALID_SECONDS,
    )


def delete_report(object_key: str) -> None:
    """Manual delete -- e.g. if a referral is cancelled and its report
    should be cleaned up immediately rather than waiting on a bucket-level
    Lifecycle Rule. Safe to call even if the object is already gone."""
    try:
        _client().delete_object(Bucket=B2_BUCKET_NAME, Key=object_key)
    except (BotoCoreError, ClientError):
        pass
