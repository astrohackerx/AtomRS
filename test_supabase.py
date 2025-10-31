#!/usr/bin/env python3
"""Test Supabase connection and update stats"""

import os
from dotenv import load_dotenv
from supabase import create_client
from datetime import datetime, timezone

load_dotenv()

def test_connection():
    url = os.getenv('SUPABASE_URL')
    key = os.getenv('SUPABASE_KEY')

    print(f"SUPABASE_URL: {url}")
    print(f"SUPABASE_KEY exists: {bool(key)}")
    print(f"SUPABASE_KEY length: {len(key) if key else 0}")
    print()

    if not url or not key:
        print("❌ Missing SUPABASE_URL or SUPABASE_KEY")
        return

    try:
        supabase = create_client(url, key)
        print("✅ Supabase client created")

        # Test SELECT
        result = supabase.from_('fee_collector_stats').select('*').eq('id', '00000000-0000-0000-0000-000000000001').maybe_single().execute()
        print(f"✅ SELECT successful")
        print(f"Current data: {result.data}")
        print()

        if result.data:
            # Test UPDATE
            new_total = float(result.data['total_sol_paid']) + 0.123456789
            new_count = result.data['successful_executions'] + 1
            now = datetime.now(timezone.utc).isoformat()

            print(f"Attempting UPDATE:")
            print(f"  new_total: {new_total}")
            print(f"  new_count: {new_count}")
            print(f"  timestamp: {now}")

            update_result = supabase.from_('fee_collector_stats').update({
                'total_sol_paid': new_total,
                'successful_executions': new_count,
                'last_payout_amount': 0.123456789,
                'last_payout_at': now,
                'updated_at': now
            }).eq('id', '00000000-0000-0000-0000-000000000001').execute()

            print(f"✅ UPDATE successful")
            print(f"Updated data: {update_result.data}")

            # Verify update
            verify = supabase.from_('fee_collector_stats').select('*').eq('id', '00000000-0000-0000-0000-000000000001').maybe_single().execute()
            print(f"✅ Verification: {verify.data}")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_connection()
