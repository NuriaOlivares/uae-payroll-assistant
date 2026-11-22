"""Retrieve legal chunks, then answer with citations. Run: python -m app.answer "your question" """
import json
import os
import sys

from app.tools import TOOL_SCHEMAS, run_tool

INDEX_DIR = os.getenv("INDEX_DIR", "data/index")
MODEL = os.getenv("ANSWER_MODEL", "claude-sonnet-5-5")
TOP_K = int(os.getenv("TOP_K", "10"))  # k=10: retrieval recall 96% vs 85% at k=5 (evals/RESULTS.md)
MAX_TOOL_ROUNDS = 4

SYSTEM = """You answer questions about UAE employment law for HR specialists and employees.
Rules:
1. Use ONLY the numbered sources provided. Do not use outside knowledge about the law.
2. Cite every legal claim with the exact citation label of the source in square brackets,
   e.g. [FDL 33/2021, Art. 29(1)]. Never cite a source you were not given.
3. Any calculation MUST be done with the provided tools. Never do arithmetic yourself.
   Gratuity uses BASIC salary only. If a needed input is missing, ask for it.
4. If the sources do not answer the question, say "I'm not sure" and say what is missing.
   Do not guess. Personal data (the user's pay, raises, company policy) is not in the sources.
5. Assume UAE federal private-sector law and say so. If the user says they work in DIFC, ADGM
   or another free zone, say your sources do not cover that regime and do not apply the federal answer.
6. Be concise. This is general information, not legal advice."""

_collection = None
_client = None


def retrieve(question: str, k: int = TOP_K) -> list[dict]:
    global _collection
    if _collection is None:
        import chromadb
        _collection = chromadb.PersistentClient(path=INDEX_DIR).get_collection("legal")
    res = _collection.query(query_texts=[question], n_results=k, where={"jurisdiction": "federal"})
    return [{"id": i, "citation": m["citation"], "text": d, "distance": dist}
            for i, m, d, dist in zip(res["ids"][0], res["metadatas"][0],
                                     res["documents"][0], res["distances"][0])]


def _anthropic():
    global _client
    if _client is None:
        from anthropic import Anthropic
        _client = Anthropic()  # reads ANTHROPIC_API_KEY
    return _client


def build_prompt(question: str, chunks: list[dict]) -> str:
    sources = "\n\n".join(f"[Source {n}] ({c['citation']})\n{c['text']}" for n, c in enumerate(chunks, 1))
    return f"Sources:\n{sources}\n\nQuestion: {question}"


def ask(question: str) -> dict:
    chunks = retrieve(question)
    messages = [{"role": "user", "content": build_prompt(question, chunks)}]
    tool_calls, answer = [], None
    for _ in range(MAX_TOOL_ROUNDS):
        resp = _anthropic().messages.create(model=MODEL, max_tokens=1000, system=SYSTEM,
                                            tools=TOOL_SCHEMAS, messages=messages)
        if resp.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": resp.content})
            results = []
            for block in resp.content:
                if block.type == "tool_use":
                    out = run_tool(block.name, block.input)
                    tool_calls.append({"name": block.name, "input": block.input, "output": out})
                    results.append({"type": "tool_result", "tool_use_id": block.id,
                                    "content": json.dumps(out)})
            messages.append({"role": "user", "content": results})
            continue
        answer = "".join(b.text for b in resp.content if b.type == "text")
        break
    return {"question": question,
            "answer": answer or "I'm not sure. I could not complete the answer.",
            "retrieved": [{"id": c["id"], "citation": c["citation"], "distance": round(c["distance"], 4)}
                          for c in chunks],
            "tool_calls": tool_calls}


if __name__ == "__main__":
    print(json.dumps(ask(" ".join(sys.argv[1:])), indent=2, ensure_ascii=False))