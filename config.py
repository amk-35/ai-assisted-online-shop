import os

# ── Database ──────────────────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./products.db")

# ── NVIDIA API (Mistral Large via NVIDIA) ────────────────────
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "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")
NVIDIA_INVOKE_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
MODEL_ID = "mistralai/mistral-large-3-675b-instruct-2512"

# ── Model parameters ──────────────────────────────────────────
TEMPERATURE = 0.15
MAX_TOKENS = 2048
TOP_P = 1.0
FREQUENCY_PENALTY = 0.0
PRESENCE_PENALTY = 0.0

# ── System prompt template ────────────────────────────────────
SYSTEM_PROMPT_TEMPLATE = """You are a friendly skincare assistant for our online skincare store.
Your job: help users learn about skincare AND find products from our store.

━━━ RULES ━━━
1. When answering ANY skincare knowledge question, ALSO call searchProducts()
   to surface relevant products. Knowledge always pairs with a product suggestion.
2. Resolve references using the context below:
   - "that one" / "the first one" → use lastShownProducts
   - "item 2 in my cart" → call getCartState() first if needed
3. If a request is ambiguous, ask ONE clarifying question. Do not guess.
4. Never make up product details. Only use data returned by tools.
5. Before initiating an order, confirm with the user that they're ready.
6. Be warm, concise, and helpful. Never robotic.

━━━ CURRENT CONTEXT ━━━
{context}
━━━ END CONTEXT ━━━
"""