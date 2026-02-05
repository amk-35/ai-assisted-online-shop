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
from sqlalchemy.orm import Session as DBSession, Session
from starlette.responses import RedirectResponse

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
                await asyncio.sleep(0.02)  # 10ms per char = ~100 chars/sec

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


# ============================================================
# RUN THE APP
# ============================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)