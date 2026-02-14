from typing import Optional, List
from sqlalchemy.orm import Session as DBSession
from sqlalchemy import func
from models import Product, Order, OrderItem
from session import Session

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

    # ── Validate stock for all items before creating order ──
    for item in items:
        product = db.query(Product).filter(Product.sku == item.sku).first()
        if not product:
            return {
                "success": False,
                "message": f"Product {item.sku} no longer exists in store."
            }
        if product.stock ==0:
            session.remove_from_cart(item.sku)  # Remove out-of-stock item from cart
            return {
                "success": False,
                "message": f"Sorry, '{product.name} [{product.sku}]' is out of stock and cannot be ordered.I removed this product from your cart. Please update your cart."
            }
        if product.stock < item.quantity:
            return {
                "success": False,
                "message": f"Sorry, only {product.stock} units of '{product.name} [{product.sku}]' available (you need {item.quantity}). Please update your cart."
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
        
        # ── Decrease stock for this product ──
        product = db.query(Product).filter(Product.sku == item.sku).first()
        if product:
            product.stock -= item.quantity

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