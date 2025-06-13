import os
import glob
from git import Repo
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance, PointStruct
from tqdm import tqdm
import torch

REPO_URL = "https://github.com/Qitmeer/docs"
LOCAL_PATH = "data/qitmeer-docs"
DOC_PATH = os.path.join(LOCAL_PATH, "Document", "content", "faqs")
COLLECTION_NAME = "qitmeer-docs"

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
print(f"[i] Using device: {DEVICE}")

embedding_model = SentenceTransformer("Qwen/Qwen3-Embedding-0.6B", device=DEVICE)
if DEVICE == "cuda":
    embedding_model = embedding_model.half()

client = QdrantClient(":memory:")


def clone_or_pull_repo():
    if not os.path.exists(LOCAL_PATH):
        print("[i] Cloning repo...")
        Repo.clone_from(REPO_URL, LOCAL_PATH)
    else:
        print("[i] Pulling latest changes...")
        repo = Repo(LOCAL_PATH)
        origin = repo.remotes.origin
        origin.pull()


def encode_in_batches(texts, batch_size=4):
    embeddings = []
    for i in tqdm(range(0, len(texts), batch_size), desc="Encoding embeddings"):
        batch = texts[i:i+batch_size]
        vecs = embedding_model.encode(batch, device=DEVICE)
        embeddings.extend(vecs)
    return embeddings


def rebuild_qdrant(batch_file_count=10, batch_encode_size=4):
    clone_or_pull_repo()

    all_files = glob.glob(os.path.join(DOC_PATH, "**/*.md"), recursive=True)
    print(f"[i] Found {len(all_files)} markdown files.")

    client.recreate_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(
            size=embedding_model.get_sentence_embedding_dimension(),
            distance=Distance.COSINE
        )
    )

    doc_id = 0
    for i in range(0, len(all_files), batch_file_count):
        batch_files = all_files[i:i+batch_file_count]
        texts = []

        for filepath in batch_files:
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    if content:
                        texts.append(content)
            except Exception as e:
                print(f"[!] Failed to read {filepath}: {e}")

        if not texts:
            continue

        vectors = encode_in_batches(texts, batch_size=batch_encode_size)

        points = [
            PointStruct(id=doc_id + j, vector=vec.tolist(), payload={"text": texts[j]})
            for j, vec in enumerate(vectors)
        ]
        client.upsert(collection_name=COLLECTION_NAME, points=points)
        doc_id += len(points)
        print(f"[+] Inserted batch {i//batch_file_count + 1}: {len(points)} points")

    print(f"[✅] Completed. Total documents embedded: {doc_id}")


def search_docs(query: str, top_k=3):
    vec = embedding_model.encode([query], device=DEVICE)[0]
    result = client.search(
        collection_name=COLLECTION_NAME,
        query_vector=vec.tolist(),
        limit=top_k,
    )
    return [(r.payload["text"], r.score) for r in result]
