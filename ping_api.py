"""Quick ping test for vLLM endpoint."""
import os
from dotenv import load_dotenv
load_dotenv()
from openai import OpenAI

key = os.getenv("OPENAI_API_KEY")
base_url = os.getenv("OPENAI_BASE_URL")
model = os.getenv("OPENAI_MODEL")
print(f"Endpoint: {base_url}")
print(f"Model:    {model}")
print(f"Key:      {key[:12]}...")

client = OpenAI(api_key=key, base_url=base_url, timeout=15.0, max_retries=0)
try:
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": "Say exactly: PING OK"}],
        max_tokens=10,
    )
    print("SUCCESS:", resp.choices[0].message.content)
except Exception as e:
    print("FAILED:", e)
