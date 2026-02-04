# ============================================================
# chat.py — Agentic Loop Orchestrator
# ============================================================
# This is the brain of the chatbot.
#
# Flow:
# 1. User message arrives via websocket
# 2. Build system prompt with session context
# 3. Call NVIDIA API with tools
# 4. If model returns tool_calls:
#    - Execute all functions in parallel
#    - Send results back to model
#    - Repeat until model returns text
# 5. Stream the final text response to websocket
# 6. Update session state (lastShownProducts, userProfile)
#
# Special case: initiateOrder triggers checkout flow
# ============================================================

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
    FREQUENCY_PENALTY,
    PRESENCE_PENALTY,
    SYSTEM_PROMPT_TEMPLATE
)
from tools import TOOLS
from functions import FUNCTION_REGISTRY, finalizeOrder
from session import Session, ShownProduct


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
Last shown products:
{json.dumps(context_dict['lastShownProducts'], indent=2) if context_dict['lastShownProducts'] else "  (none)"}

User profile:
  Skin type: {context_dict['userProfile']['skinType'] or '(not set)'}
  Concerns: {', '.join(context_dict['userProfile']['concerns']) if context_dict['userProfile']['concerns'] else '(none)'}

Current cart:
{json.dumps(context_dict['cart'], indent=2) if context_dict['cart'] else "  (empty)"}
"""

    return SYSTEM_PROMPT_TEMPLATE.format(context=context_str.strip())


# ============================================================
# HELPER: Call NVIDIA API
# ============================================================

def call_nvidia_api(
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict]] = None,
        stream: bool = False
) -> Dict[str, Any]:
    """
    Call NVIDIA API with messages and optional tools.
    Returns the full response JSON.
    """
    headers = {
        "Authorization": f"Bearer {NVIDIA_API_KEY}",
        "Accept": "text/event-stream" if stream else "application/json"
    }

    payload = {
        "model": MODEL_ID,
        "messages": messages,
        "temperature": TEMPERATURE,
        "max_tokens": MAX_TOKENS,
        "top_p": TOP_P,
        "frequency_penalty": FREQUENCY_PENALTY,
        "presence_penalty": PRESENCE_PENALTY,
        "stream": stream
    }

    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    response = requests.post(NVIDIA_INVOKE_URL, headers=headers, json=payload)

    if response.status_code != 200:
        raise Exception(f"NVIDIA API error: {response.status_code} - {response.text}")

    if stream:
        return response  # Return response object for streaming
    else:
        return response.json()


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
# MAIN: Agentic loop
# ============================================================

async def handle_message(
        user_message: str,
        session: Session,
        db: DBSession,
        websocket: WebSocket
) -> None:
    """
    Main orchestrator.
    Handles one user message through the full agentic loop.
    Streams the response back via websocket.
    """

    # ── Build messages array ──
    system_prompt = build_system_prompt(session)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message}
    ]

    # ── Agentic loop: keep calling until we get a text response ──
    max_iterations = 10  # Prevent infinite loops
    iteration = 0

    while iteration < max_iterations:
        iteration += 1

        # ── Call NVIDIA API ──
        response = call_nvidia_api(messages, tools=TOOLS, stream=False)

        # ── Extract assistant message ──
        if not response.get("choices") or len(response["choices"]) == 0:
            await websocket.send_json({
                "type": "error",
                "message": "No response from model"
            })
            return

        assistant_message = response["choices"][0]["message"]
        messages.append(assistant_message)

        # ── Check: does it have tool_calls? ──
        tool_calls = assistant_message.get("tool_calls", [])

        if not tool_calls:
            # ── No tool calls → this is the final text response ──
            final_text = assistant_message.get("content", "")

            # Stream it to the user
            await stream_response(final_text, websocket)

            # Update session state based on the response
            # (we'll extract products shown, profile updates, etc.)
            # For now, we rely on functions already updating session during execution

            return

        # ── Model returned tool_calls → execute them ──
        await websocket.send_json({
            "type": "thinking",
            "message": "Let me check that for you..."
        })

        # Execute all tool calls (can be parallel, but we'll do sequential for safety)
        for tool_call in tool_calls:
            func_name = tool_call["function"]["name"]
            func_params = json.loads(tool_call["function"]["arguments"])
            tool_call_id = tool_call["id"]

            # ── Execute the function ──
            result = execute_tool_call(func_name, func_params, session, db)

            # ── Check for special signals ──
            if result.get("type") == "initiate_checkout":
                # Special flow: collect customer info
                await handle_checkout_flow(session, db, websocket, result)
                return  # Exit the loop — checkout flow takes over

            # ── Send result back to model ──
            messages.append({
                "role": "tool",
                "name": func_name,
                "content": json.dumps(result),
                "tool_call_id": tool_call_id
            })

        # ── Loop again: model will either call more tools or respond ──

    # ── Fallback if we hit max iterations ──
    await websocket.send_json({
        "type": "error",
        "message": "Processing took too long. Please try rephrasing your request."
    })


# ============================================================
# HELPER: Stream text response to websocket
# ============================================================

async def stream_response(text: str, websocket: WebSocket) -> None:
    """
    Stream text response to websocket.
    For now, we send the full text at once.

    Later, you can implement true streaming by calling NVIDIA API
    with stream=True and parsing SSE events.
    """
    await websocket.send_json({
        "type": "message",
        "content": text
    })


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
        summary_message += f"  • {item['quantity']}x {item['name']} - ${item['price']:.2f}\n"

    summary_message += f"\n**Total: ${cart_summary['cartSummary']['total']:.2f}**\n\n"
    summary_message += "To complete your order, please provide:\n"
    summary_message += "1. Your full name\n"
    summary_message += "2. Phone number\n"
    summary_message += "3. Delivery address\n\n"
    summary_message += "You can send them in one message like:\n"
    summary_message += "`Name: John Doe, Phone: 09123456789, Address: 123 Main St`"

    await websocket.send_json({
        "type": "message",
        "content": summary_message
    })

    # ── Step 2: Wait for user's response ──
    # This is handled by the websocket endpoint in main.py
    # We set a flag in session to indicate we're waiting for checkout info
    session.awaiting_checkout = True


# ============================================================
# HELPER: Parse customer info from user message
# ============================================================

def parse_customer_info(message: str) -> Optional[Dict[str, str]]:
    """
    Parse customer info from a message.

    Expected formats:
      - "Name: X, Phone: Y, Address: Z"
      - "John Doe, 09123456789, 123 Main St"
      - etc.

    Returns dict with keys: name, phone, address
    or None if parsing fails.
    """
    import re

    # Try format: "Name: X, Phone: Y, Address: Z"
    pattern1 = r"name:\s*(.+?),\s*phone:\s*(.+?),\s*address:\s*(.+)"
    match = re.search(pattern1, message, re.IGNORECASE)
    if match:
        return {
            "name": match.group(1).strip(),
            "phone": match.group(2).strip(),
            "address": match.group(3).strip()
        }

    # Try simple comma-separated (Name, Phone, Address)
    parts = [p.strip() for p in message.split(",")]
    if len(parts) >= 3:
        return {
            "name": parts[0],
            "phone": parts[1],
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
) -> None:
    """
    Finalize the order with customer info.
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

Total: ${result['orderSummary']['total']:.2f}
Status: {result['orderSummary']['status']}

Your order has been placed successfully! Keep your Order ID for tracking.
We'll contact you at {customer_info['phone']} for delivery updates.
"""
    else:
        confirmation = f"❌ Order failed: {result['message']}"

    await websocket.send_json({
        "type": "message",
        "content": confirmation
    })

    # Clear the checkout flag
    session.awaiting_checkout = False