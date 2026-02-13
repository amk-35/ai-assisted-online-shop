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
from openai import OpenAI

client = OpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key="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"
)

# Conversation history
messages = [
    {
        "role": "system",
        "content": "You are a helpful assistant."
    }
]

while True:
    user_input = input("\nUser: ")

    if user_input.lower() in ["exit", "quit"]:
        print("Chat ended.")
        break

    # Add user message to history
    messages.append({
        "role": "user",
        "content": user_input
    })

    # Create streaming completion
    completion = client.chat.completions.create(
        model="deepseek-ai/deepseek-v3.1-terminus",
        messages=messages,
        temperature=0.2,
        top_p=0.7,
        max_tokens=2048,
        extra_body={"chat_template_kwargs": {"thinking": False}},
        stream=True
    )

    print("Assistant: ", end="")
    assistant_reply = ""

    for chunk in completion:
        if not getattr(chunk, "choices", None):
            continue

        delta = chunk.choices[0].delta
        if delta and delta.content:
            print(delta.content, end="")
            assistant_reply += delta.content

    print()  # newline after response

    # Save assistant reply back into history
    messages.append({
        "role": "assistant",
        "content": assistant_reply
    })
