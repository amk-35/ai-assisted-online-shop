# from openai import OpenAI
#
# client = OpenAI(
#     base_url="https://openrouter.ai/api/v1",
#     api_key="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",
# )
#
# # Initialize an empty conversation history
# conversation = []
#
#
# # Function to handle multi-turn conversation
# def chat():
#     while True:
#         # Get user input
#         user_input = input("You: ")
#
#         if user_input.lower() in ['exit', 'quit', 'bye']:  # End conversation if user types 'exit'
#             print("Ending the conversation.")
#             break
#
#         # Add user input to conversation history
#         conversation.append({
#             "role": "user",
#             "content": user_input
#         })
#
#         # Get assistant's response
#         completion = client.chat.completions.create(
#             extra_headers={
#                 "HTTP-Referer": "<YOUR_SITE_URL>",  # Optional. Site URL for rankings on openrouter.ai.
#                 "X-Title": "<YOUR_SITE_NAME>",  # Optional. Site title for rankings on openrouter.ai.
#             },
#             extra_body={},
#             model="deepseek/deepseek-r1-0528:free",
#             messages=conversation
#         )
#
#         # Get the assistant's message from the response
#         assistant_reply = completion.choices[0].message.content
#         print(f"Assistant: {assistant_reply}")
#
#         # Add assistant's response to conversation history
#         conversation.append({
#             "role": "assistant",
#             "content": assistant_reply
#         })
#
#
# # Start the chat
# chat()


# from openai import OpenAI
#
# client = OpenAI(
#     base_url="https://integrate.api.nvidia.com/v1",
#     api_key="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"
# )
#
# # Conversation history
# messages = [
#     {
#         "role": "system",
#         "content": "You are a helpful assistant."
#     }
# ]
#
# while True:
#     user_input = input("\nUser: ")
#
#     if user_input.lower() in ["exit", "quit"]:
#         print("Chat ended.")
#         break
#
#     # Add user message to history
#     messages.append({
#         "role": "user",
#         "content": user_input
#     })
#
#     # Create streaming completion
#     completion = client.chat.completions.create(
#         model="deepseek-ai/deepseek-v3.1-terminus",
#         messages=messages,
#         temperature=0.2,
#         top_p=0.7,
#         max_tokens=2048,
#         extra_body={"chat_template_kwargs": {"thinking": False}},
#         stream=True
#     )
#
#     print("Assistant: ", end="")
#     assistant_reply = ""
#
#     for chunk in completion:
#         if not getattr(chunk, "choices", None):
#             continue
#
#         delta = chunk.choices[0].delta
#         if delta and delta.content:
#             print(delta.content, end="")
#             assistant_reply += delta.content
#
#     print()  # newline after response
#
#     # Save assistant reply back into history
#     messages.append({
#         "role": "assistant",
#         "content": assistant_reply
#     })




# from openai import OpenAI
# import os
# import sys
#
# _USE_COLOR = sys.stdout.isatty() and os.getenv("NO_COLOR") is None
# _RESET_COLOR = "\033[0m" if _USE_COLOR else ""
#
# client = OpenAI(
#     base_url="https://integrate.api.nvidia.com/v1",
#     api_key="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"  # 🔐 best practice
# )
#
# # Store full conversation history
# messages = []
#
# def chat_once(user_input: str):
#     global messages
#
#     # Add user message
#     messages.append({"role": "user", "content": user_input})
#
#     completion = client.chat.completions.create(
#         model="z-ai/glm5",
#         messages=messages,
#         temperature=1,
#         top_p=1,
#         max_tokens=4096,
#         extra_body={
#             "chat_template_kwargs": {
#                 "enable_thinking": False,
#                 "clear_thinking": True
#             }
#         },
#         stream=True
#     )
#
#     assistant_reply = ""
#
#     for chunk in completion:
#         if not getattr(chunk, "choices", None):
#             continue
#         if not chunk.choices or not getattr(chunk.choices[0], "delta", None):
#             continue
#
#         delta = chunk.choices[0].delta
#         if getattr(delta, "content", None):
#             print(delta.content, end="", flush=True)
#             assistant_reply += delta.content
#
#     print()  # newline after response
#
#     # Save assistant reply for next turn
#     messages.append({"role": "assistant", "content": assistant_reply})
#
#
# # ===== Interactive loop =====
# print("Multi-turn chat started. Type 'exit' to quit.\n")
#
# while True:
#     user_input = input("You: ")
#     if user_input.lower() in {"exit", "quit"}:
#         break
#
#     print("Assistant: ", end="")
#     chat_once(user_input)
# import requests
#
# url = "http://127.0.0.1:11434/api/chat"
# # Initialize the conversation history
# messages = []
#
# print("--- Chat started (Type 'exit' or 'quit' to stop) ---")
#
# while True:
#     # 1. Get user input
#     user_input = input("You: ")
#
#     if user_input.lower() in ['exit', 'quit']:
#         break
#
#     # 2. Add user message to history
#     messages.append({"role": "user", "content": user_input})
#
#     payload = {
#         "model": "gemma3",
#         "messages": messages,  # Send the WHOLE history
#         "stream": False
#     }
#
#     try:
#         response = requests.post(url, json=payload)
#         response.raise_for_status()
#
#         # 3. Get AI response and add it to history
#         assistant_message = response.json()['message']
#         messages.append(assistant_message)
#
#         print(f"AI: {assistant_message['content']}\n")
#
#     except Exception as e:
#         print(f"Error: {e}")
#         break
import requests
import json
from datetime import datetime

# ────────────────────────────────────────────────
# Configuration
# ────────────────────────────────────────────────
invoke_url = "https://integrate.api.nvidia.com/v1/chat/completions"
api_key = "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"  # ← replace with your real key if needed

headers = {
    "Authorization": f"Bearer {api_key}",
    "Accept": "text/event-stream",
    "Content-Type": "application/json"
}

MODEL = "meta/llama-4-scout-17b-16e-instruct"

# Example tools (OpenAI-compatible schema)
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_current_weather",
            "description": "Get the current weather in a given location",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "The city and state, e.g. San Francisco, CA"},
                    "unit": {"type": "string", "enum": ["celsius", "fahrenheit"], "description": "Temperature unit"}
                },
                "required": ["location"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "Get the current time in UTC",
            "parameters": {"type": "object", "properties": {}}
        }
    }
]

# Simple dummy tool implementations (replace with real ones)
def get_current_weather(location: str, unit: str = "celsius") -> str:
    # Dummy response – in production call real weather API
    return f"It's 22°C and sunny in {location}."

def get_current_time() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

TOOL_MAP = {
    "get_current_weather": get_current_weather,
    "get_current_time": get_current_time
}

# ────────────────────────────────────────────────
# Multi-turn conversation with tool calling loop
# ────────────────────────────────────────────────
def chat_with_tool_calling(user_messages: list[str], max_rounds: int = 5):
    messages = [{"role": "system", "content": "You are a helpful assistant that can use tools when needed."}]

    for idx, user_text in enumerate(user_messages, 1):
        print(f"\n{'─'*60}\nUser ({idx}): {user_text}\n{'─'*60}")

        messages.append({"role": "user", "content": user_text})

        round_num = 0
        final_answer = None

        while round_num < max_rounds:
            round_num += 1
            print(f"  Round {round_num}...")

            payload = {
                "model": MODEL,
                "messages": messages,
                "tools": TOOLS,               # enable tool calling
                "tool_choice": "auto",        # "auto", "required", "none", or {"type":"function","function":{"name":"..."}}
                "max_tokens": 512,
                "temperature": 0.7,
                "top_p": 0.95,
                "stream": True
            }

            response = requests.post(invoke_url, headers=headers, json=payload, stream=True)

            full_content = ""
            tool_calls = []

            for line in response.iter_lines():
                if line:
                    decoded = line.decode("utf-8")
                    if decoded.startswith("data: "):
                        data = decoded[6:].strip()
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                            delta = chunk["choices"][0]["delta"]
                            if "content" in delta and delta["content"]:
                                print(delta["content"], end="", flush=True)
                                full_content += delta["content"]
                            if "tool_calls" in delta:
                                tool_calls.extend(delta["tool_calls"])
                        except:
                            pass

            print()  # newline after streaming

            # If no tool calls → this is the final answer
            if not tool_calls:
                final_answer = full_content.strip()
                messages.append({"role": "assistant", "content": final_answer})
                break

            # Handle tool calls
            messages.append({"role": "assistant", "content": full_content, "tool_calls": tool_calls})

            for tool_call in tool_calls:
                func_name = tool_call["function"]["name"]
                args_str = tool_call["function"]["arguments"]
                try:
                    args = json.loads(args_str)
                except:
                    args = {}

                print(f"  → Calling tool: {func_name}({args})")

                if func_name in TOOL_MAP:
                    result = TOOL_MAP[func_name](**args)
                    print(f"  ← Tool result: {result}")
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "name": func_name,
                        "content": str(result)
                    })
                else:
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "name": func_name,
                        "content": "Tool not found"
                    })

        if final_answer:
            print(f"\nFinal Answer:\n{final_answer}\n")
        else:
            print("→ Max rounds reached without final answer.")

# ────────────────────────────────────────────────
# Test multi-turn with tool usage
# ────────────────────────────────────────────────
if __name__ == "__main__":
    conversation = [
        "What's the weather like in Clifton, New Jersey right now?",
        "And what time is it in UTC?",
        "Thanks! Now tell me a short joke about AI."
    ]

    chat_with_tool_calling(conversation)