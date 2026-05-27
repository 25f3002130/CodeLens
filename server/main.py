from dotenv import load_dotenv
load_dotenv()
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
import os
import json
import asyncio
import anyio
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from app.core.analyzer import CodeAnalyzer
from app.core.auth import initialize_firebase, verify_token


app = FastAPI(title="CodeLens API")
initialize_firebase()

allowed_origins = [
    origin.strip()
    for origin in os.getenv("CODELENS_ALLOWED_ORIGINS", "http://localhost:3000").split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

@app.get("/health")
async def health_check():
    return {"status": "ok"}

# Initialize Core Services
analyzer = CodeAnalyzer()

@app.get("/analyze/stream")
async def analyze_repo_stream(url: str, user: dict = Depends(verify_token)):
    import queue
    progress_queue = queue.Queue()

    def progress_callback(message: str):
        progress_queue.put(message)

    async def event_generator():
        yield {"data": json.dumps({"status": "starting", "message": f"Initializing analysis for {url}"})}
        await asyncio.sleep(0.5)

        try:
            yield {"data": json.dumps({"status": "cloning", "message": "Cloning repository to secure volume..."})}

            # Run the heavy analysis in a separate thread, with progress callback
            import concurrent.futures
            loop = asyncio.get_event_loop()

            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = loop.run_in_executor(pool, lambda: analyzer.analyze_repo(url, progress_callback=progress_callback))

                # Poll for progress messages while waiting for completion
                while not future.done():
                    await asyncio.sleep(0.3)
                    # Drain all progress messages
                    while not progress_queue.empty():
                        try:
                            msg = progress_queue.get_nowait()
                            yield {"data": json.dumps({"status": "analyzing", "message": msg})}
                        except queue.Empty:
                            break

                # Get the result (may raise if the task failed)
                results = await asyncio.wait_for(asyncio.wrap_future(future), timeout=120)

            # Drain any remaining progress messages
            while not progress_queue.empty():
                try:
                    msg = progress_queue.get_nowait()
                    yield {"data": json.dumps({"status": "analyzing", "message": msg})}
                except queue.Empty:
                    break

            yield {"data": json.dumps({"status": "parsing", "message": f"Successfully analyzed {len(results['files'])} files"})}
            await asyncio.sleep(0.5)

            yield {"data": json.dumps({"status": "completed", "results": results})}
        except Exception as e:
            import traceback
            traceback.print_exc()
            yield {"data": json.dumps({"status": "error", "message": str(e)})}

    return EventSourceResponse(event_generator())

class ChatRequest(BaseModel):
    repo_id: str
    query: str

@app.post("/chat")
async def chat(request: ChatRequest, user: dict = Depends(verify_token)):
    # 1. Retrieve context from RAG
    context_results = analyzer.rag.query(request.repo_id, request.query)

    documents = context_results.get("documents") or [[]]
    metadatas = context_results.get("metadatas") or [[]]
    if not documents[0]:
        return {"answer": "I do not have indexed context for that repository yet. Run an analysis first, then ask again."}

    # Format context for the LLM
    context_str = ""
    for i, doc in enumerate(documents[0]):
        metadata = metadatas[0][i]
        context_str += f"\nFile: {metadata['file_path']}\n{doc}\n"

    # 2. Call LLM using NIM API
    nim_keys_env = os.getenv("NIM_API_KEYS", os.getenv("NIM_API_KEY", ""))
    nim_keys = [k.strip() for k in nim_keys_env.split(",") if k.strip()]

    if not nim_keys:
        return {"answer": "Error: No NIM API keys configured in NIM_API_KEYS."}

    prompt = f"""
    You are CodeLens AI. Answer the user's question about the following codebase context.
    Use the provided code snippets to be specific. If you don't know the answer, say so.

    Context:
    {context_str}

    Question: {request.query}
    """

    last_error = "No NIM API keys worked."

    # Try NIM Keys
    try:
        from openai import AsyncOpenAI
        for key in nim_keys:
            try:
                client = AsyncOpenAI(api_key=key, base_url="https://integrate.api.nvidia.com/v1")
                response = await client.chat.completions.create(
                    model="nvidia/llama-3.3-nemotron-super-49b-v1",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3
                )
                return {"answer": response.choices[0].message.content}
            except Exception as e:
                last_error = f"NIM error: {str(e)}"
                continue
    except ImportError:
        last_error = "openai package is not installed."

    return {"answer": f"Error: All NIM API attempts failed. Last error: {last_error}"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)