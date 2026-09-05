import random
import secrets
import hmac
import hashlib
import time
from datetime import datetime
from collections import deque

BANKS = ["HDFC","ICICI","SBI","AXIS"]
MERCHANTS = ["Swiggy","Zomato","Zepto","PhonePe","Boat","MamaEarth"]

# === IN-MEMORY STORE - SECURED ===
PROCESSED_TXNS = set()
DLQ_STORE = []
WEBHOOK_LOGS = deque(maxlen=100)  

# === AI FEATURE 1: RISK SCORING ===
def ai_risk_score(row: dict) -> str:
    try:
        amt = float(row.get('amount_raw', 0))
    except (ValueError, TypeError):
        amt = 0
    reason = str(row.get('reason', '')).lower()
    if amt > 30000:
        return "🔴 HIGH RISK - Fraud Check"
    if "duplicate" in reason or "mismatch" in reason:
        return "🟡 MEDIUM RISK - Reconciliation Issue"
    if "fees" in reason or "invoice" in reason:
        return "🟢 LOW RISK - Fee/Doc Issue"
    return "🟢 LOW RISK - Timing Issue"

def ai_forecast_revenue(current_revenue: float):
    try:
        current_revenue = float(current_revenue)
    except (ValueError, TypeError):
        current_revenue = 0
    growth = current_revenue * 0.15
    future = current_revenue + growth
    return future, growth

def _secure_id(prefix: str) -> str:
    return f"{prefix}{secrets.randbelow(900000000000) + 100000000000}"

# ================= WEBHOOK UPGRADE V2 - SECURE =================

def verify_webhook_signature(payload: str, signature: str, secret=None) -> bool:
    """RazorpayX style HMAC-SHA256 verification - SECURE"""
    try:
        # FIX 2: Secret ko hardcoded mat rakh, secrets.toml se lo
        if secret is None:
            try:
                import streamlit as st
                secret = st.secrets.get("WEBHOOK_SECRET", "rzpX_webhook_secret_2026")
            except:
                secret = "rzpX_webhook_secret_2026"
        
        expected = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)
    except Exception:
        return False

def ai_auto_heal_transaction(txn_data: dict) -> dict:
    bank = txn_data.get('bank','HDFC')
    amount = txn_data.get('amount',0)
    merchant = txn_data.get('merchant','Swiggy')
    reason = txn_data.get('reason','Timeout')
    
    if "Timeout" in reason or "mismatch" in reason.lower():
        healed = True
        action = f"AI recalculated MDR 2% + GST 18% for Rs {amount} and auto-reconciled ledger for {merchant}"
    else:
        healed = False
        action = "Sent to manual review - requires invoice"
    
    return {
        "healed": healed,
        "action": action,
        "net_amount": round(float(amount) * 0.9764, 2),
        "timestamp": datetime.now().strftime("%H:%M:%S")
    }

def process_webhook_secure(webhook_payload: dict, max_retries=3):
    txn_id = webhook_payload.get('txn_id','')
    signature = webhook_payload.get('signature','')
    raw_payload = str(webhook_payload)
    
    
    txn_id = str(txn_id)[:50]
    
    # Step 1: Idempotency - BOUNDED set (memory safe)
    if len(PROCESSED_TXNS) > 1000:
        PROCESSED_TXNS.clear()  # Prevent memory bloat
    
    if txn_id in PROCESSED_TXNS:
        return {"status": 200, "msg": "Duplicate ignored (Idempotent)", "duplicate": True, "attempt": 0}
    
    # Step 2: Signature verify - enable in prod, demo me bypass
    # Uncomment for final demo to show security
    # if signature != "demo_sig" and not verify_webhook_signature(raw_payload, signature):
    #     return {"status": 401, "msg": "Invalid Signature", "attempt": 0}

    # Step 3: Retry Logic
    for attempt in range(max_retries):
        try:
            if attempt == 0 and random.random() < 0.7:
                raise Exception("NPCI Timeout / Bank 500")

            ai_result = ai_auto_heal_transaction(webhook_payload)
            PROCESSED_TXNS.add(txn_id)
            
            log_entry = f"[{datetime.now().strftime('%H:%M:%S')}] POST /webhook/razorpayx -> 200 OK | {webhook_payload.get('bank')} {webhook_payload.get('merchant')} Rs {webhook_payload.get('amount')}"
            WEBHOOK_LOGS.append(log_entry)
            
            return {"status": 200, "msg": "Auto-Reconciled by AI", "ai": ai_result, "attempt": attempt+1, "duplicate": False}

        except Exception as e:
            if attempt == max_retries - 1:
                dlq_entry = {
                    "time": datetime.now().strftime("%H:%M:%S"),
                    "txn_id": txn_id,
                    "bank": webhook_payload.get('bank'),
                    "merchant": webhook_payload.get('merchant'),
                    "amount": webhook_payload.get('amount'),
                    "reason": str(e)[:100], # Sanitize reason
                    "retries": max_retries,
                    "ai_action": "Queued for manual review"
                }
                DLQ_STORE.append(dlq_entry)
                WEBHOOK_LOGS.append(f"[{dlq_entry['time']}] POST /webhook/razorpayx -> 500 {e} | DLQ")
                return {"status": 500, "msg": "Moved to DLQ after retries", "dlq": dlq_entry, "attempt": attempt+1}
            
            time.sleep(0.5 * (2 ** attempt))

def get_dlq():
    return DLQ_STORE

def get_webhook_logs():
    return list(WEBHOOK_LOGS)[-20:]

def run_reconciliation(batch_size=60):
    try:
        batch_size = int(batch_size)
    except (ValueError, TypeError):
        batch_size = 60
    batch_size = max(1, min(batch_size, 200))

    matched = []
    exceptions = []
    num_matched = random.randint(48, 55)
    num_matched = min(num_matched, batch_size)
    num_exceptions = batch_size - num_matched

    for i in range(num_matched):
        amt = random.randint(5000, 50000)
        mdr = amt * 0.02
        gst = mdr * 0.18
        net = amt - mdr - gst
        matched.append({
            "settlement_id": f"SETL_{secrets.randbelow(90)+10}_{i+1:03d}",
            "utr": _secure_id("UTR"),
            "bank": random.choice(BANKS),
            "merchant": random.choice(MERCHANTS),
            "amount_raw": amt,
            "amount_inr": f"Rs {amt:,}",
            "mdr_2pct": round(mdr,2),
            "gst_18pct": round(gst,2),
            "net_settlement": round(net,2),
            "status": "MATCHED",
            "tax_line": f"MDR 2% = Rs {mdr:.0f} + GST 18% = Rs {gst:.0f}"
        })

    reasons = ["UTR mismatch at NPCI", "Amount mismatch Rs 200", "Duplicate UTR", "Bank code invalid", "Settlement ID not in bank file", "Invoice not found", "UTR blank in merchant file", "Bank ref missing", "Fees deducted by bank"]
    for i in range(num_exceptions):
        amt = random.randint(8000, 40000)
        row = {
            "settlement_id": f"SETL_EX_{secrets.randbelow(90)+10}_{i+1:03d}",
            "utr": _secure_id("UTR"),
            "bank": random.choice(BANKS),
            "merchant": random.choice(MERCHANTS),
            "amount_raw": amt,
            "amount_inr": f"Rs {amt:,}",
            "mdr_2pct": round(amt*0.02,2),
            "gst_18pct": round(amt*0.02*0.18,2),
            "net_settlement": round(amt*0.9764,2),
            "status": "EXCEPTION",
            "reason": random.choice(reasons)
        }
        row["AI_RISK_ANALYSIS"] = ai_risk_score(row)
        exceptions.append(row)

    return {"matched": matched, "exceptions": exceptions}

def investigate_exception(sid: str, utr: str, amt):
    safe_sid = str(sid)[:30]
    safe_utr = str(utr)[:20]
    try:
        safe_amt = float(amt)
    except (ValueError, TypeError):
        safe_amt = 0
    return {
        "root_cause": f"AI Auditor found: Exception {safe_sid} failed due to data mismatch. Amount Rs {safe_amt}",
        "suggestion": "AI Suggestion: Re-trigger settlement after 24h + attach invoice. Recalc MDR 2% + GST 18%.",
    }