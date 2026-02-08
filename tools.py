# ============================================================
# tools.py — Mistral tool definitions (UPDATED WITH PAGINATION)
# ============================================================

TOOLS = [

    # ── Knowledge ─────────────────────────────────────────
    # {
    #     "type": "function",
    #     "function": {
    #         "name": "getSkincareKnowledge",
    #         "description": (
    #             "Answer skincare knowledge questions using your own knowledge. "
    #             "Use this when the user asks about ingredients, skin routines, skin types, "
    #             "how to use products, or general skincare advice. "
    #             "IMPORTANT: Whenever you call this, ALSO call searchProducts() in parallel with limit 5. Don't call this when the brand contain brand name that is not from our store, instead call without brand and recommend alternatives"
    #             "to surface relevant products from our store alongside the knowledge answer."
    #         ),
    #         "parameters": {
    #             "type": "object",
    #             "properties": {
    #                 "topic": {
    #                     "type": "string",
    #                     "description": "The skincare topic or ingredient. e.g. 'retinol', 'vitamin C', 'how to moisturize'"
    #                 },
    #                 "skinType": {
    #                     "type": "string",
    #                     "enum": ["oily", "dry", "combination", "sensitive", "normal"],
    #                     "description": "The user's skin type if known from context"
    #                 },
    #                 "concern": {
    #                     "type": "string",
    #                     "description": "A specific skin concern if relevant. e.g. 'acne', 'anti-aging', 'dryness'"
    #                 }
    #             },
    #             "required": ["topic"]
    #         }
    #     }
    # },
    #
    # # ── Products ──────────────────────────────────────────
    # {
    #     "type": "function",
    #     "function": {
    #         "name": "searchProducts",
    #         "description": (
    #             "Search our store's product catalog with robust fallback logic and pagination support. "
    #             "Returns up to [limit] products with total count metadata like 'showing 6 of 43'. "
    #             "Use this to: "
    #             "1) Browse products by free-text query (use for user keyword except category and brand), category(choose from context), brand, or other filters, "
    #             "2) Find recommendations based on skin type or concern, "
    #             "3) Surface relevant products alongside knowledge answers. "
    #             "If the same search is repeated, automatically excludes previously-shown products. "
    #             "Handles compound categories like 'Essence / Serums' — searching 'essence' or 'serums' works. "
    #             "If no results with all filters, automatically falls back to looser criteria. "
    #             "Call this ALWAYS when answering skincare knowledge questions. "
    #             "When user asks for 'more' of the SAME search, use searchMoreProducts() instead."
    #             "If user says: "
    #               "around 30000 → min_price: 20000, max_price: 40000"
    #               "between 15000 and 25000 → min_price: 15000, max_price: 25000"
    #               "cheap → max_price: 20000"
    #               "premium → min_price: 500000"
    #             "If user ask with tell me more about the ....., search that with just query parameter."
    #             "Don't call this when the brand contain brand name that is not from our store, instead call without brand and recommend alternatives"
    #             "Don't call this too many times. Max 3"
    #         ),
    #         "parameters": {
    #             "type": "object",
    #             "properties": {
    #                 "query": {
    #                     "type": "string",
    #                     "description": "Free-text search across product name, description, and ingredients. e.g. 'vitamin C', 'gel cleanser'"
    #                 },
    #                 "sku": {
    #                     "type": "string",
    #                     "description": "Search by product SKU code. e.g. 'SKU-001'"
    #                 },
    #                 "category": {
    #                     "type": "string",
    #                     "description": "Product category. e.g. 'cleanser', 'moisturizer', 'serum', 'essence', 'toner', 'sunscreen'"
    #                 },
    #                 "skinType": {
    #                     "type": "string",
    #                     "enum": ["oily", "dry", "combination", "sensitive", "normal"],
    #                     "description": "Filter by skin type"
    #                 },
    #                 "concern": {
    #                     "type": "string",
    #                     "description": "Filter by concern. e.g. 'acne', 'anti-aging', 'dryness', 'brightening'"
    #                 },
    #                 "brand": {
    #                     "type": "string",
    #                     "description": "Filter by brand name"
    #                 },
    #                 "minPrice": {
    #                     "type": "number",
    #                     "description": "Minimum price filter"
    #                 },
    #                 "maxPrice": {
    #                     "type": "number",
    #                     "description": "Maximum price filter"
    #                 },
    #                 "stock": {
    #                     "type": "boolean",
    #                     "description": "Filter by availability. true = in stock only, false = out of stock only"
    #                 },
    #                 "limit": {
    #                     "type": "integer",
    #                     "description": "Max number of results to return. Default: 6.",
    #                     "default": 6
    #                 }
    #             },
    #             "required": []
    #         }
    #     }
    # },
    # {
    #     "type": "function",
    #     "function": {
    #         "name": "searchMoreProducts",
    #         "description": (
    #             "Get MORE products from the previous search. Use this when user says: "
    #             "'show me more', 'what else?', 'see other options', 'next', 'different ones', or similar. "
    #             "This continues the last search with the SAME filters but shows NEW products "
    #             "that haven't been shown yet (automatically excludes already-shown products). "
    #             "Returns an error if there's no previous search or all matching products have been shown. "
    #             "IMPORTANT: Only use this if the user is explicitly asking for MORE of the SAME search, "
    #             "NOT if they're changing filters or asking a completely different question. "
    #             "Examples: 'show me more serums' after already showing serums → use this. "
    #             "'show me moisturizers' after showing serums → use searchProducts instead."
    #         ),
    #         "parameters": {
    #             "type": "object",
    #             "properties": {},
    #             "required": []
    #         }
    #     }
    # },
    # {
    #     "type": "function",
    #     "function": {
    #         "name": "printAllProductsByBrand",
    #         "description": (
    #             "Print all products from the database grouped by brand. "
    #             "Use this only when the user asks to see all products."
    #             "or wants a complete inventory listing."
    #             "Don't use this when user is asking just all available brands"
    #             "Returns a formatted output showing each brand with its products and SKUs."
    #             "Give the response to user with the the same output as this function."
    #         ),
    #         "parameters": {
    #             "type": "object",
    #             "properties": {},
    #             "required": []
    #         }
    #     }
    # },
    # {
    #     "type": "function",
    #     "function": {
    #         "name": "findProductsByBrand",
    #         "description": (
    #             "Find all products for a specific brand. "
    #             "Use this when the user asks to see products from a particular brand.Not when user is just asking all available brands."
    #             "Don't use brand names that are not in our store.Don't call this function when user give a brand name that is not from our store, instead say brand not available. "
    #             "Returns products organized by brand name with their SKUs, prices, and availability."
    #             "Use when needed."
    #             "Give the response to user with the same output as this function."
    #         ),
    #         "parameters": {
    #             "type": "object",
    #             "properties": {
    #                 "brand": {
    #                     "type": "string",
    #                     "description": "The brand name to search for. e.g. 'Simple', 'Garnier'"
    #                 }
    #             },
    #             "required": ["brand"]
    #         }
    #     }
    # },
    # {
    #     "type": "function",
    #     "function": {
    #         "name": "getProductDetail",
    #         "description": (
    #             "Get full details for one specific product: ingredients, price, stock, description. "
    #             "Use this when the user says 'tell me more about...' or 'what are the ingredients of...' "
    #             "a specific product. Resolve 'that one' or 'the first one' using the lastShownProducts "
    #             "context in the system prompt to get the correct productId."
    #         ),
    #         "parameters": {
    #             "type": "object",
    #             "properties": {
    #                 "productId": {
    #                     "type": "integer",
    #                     "description": "The product ID. Get this from lastShownProducts context."
    #                 }
    #             },
    #             "required": ["productId"]
    #         }
    #     }
    # },
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

    # ── Inventory Metadata ────────────────────────────────
    # {
    #     "type": "function",
    #     "function": {
    #         "name": "getTotalProductsCount",
    #         "description": (
    #             "Get the total count of all products available in the store. "
    #             "Use this when the user wants to know how many products are available. "
    #             "Returns the total number of items in the product catalog."
    #         ),
    #         "parameters": {
    #             "type": "object",
    #             "properties": {},
    #             "required": []
    #         }
    #     }
    # },

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
                "Be aware of user messages for skin types and concerns."
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
                "Resolve references first. Use last chat messages to resolve sku intelligently."
                "look at previous chat history to find the correct sku of the product user is telling."
                "Only use sku you can see in the context — never guess. If you are not sure, ask back to user."
                "If you are sure, don't ask back to user."
                "You must call multiple times if there are many products or a set of products. Be precise in sku."
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
                "Remove a product from the cart."
                "If the user says 'remove item 2' or 'remove the cleanser', "
                "resolve the reference using the cart contents (call getCartState first if needed)."
                "If you are not sure ask back to user."
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
                "Resolve references first. Use last chat messages to resolve sku intelligently."
                "Update the quantity of an item already in the cart."
                "Use this when updating existing items in the cart, don't confuse with addToCart function."
                "Call this intelligently using chat messages."
                "Only use sku you can see in the context — never guess. If you are not sure, ask back to user."
                "If you are sure, don't ask back to user."
                "You must call multiple times if there are many products or a set of products. Be precise in sku."
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