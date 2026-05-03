"""
Qdrant data dashboard — visual overview of all indexed companies.

Usage:
    python indexers/qdrant_dashboard.py
    # Opens browser at http://localhost:7861
"""

import os
from collections import Counter, defaultdict

import gradio as gr
from dotenv import load_dotenv
from qdrant_client import QdrantClient

load_dotenv()

# ── Qdrant helpers ─────────────────────────────────────────────────────────────

def _client() -> QdrantClient:
    return QdrantClient(
        url=os.getenv("QDRANT_HOST", "localhost"),
        api_key=os.getenv("QDRANT_API_KEY"),
        prefer_grpc=False,
    )


def _fetch_all_records(client: QdrantClient, collection: str) -> list[dict]:
    """Scroll all records from a collection."""
    records, offset = [], None
    while True:
        result, next_offset = client.scroll(
            collection_name=collection,
            offset=offset,
            limit=100,
            with_payload=True,
            with_vectors=False,
        )
        records.extend(r.payload or {} for r in result)
        if next_offset is None:
            break
        offset = next_offset
    return records


# ── Views ──────────────────────────────────────────────────────────────────────

def load_overview() -> tuple[str, list[list]]:
    """
    Returns (status_text, table_rows).
    Table columns: Company | Total | default | company_specific | source_types
    """
    try:
        client = _client()
        collections = sorted(c.name for c in client.get_collections().collections)
    except Exception as e:
        return f"❌ Cannot connect to Qdrant: {e}", []

    rows = []
    for col in collections:
        try:
            info  = client.get_collection(col)
            total = info.points_count or 0

            # Quick tag + source_type breakdown from a sample (max 250)
            result, _ = client.scroll(col, limit=250, with_payload=True, with_vectors=False)
            payloads   = [r.payload or {} for r in result]

            tag_counter  = Counter()
            type_counter = Counter()
            for p in payloads:
                for t in (p.get("tags") or "").split(";"):
                    t = t.strip()
                    if t:
                        tag_counter[t] += 1
                stype = (p.get("source_type") or "").strip()
                if stype:
                    type_counter[stype] += 1

            defaults  = tag_counter.get("default", 0)
            specific  = tag_counter.get("company_specific", 0)
            types_str = ", ".join(f"{k}:{v}" for k, v in sorted(type_counter.items()))

            rows.append([col, total, defaults, specific, types_str or "—"])
        except Exception as e:
            rows.append([col, "error", "—", "—", str(e)])

    status = f"✅ Connected — {len(collections)} collections"
    return status, rows


def load_company_detail(collection: str) -> tuple[str, list[list]]:
    """Returns (summary_text, article_rows)."""
    if not collection:
        return "Select a company above.", []
    try:
        client  = _client()
        records = _fetch_all_records(client, collection)
    except Exception as e:
        return f"❌ {e}", []

    if not records:
        return f"No records in `{collection}`.", []

    type_counter = Counter(r.get("source_type", "—") for r in records)
    tag_counter  = Counter(
        t.strip()
        for r in records
        for t in (r.get("tags") or "").split(";")
        if t.strip()
    )

    summary = (
        f"**{collection}** — {len(records)} articles\n\n"
        f"Source types: {dict(type_counter)}\n\n"
        f"Tags: {dict(tag_counter)}"
    )

    article_rows = [
        [
            r.get("source_type", ""),
            "✅ default" if "default" in (r.get("tags") or "") else "🏢 specific",
            r.get("question", "")[:80],
            r.get("answer", "")[:120],
        ]
        for r in records
    ]
    return summary, article_rows


def search_collection(collection: str, query: str) -> list[list]:
    """Simple keyword search across question + answer fields."""
    if not collection or not query.strip():
        return []
    try:
        client  = _client()
        records = _fetch_all_records(client, collection)
    except Exception:
        return []

    q = query.lower()
    results = []
    for r in records:
        question = r.get("question", "") or ""
        answer   = r.get("answer",   "") or ""
        if q in question.lower() or q in answer.lower():
            results.append([
                r.get("source_type", ""),
                "✅" if "default" in (r.get("tags") or "") else "🏢",
                question[:80],
                answer[:150],
            ])
    return results


# ── Gradio UI ──────────────────────────────────────────────────────────────────

def _get_collection_names() -> list[str]:
    try:
        return sorted(c.name for c in _client().get_collections().collections)
    except Exception:
        return []


with gr.Blocks(title="Qdrant Dashboard", theme=gr.themes.Soft()) as demo:

    gr.Markdown("# 📊 Qdrant Data Dashboard")

    # Shared state: collection names loaded on demand
    _collections_state = gr.State([])

    with gr.Row():
        connect_btn = gr.Button("🔌 Connect to Qdrant", variant="primary")
        connect_status = gr.Textbox(label="Status", interactive=False, scale=5,
                                    value="Click 'Connect to Qdrant' to load data.")

    def _connect():
        try:
            names = _get_collection_names()
            status = f"✅ Connected — {len(names)} collections found"
            return status, names, gr.Dropdown(choices=names), gr.Dropdown(choices=names)
        except Exception as e:
            return f"❌ {e}", [], gr.Dropdown(choices=[]), gr.Dropdown(choices=[])

    # ── Tab 1: Overview ────────────────────────────────────────────────────────
    with gr.Tab("Overview"):
        gr.Markdown("All indexed companies and their article counts.")

        with gr.Row():
            refresh_btn  = gr.Button("🔄 Load Overview", variant="secondary", scale=1)
            filter_box   = gr.Textbox(label="Filter by company name", placeholder="happy / hns / crg …", scale=4)

        _overview_state = gr.State([])
        overview_table  = gr.Dataframe(
            headers=["Company", "Total", "Default", "Company-specific", "Source types"],
            datatype=["str", "number", "number", "number", "str"],
            interactive=False,
            wrap=True,
        )

        def _refresh():
            _, rows = load_overview()
            return rows, rows

        def _filter(rows, keyword):
            if not keyword.strip():
                return rows
            kw = keyword.strip().lower()
            return [r for r in rows if kw in r[0].lower()]

        refresh_btn.click(_refresh, outputs=[_overview_state, overview_table])
        filter_box.change(_filter, inputs=[_overview_state, filter_box], outputs=[overview_table])

    # ── Tab 2: Company detail ──────────────────────────────────────────────────
    with gr.Tab("Company Detail"):
        gr.Markdown("Browse all articles for a specific company collection.")

        company_dd = gr.Dropdown(choices=[], label="Select company", interactive=True)
        load_btn   = gr.Button("Load Articles", variant="secondary")
        summary_md = gr.Markdown()
        detail_table = gr.Dataframe(
            headers=["Source type", "Tag", "Question", "Answer preview"],
            datatype=["str", "str", "str", "str"],
            interactive=False,
            wrap=True,
        )

        load_btn.click(
            lambda col: load_company_detail(col),
            inputs=[company_dd],
            outputs=[summary_md, detail_table],
        )

    # ── Tab 3: Search ──────────────────────────────────────────────────────────
    with gr.Tab("Search"):
        gr.Markdown("Keyword search within a company's collection.")

        with gr.Row():
            search_company = gr.Dropdown(choices=[], label="Company", interactive=True, scale=2)
            search_box     = gr.Textbox(label="Search keyword", placeholder="เบิกเงิน / OTP / withdraw", scale=3)
            search_btn     = gr.Button("Search 🔍", variant="primary", scale=1)

        search_results = gr.Dataframe(
            headers=["Source type", "Tag", "Question", "Answer preview"],
            datatype=["str", "str", "str", "str"],
            interactive=False,
            wrap=True,
        )

        search_btn.click(search_collection, inputs=[search_company, search_box], outputs=[search_results])
        search_box.submit(search_collection, inputs=[search_company, search_box], outputs=[search_results])

    # Connect button wires up status + both dropdowns at once
    connect_btn.click(
        _connect,
        outputs=[connect_status, _collections_state, company_dd, search_company],
    )


if __name__ == "__main__":
    demo.launch(server_port=7861, share=False)
