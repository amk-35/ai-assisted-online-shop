# ============================================================
# session.py — Session state manager
# ============================================================
# Each websocket connection gets a Session instance.
# This holds:
#   - cart: { productId → quantity }
#   - lastShownProducts: list of products shown in last response
#   - userProfile: { skinType, concerns }
#
# All in-memory. Lost on disconnect. Perfect for messenger-style chat.
# ============================================================

from typing import Dict, List, Optional
from dataclasses import dataclass, field


@dataclass
class CartItem:
    """One item in the cart."""
    product_id: int
    quantity: int
    name: str  # cached product name for display
    price: float  # cached price at time of adding


@dataclass
class ShownProduct:
    """One product shown to the user in the last response."""
    position: int  # 1-indexed position in the list
    product_id: int
    name: str
    price: float
    sku: str


@dataclass
class UserProfile:
    """The user's stated skin type and concerns."""
    skin_type: Optional[str] = None  # oily | dry | combination | sensitive | normal
    concerns: List[str] = field(default_factory=list)  # ["acne", "hydration", ...]


class Session:
    """
    Per-connection session state.
    Created when websocket connects, destroyed on disconnect.
    """

    def __init__(self, connection_id: str):
        self.connection_id = connection_id
        self.cart: Dict[int, CartItem] = {}  # productId → CartItem
        self.last_shown_products: List[ShownProduct] = []
        self.user_profile = UserProfile()
        self.awaiting_checkout = False  # Flag: waiting for customer info

    # ── Cart operations ──────────────────────────────────────

    def add_to_cart(self, product_id: int, quantity: int, name: str, price: float):
        """Add or update a product in the cart."""
        if product_id in self.cart:
            self.cart[product_id].quantity += quantity
        else:
            self.cart[product_id] = CartItem(
                product_id=product_id,
                quantity=quantity,
                name=name,
                price=price
            )

    def remove_from_cart(self, product_id: int):
        """Remove a product from the cart."""
        if product_id in self.cart:
            del self.cart[product_id]

    def update_cart_item(self, product_id: int, quantity: int):
        """Update quantity. If quantity is 0, removes the item."""
        if quantity == 0:
            self.remove_from_cart(product_id)
        elif product_id in self.cart:
            self.cart[product_id].quantity = quantity

    def get_cart_items(self) -> List[CartItem]:
        """Get all cart items as a list."""
        return list(self.cart.values())

    def clear_cart(self):
        """Empty the cart. Called after order is placed."""
        self.cart.clear()

    def get_cart_total(self) -> float:
        """Calculate total price of all items in cart."""
        return sum(item.price * item.quantity for item in self.cart.values())

    # ── LastShownProducts ────────────────────────────────────

    def update_last_shown(self, products: List[ShownProduct]):
        """Overwrite lastShownProducts. Called after response generation."""
        self.last_shown_products = products

    def clear_last_shown(self):
        """Clear lastShownProducts. Called after order is placed."""
        self.last_shown_products = []

    def resolve_reference(self, ref: str) -> Optional[int]:
        """
        Resolve a reference like 'that one', 'the first one', 'the second one'
        to a product_id using lastShownProducts.

        Returns product_id if resolved, None otherwise.

        Examples:
          - "that one" / "that" → position 1
          - "the first one" / "first" → position 1
          - "the second one" / "second" → position 2
          - "number 3" / "item 3" → position 3
        """
        if not self.last_shown_products:
            return None

        ref_lower = ref.lower().strip()

        # Default reference: "that" or "that one" → first item
        if ref_lower in ["that", "that one", "it"]:
            return self.last_shown_products[0].product_id

        # Ordinal references
        ordinals = {
            "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5,
            "1st": 1, "2nd": 2, "3rd": 3, "4th": 4, "5th": 5,
        }
        for word, pos in ordinals.items():
            if word in ref_lower:
                if pos <= len(self.last_shown_products):
                    return self.last_shown_products[pos - 1].product_id

        # Numeric references: "number 2", "item 3"
        import re
        match = re.search(r'\d+', ref_lower)
        if match:
            pos = int(match.group())
            if 1 <= pos <= len(self.last_shown_products):
                return self.last_shown_products[pos - 1].product_id

        return None

    # ── UserProfile ──────────────────────────────────────────

    def update_profile(self, skin_type: Optional[str] = None, concerns: Optional[List[str]] = None):
        """
        Update user profile.
        skin_type overwrites.
        concerns are APPENDED (deduplicated).
        """
        if skin_type:
            self.user_profile.skin_type = skin_type

        if concerns:
            # Append new concerns, deduplicate
            existing = set(self.user_profile.concerns)
            for concern in concerns:
                if concern.lower() not in existing:
                    self.user_profile.concerns.append(concern.lower())
                    existing.add(concern.lower())

    # ── Serialization for system prompt ──────────────────────

    def to_context_dict(self) -> dict:
        """
        Serialize session state to dict for injection into system prompt.
        This is what the LLM sees.
        """
        return {
            "lastShownProducts": [
                {
                    "position": p.position,
                    "productId": p.product_id,
                    "name": p.name,
                    "price": p.price,
                    "sku": p.sku
                }
                for p in self.last_shown_products
            ],
            "userProfile": {
                "skinType": self.user_profile.skin_type,
                "concerns": self.user_profile.concerns
            },
            "cart": [
                {
                    "productId": item.product_id,
                    "name": item.name,
                    "quantity": item.quantity,
                    "price": item.price
                }
                for item in self.get_cart_items()
            ]
        }


# ── Session registry (global, in-memory) ────────────────────
# Maps connection_id → Session
_sessions: Dict[str, Session] = {}


def create_session(connection_id: str) -> Session:
    """Create a new session for a websocket connection."""
    session = Session(connection_id)
    _sessions[connection_id] = session
    return session


def get_session(connection_id: str) -> Optional[Session]:
    """Get an existing session."""
    return _sessions.get(connection_id)


def destroy_session(connection_id: str):
    """Destroy a session when websocket disconnects."""
    if connection_id in _sessions:
        del _sessions[connection_id]