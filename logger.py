import os
from supabase import create_client, Client
from datetime import datetime
from typing import Optional

class CollectorLogger:
    def __init__(self):
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_KEY")

        if url and key:
            self.supabase = create_client(url, key)
            self.enabled = True
        else:
            self.supabase = None
            self.enabled = False

    def log(self, level: str, message: str, sol_amount: Optional[float] = None,
            tx_signature: Optional[str] = None, metadata: Optional[dict] = None):
        print(f"[{level.upper()}] {message}")

        if not self.enabled:
            return

        try:
            log_entry = {
                'level': level,
                'message': message,
                'timestamp': datetime.utcnow().isoformat()
            }

            if sol_amount is not None:
                log_entry['sol_amount'] = float(sol_amount)

            if tx_signature:
                log_entry['tx_signature'] = tx_signature

            if metadata:
                log_entry['metadata'] = metadata

            self.supabase.table('collector_logs').insert(log_entry).execute()
        except Exception as e:
            print(f"Failed to write log to database: {e}")

    def info(self, message: str, **kwargs):
        self.log('info', message, **kwargs)

    def success(self, message: str, **kwargs):
        self.log('success', message, **kwargs)

    def error(self, message: str, **kwargs):
        self.log('error', message, **kwargs)

    def warning(self, message: str, **kwargs):
        self.log('warning', message, **kwargs)
