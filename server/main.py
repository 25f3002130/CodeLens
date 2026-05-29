from dotenv import load_dotenv
load_dotenv()
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
import os
import json
import asyncio
import anyio
import re
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

allow_origin_regex = None
if os.getenv("ALLOW_VERCEL_ORIGINS", "true").lower() in {"1", "true", "yes", "on"}:
    allow_origin_regex = r"https://.*\.vercel\.app"

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=allow_origin_regex,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

@app.get("/health")
async def health_check():
    return {"status": "ok"}

# Initialize Core Services
analyzer = CodeAnalyzer()


def _safe_read_file(repo_path: str, relative_path: str, max_bytes: int = 12000) -> str:
    if not repo_path or not relative_path:
        return ""

    full_path = os.path.normpath(os.path.join(repo_path, relative_path))
    repo_root = os.path.normpath(repo_path)
    if not full_path.startswith(repo_root):
        return ""

    if not os.path.exists(full_path) or not os.path.isfile(full_path):
        return ""

    try:
        with open(full_path, "r", errors="ignore") as handle:
            return handle.read(max_bytes)
    except Exception:
        return ""


def _build_graph_neighbors(snapshot: dict) -> dict:
    neighbors = {}
    for link in snapshot.get("graph", {}).get("links", []):
        source = str(link.get("source", ""))
        target = str(link.get("target", ""))
        if not source or not target:
            continue
        neighbors.setdefault(source, set()).add(target)
        neighbors.setdefault(target, set()).add(source)
    return neighbors


def _resolve_file_candidates(snapshot: dict, query: str):
    files = snapshot.get("files", [])
    lowered = query.lower()

    exact_path_matches = [f for f in files if f.get("file_path") and f["file_path"].lower() in lowered]
    if exact_path_matches:
        return exact_path_matches

    basename_matches = []
    for f in files:
        file_path = str(f.get("file_path", ""))
        basename = os.path.basename(file_path).lower()
        if basename and basename in lowered:
            basename_matches.append(f)

    if basename_matches:
        return basename_matches

    tokens = [token.strip(".,:;!?()[]{}\"'").lower() for token in query.split()]
    heuristic_matches = []
    for f in files:
        file_path = str(f.get("file_path", "")).lower()
        basename = os.path.basename(file_path)
        if any(token == basename.lower() or token in file_path for token in tokens if len(token) > 2):
            heuristic_matches.append(f)

    return heuristic_matches


def _is_general_query(query: str) -> bool:
    lowered = query.lower()
    general_markers = ["overview", "summary", "what does", "how does", "explain", "architecture", "repo", "project", "security", "dependency", "hotspot", "readme"]
    return any(marker in lowered for marker in general_markers)


def _build_file_context(snapshot: dict, targets: list[dict], query: str) -> tuple[str, list[str]]:
    repo_path = snapshot.get("repo_path", "")
    neighbors = _build_graph_neighbors(snapshot)
    files_by_path = {str(f.get("file_path", "")): f for f in snapshot.get("files", [])}

    if len(targets) > 1:
        choices = "\n".join([f"- {f.get('file_path')}" for f in targets[:8]])
        return (
            f"I found multiple files matching your request. Please specify the exact file path:\n{choices}",
            []
        )

    target = targets[0]
    target_path = str(target.get("file_path", ""))
    context_files = [target_path]

    related_paths = []
    for path in sorted(neighbors.get(target_path, set())):
        if path in files_by_path and path != target_path:
            related_paths.append(path)

    same_dir = os.path.dirname(target_path)
    for f in snapshot.get("files", []):
        path = str(f.get("file_path", ""))
        if path != target_path and os.path.dirname(path) == same_dir:
            related_paths.append(path)

    if target_path.lower().endswith("readme.md"):
        related_paths = related_paths[:3]

    unique_related = []
    seen = set(context_files)
    for path in related_paths:
        if path not in seen:
            seen.add(path)
            unique_related.append(path)

    sections = [f"Target file: {target_path}"]
    target_content = _safe_read_file(repo_path, target_path)
    if target_content:
        sections.append(f"\nFile content of {target_path}:\n{target_content}")

    if unique_related:
        sections.append("\nDirectly related files:")
    for path in unique_related[:5]:
        related_content = _safe_read_file(repo_path, path)
        if related_content:
            sections.append(f"\nFile content of {path}:\n{related_content}")

    return "\n".join(sections), [target_path, *unique_related[:5]]


def _build_general_context(snapshot: dict) -> str:
    parts = [
        f"Repository URL: {snapshot.get('repo_url', '')}",
        f"Total files: {len(snapshot.get('files', []))}",
    ]

    tech_stack = snapshot.get("tech_stack", {}) or {}
    if tech_stack:
        parts.append(f"Tech stack: {json.dumps(tech_stack)[:3000]}")

    dependencies = snapshot.get("ai_dependencies", {}) or {}
    if dependencies:
        parts.append(f"Dependencies: {json.dumps(dependencies)[:3000]}")

    hotspots = snapshot.get("hotspots", []) or []
    if hotspots:
        parts.append(f"Hotspots: {json.dumps(hotspots[:10])[:3000]}")

    vulnerabilities = snapshot.get("vulnerabilities", []) or []
    if vulnerabilities:
        parts.append(f"Security findings: {json.dumps(vulnerabilities[:10])[:3000]}")

    special_files = snapshot.get("special_files", []) or []
    for file_info in special_files[:5]:
        parts.append(f"\nFile: {file_info.get('file_path')}\n{file_info.get('content', '')[:3000]}")

    top_files = snapshot.get("files", [])[:8]
    if top_files:
        parts.append("\nRepository structure:")
        parts.extend([f"- {f.get('file_path')} ({f.get('language')})" for f in top_files])

    return "\n".join(parts)

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
    snapshot = analyzer.ingestion.load_snapshot(request.repo_id)
    if not snapshot:
        return {"answer": "I could not find a stored repo snapshot for that repository yet. Run an analysis first, then ask again."}

    matched_files = _resolve_file_candidates(snapshot, request.query)
    if matched_files and not _is_general_query(request.query):
        context_str, matched_paths = _build_file_context(snapshot, matched_files, request.query)
        if "Please specify the exact file path" in context_str:
            return {"answer": context_str}
    else:
        context_str = _build_general_context(snapshot)
        matched_paths = []

    # 2. Call LLM using NIM API
    nim_keys_env = os.getenv("NIM_API_KEYS", os.getenv("NIM_API_KEY", ""))
    nim_keys = [k.strip() for k in nim_keys_env.split(",") if k.strip()]

    if not nim_keys:
        return {"answer": "Error: No NIM API keys configured in NIM_API_KEYS."}

    prompt = f"""
    You are CodeLens AI. Answer the user's question about the following codebase context.
    Use the provided repo structure, linked files, hotspots, dependencies, security findings, and direct file contents to be specific.
    If the query references a file and the file is provided below, prioritize that file and its directly related neighbors.
    If the query is general, summarize the repository from the provided context.

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