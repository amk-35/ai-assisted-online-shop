
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "getProductDetailsBySKU",
            "description": (
                "Get full details for one specific product by its SKU code to obtain ingredients, price, stock, description. "
                "Use this when the user asks for product details "
                "Reference the chat to get SKU."
                "Returns comprehensive product information including ingredients, pricing, and availability."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "sku": {
                        "type": "string",
                        "description": "The product SKU code to search for. e.g. 'SKU-001', 'PROD-123', 'TO-CL-001'"
                    }
                },
                "required": ["sku"]
            }
        }
    },

    # ── Profile Management ────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "updateUserProfile",
            "description": (
                "Only update user profile with skin type and/or skincare concerns if the user explicitly states a skin type and/or skincare concerns."
                "Use this when the user specifies their skin type or tells you about their skin concerns. "
                "Skin types should be one of: All Skin Types, Combination, Dry, Normal, Oily, Sensitive. "
                "Concerns should be specific issues like acne, anti-aging, dryness, brightening, etc."
                "Be aware of user input messages for skin types and concerns."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "skinType": {
                        "type": "string",
                        "description": "The user's skin type. e.g. 'Oily', 'Dry', 'Combination', 'Sensitive', 'Normal', 'All Skin Types'"
                    },
                    "concerns": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of skincare concerns. e.g. ['acne', 'anti-aging', 'dryness', 'brightening']"
                    }
                },
                "required": []
            }
        }
    },

    # ── Cart ──────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "getCartState",
            "description": (
                "Get the user's current cart contents including items, quantities, prices, and total. "
                "REQUIRED BEFORE: updateCartItem, removeFromCart, initiateOrder. "
                "Call this when: user asks 'show my cart', before any quantity change, "
                "before checkout, or when resolving ambiguous references like 'remove item 2'. "
                "Never assume cart contents — always call this when in doubt."
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
                "Add a product to the user's cart. WORKFLOW: (1) Call getProductDetailsBySKU(sku) first to verify product exists, "
                "(2) Call addToCart(sku, quantity). Use SKU from chat context or previous tool calls — never guess. "
                "Extract SKU from product recommendations, search results, or user messages. "
                "If SKU is unclear, ask the user first. Quantity defaults to 1 if not specified. "
                "If adding multiple products, call this multiple times, once per product. "
                "Confirm the addition to user with product name, price, and quantity."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "sku": {
                        "type": "string",
                        "description": "The product sku (user is willing to order or add to cart) from last messages."
                    },
                    "quantity": {
                        "type": "integer",
                        "description": "How many. Defaults to 1 if not specified.",
                        "default": 1
                    }
                },
                "required": ["sku"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "removeFromCart",
            "description": (
                "Remove a product completely from the cart. WORKFLOW: (1) Call getCartState first if the reference is ambiguous (e.g., 'item 2' or 'the serum'), "
                "(2) Call removeFromCart(sku). OR use updateCartItem(sku, 0) to remove. "
                "If user says 'remove the cleanser' and there are multiple cleansers in cart, ask which one. "
                "Confirm removal to user with product name."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "sku": {
                        "type": "string",
                        "description": "The product sku to remove"
                    }
                },
                "required": ["sku"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "updateCartItem",
            "description": (
                "Update the quantity of an item already in the cart. WORKFLOW: (1) Call getCartState first to see current cart, "
                "(2) Call updateCartItem(sku, newQuantity). Use quantity=0 to remove an item. "
                "Use this to CHANGE quantity of existing items, NOT to add new items (use addToCart for that). "
                "Extract SKU from getCartState response or chat context — never guess. "
                "If multiple items match the description, ask user which one. "
                "Confirm the update to user with new quantity and total price."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "sku": {
                        "type": "string",
                        "description": "The product sku to update"
                    },
                    "quantity": {
                        "type": "integer",
                        "description": "The new quantity. Use 0 to remove."
                    }
                },
                "required": ["sku", "quantity"]
            }
        }
    },

    # ── Orders ────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "initiateOrder",
            "description": (
                "Start the order checkout process. WORKFLOW: (1) User says 'order', 'checkout', 'buy', etc., "
                "(2) Call getCartState to confirm cart is NOT empty, (3) Call initiateOrder() with no parameters. "
                "This triggers the backend to ask for customer name, phone number, and delivery address. "
                "DO NOT place order until user confirms they're ready. This is just the FIRST step of checkout. "
                "Backend will handle the rest and return an order ID on completion."
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
                "Look up a past order by its order ID. Call this when the user asks about order status, "
                "'where is my order?', or provides an order ID (8-character uppercase string like 'A1B2C3D4'). "
                "Returns order details including status, items, customer info, and timestamps. "
                "Confirm the order ID with user if unclear."
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