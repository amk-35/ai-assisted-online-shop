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
import os
import shutil
import time
import uuid
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, UploadFile, HTTPException, Form, File
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session as DBSession, Session, joinedload
from starlette.responses import RedirectResponse

from database import get_db, init_db
from models import Product, Order, OrderItem
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
    try:
        await websocket.accept()
    except Exception as e:
        print(f"❌ Failed to accept websocket: {e}")
        import traceback
        traceback.print_exc()
        return

    # ── Create session ──
    connection_id = str(uuid.uuid4())
    session = create_session(connection_id)

    print(f"✅ WebSocket connected: {connection_id}")
    print(f"   📊 Session created, cart initialized")

    try:
        while True:
            try:
                # ── Wait for user message ──
                user_message = await websocket.receive_text()
                print(f"📩 [{connection_id}] User: {user_message}")

            except Exception as e:
                print(f"❌ [{connection_id}] Error receiving message: {e}")
                import traceback
                traceback.print_exc()
                break

            # ── Check if we're in checkout flow ──
            if session.awaiting_checkout:
                print(f"🛒 [{connection_id}] In checkout flow, parsing customer info...")
                try:
                    # Parse customer info
                    customer_info = parse_customer_info(user_message)

                    if customer_info:
                        print(f"✅ [{connection_id}] Customer info valid: {customer_info['name']}")
                        # Valid info → complete the order
                        responded_text= await complete_checkout(customer_info, session, db, websocket)
                        await websocket.send_text("__END__")
                        # Save to history
                        session.add_to_history("user", user_message)
                        session.add_to_history("assistant", responded_text)
                    else:
                        print(f"❌ [{connection_id}] Customer info validation failed")
                        # Invalid format or invalid phone → ask again
                        response_text = (
                            "❌ Invalid format. Please check:\n"
                            "• Name: Your full name\n"
                            "• Phone: Must start with 09 and have exactly 11 digits (e.g., 09123456789)\n"
                            "• Address: Your delivery address\n\n"
                            "Example: Name: John Doe, Phone: 09123456789, Address: 123 Main St"
                        )
                        await websocket.send_text(response_text)
                        await websocket.send_text("__END__")
                        # Save to history
                        session.add_to_history("user", user_message)
                        session.add_to_history("assistant", response_text)
                except Exception as e:
                    print(f"❌ [{connection_id}] Error in checkout flow: {e}")
                    import traceback
                    traceback.print_exc()
                    await websocket.send_text("Error processing checkout. Please try again.")
                    await websocket.send_text("__END__")

            else:
                print(f"💬 [{connection_id}] Normal message flow, calling handle_message_with_streaming...")
                try:
                    # ── Normal flow: handle message through agentic loop ──
                    await handle_message_with_streaming(
                        user_message=user_message,
                        session=session,
                        db=db,
                        websocket=websocket
                    )
                    print(f"✅ [{connection_id}] Message processed successfully")
                except Exception as e:
                    print(f"❌ [{connection_id}] Error in handle_message_with_streaming: {e}")
                    import traceback
                    traceback.print_exc()
                    try:
                        await websocket.send_text(f"Error processing message: {str(e)}")
                        await websocket.send_text("__END__")
                    except:
                        pass

    except WebSocketDisconnect:
        print(f"⚠️  [{connection_id}] WebSocket disconnected by client")
        destroy_session(connection_id)

    except Exception as e:
        print(f"❌ FATAL ERROR in websocket {connection_id}: {e}")
        print(f"   Exception type: {type(e).__name__}")
        import traceback
        traceback.print_exc()
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
    max_iterations = 20
    iteration = 0

    while iteration < max_iterations:
        iteration += 1

        # ── Get active model configuration ──
        model_config = config.get_model_config()

        # ── Call NVIDIA API ──
        headers = {
            "Authorization": f"Bearer {model_config['api_key']}",
            "Accept": "application/json"
        }

        payload = {
            "model": model_config['model_id'],
            "messages": messages,
            "temperature": model_config['temperature'],
            "max_tokens": model_config['max_tokens'],
            "top_p": model_config['top_p'],
            "tools": TOOLS,
            "tool_choice": "auto",
            "stream": False
        }

        # ── Add extra_body if present (e.g., for Deepseek) ──
        if model_config['extra_body']:
            payload["extra_body"] = model_config['extra_body']

        response = requests.post(model_config['invoke_url'], headers=headers, json=payload)

        if response.status_code != 200:
            await websocket.send_text(f"Error: API returned {response}. Try again...")
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

            # Stream in chunks (optimized for concurrent sessions)
            # Larger chunks + longer delays = less server load with many concurrent users
            chunk_size = 150  # 150 chars per chunk (increased from 50)
            chunk_delay = 0.075  # 75ms between chunks (increased from 20ms)
            
            for i in range(0, len(final_text), chunk_size):
                chunk = final_text[i:i + chunk_size]
                try:
                    await websocket.send_text(chunk)
                    await asyncio.sleep(chunk_delay)  # Delay between chunks
                except Exception as e:
                    print(f"⚠️  [{session.connection_id}] Failed to send chunk: {e}")
                    return  # Client disconnected, exit gracefully

            try:
                await websocket.send_text("__END__")  # Signal end
            except Exception as e:
                print(f"⚠️  [{session.connection_id}] Failed to send END signal: {e}")

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




@app.get("/admin", response_class=HTMLResponse)
def admin_home(
    category: str = None,
    skin_type: str = None,
    db: Session = Depends(get_db)
):
    """
    Admin dashboard with category and skin type filtering.
    Query params: ?category=Cleanser&skin_type=oily
    """
    
    # Get all categories for the dropdown
    all_categories = db.query(Product.category).distinct().all()
    category_list = sorted([cat[0] for cat in all_categories if cat[0]])
    
    # Get all skin types for the dropdown
    all_skin_types_entries = db.query(Product.skin_types).all()
    skin_types_set = set()
    for entry in all_skin_types_entries:
        if entry[0]:
            types = [st.strip() for st in entry[0].split(",") if st.strip()]
            skin_types_set.update(types)
    skin_types_list = sorted(list(skin_types_set))
    
    # Filter products by category and/or skin type
    query = db.query(Product)
    if category:
        query = query.filter(Product.category.ilike(f"%{category}%"))
    if skin_type:
        query = query.filter(Product.skin_types.ilike(f"%{skin_type}%"))
    
    products = query.all()
    
    # Build table rows
    rows = "".join([
        f"<tr><td>{p.id}</td><td>{p.name}</td><td>{p.price}</td><td>{p.stock}</td>"
        f"<td><img src='/images/{p.image_filename}' width='60'></td>"
        f"<td><a href='/admin/edit/{p.id}'>Edit</a> | "
        f"<a href='/admin/delete/{p.id}'>Delete</a></td></tr>"
        for p in products
    ])
    
    # Build category dropdown options
    category_options = "".join([
        f"<option value='{cat}' {'selected' if category == cat else ''}>{cat}</option>"
        for cat in category_list
    ])
    
    # Build skin type dropdown options
    skin_type_options = "".join([
        f"<option value='{st}' {'selected' if skin_type == st else ''}>{st}</option>"
        for st in skin_types_list
    ])
    
    html = f"""
    <h1>Admin - Product Management</h1>
    <a href="/admin/new">➕ Add Product</a>
    
    <div style="margin: 15px 0;">
        <label for="category-filter">Filter by Category:</label>
        <select id="category-filter" onchange="applyFilters()">
            <option value="">-- All Categories --</option>
            {category_options}
        </select>
        
        <label for="skin-type-filter" style="margin-left: 20px;">Filter by Skin Type:</label>
        <select id="skin-type-filter" onchange="applyFilters()">
            <option value="">-- All Skin Types --</option>
            {skin_type_options}
        </select>
    </div>
    
    <table border="1" cellpadding="6">
        <tr><th>ID</th><th>Name</th><th>Price</th><th>Stock</th><th>Image</th><th>Actions</th></tr>
        {rows}
    </table>
    
    <script>
        function applyFilters() {{
            const selectedCategory = document.getElementById('category-filter').value;
            const selectedSkinType = document.getElementById('skin-type-filter').value;
            
            let url = '/admin';
            const params = [];
            
            if (selectedCategory) {{
                params.push(`category=${{selectedCategory}}`);
            }}
            if (selectedSkinType) {{
                params.push(`skin_type=${{selectedSkinType}}`);
            }}
            
            if (params.length > 0) {{
                url += '?' + params.join('&');
            }}
            
            window.location.href = url;
        }}
    </script>
    """
    return html


@app.get("/admin/new", response_class=HTMLResponse)
def new_product_form():
    return """
    <h2>Add Product</h2>
    <form method="post" action="/admin/new" enctype="multipart/form-data">
        SKU: <input name="sku"><br>
        Name: <input name="name"><br>
        Category: <input name="category"><br>
        Price: <input name="price"><br>
        Stock: <input name="stock"><br>
        Skin Types (comma): <input name="skin_types"><br>
        Concerns (comma): <input name="concerns"><br>
        Brand: <input name="brand"><br>
        Volume: <input name="volume"><br>
        Image: <input type="file" name="image"><br>
        Ingredients: <textarea name="ingredients"></textarea><br>
        Description: <textarea name="description"></textarea><br>
        <button type="submit">Save</button>
    </form>
    """


@app.post("/admin/new")
def create_product(
    sku: str = Form(...),
    name: str = Form(...),
    category: str = Form(...),
    price: float = Form(...),
    stock: int = Form(...),
    skin_types: str = Form(...),
    concerns: str = Form(...),
    brand: str = Form(...),
    volume: str = Form(...),
    ingredients: str = Form(...),
    description: str = Form(...),
    image: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    filename = save_image(image)

    product = Product(
        sku=sku,
        name=name,
        category=category,
        price=price,
        stock=stock,
        skin_types=skin_types,
        concerns=concerns,
        brand=brand,
        volume=volume,
        ingredients=ingredients,
        description=description,
        image_filename=filename
    )
    db.add(product)
    db.commit()
    return RedirectResponse("/admin", status_code=303)


@app.get("/admin/edit/{product_id}", response_class=HTMLResponse)
def edit_product_form(product_id: int, db: Session = Depends(get_db)):
    p = db.query(Product).filter(Product.id == product_id).first()
    if not p:
        return "Not found"

    return f"""
    <h2>Edit Product</h2>
    <form method="post" action="/admin/edit/{p.id}" enctype="multipart/form-data">
        SKU: <input name="sku" value="{p.sku}"><br>
        Name: <input name="name" value="{p.name}"><br>
        Category: <input name="category" value="{p.category}"><br>
        Price: <input name="price" value="{p.price}"><br>
        Stock: <input name="stock" value="{p.stock}"><br>
        Skin Types: <input name="skin_types" value="{p.skin_types}"><br>
        Concerns: <input name="concerns" value="{p.concerns}"><br>
        Brand: <input name="brand" value="{p.brand}"><br>
        Volume: <input name="volume" value="{p.volume}"><br>
        Current Image:<br>
        <img src='/images/{p.image_filename}' width='120'><br>
        Replace Image: <input type="file" name="image"><br>
        Ingredients: <textarea name="ingredients">{p.ingredients}</textarea><br>
        Description: <textarea name="description">{p.description}</textarea><br>
        <button type="submit">Update</button>
    </form>
    """


@app.post("/admin/edit/{product_id}")
def update_product(
    product_id: int,
    sku: str = Form(...),
    name: str = Form(...),
    category: str = Form(...),
    price: float = Form(...),
    stock: int = Form(...),
    skin_types: str = Form(...),
    concerns: str = Form(...),
    brand: str = Form(...),
    volume: str = Form(...),
    ingredients: str = Form(...),
    description: str = Form(...),
    image: UploadFile = File(None),
    db: Session = Depends(get_db)
):
    p = db.query(Product).filter(Product.id == product_id).first()
    if not p:
        raise HTTPException(status_code=404)

    if image and image.filename:
        filename = save_image(image)
        p.image_filename = filename

    p.sku = sku
    p.name = name
    p.category = category
    p.price = price
    p.stock = stock
    p.skin_types = skin_types
    p.concerns = concerns
    p.brand = brand
    p.volume = volume
    p.ingredients = ingredients
    p.description = description

    db.commit()
    return RedirectResponse("/admin", status_code=303)


@app.get("/admin/delete/{product_id}")
def delete_product(product_id: int, db: Session = Depends(get_db)):
    p = db.query(Product).filter(Product.id == product_id).first()
    if p:
        db.delete(p)
        db.commit()
    return RedirectResponse("/admin", status_code=303)


# ------------------
# Get Products by IDs (for chat memory / order sync)
# Example: /api/products/by-ids?ids=1,3,7
# ------------------
@app.get("/api/products/by-ids")
def get_products_by_ids(ids: str, db: Session = Depends(get_db)):
    # Parse comma-separated IDs
    try:
        id_list = [int(i.strip()) for i in ids.split(",") if i.strip().isdigit()]
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid IDs format")

    if not id_list:
        return []

    products = (
        db.query(Product)
        .filter(Product.id.in_(id_list))
        .all()
    )

    return products


# ------------------
# Get all unique categories
# ------------------
@app.get("/api/categories")
def get_categories(db: Session = Depends(get_db)):
    """Return all unique categories from the products table."""
    
    # Get all distinct categories
    categories = db.query(Product.category).distinct().all()
    
    # Extract category strings and remove None values
    category_list = [
        cat[0] 
        for cat in categories 
        if cat[0]
    ]
    
    # Sort alphabetically
    category_list = sorted(category_list)
    
    return {
        "count": len(category_list),
        "categories": category_list
    }


# ------------------
# Get all unique skin types
# ------------------
@app.get("/api/skin-types")
def get_skin_types(db: Session = Depends(get_db)):
    """
    Return all unique skin types from the products table.
    Skin types are stored as comma-separated values, so we parse and deduplicate them.
    """
    
    # Get all skin_types entries
    all_entries = db.query(Product.skin_types).all()
    
    # Parse comma-separated values and collect unique skin types
    skin_types_set = set()
    for entry in all_entries:
        if entry[0]:
            # Split by comma, strip whitespace, and add to set
            types = [
                st.strip() 
                for st in entry[0].split(",") 
                if st.strip()
            ]
            skin_types_set.update(types)
    
    # Convert to sorted list
    skin_types_list = sorted(list(skin_types_set))
    
    return {
        "count": len(skin_types_list),
        "skin_types": skin_types_list
    }




# ------------------
# Helper: Save Image
# ------------------
def save_image(file: UploadFile):
    ext = os.path.splitext(file.filename)[1]
    filename = f"{int(time.time())}_{file.filename}"
    filepath = os.path.join("product_images", filename)
    with open(filepath, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    return filename


class StatusUpdateRequest(BaseModel):
    status: str


# ============================================================
# API ENDPOINTS
# ============================================================

@app.get("/api/orders")
def get_orders(search: str = None, db: Session = Depends(get_db)):
    query = db.query(Order).order_by(Order.created_at.desc())

    if search:
        # We now search across three columns: name, phone, OR Order ID
        query = query.filter(
            or_(
                Order.customer_name.ilike(f"%{search}%"),
                Order.phone.ilike(f"%{search}%"),
                Order.id.ilike(f"%{search}%")  # Added this line
            )
        )

    orders = query.all()
    return [
        {
            "id": o.id,
            "customer_name": o.customer_name,
            "phone": o.phone,
            "status": o.status,
            "created_at": o.created_at.isoformat() if o.created_at else None
        }
        for o in orders
    ]


@app.get("/api/orders/{order_id}")
def get_order_details(order_id: str, db: Session = Depends(get_db)):
    order = db.query(Order).options(
        joinedload(Order.items).joinedload(OrderItem.product)
    ).filter(Order.id == order_id).first()

    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    items_data = []
    total_cost = 0.0
    for item in order.items:
        line_total = item.price * item.quantity
        total_cost += line_total
        items_data.append({
            "sku": item.product_sku,
            "product_name": item.product.name if item.product else "Unknown",
            "quantity": item.quantity,
            "price": item.price,
            "line_total": line_total
        })

    return {
        "id": order.id,
        "customer_name": order.customer_name,
        "phone": order.phone,
        "address": order.address,
        "status": order.status,
        "total_cost": round(total_cost, 2),
        "items": items_data
    }


@app.patch("/api/orders/{order_id}/status")
def update_order_status(order_id: str, payload: StatusUpdateRequest, db: Session = Depends(get_db)):
    valid_statuses = ["pending", "confirmed", "shipped", "delivered", "rejected"]

    if payload.status not in valid_statuses:
        raise HTTPException(status_code=400, detail="Invalid status")

    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    # Prevent re-processing if already rejected
    if order.status == "rejected":
        raise HTTPException(status_code=400, detail="Order is already rejected.")

    # LOGIC: If status is being changed TO rejected, restore stock
    if payload.status == "rejected":
        for item in order.items:
            product = db.query(Product).filter(Product.sku == item.product_sku).first()
            if product:
                product.stock += item.quantity  # Increase stock back

    order.status = payload.status
    db.commit()

    return {"message": "Status updated", "new_status": order.status}

# ============================================================
# HTML ADMIN UI
# ============================================================

@app.get("/admin/order", response_class=HTMLResponse)
def admin_dashboard():
    """Serves the simple HTML/JS UI for Admin Management."""
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Admin - Order Management</title>
        <style>
           .rejected { background: #e74c3c; color: #fff; } /* Red for rejected */
            button:disabled { background: #bdc3c7; cursor: not-allowed; }
            body { font-family: Arial, sans-serif; margin: 20px; background: #f4f4f9; color: #333; }
            h1 { color: #2c3e50; }
            .container { display: flex; gap: 20px; }
            .left-panel, .right-panel { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
            .left-panel { flex: 2; }
            .right-panel { flex: 1; display: none; }
            table { width: 100%; border-collapse: collapse; margin-top: 15px; }
            th, td { padding: 10px; border-bottom: 1px solid #ddd; text-align: left; }
            th { background-color: #f8f9fa; }
            input[type="text"] { padding: 8px; width: 300px; border: 1px solid #ccc; border-radius: 4px; }
            button { padding: 8px 12px; cursor: pointer; background: #3498db; color: white; border: none; border-radius: 4px; }
            button:hover { background: #2980b9; }
            .status-badge { padding: 4px 8px; border-radius: 12px; font-size: 0.85em; font-weight: bold; text-transform: uppercase; }
            .pending { background: #f1c40f; color: #fff; }
            .confirmed { background: #3498db; color: #fff; }
            .shipped { background: #9b59b6; color: #fff; }
            .delivered { background: #2ecc71; color: #fff; }
            select { padding: 8px; margin-right: 10px; border-radius: 4px; }
        </style>
    </head>
    <body>

        <h1>Order Management Dashboard</h1>

        <div class="container">
            <div class="left-panel">
                <div>
                    <input type="text" id="searchInput" placeholder="Search by name, phone, or Order ID..." onkeyup="if(event.key === 'Enter') fetchOrders()">
                    <button onclick="fetchOrders()">Search</button>
                    <button onclick="document.getElementById('searchInput').value=''; fetchOrders()" style="background:#95a5a6;">Clear</button>
                </div>

                <table>
                    <thead>
                        <tr>
                            <th>Order ID</th>
                            <th>Customer</th>
                            <th>Phone</th>
                            <th>Status</th>
                            <th>Action</th>
                        </tr>
                    </thead>
                    <tbody id="ordersTableBody">
                        </tbody>
                </table>
            </div>

            <div class="right-panel" id="detailsPanel">
                <h3>Order Details <span id="detailOrderId"></span></h3>
    <p><strong>Name:</strong> <span id="detailName"></span></p>
    <p><strong>Phone:</strong> <span id="detailPhone"></span></p>
    <p><strong>Address:</strong> <span id="detailAddress"></span></p>
    <p style="font-size: 1.1em; color: #27ae60;"><strong>Total: $<span id="detailTotal"></span></strong></p>
                <hr style="border: 0; border-top: 1px solid #eee; margin: 15px 0;">

                <div style="margin-bottom: 15px;">
                    <label><strong>Update Status:</strong></label><br><br>
                    <select id="statusSelect">
    <option value="pending">Pending</option>
    <option value="confirmed">Confirmed</option>
    <option value="shipped">Shipped</option>
    <option value="delivered">Delivered</option>
    <option value="rejected">Rejected</option>
</select>
<button id="saveStatusBtn" onclick="updateStatus()">Save Status</button>
                </div>

                <h4>Items</h4>
                <table style="font-size: 0.9em;">
                    <thead>
                        <tr>
                            <th>Product</th>
                            <th>Qty</th>
                            <th>Price</th>
                        </tr>
                    </thead>
                    <tbody id="itemsTableBody">
                    </tbody>
                </table>
                <br>
                <button onclick="closeDetails()" style="background:#e74c3c;">Close Details</button>
            </div>
        </div>

        <script>
            let currentOrderId = null;

            async function fetchOrders() {
                const search = document.getElementById('searchInput').value;
                const url = search ? `/api/orders?search=${encodeURIComponent(search)}` : `/api/orders`;

                const response = await fetch(url);
                const orders = await response.json();

                const tbody = document.getElementById('ordersTableBody');
                tbody.innerHTML = '';

                orders.forEach(order => {
                    const tr = document.createElement('tr');
                    tr.innerHTML = `
                        <td>${order.id}</td>
                        <td>${order.customer_name}</td>
                        <td>${order.phone}</td>
                        <td><span class="status-badge ${order.status}">${order.status}</span></td>
                        <td><button onclick="viewDetails('${order.id}')">View</button></td>
                    `;
                    tbody.appendChild(tr);
                });
            }

            async function viewDetails(orderId) {
                currentOrderId = orderId;
                const response = await fetch(`/api/orders/${orderId}`);
                const order = await response.json();

                document.getElementById('detailOrderId').textContent = `(#${order.id})`;
                document.getElementById('detailName').textContent = order.customer_name;
                document.getElementById('detailPhone').textContent = order.phone;
                document.getElementById('detailAddress').textContent = order.address;
                document.getElementById('statusSelect').value = order.status;
                document.getElementById('detailTotal').textContent = order.total_cost.toFixed(2);
                
                const statusSelect = document.getElementById('statusSelect');
    const saveBtn = document.getElementById('saveStatusBtn'); // Make sure your button has this ID

    statusSelect.value = order.status;

    // Logic: Disable button and select if status is 'rejected' or 'delivered'
    if (order.status === 'rejected' || order.status === 'delivered') {
        statusSelect.disabled = true;
        saveBtn.disabled = true;
    } else {
        statusSelect.disabled = false;
        saveBtn.disabled = false;
    }

                const tbody = document.getElementById('itemsTableBody');
                tbody.innerHTML = '';

                order.items.forEach(item => {
                    const tr = document.createElement('tr');
                    tr.innerHTML = `
                        <td>${item.product_name}<br><small style="color:#7f8c8d;">SKU: ${item.sku}</small></td>
                        <td>${item.quantity}</td>
                        <td>$${item.price}</td>
                    `;
                    tbody.appendChild(tr);
                });

                document.getElementById('detailsPanel').style.display = 'block';
            }

            async function updateStatus() {
                if (!currentOrderId) return;

                const newStatus = document.getElementById('statusSelect').value;
                const response = await fetch(`/api/orders/${currentOrderId}/status`, {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ status: newStatus })
                });

                if (response.ok) {
                    alert('Status updated successfully');
                    fetchOrders(); // Refresh table
                    viewDetails(currentOrderId); // Refresh details view
                } else {
                    alert('Failed to update status');
                }
            }

            function closeDetails() {
                document.getElementById('detailsPanel').style.display = 'none';
                currentOrderId = null;
            }

            // Load orders on page startup
            window.onload = fetchOrders;
        </script>
    </body>
    </html>
    """

# ============================================================
# RUN THE APP
# ============================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)