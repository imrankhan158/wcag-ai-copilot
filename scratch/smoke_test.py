# /// script
# dependencies = [
#   "psycopg2-binary",
#   "requests",
# ]
# ///
import sys
import uuid
import time
import requests
import psycopg2
from datetime import datetime, UTC

GATEWAY_URL = "http://localhost:8000"
QDRANT_URL = "http://localhost:6333"

# Connection config helper for PostgreSQL
def get_db_conn(port, db="postgres"):
    return psycopg2.connect(
        host="localhost",
        port=port,
        database=db,
        user="admin",
        password="admin123",
        connect_timeout=3
    )

def run_db_and_vector_tests():
    print("\n" + "="*50)
    print("1. Data & Vector Scaling Checks (Phase 6)")
    print("="*50)
    
    overall_ok = True

    # 1.1 Auth Replication & Standby Read-only check
    print("\n--- [1.1] Testing Auth Database Replication & Read-only Standby ---")
    try:
        conn_primary = get_db_conn(6432, "wcag_copilot")
        cursor_primary = conn_primary.cursor()
        
        user_id = str(uuid.uuid4())
        email = f"smoke_test_{uuid.uuid4().hex[:6]}@test.com"
        hashed_password = "hashed_pbkdf2_sha256$..."
        
        print(f"Primary PgBouncer (6432): Inserting user '{email}'...")
        cursor_primary.execute(
            "INSERT INTO users (id, email, hashed_password) VALUES (%s, %s, %s)",
            (user_id, email, hashed_password)
        )
        conn_primary.commit()
        cursor_primary.close()
        conn_primary.close()
        print("✔ Write successful on primary.")
        
        # Standby Replication lag wait
        time.sleep(1)
        
        # Read from standby replica
        print("Standby Replica (5442): Verifying replication...")
        conn_replica = get_db_conn(5442, "wcag_copilot")
        cursor_replica = conn_replica.cursor()
        cursor_replica.execute("SELECT email FROM users WHERE id = %s", (user_id,))
        row = cursor_replica.fetchone()
        
        if row and row[0] == email:
            print("✔ Standby Replication verification: PASSED.")
        else:
            print("✘ Standby Replication verification: FAILED.")
            overall_ok = False
            
        # Verify read-only enforcement
        print("Standby Replica (5442): Testing read-only write rejection...")
        try:
            cursor_replica.execute(
                "INSERT INTO users (id, email, hashed_password) VALUES (%s, %s, %s)",
                (str(uuid.uuid4()), "bad_insert@test.com", "foo")
            )
            conn_replica.commit()
            print("✘ Standby write constraint check: FAILED (Write succeeded on standby).")
            overall_ok = False
        except psycopg2.errors.ReadOnlySqlTransaction:
            print("✔ Standby write constraint check: PASSED (Insert rejected with ReadOnlySqlTransaction).")
            conn_replica.rollback()
        except Exception as e:
            print(f"✔ Standby write constraint check: PASSED (Insert failed as expected: {e}).")
            conn_replica.rollback()
            
        cursor_replica.close()
        conn_replica.close()
    except Exception as e:
        print(f"✘ Auth replication checks failed with exception: {e}")
        overall_ok = False

    # 1.2 Audit Replication & Monthly Range Partitioning check
    print("\n--- [1.2] Testing Audit Replication & Partition Routing ---")
    try:
        conn_primary = get_db_conn(6432, "wcag_copilot")
        cursor_primary = conn_primary.cursor()
        
        audit_id = str(uuid.uuid4())
        test_user_id = str(uuid.uuid4())
        created_at = datetime.now(UTC)
        
        print("Primary PgBouncer (6432): Inserting partition test audit & violation...")
        cursor_primary.execute(
            """INSERT INTO audits 
               (id, user_id, input_type, input_content, summary, score_a, score_aa, score_aaa, score_total, created_at) 
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (audit_id, test_user_id, "code", "<div></div>", "Summary", 0, 0, 0, 0, created_at)
        )
        
        violation_id = str(uuid.uuid4())
        cursor_primary.execute(
            """INSERT INTO audit_violations
               (id, audit_id, criterion_id, title, level, issue, element, fix, explanation, created_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (violation_id, audit_id, "1.1.1", "Missing alt text", "A", "Issue", "<img>", "Add alt", "Exp", created_at)
        )
        conn_primary.commit()
        
        # Verify routing into correct partition table
        partition_name = f"audits_y{created_at.year}m{created_at.month:02d}"
        cursor_primary.execute(f"SELECT COUNT(*) FROM {partition_name} WHERE id = %s", (audit_id,))
        count = cursor_primary.fetchone()[0]
        if count == 1:
            print(f"✔ Range Partition routing check: PASSED (Row resides in '{partition_name}').")
        else:
            print("✘ Range Partition routing check: FAILED (Row not inside child partition table).")
            overall_ok = False
            
        cursor_primary.close()
        conn_primary.close()
        
        # Wait for replication
        time.sleep(1)
        
        # Read audit and violation from Replica bouncer (6433)
        print("Replica PgBouncer (6433): Verifying read replication...")
        conn_replica = get_db_conn(6433, "wcag_copilot")
        cursor_replica = conn_replica.cursor()
        
        cursor_replica.execute("SELECT user_id FROM audits WHERE id = %s", (audit_id,))
        audit_row = cursor_replica.fetchone()
        cursor_replica.execute("SELECT id FROM audit_violations WHERE audit_id = %s", (audit_id,))
        violation_row = cursor_replica.fetchone()
        
        if audit_row and audit_row[0] == test_user_id and violation_row and violation_row[0] == violation_id:
            print("✔ Standby Replica connection pooler query: PASSED.")
        else:
            print("✘ Standby Replica connection pooler query: FAILED.")
            overall_ok = False
            
        cursor_replica.close()
        conn_replica.close()
    except Exception as e:
        print(f"✘ Audit replication checks failed with exception: {e}")
        overall_ok = False

    # 1.3 Conversations & Messages Partition check
    print("\n--- [1.3] Testing Chat Replication & Message Partition Routing ---")
    try:
        conn_primary = get_db_conn(6432, "wcag_copilot")
        cursor_primary = conn_primary.cursor()
        
        conv_id = str(uuid.uuid4())
        test_user_id = str(uuid.uuid4())
        msg_id = str(uuid.uuid4())
        created_at = datetime.now(UTC)
        
        print("Primary PgBouncer (6432): Inserting conversation & message partition row...")
        cursor_primary.execute(
            "INSERT INTO conversations (id, user_id, title, created_at) VALUES (%s, %s, %s, %s)",
            (conv_id, test_user_id, "Smoke Test Chat", created_at)
        )
        cursor_primary.execute(
            "INSERT INTO messages (id, conversation_id, role, content, created_at) VALUES (%s, %s, %s, %s, %s)",
            (msg_id, conv_id, "user", "Message content", created_at)
        )
        conn_primary.commit()
        
        # Verify routing into correct messages partition
        partition_name = f"messages_y{created_at.year}m{created_at.month:02d}"
        cursor_primary.execute(f"SELECT COUNT(*) FROM {partition_name} WHERE id = %s", (msg_id,))
        count = cursor_primary.fetchone()[0]
        if count == 1:
            print(f"✔ Messages Range Partition routing check: PASSED (Row resides in '{partition_name}').")
        else:
            print("✘ Messages Range Partition routing check: FAILED (Row not inside child partition table).")
            overall_ok = False
            
        cursor_primary.close()
        conn_primary.close()
        
        # Wait for replication
        time.sleep(1)
        
        # Read from standby replica pooler
        print("Replica PgBouncer (6433): Verifying chat replication...")
        conn_replica = get_db_conn(6433, "wcag_copilot")
        cursor_replica = conn_replica.cursor()
        cursor_replica.execute("SELECT content FROM messages WHERE id = %s", (msg_id,))
        msg_row = cursor_replica.fetchone()
        
        if msg_row and msg_row[0] == "Message content":
            print("✔ Standby Replica chat query: PASSED.")
        else:
            print("✘ Standby Replica chat query: FAILED.")
            overall_ok = False
            
        cursor_replica.close()
        conn_replica.close()
    except Exception as e:
        print(f"✘ Chat replication checks failed with exception: {e}")
        overall_ok = False

    # 1.4 Qdrant Raft Consensus status check
    print("\n--- [1.4] Testing Qdrant 3-Node Raft Cluster Health ---")
    try:
        r = requests.get(f"{QDRANT_URL}/cluster")
        r.raise_for_status()
        cluster_info = r.json().get("result", {})
        status = cluster_info.get("status")
        peers = cluster_info.get("peers", {})
        
        print(f"Qdrant Cluster status: '{status}'")
        print(f"Active peers registered: {len(peers)}")
        
        if status == "enabled" and len(peers) == 3:
            print("✔ Qdrant Raft consensus check: PASSED.")
        else:
            print(f"✘ Qdrant Raft consensus check: FAILED (status={status}, peerCount={len(peers)}).")
            overall_ok = False
    except Exception as e:
        print(f"✘ Qdrant consensus verification failed: {e}")
        overall_ok = False

    return overall_ok


def run_api_integration_tests():
    print("\n" + "="*50)
    print("2. Edge Gateway & Core Services Integration (Phase 5)")
    print("="*50)

    overall_ok = True

    # Generate test user
    email = f"smoke_user_{uuid.uuid4().hex[:6]}@test.com"
    password = "SecurePassword123!"
    token = None

    # 2.1 User Registration
    print("\n--- [2.1] Registering user account ---")
    try:
        r = requests.post(f"{GATEWAY_URL}/api/auth/register", json={"email": email, "password": password})
        r.raise_for_status()
        resp_data = r.json()
        token = resp_data.get("access_token")
        if token:
            print(f"✔ Registration check: PASSED (Registered '{email}').")
        else:
            print("✘ Registration check: FAILED (No access token returned).")
            overall_ok = False
    except Exception as e:
        print(f"✘ Registration failed with exception: {e}")
        return False

    headers = {"Authorization": f"Bearer {token}"}
    audit_id = None

    # 2.2 Accessibility Check
    print("\n--- [2.2] Submitting audit check request ---")
    try:
        r = requests.post(
            f"{GATEWAY_URL}/api/check", 
            json={"input": "<h1>Accessibility Compliance Audit Header</h1>"}, 
            headers=headers
        )
        r.raise_for_status()
        check_data = r.json()
        if "violations" in check_data:
            print("✔ Accessibility audit check: PASSED.")
        else:
            print("✘ Accessibility audit check: FAILED (No violations key returned).")
            overall_ok = False
    except Exception as e:
        print(f"✘ Accessibility audit check failed: {e}")
        overall_ok = False

    # 2.3 Fetch Audit Logs
    print("\n--- [2.3] Fetching audits history ---")
    try:
        r = requests.get(f"{GATEWAY_URL}/api/history/audits", headers=headers)
        r.raise_for_status()
        audits = r.json()
        print(f"Returned history logs count: {len(audits)}")
        if len(audits) > 0:
            audit_id = audits[0].get("id")
            print("✔ Audits history logs check: PASSED.")
        else:
            print("✘ Audits history logs check: FAILED (History log empty).")
            overall_ok = False
    except Exception as e:
        print(f"✘ Audits history logs fetch failed: {e}")
        overall_ok = False

    # 2.4 Fetch Audit Detail
    if audit_id:
        print(f"\n--- [2.4] Retrieving specific audit detail (ID: {audit_id}) ---")
        try:
            r = requests.get(f"{GATEWAY_URL}/api/history/audits/{audit_id}", headers=headers)
            r.raise_for_status()
            detail = r.json()
            if detail.get("id") == audit_id and "violations" in detail:
                print("✔ Specific audit details lookup check: PASSED.")
            else:
                print("✘ Specific audit details lookup check: FAILED.")
                overall_ok = False
        except Exception as e:
            print(f"✘ Specific audit details lookup failed: {e}")
            overall_ok = False

    # 2.5 QA Chatbot SSE Stream
    print("\n--- [2.5] Querying chatbot RAG endpoint (Server-Sent Events stream) ---")
    conversation_id = None
    try:
        chat_payload = {
            "message": "Verify compliance details for Success Criterion 1.1.1",
            "history": [],
            "conversation_id": None
        }
        r = requests.post(f"{GATEWAY_URL}/api/chat/qa", json=chat_payload, headers=headers, stream=True)
        r.raise_for_status()
        
        chunks_received = 0
        for line in r.iter_lines():
            if line:
                decoded_line = line.decode('utf-8')
                if decoded_line.startswith("data: "):
                    data_str = decoded_line[6:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                        if chunk.get("type") == "conversation_id":
                            conversation_id = chunk.get("id")
                        elif chunk.get("type") == "token":
                            chunks_received += 1
                    except Exception:
                        pass
        print(f"Created Conversation ID: '{conversation_id}'")
        print(f"Tokens streamed: {chunks_received}")
        if conversation_id and chunks_received > 0:
            print("✔ Chatbot RAG SSE stream check: PASSED.")
        else:
            print("✘ Chatbot RAG SSE stream check: FAILED.")
            overall_ok = False
    except Exception as e:
        print(f"✘ Chatbot RAG SSE stream check failed: {e}")
        overall_ok = False

    # 2.6 Fetch Chat History
    if conversation_id:
        print("\n--- [2.6] Fetching conversations history ---")
        try:
            r = requests.get(f"{GATEWAY_URL}/api/history/chats", headers=headers)
            r.raise_for_status()
            chats = r.json()
            print(f"Returned conversation history count: {len(chats)}")
            if any(c.get("id") == conversation_id for c in chats):
                print("✔ Conversation history lookup: PASSED.")
            else:
                print("✘ Conversation history lookup: FAILED (New session missing in history).")
                overall_ok = False
        except Exception as e:
            print(f"✘ Conversation history lookup failed: {e}")
            overall_ok = False

        # 2.7 Fetch Conversation Message Details
        print(f"\n--- [2.7] Retrieving message list for Conversation ID: {conversation_id} ---")
        try:
            r = requests.get(f"{GATEWAY_URL}/api/history/chats/{conversation_id}", headers=headers)
            r.raise_for_status()
            chat_detail = r.json()
            if chat_detail.get("id") == conversation_id and len(chat_detail.get("messages", [])) > 0:
                print("✔ Messages history list check: PASSED.")
            else:
                print("✘ Messages history list check: FAILED.")
                overall_ok = False
        except Exception as e:
            print(f"✘ Messages history list lookup failed: {e}")
            overall_ok = False

    # 2.8 Criteria List
    print("\n--- [2.8] Retrieving WCAG criteria guidelines ---")
    try:
        r = requests.get(f"{GATEWAY_URL}/api/criteria", headers=headers)
        r.raise_for_status()
        criteria_list = r.json().get("criteria", [])
        print(f"Total WCAG guidelines fetched: {len(criteria_list)}")
        if len(criteria_list) > 0:
            print("✔ Criteria database check: PASSED.")
        else:
            print("✘ Criteria database check: FAILED.")
            overall_ok = False
    except Exception as e:
        print(f"✘ Criteria list fetch failed: {e}")
        overall_ok = False

    # 2.9 Criteria Detail
    print("\n--- [2.9] Retrieving success criteria details (ID: 1.1.1) ---")
    try:
        r = requests.get(f"{GATEWAY_URL}/api/criteria/1.1.1", headers=headers)
        r.raise_for_status()
        crit = r.json()
        if crit.get("criterion_id") == "1.1.1":
            print(f"✔ Guideline details check: PASSED (Title: '{crit.get('title')}').")
        else:
            print("✘ Guideline details check: FAILED.")
            overall_ok = False
    except Exception as e:
        print(f"✘ Guideline details query failed: {e}")
        overall_ok = False

    return overall_ok


if __name__ == "__main__":
    import json
    print("="*60)
    print("   WCAG AI COPILOT — UNIFIED PLATFORM SMOKE TEST")
    print("="*60)
    
    # Run storage layer validations
    db_pass = run_db_and_vector_tests()
    
    # Run API and edge integration validations
    api_pass = run_api_integration_tests()
    
    print("\n" + "="*50)
    print("SMOKE TEST RESULTS SUMMARY")
    print("="*50)
    print(f"1. Database Partitioning, Standby & Cluster Health: {'PASSED' if db_pass else 'FAILED'}")
    print(f"2. Gateway edge proxy routing & SSE flows:         {'PASSED' if api_pass else 'FAILED'}")
    print("="*50)
    
    if db_pass and api_pass:
        print("\n✔ ALL SYSTEM SMOKE TESTS PASSED SUCCESSFULLY!")
        sys.exit(0)
    else:
        print("\n✘ SOME SMOKE TESTS FAILED. PLEASE CHECK THE HEALTH OF CONCERNED SERVICES.")
        sys.exit(1)
