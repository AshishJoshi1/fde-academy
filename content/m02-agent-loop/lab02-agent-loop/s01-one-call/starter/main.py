import os

import anthropic

client = anthropic.Anthropic()  # in the lab, the key and URL are injected for you (relay)
MODEL = os.getenv("LAB_MODEL", "claude-opus-5-5")

response = client.messages.create(
    model=MODEL,
    max_tokens=1024,
    output_config={"effort": "low"},  # Opus 5.5: thinking can't be disabled; effort is the dial
    messages=[{"role": "user", "content": "In one sentence: what is an agent loop?"}],
)

print("stop_reason:", response.stop_reason)
print("blocks:", [block.type for block in response.content])

# Keep only text blocks: content[0] may be a (empty) thinking block.
answer = "".join(block.text for block in response.content if block.type == "text")
print("answer:", answer)

u = response.usage
print(f"usage: input={u.input_tokens} output={u.output_tokens} "
      f"cache_write={u.cache_creation_input_tokens} cache_read={u.cache_read_input_tokens}")
