# ============================================================
# tools.py — Mistral tool definitions
# ============================================================
# These JSON schemas are what Mistral reads to decide:
#   - Which function to call
#   - What parameters to pass
#   - When NOT to call a function (just reply with text)
#
# The "description" fields are critical — they are your
# instruction layer to the model. Write them like you're
# telling a smart assistant when and why to use each tool.
# ============================================================

TOOLS = [

    # ── Knowledge ─────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "getSkincareKnowledge",
            "description": (
                "Answer skincare knowledge questions using your own knowledge. "
                "Use this when the user asks about ingredients, skin routines, skin types, "
                "how to use products, or general skincare advice. "
                "IMPORTANT: Whenever you call this, ALSO call searchProducts() in parallel "
                "to surface relevant products from our store alongside the knowledge answer."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": "The skincare topic or ingredient. e.g. 'retinol', 'vitamin C', 'how to moisturize'"
                    },
                    "skinType": {
                        "type": "string",
                        "enum": ["oily", "dry", "combination", "sensitive", "normal"],
                        "description": "The user's skin type if known from context"
                    },
                    "concern": {
                        "type": "string",
                        "description": "A specific skin concern if relevant. e.g. 'acne', 'anti-aging', 'dryness'"
                    }
                },
                "required": ["topic"]
            }
        }
    },

    # ── Products ──────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "searchProducts",
            "description": (
                "Search our store's product catalog. Use this to: "
                "1) Browse products by category or filter, "
                "2) Find recommendations based on skin type or concern, "
                "3) Surface relevant products alongside knowledge answers. "
                "Leave any filter you don't have info on as null — the function handles partial filters. "
                "Call this ALWAYS when answering skincare knowledge questions."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "description": "Product category. e.g. 'cleanser', 'moisturizer', 'serum', 'toner', 'sunscreen'"
                    },
                    "skinType": {
                        "type": "string",
                        "enum": ["oily", "dry", "combination", "sensitive", "normal"],
                        "description": "Filter by skin type"
                    },
                    "concern": {
                        "type": "string",
                        "description": "Filter by concern. e.g. 'acne', 'anti-aging', 'dryness', 'brightening'"
                    },
                    "maxPrice": {
                        "type": "number",
                        "description": "Maximum price filter if the user mentioned a budget"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "getProductDetail",
            "description": (
                "Get full details for one specific product: ingredients, price, stock, description. "
                "Use this when the user says 'tell me more about...' or 'what are the ingredients of...' "
                "a specific product. Resolve 'that one' or 'the first one' using the lastShownProducts "
                "context in the system prompt to get the correct productId."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "productId": {
                        "type": "integer",
                        "description": "The product ID. Get this from lastShownProducts context."
                    }
                },
                "required": ["productId"]
            }
        }
    },

    # ── Cart ──────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "getCartState",
            "description": (
                "Get the user's current cart contents. "
                "Call this when: the user asks to see their cart, "
                "before placing an order, or when you need to know what's in the cart "
                "to respond accurately."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "addToCart",
            "description": (
                "Add a product to the user's cart. "
                "IMPORTANT: Resolve references first. If the user says 'add that one' or 'add the first one', "
                "look at lastShownProducts in the system prompt context to find the correct productId. "
                "Only use productIds you can see in the context — never guess."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "productId": {
                        "type": "integer",
                        "description": "The product ID from lastShownProducts or search results"
                    },
                    "quantity": {
                        "type": "integer",
                        "description": "How many. Defaults to 1 if not specified.",
                        "default": 1
                    }
                },
                "required": ["productId"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "removeFromCart",
            "description": (
                "Remove a product from the cart. "
                "If the user says 'remove item 2' or 'remove the cleanser', "
                "resolve the reference using the cart contents (call getCartState first if needed)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "productId": {
                        "type": "integer",
                        "description": "The product ID to remove"
                    }
                },
                "required": ["productId"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "updateCartItem",
            "description": "Update the quantity of an item already in the cart.",
            "parameters": {
                "type": "object",
                "properties": {
                    "productId": {
                        "type": "integer",
                        "description": "The product ID to update"
                    },
                    "quantity": {
                        "type": "integer",
                        "description": "The new quantity. Use 0 to remove."
                    }
                },
                "required": ["productId", "quantity"]
            }
        }
    },

    # ── Orders ────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "initiateOrder",
            "description": (
                "Start the order process. Call this when the user says they want to place an order "
                "or checkout. This does NOT place the order yet — it triggers the backend to ask "
                "the user for name, phone number, and delivery address before finalizing. "
                "Call getCartState first to confirm the cart is not empty."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "getOrderInfo",
            "description": (
                "Look up a past order by its order ID. Use this when the user asks about "
                "an order status or types an order ID. Order IDs are 8-character uppercase strings."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "orderId": {
                        "type": "string",
                        "description": "The 8-character order ID. e.g. 'A1B2C3D4'"
                    }
                },
                "required": ["orderId"]
            }
        }
    },
]