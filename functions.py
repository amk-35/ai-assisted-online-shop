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
from sqlalchemy import or_, and_, func, distinct
from models import Product, Order, OrderItem
from session import Session, SearchContext
from datetime import datetime, timedelta
import json


# ============================================================
# VOCABULARY CACHE
# ============================================================
#
# _vocabulary_cache = None
# _cache_timestamp = None
# CACHE_TTL_SECONDS = 3600  # 1 hour

# # Static skin types (never changes)
# SKIN_TYPES = [
#     "All Skin Types",
#     "Combination",
#     "Dry",
#     "Normal",
#     "Oily",
#     "Sensitive"
# ]

#
# def get_vocabulary(db: DBSession, force_refresh: bool = False) -> Dict[str, List[str]]:
#     """
#     Get all distinct categories and concerns from DB.
#     Cached for 1 hour.
#     Skin types are static (hardcoded).
#     """
#     global _vocabulary_cache, _cache_timestamp
#
#     now = datetime.now()
#
#     # Check cache
#     if not force_refresh and _vocabulary_cache is not None:
#         if (now - _cache_timestamp).total_seconds() < CACHE_TTL_SECONDS:
#             return _vocabulary_cache
#
#     # Fetch categories (distinct, sorted)
#     categories_raw = db.query(distinct(Product.category))\
#                        .filter(Product.category.isnot(None))\
#                        .filter(Product.category != "")\
#                        .order_by(Product.category)\
#                        .all()
#
#     categories = [cat[0] for cat in categories_raw if cat[0]]
#
#     # Fetch and parse concerns (comma-separated)
#     concerns_raw = db.query(Product.concerns)\
#                      .filter(Product.concerns.isnot(None))\
#                      .filter(Product.concerns != "")\
#                      .all()
#
#     concerns_set = set()
#     for (concerns_str,) in concerns_raw:
#         if concerns_str:
#             # Split by comma, strip whitespace, normalize
#             parsed = [c.strip() for c in concerns_str.split(',') if c.strip()]
#             concerns_set.update(parsed)
#
#     concerns = sorted(list(concerns_set))
#
#     # Update cache
#     _vocabulary_cache = {
#         "categories": categories,
#         "concerns": concerns,
#         "skin_types": SKIN_TYPES  # Static
#     }
#     _cache_timestamp = now
#
#     return _vocabulary_cache

#
# # ============================================================
# # SMART SKIN TYPE MATCHING
# # ============================================================
#
# def build_skin_type_filter(skin_type: str):
#     """
#     Build filter for skin type that includes "All Skin Types".
#
#     Example:
#       User specifies: "Oily"
#       Matches: Products with "Oily" OR "All Skin Types"
#     """
#     if not skin_type:
#         return None
#
#     # Match products with specified skin type OR "All Skin Types"
#     return or_(
#         Product.skin_types.ilike(f"%{skin_type}%"),
#         Product.skin_types.ilike("%All Skin Types%")
#     )


# ============================================================
# KNOWLEDGE
# ============================================================
#
# def getSkincareKnowledge(
#         session: Session,
#         db: DBSession,
#         topic: str,
#         skinType: Optional[str] = None,
#         concern: Optional[str] = None
# ) -> dict:
#     """The model answers using its own knowledge."""
#     return {
#         "type": "knowledge_question",
#         "topic": topic,
#         "note": "The model will answer this using its own knowledge."
#     }


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
    Enhanced product search with:
    - Smart category matching (LIKE %Cleanser% matches "Cleanser, Foam")
    - Smart skin type matching (Oily matches "Oily" OR "All Skin Types")
    - Pagination support (excludes already-shown products)
    - Total count exposure
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
    
    # Clean for comparison
    current_filters_clean = {k: v for k, v in current_filters.items() if v is not None}
    
    # ── Check if filters match previous search (pagination) ──
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
    
    # ── Apply filters ──
    filters = []
    
    # Free-text query
    if query:
        search_term = f"%{query}%"
        filters.append(or_(
            Product.name.ilike(search_term),
            Product.description.ilike(search_term),
            Product.ingredients.ilike(search_term)
        ))
    
    # SKU
    if sku:
        filters.append(Product.sku.ilike(f"%{sku}%"))
    
    # Brand
    if brand:
        filters.append(Product.brand.ilike(f"%{brand}%"))
    
    # Category (fuzzy - matches subcategories)
    # "Cleanser" matches "Cleanser", "Cleanser, Foam", "Men's Cleanser"
    if category:
        filters.append(Product.category.ilike(f"%{category}%"))
    
    # Skin type (smart - includes "All Skin Types")
    if skinType:
        skin_filter = build_skin_type_filter(skinType)
        if skin_filter is not None:
            filters.append(skin_filter)
    
    # Concern (fuzzy - matches comma-separated)
    if concern:
        filters.append(Product.concerns.ilike(f"%{concern}%"))
    
    # Price range
    if minPrice is not None:
        filters.append(Product.price >= minPrice)
    if maxPrice is not None:
        filters.append(Product.price <= maxPrice)
    
    # Stock availability
    if stock is not None:
        if stock:
            filters.append(Product.stock > 0)
        else:
            filters.append(Product.stock == 0)
    
    # Apply all filters
    if filters:
        base_query = base_query.filter(and_(*filters))
    
    # ── Exclude already-shown products (pagination) ──
    if exclude_ids:
        base_query = base_query.filter(~Product.id.in_(exclude_ids))
    
    # ── Get total count BEFORE limit ──
    total_count = base_query.count()
    
    # ── Get this page's results ──
    products = base_query.order_by(Product.stock.desc()).limit(limit).all()
    
    # ── Handle exhaustion ──
    if not products and exclude_ids:
        return {
            "found": False,
            "exhausted": True,
            "message": f"You've seen all {len(exclude_ids)} matching products.",
            "totalShown": len(exclude_ids)
        }
    
    # ── No results ──
    if not products:
        return {
            "found": False,
            "message": "No products found matching those filters. Try different search terms.",
            "filtersUsed": current_filters
        }
    
    # ── Update search context (pagination state) ──
    new_shown_ids = exclude_ids + [p.id for p in products]
    has_more = (len(new_shown_ids) < total_count)
    
    if session.search_context and filters_match:
        # Update existing context
        session.search_context.shown_product_ids = new_shown_ids
        session.search_context.page += 1
        session.search_context.has_more = has_more
        session.search_context.total_count = total_count
    else:
        # Create new context
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
                "description": p.description[:150] + "..." if p.description and len(p.description) > 150 else (p.description or ""),
                "skinTypes": p.skin_types,
                "concerns": p.concerns,
                "volume": p.volume
            }
            for i, p in enumerate(products)
        ]
    }


def searchMoreProducts(session: Session, db: DBSession) -> dict:
    """
    Get next page from last search.
    Reuses saved filters, excludes already-shown products.
    """
    
    if not session.search_context:
        return {
            "error": True,
            "message": "No previous search to continue. Search for products first."
        }
    
    if not session.search_context.has_more:
        total = session.search_context.total_count
        shown = len(session.search_context.shown_product_ids)
        return {
            "found": False,
            "exhausted": True,
            "message": f"You've seen all {shown} matching products (out of {total} total)."
        }
    
    # Reuse previous filters
    filters = session.search_context.filters
    
    # Call searchProducts with same filters (auto-excludes shown products)
    return searchProducts(session=session, db=db, **filters)


# ============================================================
# INVENTORY TOOLS (for LLM context)
# ============================================================
#
# def getCategories(session: Session, db: DBSession) -> dict:
#     """Get all unique categories with counts."""
#
#     categories_raw = db.query(
#         Product.category,
#         func.count(Product.id).label('count')
#     ).filter(
#         Product.category.isnot(None),
#         Product.category != ""
#     ).group_by(Product.category)\
#      .order_by(func.count(Product.id).desc())\
#      .all()
#
#     categories = [
#         {"name": cat, "count": count}
#         for cat, count in categories_raw
#     ]
#
#     return {
#         "found": True,
#         "count": len(categories),
#         "categories": categories
#     }


# def getConcerns(session: Session, db: DBSession) -> dict:
#     """Get all unique concerns (parsed from comma-separated)."""
#
#     vocab = get_vocabulary(db)
#
#     return {
#         "found": True,
#         "count": len(vocab["concerns"]),
#         "concerns": vocab["concerns"]
#     }


# def getSkinTypes(session: Session, db: DBSession) -> dict:
#     """Get all skin types (static list)."""
#
#     return {
#         "found": True,
#         "count": len(SKIN_TYPES),
#         "skinTypes": SKIN_TYPES
#     }


def getTotalProductsCount(session: Session, db: DBSession) -> dict:
    """Get total count of all products in the database."""
    
    total_count = db.query(func.count(Product.id)).scalar()
    
    return {
        "found": True,
        "totalProductsCount": total_count,
        "message": f"Total products in store: {total_count}"
    }


# ============================================================
# PROFILE MANAGEMENT
# ============================================================

def updateUserProfile(
    session: Session,
    db: DBSession,
    skinType: Optional[str] = None,
    concerns: Optional[List[str]] = None
) -> dict:
    """
    Update user profile.
    LLM should use exact values from vocabulary context.
    """
    
    updated = []
    
    # Update skin type
    if skinType:
        # Validate against known types
        if skinType in SKIN_TYPES:
            session.user_profile.skin_type = skinType
            updated.append(f"skin type: {skinType}")
        else:
            # Try case-insensitive match
            for valid_type in SKIN_TYPES:
                if skinType.lower() == valid_type.lower():
                    session.user_profile.skin_type = valid_type
                    updated.append(f"skin type: {valid_type}")
                    break
    
    # Update concerns
    if concerns:
        # Just save as-is (LLM should use vocabulary from context)
        session.update_profile(concerns=concerns)
        updated.append(f"concerns: {', '.join(concerns)}")
    
    if not updated:
        return {
            "success": False,
            "message": "No profile updates provided."
        }
    
    return {
        "success": True,
        "message": f"Profile updated: {', '.join(updated)}",
        "currentProfile": {
            "skinType": session.user_profile.skin_type,
            "concerns": session.user_profile.concerns
        }
    }


def getUserProfile(session: Session, db: DBSession) -> dict:
    """Get current user profile."""
    
    profile = session.user_profile
    
    if not profile.skin_type and not profile.concerns:
        return {
            "profileSet": False,
            "message": "No profile saved yet."
        }
    
    return {
        "profileSet": True,
        "skinType": profile.skin_type,
        "concerns": profile.concerns
    }


# ============================================================
# PRODUCT DETAILS
# ============================================================

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


def getProductDetailsBySKU(
        session: Session,
        db: DBSession,
        sku: str
) -> dict:
    """Get full details for one product by SKU."""
    product = db.query(Product).filter(Product.sku.ilike(f"%{sku}%")).first()

    if not product:
        return {
            "found": False,
            "message": f"Product with SKU '{sku}' not found."
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
                "sku": item.sku,
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
        sku: str,
        quantity: int = 1
) -> dict:
    """Add a product to cart."""
    product = db.query(Product).filter(Product.sku==sku).first()

    if not product:
        return {
            "success": False,
            "message": f"Product with sku {sku} not found."
        }

    if product.stock < quantity:
        return {
            "success": False,
            "message": f"Only {product.stock} units of {product.name} available in stock."
        }

    session.add_to_cart(
        sku=product.sku,
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


def removeFromCart(session: Session, db: DBSession, sku: str) -> dict:
    """Remove a product from cart."""
    if sku not in session.cart:
        return {
            "success": False,
            "message": "That product is not in your cart."
        }

    item_name = session.cart[sku].name
    session.remove_from_cart(sku)

    return {
        "success": True,
        "message": f"Removed {item_name} from your cart.",
        "cartItemCount": len(session.get_cart_items()),
        "cartTotal": session.get_cart_total()
    }


def updateCartItem(
        session: Session,
        db: DBSession,
        sku: str,
        quantity: int
) -> dict:
    """Update quantity of cart item."""
    if sku not in session.cart:
        return {
            "success": False,
            "message": "That product is not in your cart."
        }

    if quantity == 0:
        return removeFromCart(session, db, sku)

    product = db.query(Product).filter(Product.sku == sku).first()
    if product and product.stock < quantity:
        return {
            "success": False,
            "message": f"Only {product.stock} units available."
        }

    session.update_cart_item(sku, quantity)

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
            product_sku=item.sku,
            quantity=item.quantity,
            price=item.price
        )
        db.add(order_item)

    db.commit()

    session.clear_cart()
    # session.clear_last_shown()

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
# PRINT ALL PRODUCTS BY BRAND
# ============================================================

def printAllProductsByBrand(session: Session, db: DBSession) -> dict:
    """
    Print all products grouped by brand.
    Format:
        Brand
        ---------
        -product name, (category), (skin_types), price [sku]
        -product name, (category), (skin_types), price [sku]
    """
    
    # Get all unique brands, sorted
    brands = db.query(Product.brand)\
               .filter(Product.brand.isnot(None))\
               .filter(Product.brand != "")\
               .order_by(Product.brand)\
               .distinct()\
               .all()
    
    if not brands:
        print("No brands found in database.")
        return {
            "success": True,
            "message": "No brands found in database."
        }
    
    output = []
    
    # For each brand, get all products
    for (brand,) in brands:
        products = db.query(Product)\
                     .filter(Product.brand == brand)\
                     .order_by(Product.name)\
                     .all()
        
        if products:
            # Print brand header
            print(f"\n{brand}")
            print("-" * 9)
            output.append(f"\n{brand}")
            output.append("-" * 9)
            
            # Print each product
            for product in products:
                line = f"-{product.name}, ({product.category}), ({product.skin_types}), {product.price} [{product.sku}]"
                print(line)
                output.append(line)
    
    return {
        "success": True,
        "message": f"Printed all products from {len(brands)} brands.",
        "brandCount": len(brands),
        "output": "\n".join(output)
    }


def findProductsByBrand(
    session: Session,
    db: DBSession,
    brand: str
) -> dict:
    """
    Find all products for a specific brand.
    Format:
        Brand
        ---------
        -product name [sku] (In stock or Out of stock)
        -product name [sku] (In stock or Out of stock)
    """
    
    # Query for the brand (case-insensitive search)
    products = db.query(Product)\
                 .filter(Product.brand.ilike(f"%{brand}%"))\
                 .order_by(Product.name)\
                 .all()
    
    if not products:
        return {
            "found": False,
            "message": f"No products found for brand '{brand}'."
        }
    
    # Get the actual brand name from first product
    actual_brand = products[0].brand
    
    output = []
    
    # Format output
    print(f"\n{actual_brand}")
    print("-" * 9)
    output.append(f"{actual_brand}")
    output.append("-" * 9)
    
    # Print each product
    for product in products:
        stock_status = "In stock" if product.stock > 0 else "Out of stock"
        line = f"-{product.name} [{product.sku}] ({stock_status})"
        print(line)
        output.append(line)
    
    return {
        "found": True,
        "brand": actual_brand,
        "productCount": len(products),
        "message": f"Found {len(products)} products for {actual_brand}.",
        "products": [
            {
                "name": p.name,
                "sku": p.sku,
                "price": p.price,
                "stock": p.stock,
                "stockStatus": "In stock" if p.stock > 0 else "Out of stock",
                "category": p.category
            }
            for p in products
        ],
        "output": "\n".join(output)
    }


# ============================================================
# FUNCTION REGISTRY
# ============================================================

FUNCTION_REGISTRY = {
    # "getSkincareKnowledge": getSkincareKnowledge,
    # "searchProducts": searchProducts,
    # "searchMoreProducts": searchMoreProducts,
    # "getCategories": getCategories,
    # "getConcerns": getConcerns,
    # "getSkinTypes": getSkinTypes,
    "getTotalProductsCount": getTotalProductsCount,
    "updateUserProfile": updateUserProfile,
    "getUserProfile": getUserProfile,
    "getProductDetail": getProductDetail,
    "getProductDetailsBySKU": getProductDetailsBySKU,
    "getCartState": getCartState,
    "addToCart": addToCart,
    "removeFromCart": removeFromCart,
    "updateCartItem": updateCartItem,
    "initiateOrder": initiateOrder,
    "getOrderInfo": getOrderInfo,
    "printAllProductsByBrand": printAllProductsByBrand,
    "findProductsByBrand": findProductsByBrand,
}