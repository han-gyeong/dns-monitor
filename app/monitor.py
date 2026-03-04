import hashlib
import json
import os
import smtplib
from email.message import EmailMessage

import dns.resolver
from sqlalchemy import desc
from sqlalchemy.orm import Session

from .models import ChangeEvent, DNSSnapshot, MXARecord, MXRecord, MonitoredDomain, NotificationLog


class DNSMonitorService:
    def __init__(self, timeout: float = 4.0):
        self.resolver = dns.resolver.Resolver()
        self.resolver.lifetime = timeout
        self.resolver.timeout = timeout

    def resolve_domain(self, domain: str) -> tuple[list[tuple[int, str]], list[tuple[str, str]]]:
        mx_records: list[tuple[int, str]] = []
        mx_a_records: list[tuple[str, str]] = []

        answers = self.resolver.resolve(domain, "MX")
        for answer in answers:
            exchange = str(answer.exchange).rstrip(".").lower()
            priority = int(answer.preference)
            mx_records.append((priority, exchange))

        for _, exchange in mx_records:
            try:
                a_answers = self.resolver.resolve(exchange, "A")
                for record in a_answers:
                    mx_a_records.append((exchange, str(record)))
            except Exception:
                continue

        mx_records = sorted(set(mx_records), key=lambda x: (x[0], x[1]))
        mx_a_records = sorted(set(mx_a_records), key=lambda x: (x[0], x[1]))
        return mx_records, mx_a_records

    def save_snapshot(self, db: Session, domain_obj: MonitoredDomain, mx_records, mx_a_records, status="success", error=None):
        snapshot = DNSSnapshot(domain_id=domain_obj.id, status=status, error_message=error)
        db.add(snapshot)
        db.flush()

        for priority, exchange in mx_records:
            db.add(MXRecord(snapshot_id=snapshot.id, priority=priority, exchange=exchange))

        for exchange, ip in mx_a_records:
            db.add(MXARecord(snapshot_id=snapshot.id, exchange=exchange, ipv4=ip))

        db.commit()
        db.refresh(snapshot)
        return snapshot

    @staticmethod
    def _snapshot_sets(snapshot: DNSSnapshot):
        mx_set = {(m.priority, m.exchange) for m in snapshot.mx_records}
        a_set = {(m.exchange, m.ipv4) for m in snapshot.mx_a_records}
        return mx_set, a_set

    def detect_changes(self, prev: DNSSnapshot | None, current: DNSSnapshot):
        if prev is None:
            return []

        prev_mx, prev_a = self._snapshot_sets(prev)
        curr_mx, curr_a = self._snapshot_sets(current)

        events = []
        mx_added = sorted(curr_mx - prev_mx)
        mx_removed = sorted(prev_mx - curr_mx)
        a_added = sorted(curr_a - prev_a)
        a_removed = sorted(prev_a - curr_a)

        if mx_added or mx_removed:
            details = {"mx_added": mx_added, "mx_removed": mx_removed}
            events.append(("MX_CHANGED", self._summary(details), details))

        if a_added or a_removed:
            details = {"a_added": a_added, "a_removed": a_removed}
            events.append(("A_CHANGED", self._summary(details), details))

        return events

    @staticmethod
    def _summary(details: dict) -> str:
        chunks = []
        for key, value in details.items():
            if value:
                chunks.append(f"{key}={len(value)}")
        return ", ".join(chunks) if chunks else "no_changes"

    @staticmethod
    def _fingerprint(domain: str, change_type: str, detail: dict) -> str:
        raw = f"{domain}:{change_type}:{json.dumps(detail, sort_keys=True)}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def create_event_and_notify(self, db: Session, domain_obj: MonitoredDomain, change_type: str, summary: str, detail: dict):
        fp = self._fingerprint(domain_obj.domain, change_type, detail)
        existing = db.query(ChangeEvent).filter(ChangeEvent.domain_id == domain_obj.id, ChangeEvent.fingerprint == fp).first()
        if existing:
            return
        event = ChangeEvent(
            domain_id=domain_obj.id,
            change_type=change_type,
            summary=summary,
            detail_json=json.dumps(detail, ensure_ascii=False),
            fingerprint=fp,
        )
        db.add(event)
        db.commit()
        db.refresh(event)

        status, response = self.send_email_alert(domain_obj.domain, change_type, summary, detail)
        db.add(NotificationLog(event_id=event.id, channel="email", status=status, response=response))
        db.commit()

    def send_email_alert(self, domain: str, change_type: str, summary: str, detail: dict) -> tuple[str, str]:
        smtp_host = os.getenv("SMTP_HOST")
        smtp_port = int(os.getenv("SMTP_PORT", "587"))
        smtp_user = os.getenv("SMTP_USER")
        smtp_password = os.getenv("SMTP_PASSWORD")
        from_email = os.getenv("ALERT_FROM")
        to_email = os.getenv("ALERT_TO")

        if not all([smtp_host, smtp_user, smtp_password, from_email, to_email]):
            return "skipped", "SMTP env vars not configured"

        msg = EmailMessage()
        msg["Subject"] = f"[DNS Monitor] {domain} {change_type}"
        msg["From"] = from_email
        msg["To"] = to_email
        msg.set_content(f"Summary: {summary}\n\nDetails:\n{json.dumps(detail, indent=2)}")

        try:
            with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as smtp:
                smtp.starttls()
                smtp.login(smtp_user, smtp_password)
                smtp.send_message(msg)
            return "sent", "ok"
        except Exception as exc:
            return "failed", str(exc)


def run_single_check(db: Session, monitor: DNSMonitorService, domain_obj: MonitoredDomain):
    previous = (
        db.query(DNSSnapshot)
        .filter(DNSSnapshot.domain_id == domain_obj.id, DNSSnapshot.status == "success")
        .order_by(desc(DNSSnapshot.checked_at))
        .first()
    )

    try:
        mx_records, mx_a_records = monitor.resolve_domain(domain_obj.domain)
        current = monitor.save_snapshot(db, domain_obj, mx_records, mx_a_records)
    except Exception as exc:
        monitor.save_snapshot(db, domain_obj, [], [], status="fail", error=str(exc))
        return

    changes = monitor.detect_changes(previous, current)
    for ctype, summary, detail in changes:
        monitor.create_event_and_notify(db, domain_obj, ctype, summary, detail)
