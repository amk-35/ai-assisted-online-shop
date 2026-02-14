
import json
import asyncio
import requests
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session as DBSession
from fastapi import WebSocket

from config import (
    NVIDIA_API_KEY,
    NVIDIA_INVOKE_URL,
    MODEL_ID,
    TEMPERATURE,
    MAX_TOKENS,
    TOP_P,
    SYSTEM_PROMPT_TEMPLATE
)
from tools import TOOLS
from functions import FUNCTION_REGISTRY, finalizeOrder
from session import Session


# ============================================================
# HELPER: Build system prompt with context injection
# ============================================================

def build_system_prompt(session: Session) -> str:
    """
    Build the system prompt with live session state injected.
    This is rebuilt fresh on every turn.
    """
    context_dict = session.to_context_dict()

    # Format context nicely for the model to read
    context_str = f"""
User profile:
  Skin type: {context_dict['userProfile']['skinType'] or '(not set)'}
  Concerns: {', '.join(context_dict['userProfile']['concerns']) if context_dict['userProfile']['concerns'] else '(none)'}

Current cart:
{json.dumps(context_dict['cart'], indent=2) if context_dict['cart'] else "  (empty)"}
"""

    return SYSTEM_PROMPT_TEMPLATE.format(context=context_str.strip())



# ============================================================
# HELPER: Execute a tool call
# ============================================================

def execute_tool_call(
        tool_name: str,
        tool_params: Dict[str, Any],
        session: Session,
        db: DBSession
) -> Dict[str, Any]:
    """
    Execute a single tool call.
    Returns the result dict.
    """
    if tool_name not in FUNCTION_REGISTRY:
        return {
            "error": f"Unknown function: {tool_name}"
        }

    func = FUNCTION_REGISTRY[tool_name]

    try:
        # All functions receive session + db as first two args
        result = func(session, db, **tool_params)
        return result
    except Exception as e:
        return {
            "error": f"Function {tool_name} failed: {str(e)}"
        }


# ============================================================
# SPECIAL FLOW: Checkout (collect customer info)
# ============================================================

async def handle_checkout_flow(
        session: Session,
        db: DBSession,
        websocket: WebSocket,
        cart_summary: Dict[str, Any]
) -> None:
    """
    Special flow triggered when initiateOrder is called.

    Steps:
    1. Show cart summary
    2. Ask for name, phone, address
    3. Wait for user to send them
    4. Call finalizeOrder()
    5. Confirm order
    """

    # ── Step 1: Show cart and ask for details ──
    summary_message = f"""Great! Here's what you're ordering:

"""
    for item in cart_summary["cartSummary"]["items"]:
        summary_message += f"  • {item['quantity']}x {item['name']} - MMK {item['price']:.2f}\n"

    summary_message += f"\n**Total: MMK {cart_summary['cartSummary']['total']:.2f}**\n\n"
    summary_message += "To complete your order, please provide:\n"
    summary_message += "1. Your full name\n"
    summary_message += "2. Phone number\n"
    summary_message += "3. Delivery address\n\n"
    summary_message += "You can send them in one message like:\n"
    summary_message += "`Name: John Doe, Phone: 09123456789, Address: 123 Main St` (OR)\n"
    summary_message += "`Name, Phone, Address`"

    await websocket.send_text(summary_message)

    # ── Step 2: Wait for user's response ──
    # This is handled by the websocket endpoint in main.py
    # We set a flag in session to indicate we're waiting for checkout info
    session.awaiting_checkout = True


# ============================================================
# HELPER: Parse customer info from user message
# ============================================================

def validate_phone(phone: str) -> bool:
    """
    Validate phone number format.
    Must start with 09 and have exactly 11 digits total.
    """
    import re
    # Remove spaces/dashes if any
    phone = phone.replace(" ", "").replace("-", "")
    # Check: starts with 09 and exactly 11 digits
    return bool(re.match(r"^09\d{9}$", phone))


def parse_customer_info(message: str) -> Optional[Dict[str, str]]:
    """
    Parse customer info from a message.

    Expected formats:
      - "Name: X, Phone: Y, Address: Z"
      - "John Doe, 09123456789, 123 Main St"
      - etc.

    Returns dict with keys: name, phone, address
    or None if parsing fails or phone is invalid.
    """
    import re

    # Try format: "Name: X, Phone: Y, Address: Z"
    pattern1 = r"name:\s*(.+?),\s*phone:\s*(.+?),\s*address:\s*(.+)"
    match = re.search(pattern1, message, re.IGNORECASE)
    if match:
        phone = match.group(2).strip()
        if not validate_phone(phone):
            return None  # Invalid phone format
        return {
            "name": match.group(1).strip(),
            "phone": phone,
            "address": match.group(3).strip()
        }

    # Try simple comma-separated (Name, Phone, Address)
    parts = [p.strip() for p in message.split(",")]
    if len(parts) >= 3:
        phone = parts[1]
        if not validate_phone(phone):
            return None  # Invalid phone format
        return {
            "name": parts[0],
            "phone": phone,
            "address": ", ".join(parts[2:])  # Rest is address
        }

    return None


# ============================================================
# HELPER: Complete checkout after receiving customer info
# ============================================================

async def complete_checkout(
        customer_info: Dict[str, str],
        session: Session,
        db: DBSession,
        websocket: WebSocket
) -> str:
    """
    Finalize the order with customer info.
    Returns the confirmation message text.
    """
    result = finalizeOrder(
        session=session,
        db=db,
        customer_name=customer_info["name"],
        phone=customer_info["phone"],
        address=customer_info["address"]
    )

    if result["success"]:
        confirmation = f"""✅ **Order Confirmed!**

Order ID: **{result['orderId']}**
Customer: {customer_info['name']}
Phone: {customer_info['phone']}
Address: {customer_info['address']}

Total: MMK {result['orderSummary']['total']:.2f}
Status: {result['orderSummary']['status']}

Your order has been placed successfully! Keep your Order ID for tracking.
We'll contact you at {customer_info['phone']} for delivery updates.
"""
    else:
        confirmation = f"❌ Order failed: {result['message']}"

    await websocket.send_text(confirmation)

    # Clear the checkout flag
    session.awaiting_checkout = False
    
    return confirmation