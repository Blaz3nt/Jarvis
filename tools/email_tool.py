import imaplib
import email
from email.header import decode_header
from datetime import datetime
import config


def _connect():
    """Connect to IMAP server and return the connection."""
    if not config.EMAIL_IMAP_SERVER:
        raise ValueError("Email not configured. Set EMAIL_IMAP_SERVER, EMAIL_ADDRESS, and EMAIL_PASSWORD.")
    mail = imaplib.IMAP4_SSL(config.EMAIL_IMAP_SERVER)
    mail.login(config.EMAIL_ADDRESS, config.EMAIL_PASSWORD)
    return mail


def _decode_header_value(value):
    """Decode an email header value."""
    if value is None:
        return ""
    decoded_parts = decode_header(value)
    result = []
    for part, charset in decoded_parts:
        if isinstance(part, bytes):
            result.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            result.append(part)
    return " ".join(result)


def _parse_email(msg):
    """Extract key fields from an email message."""
    subject = _decode_header_value(msg.get("Subject"))
    sender = _decode_header_value(msg.get("From"))
    date = msg.get("Date", "")

    # Get body preview
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    body = payload.decode("utf-8", errors="replace")
                    break
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            body = payload.decode("utf-8", errors="replace")

    # Truncate body to first 200 chars as preview
    preview = body.strip()[:200]
    if len(body.strip()) > 200:
        preview += "..."

    return {
        "subject": subject,
        "from": sender,
        "date": date,
        "preview": preview
    }


def read_emails(folder="INBOX", count=5):
    """Read recent emails from the specified folder."""
    count = min(count, 20)
    mail = _connect()
    try:
        mail.select(folder, readonly=True)
        _, message_numbers = mail.search(None, "ALL")
        nums = message_numbers[0].split()

        # Get the most recent emails
        recent = nums[-count:] if len(nums) >= count else nums
        recent.reverse()  # Most recent first

        results = []
        for num in recent:
            _, msg_data = mail.fetch(num, "(RFC822)")
            msg = email.message_from_bytes(msg_data[0][1])
            results.append(_parse_email(msg))

        if not results:
            return "No emails found."

        output = []
        for i, e in enumerate(results, 1):
            output.append(f"{i}. From: {e['from']}\n   Subject: {e['subject']}\n   Date: {e['date']}\n   Preview: {e['preview']}")
        return "\n\n".join(output)
    finally:
        mail.logout()


def search_emails(query, folder="INBOX", count=5):
    """Search emails by subject or sender."""
    count = min(count, 20)
    mail = _connect()
    try:
        mail.select(folder, readonly=True)

        # Search in subject and from fields
        _, subject_nums = mail.search(None, f'(SUBJECT "{query}")')
        _, from_nums = mail.search(None, f'(FROM "{query}")')

        # Combine and deduplicate
        all_nums = set(subject_nums[0].split() + from_nums[0].split())
        all_nums.discard(b"")
        all_nums = sorted(all_nums, key=lambda x: int(x), reverse=True)[:count]

        if not all_nums:
            return f"No emails found matching '{query}'."

        results = []
        for num in all_nums:
            _, msg_data = mail.fetch(num, "(RFC822)")
            msg = email.message_from_bytes(msg_data[0][1])
            results.append(_parse_email(msg))

        output = []
        for i, e in enumerate(results, 1):
            output.append(f"{i}. From: {e['from']}\n   Subject: {e['subject']}\n   Date: {e['date']}\n   Preview: {e['preview']}")
        return "\n\n".join(output)
    finally:
        mail.logout()
