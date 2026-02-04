# ============================================================
# main.py — FastAPI Application
# ============================================================
# Endpoints:
#   GET  /                  → Serve the HTML UI
#   GET  /api/products      → Return all products as JSON
#   WS   /ws/chat           → WebSocket chat endpoint
#
# WebSocket flow:
#   1. Client connects → create Session
#   2. Client sends message → route to handle_message or complete_checkout
#   3. Stream response back character-by-character
#   4. Client disconnects → destroy Session
# ============================================================

import asyncio
import uuid
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session as DBSession

from database import get_db, init_db
from models import Product
from session import create_session, get_session, destroy_session
from chat import parse_customer_info, complete_checkout
import config

# ── Initialize FastAPI app ────────────────────────────────────
app = FastAPI(title="Skincare Chatbot")

# ── Serve static files (images) ───────────────────────────────
# Your HTML references images via /images/<filename>
# Make sure you have an "images" folder in the same directory as main.py
app.mount("/images", StaticFiles(directory="product_images"), name="images")


# ── Startup: create database tables ───────────────────────────
@app.on_event("startup")
def on_startup():
    init_db()
    print("✅ Database initialized")


# ============================================================
# ENDPOINT: Serve HTML UI
# ============================================================

@app.get("/", response_class=HTMLResponse)
async def serve_ui():
    """
    Serve the HTML chat interface.
    Reads from index.html in the same directory.
    """
    with open("index.html", "r", encoding="utf-8") as f:
        html_content = f.read()
    return HTMLResponse(content=html_content)


# ============================================================
# ENDPOINT: Get all products (for the product grid)
# ============================================================

@app.get("/api/products")
async def get_products(db: DBSession = Depends(get_db)):
    """
    Return all products as JSON for the product grid.
    """
    products = db.query(Product).all()

    return [
        {
            "id": p.id,
            "sku": p.sku,
            "name": p.name,
            "brand": p.brand,
            "category": p.category,
            "price": p.price,
            "stock": p.stock,
            "description": p.description,
            "skin_types": p.skin_types,
            "concerns": p.concerns,
            "image_filename": p.image_filename,
            "volume": p.volume
        }
        for p in products
    ]


# ============================================================
# WEBSOCKET: Chat endpoint with streaming
# ============================================================

@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket, db: DBSession = Depends(get_db)):
    """
    WebSocket chat endpoint.

    Flow:
    1. Accept connection
    2. Create a Session for this connection
    3. Listen for messages
    4. Route to either handle_message or complete_checkout
    5. Stream response back character-by-character
    6. On disconnect, destroy Session
    """
    await websocket.accept()

    # ── Create session ──
    connection_id = str(uuid.uuid4())
    session = create_session(connection_id)

    print(f"✅ WebSocket connected: {connection_id}")

    try:
        while True:
            # ── Wait for user message ──
            user_message = await websocket.receive_text()

            print(f"📩 [{connection_id}] User: {user_message}")

            # ── Check if we're in checkout flow ──
            if session.awaiting_checkout:
                # Parse customer info
                customer_info = parse_customer_info(user_message)

                if customer_info:
                    # Valid info → complete the order
                    await complete_checkout(customer_info, session, db, websocket)
                    # Save to history
                    session.add_to_history("user", user_message)
                    session.add_to_history("assistant", f"Order placed for {customer_info['name']}")
                else:
                    # Invalid format → ask again
                    response_text = (
                        "I couldn't parse that. Please send your details like this:\n"
                        "Name: John Doe, Phone: 09123456789, Address: 123 Main St"
                    )
                    await websocket.send_text(response_text)
                    await websocket.send_text("__END__")
                    # Save to history
                    session.add_to_history("user", user_message)
                    session.add_to_history("assistant", response_text)

            else:
                # ── Normal flow: handle message through agentic loop ──
                await handle_message_with_streaming(
                    user_message=user_message,
                    session=session,
                    db=db,
                    websocket=websocket
                )

    except WebSocketDisconnect:
        print(f"❌ WebSocket disconnected: {connection_id}")
        destroy_session(connection_id)

    except Exception as e:
        print(f"❌ Error in websocket {connection_id}: {e}")
        destroy_session(connection_id)
        raise


# ============================================================
# HELPER: Handle message with true streaming
# ============================================================

async def handle_message_with_streaming(
        user_message: str,
        session,
        db: DBSession,
        websocket: WebSocket
):
    """
    The agentic loop with character-by-character streaming + conversation history.

    Flow:
    1. Get messages from session (includes history + system prompt)
    2. Call NVIDIA API (non-streaming to check for tool calls)
    3. If tool_calls → execute them, append results, loop
    4. If text response → STREAM it character-by-character
    5. Save user message + assistant response to history
    """
    import requests
    import json
    from chat import execute_tool_call, handle_checkout_flow
    from tools import TOOLS

    # ── Build messages with history ──
    messages = session.get_messages_for_api(user_message)

    # ── Agentic loop ──
    max_iterations = 10
    iteration = 0

    while iteration < max_iterations:
        iteration += 1

        # ── Call NVIDIA API ──
        headers = {
            "Authorization": f"Bearer {config.NVIDIA_API_KEY}",
            "Accept": "application/json"
        }

        payload = {
            "model": config.MODEL_ID,
            "messages": messages,
            "temperature": config.TEMPERATURE,
            "max_tokens": config.MAX_TOKENS,
            "top_p": config.TOP_P,
            "tools": TOOLS,
            "tool_choice": "auto",
            "stream": False
        }

        response = requests.post(config.NVIDIA_INVOKE_URL, headers=headers, json=payload)

        if response.status_code != 200:
            await websocket.send_text(f"Error: API returned {response.status_code}")
            await websocket.send_text("__END__")
            return

        response_json = response.json()
        assistant_message = response_json["choices"][0]["message"]
        messages.append(assistant_message)

        # ── Check for tool calls ──
        tool_calls = assistant_message.get("tool_calls", [])

        if not tool_calls:
            # ── No tool calls → final response, STREAM it ──
            final_text = assistant_message.get("content", "")

            # Stream character by character
            for char in final_text:
                await websocket.send_text(char)
                await asyncio.sleep(0.01)  # 10ms per char = ~100 chars/sec

            await websocket.send_text("__END__")  # Signal end

            # ── Save to conversation history ──
            session.add_to_history("user", user_message)
            session.add_to_history("assistant", final_text)

            return

        # ── Execute tool calls ──
        for tool_call in tool_calls:
            func_name = tool_call["function"]["name"]
            func_params = json.loads(tool_call["function"]["arguments"])
            tool_call_id = tool_call["id"]

            print(f"🔧 [{session.connection_id}] Calling {func_name}({func_params})")

            # Execute
            result = execute_tool_call(func_name, func_params, session, db)

            # Check for checkout signal
            if result.get("type") == "initiate_checkout":
                # Trigger checkout flow
                await handle_checkout_flow(session, db, websocket, result)
                await websocket.send_text("__END__")

                # Save to history
                session.add_to_history("user", user_message)
                session.add_to_history("assistant", "Starting checkout process...")

                return

            # Add tool result to messages
            messages.append({
                "role": "tool",
                "name": func_name,
                "content": json.dumps(result),
                "tool_call_id": tool_call_id
            })

        # Loop again

    # ── Max iterations reached ──
    await websocket.send_text("Processing took too long. Please try again.")
    await websocket.send_text("__END__")


# ============================================================
# RUN THE APP
# ============================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)