# ============================================================
# functions.py — Tool function implementations
# ============================================================
# Each function here corresponds to a tool definition in tools.py.
# They are called by the agentic loop when Mistral returns tool_calls.
#
# All functions return dict (serialized to JSON for the model).
# All functions receive a Session object + DB session.
# ============================================================

from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session as DBSession
from sqlalchemy import or_, and_
from models import Product, Order, OrderItem
from session import Session, ShownProduct
import json


# ============================================================
# KNOWLEDGE
# ============================================================

def getSkincareKnowledge(
        session: Session,
        db: DBSession,
        topic: str,
        skinType: Optional[str] = None,
        concern: Optional[str] = None
) -> dict:
    """
    This function doesn't actually need to DO anything —
    the model answers using its own knowledge.

    We just return a signal that tells the orchestrator:
    "Let the model answer this directly, don't inject a result."

    OR, if you have a curated knowledge base, query it here.
    """
    return {
        "type": "knowledge_question",
        "topic": topic,
        "note": "The model will answer this using its own knowledge. No limitDB query needed."
    }


# ============================================================
# PRODUCTS
# ============================================================

def searchProducts(
        session: Session,
        db: DBSession,
        query: Optional[str] = None,
        sku: Optional[str] = None,
        category: Optional[str] = None,
        skinType: Optional[str] = None,
        concern: Optional[str] = None,
        brand: Optional[str] = None,
        minPrice: Optional[float] = None,
        maxPrice: Optional[float] = None,
        stock: Optional[bool] = None,
        limit: int = 10
) -> dict:
    """
    Robust product search with multiple filters and fallback logic.
    
    All filters are optional. When multiple filters are provided,
    results must match ALL filters (AND logic).
    
    Handles compound categories: searching for "essence" or "serums"
    will match products with category "Essence / Serums".
    
    Fallback: If exact filters return no results, searches with looser criteria.
    """
    
    def build_query(base_query, strict: bool = True):
        """Build query with filters. If strict=False, loosens some criteria."""
        q = base_query
        
        # ── Free-text query (name, description, ingredients) ──
        if query:
            search_term = f"%{query}%"
            q = q.filter(or_(
                Product.name.ilike(search_term),
                Product.description.ilike(search_term),
                Product.ingredients.ilike(search_term) if Product.ingredients else False
            ))
        
        # ── SKU search (exact or partial) ──
        if sku:
            q = q.filter(Product.sku.ilike(f"%{sku}%"))
        
        # ── Brand search ──
        if brand:
            q = q.filter(Product.brand.ilike(f"%{brand}%"))
        
        # ── Category search with compound category support ──
        if category:
            cat_lower = category.lower()
            # Split category by "/" to handle compound categories
            # e.g., "essence / serums" → ["essence", "serums"]
            cat_parts = [part.strip() for part in category.split("/")]
            
            # Match if ANY part of the search category is in the product category
            or_conditions = [Product.category.ilike(f"%{part}%") for part in cat_parts]
            q = q.filter(or_(*or_conditions))
        
        # ── Skin type search (comma-separated field) ──
        if skinType:
            q = q.filter(Product.skin_types.ilike(f"%{skinType}%"))
        
        # ── Concern search (comma-separated field) ──
        if concern:
            q = q.filter(Product.concerns.ilike(f"%{concern}%"))
        
        # ── Price range ──
        if minPrice is not None:
            q = q.filter(Product.price >= minPrice)
        if maxPrice is not None:
            q = q.filter(Product.price <= maxPrice)
        
        # ── Stock availability ──
        if stock is not None:
            if stock:
                q = q.filter(Product.stock > 0)
            else:
                q = q.filter(Product.stock == 0)
        
        return q
    
    # ── Attempt strict search first ──
    base_query = db.query(Product)
    strict_query = build_query(base_query, strict=True)
    products = strict_query.limit(limit).all()
    filters_applied = "strict"
    
    # ── Fallback 1: If no results and multiple filters, try without category ──
    if not products and category and (query or concern or brand):
        base_query = db.query(Product)
        fallback_query = db.query(Product)
        # Rebuild without category
        if query:
            search_term = f"%{query}%"
            fallback_query = fallback_query.filter(or_(
                Product.name.ilike(search_term),
                Product.description.ilike(search_term),
                Product.ingredients.ilike(search_term) if Product.ingredients else False
            ))
        if brand:
            fallback_query = fallback_query.filter(Product.brand.ilike(f"%{brand}%"))
        if concern:
            fallback_query = fallback_query.filter(Product.concerns.ilike(f"%{concern}%"))
        if minPrice is not None:
            fallback_query = fallback_query.filter(Product.price >= minPrice)
        if maxPrice is not None:
            fallback_query = fallback_query.filter(Product.price <= maxPrice)
        if stock is not None:
            if stock:
                fallback_query = fallback_query.filter(Product.stock > 0)
            else:
                fallback_query = fallback_query.filter(Product.stock == 0)
        
        products = fallback_query.limit(limit).all()
        filters_applied = "fallback_1_no_category"
    
    # ── Fallback 2: If still no results and query provided, search by query alone ──
    if not products and query:
        search_term = f"%{query}%"
        fallback_query = db.query(Product).filter(or_(
            Product.name.ilike(search_term),
            Product.description.ilike(search_term),
            Product.ingredients.ilike(search_term) if Product.ingredients else False
        ))
        if stock is not None:
            if stock:
                fallback_query = fallback_query.filter(Product.stock > 0)
            else:
                fallback_query = fallback_query.filter(Product.stock == 0)
        
        products = fallback_query.limit(limit).all()
        filters_applied = "fallback_2_query_only"
    
    # ── Fallback 3: If still no results, return popular/high-stock products ──
    if not products:
        fallback_query = db.query(Product)
        if stock is None or stock:  # Show in-stock items by default
            fallback_query = fallback_query.filter(Product.stock > 0)
        products = fallback_query.order_by(Product.stock.desc()).limit(limit).all()
        filters_applied = "fallback_3_popular"
    
    if not products:
        return {
            "found": False,
            "message": "No products found matching those filters.",
            "filters_used": {
                "query": query,
                "sku": sku,
                "category": category,
                "skinType": skinType,
                "concern": concern,
                "brand": brand,
                "minPrice": minPrice,
                "maxPrice": maxPrice,
                "stock": stock,
                "limit": limit
            },
            "fallback_applied": filters_applied
        }

    # ── Update session.lastShownProducts ──
    shown = [
        ShownProduct(
            position=i + 1,
            product_id=p.id,
            name=p.name,
            price=p.price,
            sku=p.sku
        )
        for i, p in enumerate(products)
    ]
    session.update_last_shown(shown)

    # ── Return results ──
    return {
        "found": True,
        "count": len(products),
        "fallback_applied": filters_applied if filters_applied != "strict" else None,
        "products": [
            {
                "position": i + 1,
                "productId": p.id,
                "sku": p.sku,
                "name": p.name,
                "brand": p.brand,
                "category": p.category,
                "price": p.price,
                "stock": p.stock,
                "description": p.description[:150] + "..." if len(p.description) > 150 else p.description,
                "skinTypes": p.skin_types,
                "concerns": p.concerns
            }
            for i, p in enumerate(products)
        ]
    }


def getProductDetail(
        session: Session,
        db: DBSession,
        productId: int
) -> dict:
    """
    Get full details for one product.
    Returns ingredients, full description, etc.
    """
    product = db.query(Product).filter(Product.id == productId).first()

    if not product:
        return {
            "found": False,
            "message": f"Product with ID {productId} not found."
        }

    return {
        "found": True,
        "product": {
            "productId": product.id,
            "sku": product.sku,
            "name": product.name,
            "brand": product.brand,
            "category": product.category,
            "price": product.price,
            "stock": product.stock,
            "volume": product.volume,
            "description": product.description,
            "ingredients": product.ingredients,
            "skinTypes": product.skin_types,
            "concerns": product.concerns,
            "imageFilename": product.image_filename
        }
    }


# ============================================================
# CART
# ============================================================

def getCartState(
        session: Session,
        db: DBSession
) -> dict:
    """Get the current cart contents."""
    items = session.get_cart_items()

    if not items:
        return {
            "empty": True,
            "message": "Your cart is empty."
        }

    return {
        "empty": False,
        "itemCount": len(items),
        "total": session.get_cart_total(),
        "items": [
            {
                "productId": item.product_id,
                "name": item.name,
                "quantity": item.quantity,
                "price": item.price,
                "subtotal": item.price * item.quantity
            }
            for item in items
        ]
    }


def addToCart(
        session: Session,
        db: DBSession,
        productId: int,
        quantity: int = 1
) -> dict:
    """
    Add a product to the cart.
    Fetch product from DB to get name and price.
    """
    product = db.query(Product).filter(Product.id == productId).first()

    if not product:
        return {
            "success": False,
            "message": f"Product with ID {productId} not found."
        }

    if product.stock < quantity:
        return {
            "success": False,
            "message": f"Only {product.stock} units of {product.name} available in stock."
        }

    session.add_to_cart(
        product_id=product.id,
        quantity=quantity,
        name=product.name,
        price=product.price
    )

    return {
        "success": True,
        "message": f"Added {quantity}x {product.name} to your cart.",
        "cartItemCount": len(session.get_cart_items()),
        "cartTotal": session.get_cart_total()
    }


def removeFromCart(
        session: Session,
        db: DBSession,
        productId: int
) -> dict:
    """Remove a product from the cart."""
    if productId not in session.cart:
        return {
            "success": False,
            "message": "That product is not in your cart."
        }

    item_name = session.cart[productId].name
    session.remove_from_cart(productId)

    return {
        "success": True,
        "message": f"Removed {item_name} from your cart.",
        "cartItemCount": len(session.get_cart_items()),
        "cartTotal": session.get_cart_total()
    }


def updateCartItem(
        session: Session,
        db: DBSession,
        productId: int,
        quantity: int
) -> dict:
    """Update quantity of a cart item."""
    if productId not in session.cart:
        return {
            "success": False,
            "message": "That product is not in your cart."
        }

    if quantity == 0:
        return removeFromCart(session, db, productId)

    # Check stock
    product = db.query(Product).filter(Product.id == productId).first()
    if product and product.stock < quantity:
        return {
            "success": False,
            "message": f"Only {product.stock} units available."
        }

    session.update_cart_item(productId, quantity)

    return {
        "success": True,
        "message": f"Updated quantity to {quantity}.",
        "cartItemCount": len(session.get_cart_items()),
        "cartTotal": session.get_cart_total()
    }


# ============================================================
# ORDERS
# ============================================================

def initiateOrder(
        session: Session,
        db: DBSession
) -> dict:
    """
    Initiate the order process.
    This does NOT place the order yet — it signals the orchestrator
    to start collecting customer info (name, phone, address).

    Returns a special signal that the orchestrator recognizes.
    """
    items = session.get_cart_items()

    if not items:
        return {
            "success": False,
            "message": "Your cart is empty. Add some products before placing an order."
        }

    # Return a signal to the orchestrator
    return {
        "type": "initiate_checkout",
        "cartSummary": {
            "itemCount": len(items),
            "total": session.get_cart_total(),
            "items": [
                {
                    "name": item.name,
                    "quantity": item.quantity,
                    "price": item.price
                }
                for item in items
            ]
        },
        "message": "Ready to place your order. I'll need your delivery details."
    }


def finalizeOrder(
        session: Session,
        db: DBSession,
        customer_name: str,
        phone: str,
        address: str
) -> dict:
    """
    Actually create the order in the database.
    Called AFTER customer info is collected.

    This is NOT a tool — it's called directly by the orchestrator
    after the user provides name/phone/address.
    """
    items = session.get_cart_items()

    if not items:
        return {
            "success": False,
            "message": "Cart is empty. Cannot place order."
        }

    # ── Create Order ──
    order = Order(
        customer_name=customer_name,
        phone=phone,
        address=address,
        status="pending"
    )
    db.add(order)
    db.flush()  # Get the order.id before adding items

    # ── Create OrderItems ──
    for item in items:
        order_item = OrderItem(
            order_id=order.id,
            product_id=item.product_id,
            quantity=item.quantity,
            price=item.price  # Snapshot price
        )
        db.add(order_item)

    db.commit()

    # ── Clear cart and lastShownProducts ──
    session.clear_cart()
    session.clear_last_shown()

    # ── Return order confirmation ──
    return {
        "success": True,
        "orderId": order.id,
        "message": f"Order placed successfully! Your order ID is {order.id}. Keep this for tracking.",
        "orderSummary": {
            "orderId": order.id,
            "customerName": customer_name,
            "itemCount": len(items),
            "total": sum(item.price * item.quantity for item in items),
            "status": "pending"
        }
    }


def getOrderInfo(
        session: Session,
        db: DBSession,
        orderId: str
) -> dict:
    """Look up an order by ID."""
    order = db.query(Order).filter(Order.id == orderId.upper()).first()

    if not order:
        return {
            "found": False,
            "message": f"No order found with ID {orderId}."
        }

    # ── Load items ──
    items = []
    for order_item in order.items:
        items.append({
            "productName": order_item.product.name,
            "quantity": order_item.quantity,
            "price": order_item.price,
            "subtotal": order_item.price * order_item.quantity
        })

    total = sum(item["subtotal"] for item in items)

    return {
        "found": True,
        "order": {
            "orderId": order.id,
            "customerName": order.customer_name,
            "phone": order.phone,
            "address": order.address,
            "status": order.status,
            "createdAt": order.created_at.isoformat(),
            "itemCount": len(items),
            "total": total,
            "items": items
        }
    }


# ============================================================
# FUNCTION REGISTRY
# ============================================================
# Maps function names (from tool_calls) to actual Python functions.
# The orchestrator uses this to dispatch dynamically.
# ============================================================

FUNCTION_REGISTRY = {
    "getSkincareKnowledge": getSkincareKnowledge,
    "searchProducts": searchProducts,
    "getProductDetail": getProductDetail,
    "getCartState": getCartState,
    "addToCart": addToCart,
    "removeFromCart": removeFromCart,
    "updateCartItem": updateCartItem,
    "initiateOrder": initiateOrder,
    "getOrderInfo": getOrderInfo,
    # Note: finalizeOrder is NOT in the registry — it's called directly by the orchestrator
}