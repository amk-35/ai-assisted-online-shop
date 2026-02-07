# ============================================================
# session.py — Session state manager
# ============================================================
# Each websocket connection gets a Session instance.
# This holds:
#   - cart: { productId → quantity }
#   - lastShownProducts: list of products shown in last response
#   - userProfile: { skinType, concerns }
#   - conversation_history: last 10 messages
#   - conversation_summary: summarized older messages
#
# All in-memory. Lost on disconnect. Perfect for messenger-style chat.
# ============================================================

import json
from typing import Dict, List, Optional, Any
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


@dataclass
class SearchContext:
    """Stores pagination state for product searches."""
    filters: Dict[str, Any] = field(default_factory=dict)  # Last search filters
    total_count: int = 0  # Total matching products
    shown_product_ids: List[int] = field(default_factory=list)  # All shown IDs
    page: int = 1  # Current page
    has_more: bool = False  # More results available?


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
        self.conversation_history: List[Dict[str, str]] = []  # Stores last 10 messages
        self.conversation_summary: Optional[str] = None  # Summary of older messages
        self.search_context: Optional[SearchContext] = None  # Product search pagination

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

    # ── Conversation History ─────────────────────────────────

    def add_to_history(self, role: str, content: str):
        """
        Add a message to conversation history.
        Keeps only last 10 messages. When it exceeds 10, triggers summarization.
        """
        self.conversation_history.append({
            "role": role,
            "content": content
        })

        # If we have more than 10 messages, summarize the oldest ones
        if len(self.conversation_history) > 10:
            self._summarize_old_messages()

    def _summarize_old_messages(self):
        """
        When history exceeds 10 messages, summarize the oldest 5 and keep the recent 5.
        This prevents token overflow while maintaining context.
        """
        # Take the oldest 5 messages to summarize
        messages_to_summarize = self.conversation_history[:5]

        # Create a text summary (simple version - you can enhance this)
        summary_parts = []
        for msg in messages_to_summarize:
            role = "User" if msg["role"] == "user" else "Assistant"
            summary_parts.append(f"{role}: {msg['content'][:100]}")  # First 100 chars

        new_summary = "\n".join(summary_parts)

        # Append to existing summary or create new one
        if self.conversation_summary:
            self.conversation_summary += f"\n\n[Earlier conversation]\n{new_summary}"
        else:
            self.conversation_summary = f"[Earlier conversation]\n{new_summary}"

        # Keep only the recent 5 messages
        self.conversation_history = self.conversation_history[5:]

    def get_messages_for_api(self, current_user_message: str) -> List[Dict[str, str]]:
        """
        Build the messages array for the API call.

        Returns:
        [
            {"role": "system", "content": system_prompt_with_context_and_summary},
            {"role": "user", "content": "..."},
            {"role": "assistant", "content": "..."},
            ...
            {"role": "user", "content": current_user_message}
        ]
        """
        # Build system prompt with context
        system_prompt = self._build_system_prompt()

        # If we have a summary, prepend it to the system prompt
        if self.conversation_summary:
            system_prompt = f"{system_prompt}\n\n━━━ CONVERSATION SUMMARY ━━━\n{self.conversation_summary}\n━━━ END SUMMARY ━━━"

        messages = [{"role": "system", "content": system_prompt}]

        # Add conversation history (last 10 messages)
        messages.extend(self.conversation_history)

        # Add current user message
        messages.append({"role": "user", "content": current_user_message})

        return messages

    def _build_system_prompt(self) -> str:
        """
        Build the system prompt with live session state AND vocabulary injected.
        """
        from config import SYSTEM_PROMPT_TEMPLATE

        # Get vocabulary (cached)
        # Import here to avoid circular dependency
        from database import SessionLocal
        db = SessionLocal()
        try:
            from functions import get_vocabulary
            vocab = get_vocabulary(db)
        finally:
            db.close()

        # Format vocabulary for prompt
        skin_types_str = ", ".join(vocab["skin_types"])

        # Show sample of concerns (first 15) to keep prompt compact
        concerns_sample = vocab["concerns"][:15]
        concerns_str = ", ".join(concerns_sample)
        if len(vocab["concerns"]) > 15:
            concerns_str += f", ... ({len(vocab['concerns']) - 15} more)"

        # Show sample of categories (first 10)
        categories_sample = vocab["categories"][:10]
        categories_str = ", ".join(categories_sample)
        if len(vocab["categories"]) > 10:
            categories_str += f", ... ({len(vocab['categories']) - 10} more)"

        # Get session context
        context_dict = self.to_context_dict()

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

        return SYSTEM_PROMPT_TEMPLATE.format(
            skin_types=skin_types_str,
            concerns=concerns_str,
            categories=categories_str,
            context=context_str.strip()
        )

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