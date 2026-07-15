import asyncio
import time
import inspect
from src.polaris_graph.llm.openrouter_client import OpenRouterClient


async def one(c, i):
    t = time.time()
    try:
        r = await c.generate(
            prompt=f"Write one plain sentence ({i}) about generative AI and jobs.",
            max_tokens=2000, temperature=0.3,
        )
        txt = getattr(r, "content", None)
        if txt is None and isinstance(r, dict):
            txt = r.get("content")
        print(f"call {i}: {time.time()-t:.1f}s ok content_len={len(txt or '')} preview={str(txt)[:80]!r}", flush=True)
    except Exception as e:
        print(f"call {i}: {time.time()-t:.1f}s ERR {type(e).__name__}: {str(e)[:160]}", flush=True)


async def go():
    print("generate sig:", str(inspect.signature(OpenRouterClient.generate)), flush=True)
    c = OpenRouterClient(model="z-ai/glm-5.2")
    # 5 sequential + concurrency-3 batch to mirror the writer
    t0 = time.time()
    res = await asyncio.gather(*[one(c, i) for i in range(3)])
    print(f"batch-of-3 total {time.time()-t0:.1f}s", flush=True)


asyncio.run(go())
