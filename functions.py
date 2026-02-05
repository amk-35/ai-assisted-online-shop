# ============================================================
# functions.py — Tool function implementations (ENHANCED)
# ============================================================
# CHANGES FROM PREVIOUS VERSION:
# - searchProducts() now tracks pagination state
# - Exposes total count ("showing 6 of 43")
# - Smart exclusion of already-shown products
# - New function: searchMoreProducts() for explicit pagination
# ============================================================

from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session as DBSession
from sqlalchemy import or_, and_
from models import Product, Order, OrderItem
from session import Session, ShownProduct, SearchContext
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
    """The model answers using its own knowledge."""
    return {
        "type": "knowledge_question",
        "topic": topic,
        "note": "The model will answer this using its own knowledge."
    }


# ============================================================
# PRODUCTS — ENHANCED WITH PAGINATION
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
        limit: int = 6
) -> dict:
    """
    Enhanced product search with pagination support.

    Features:
    - Exposes total count ("showing 6 of 43")
    - Tracks already-shown products per search
    - Auto-excludes shown products when same filters
    - Resets when filters change
    """

    # ── Build current filters dict ──
    current_filters = {
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
    }

    # Clean for comparison (remove None values)
    current_filters_clean = {k: v for k, v in current_filters.items() if v is not None}

    # ── Check if filters match previous search ──
    filters_match = False
    exclude_ids = []

    if session.search_context:
        prev_filters_clean = {k: v for k, v in session.search_context.filters.items() if v is not None}
        filters_match = (current_filters_clean == prev_filters_clean)

        if filters_match:
            exclude_ids = session.search_context.shown_product_ids.copy()

    # ── Reset if filters changed ──
    if not filters_match:
        session.search_context = None
        exclude_ids = []

    # ── Build base query ──
    base_query = db.query(Product)

    # Apply filters
    filtered_query = _apply_filters(
        base_query,
        query_text=query,
        sku=sku,
        category=category,
        skinType=skinType,
        concern=concern,
        brand=brand,
        minPrice=minPrice,
        maxPrice=maxPrice,
        stock=stock
    )

    # ── Exclude already-shown products ──
    if exclude_ids:
        filtered_query = filtered_query.filter(~Product.id.in_(exclude_ids))

    # ── Get total count BEFORE limit ──
    total_count = filtered_query.count()

    # ── Get this page's results ──
    products = filtered_query.order_by(Product.stock.desc()).limit(limit).all()

    # ── Handle exhaustion ──
    if not products and exclude_ids:
        return {
            "found": False,
            "exhausted": True,
            "message": f"No more products matching those filters. You've seen all {len(exclude_ids)} results.",
            "total_shown": len(exclude_ids)
        }

    # ── Standard fallback ──
    if not products:
        return {
            "found": False,
            "message": "No products found matching those filters. Try different search terms.",
            "filters_used": current_filters
        }

    # ── Update search context ──
    new_shown_ids = exclude_ids + [p.id for p in products]
    has_more = (len(new_shown_ids) < total_count)

    if session.search_context and filters_match:
        # Update existing
        session.search_context.shown_product_ids = new_shown_ids
        session.search_context.page += 1
        session.search_context.has_more = has_more
        session.search_context.total_count = total_count
    else:
        # Create new
        session.search_context = SearchContext(
            filters=current_filters,
            total_count=total_count,
            shown_product_ids=new_shown_ids,
            page=1,
            has_more=has_more
        )

    # ── Update lastShownProducts (for "add that one") ──
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

    # ── Return with pagination metadata ──
    return {
        "found": True,
        "count": len(products),
        "total": total_count,
        "page": session.search_context.page,
        "hasMore": has_more,
        "showing": f"{len(products)} of {total_count}" if has_more else f"all {total_count}",
        "totalShown": len(new_shown_ids),
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
                "description": p.description[:150] + "..." if p.description and len(p.description) > 150 else (
                            p.description or ""),
                "skinTypes": p.skin_types,
                "concerns": p.concerns,
                "volume": p.volume
            }
            for i, p in enumerate(products)
        ]
    }


def _apply_filters(
        query,
        query_text: Optional[str] = None,
        sku: Optional[str] = None,
        category: Optional[str] = None,
        skinType: Optional[str] = None,
        concern: Optional[str] = None,
        brand: Optional[str] = None,
        minPrice: Optional[float] = None,
        maxPrice: Optional[float] = None,
        stock: Optional[bool] = None
):
    """Helper to apply all filters to a query."""

    if query_text:
        search_term = f"%{query_text}%"
        query = query.filter(or_(
            Product.name.ilike(search_term),
            Product.description.ilike(search_term),
            Product.ingredients.ilike(search_term) if Product.ingredients else False
        ))

    if sku:
        query = query.filter(Product.sku.ilike(f"%{sku}%"))

    if brand:
        query = query.filter(Product.brand.ilike(f"%{brand}%"))

    if category:
        cat_parts = [part.strip() for part in category.split("/")]
        or_conditions = [Product.category.ilike(f"%{part}%") for part in cat_parts]
        query = query.filter(or_(*or_conditions))

    if skinType:
        query = query.filter(Product.skin_types.ilike(f"%{skinType}%"))

    if concern:
        query = query.filter(Product.concerns.ilike(f"%{concern}%"))

    if minPrice is not None:
        query = query.filter(Product.price >= minPrice)
    if maxPrice is not None:
        query = query.filter(Product.price <= maxPrice)

    if stock is not None:
        query = query.filter(Product.stock > 0 if stock else Product.stock == 0)

    return query


def searchMoreProducts(
        session: Session,
        db: DBSession
) -> dict:
    """
    Get next page from the last search.
    Reuses saved filters and excludes already-shown products.
    """

    if not session.search_context:
        return {
            "error": True,
            "message": "No previous search to continue. Try searching for products first."
        }

    if not session.search_context.has_more:
        total = session.search_context.total_count
        shown = len(session.search_context.shown_product_ids)
        return {
            "found": False,
            "exhausted": True,
            "message": f"You've already seen all {shown} matching products (out of {total} total)."
        }

    # Reuse previous filters
    filters = session.search_context.filters

    # Call searchProducts with same filters (it will auto-exclude shown products)
    return searchProducts(session=session, db=db, **filters)


def getProductDetail(
        session: Session,
        db: DBSession,
        productId: int
) -> dict:
    """Get full details for one product."""
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

def getCartState(session: Session, db: DBSession) -> dict:
    """Get current cart contents."""
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
    """Add a product to cart."""
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


def removeFromCart(session: Session, db: DBSession, productId: int) -> dict:
    """Remove a product from cart."""
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
    """Update quantity of cart item."""
    if productId not in session.cart:
        return {
            "success": False,
            "message": "That product is not in your cart."
        }

    if quantity == 0:
        return removeFromCart(session, db, productId)

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

def initiateOrder(session: Session, db: DBSession) -> dict:
    """Initiate order process (triggers customer info collection)."""
    items = session.get_cart_items()

    if not items:
        return {
            "success": False,
            "message": "Your cart is empty. Add some products before placing an order."
        }

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
    """Create order in DB after collecting customer info."""
    items = session.get_cart_items()

    if not items:
        return {
            "success": False,
            "message": "Cart is empty. Cannot place order."
        }

    order = Order(
        customer_name=customer_name,
        phone=phone,
        address=address,
        status="pending"
    )
    db.add(order)
    db.flush()

    for item in items:
        order_item = OrderItem(
            order_id=order.id,
            product_id=item.product_id,
            quantity=item.quantity,
            price=item.price
        )
        db.add(order_item)

    db.commit()

    session.clear_cart()
    session.clear_last_shown()

    return {
        "success": True,
        "orderId": order.id,
        "message": f"Order placed successfully! Your order ID is {order.id}.",
        "orderSummary": {
            "orderId": order.id,
            "customerName": customer_name,
            "itemCount": len(items),
            "total": sum(item.price * item.quantity for item in items),
            "status": "pending"
        }
    }


def getOrderInfo(session: Session, db: DBSession, orderId: str) -> dict:
    """Look up order by ID."""
    order = db.query(Order).filter(Order.id == orderId.upper()).first()

    if not order:
        return {
            "found": False,
            "message": f"No order found with ID {orderId}."
        }

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

FUNCTION_REGISTRY = {
    "getSkincareKnowledge": getSkincareKnowledge,
    "searchProducts": searchProducts,
    "searchMoreProducts": searchMoreProducts,  # NEW
    "getProductDetail": getProductDetail,
    "getCartState": getCartState,
    "addToCart": addToCart,
    "removeFromCart": removeFromCart,
    "updateCartItem": updateCartItem,
    "initiateOrder": initiateOrder,
    "getOrderInfo": getOrderInfo,
}