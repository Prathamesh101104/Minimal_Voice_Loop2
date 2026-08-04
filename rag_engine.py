import time
import os
import re
import numpy as np
from sklearn.decomposition import PCA

# Try importing FAISS; if not found, we will fall back to a NumPy-based cosine similarity matrix.
try:
    import faiss
    FAISS_AVAILABLE = True
except ImportError:
    FAISS_AVAILABLE = False

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONTEXT_PATH = os.path.join(BASE_DIR, "nimbus-voice-agent-starter", "data", "context.md")


# Singleton engine instance
_RAG_ENGINE = None

class SimpleMockEmbedder:
    """Fallback embedding generator based on word frequencies if no API keys are provided."""
    def __init__(self, vocab_size=128):
        self.vocab = {}
        self.vocab_size = vocab_size

    def fit(self, texts):
        # Build simple vocabulary
        words = []
        for t in texts:
            words.extend(re.findall(r'\w+', t.lower()))
        
        # Keep most common
        from collections import Counter
        common = Counter(words).most_common(self.vocab_size)
        self.vocab = {word: idx for idx, (word, _) in enumerate(common)}

    def embed(self, text):
        vector = np.zeros(self.vocab_size)
        for word in re.findall(r'\w+', text.lower()):
            if word in self.vocab:
                vector[self.vocab[word]] += 1
        norm = np.linalg.norm(vector)
        if norm > 0:
            vector = vector / norm
        return vector

class RAGEngine:
    def __init__(self, openai_key=None, gemini_key=None):
        # Validate and sanitize key formats to avoid failing API network loops on startup
        raw_openai = openai_key or os.getenv("OPENAI_API_KEY")
        raw_gemini = gemini_key or os.getenv("GEMINI_API_KEY")
        
        self.openai_key = raw_openai if (raw_openai and raw_openai.strip().startswith("sk-") and len(raw_openai.strip()) > 10) else None
        self.gemini_key = raw_gemini if (raw_gemini and raw_gemini.strip().startswith("AIzaSy") and len(raw_gemini.strip()) > 10) else None
        
        self.chunks = []          # List of dicts: {"id": int, "title": str, "content": str, "category": str}
        self.embeddings = None     # NumPy array of shape (N, D)
        self.index = None         # FAISS Index
        self.pca = None           # Fitted PCA instance
        self.coords_2d = None     # 2D coordinates for chunks
        self.embedder = None      # Mock or API-based embedder
        
        self.load_and_chunk_context()
        self.build_index()

    def load_and_chunk_context(self):
        if not os.path.exists(CONTEXT_PATH):
            # Fallback if context.md doesn't exist
            self.chunks = [{"id": 0, "title": "Welcome", "content": "Nimbus all-in-one cloud platform.", "category": "Company"}]
            return

        with open(CONTEXT_PATH, 'r', encoding='utf-8') as f:
            content = f.read()

        # Split by headers (e.g. ## Product:, ## Company Policies, etc.)
        sections = re.split(r'\n(?=## )', content)
        
        chunk_id = 0
        for sec in sections:
            sec = sec.strip()
            if not sec:
                continue
                
            # Parse header/title
            lines = sec.split('\n')
            title = lines[0].replace('##', '').strip()
            
            # Determine category based on content/title
            category = "Company"
            if "Product:" in title or "Product ID" in sec:
                category = "Product"
            elif "Policy" in title or "Policies" in sec:
                category = "Policy"
            elif "FAQ" in title or "Q:" in sec:
                category = "FAQ"

            # If section is very large, split it further by subheadings or paragraphs
            if len(sec) > 1500:
                subsections = re.split(r'\n(?=### |#### )', sec)
                for sub in subsections:
                    sub = sub.strip()
                    if not sub:
                        continue
                    sub_lines = sub.split('\n')
                    sub_title = sub_lines[0].replace('###', '').replace('####', '').strip()
                    self.chunks.append({
                        "id": chunk_id,
                        "title": f"{title} - {sub_title}",
                        "content": sub,
                        "category": category
                    })
                    chunk_id += 1
            else:
                self.chunks.append({
                    "id": chunk_id,
                    "title": title,
                    "content": sec,
                    "category": category
                })
                chunk_id += 1

    def get_embedding(self, text):
        """Generates embedding using OpenAI, Gemini or local mock embedder depending on keys."""
        # Use mock embedding if keys are missing
        if not self.openai_key and not self.gemini_key:
            if not isinstance(self.embedder, SimpleMockEmbedder):
                self.embedder = SimpleMockEmbedder()
                self.embedder.fit([c["content"] for c in self.chunks])
            return self.embedder.embed(text)
            
        # Use OpenAI Embeddings if key exists
        if self.openai_key:
            try:
                import openai
                client = openai.OpenAI(api_key=self.openai_key)
                response = client.embeddings.create(
                    input=[text],
                    model="text-embedding-3-small"
                )
                return np.array(response.data[0].embedding, dtype=np.float32)
            except Exception as e:
                print(f"OpenAI embedding error: {e}. Falling back to mock.")
                
        # Use Gemini Embeddings if key exists
        if self.gemini_key and self.gemini_key.startswith("AIzaSy"):
            try:
                import google.generativeai as genai
                genai.configure(api_key=self.gemini_key)
                result = genai.embed_content(
                    model="models/text-embedding-004",
                    content=text,
                    task_type="retrieval_document",
                    request_options={"timeout": 1.0}
                )
                return np.array(result['embedding'], dtype=np.float32)
            except Exception as e:
                print(f"Gemini embedding skipped: {e}. Using fast local vector embedder.")

        # Final fallback
        if not self.embedder:
            self.embedder = SimpleMockEmbedder()
            self.embedder.fit([c["content"] for c in self.chunks])
        return self.embedder.embed(text)

    def build_index(self):
        if not self.chunks:
            return

        print(f"Embedding {len(self.chunks)} chunks for RAG...")
        embeddings_list = []
        for c in self.chunks:
            emb = self.get_embedding(c["content"])
            embeddings_list.append(emb)

        self.embeddings = np.array(embeddings_list, dtype=np.float32)
        
        # Build vector index
        if FAISS_AVAILABLE:
            dimension = self.embeddings.shape[1]
            self.index = faiss.IndexFlatIP(dimension) # Inner Product for Cosine Similarity (vectors must be normalized)
            # Normalize vectors
            norms = np.linalg.norm(self.embeddings, axis=1, keepdims=True)
            norms[norms == 0] = 1.0 # avoid divide by zero
            normalized_embeddings = self.embeddings / norms
            self.index.add(normalized_embeddings)
            print("FAISS index built successfully.")
        else:
            print("FAISS not available. Falling back to NumPy cosine similarity.")

        # Fit PCA to project to 2D
        n_samples = self.embeddings.shape[0]
        n_features = self.embeddings.shape[1]
        n_components = min(2, n_samples, n_features)
        
        self.pca = PCA(n_components=n_components)
        self.coords_2d = self.pca.fit_transform(self.embeddings)
        
        # If n_components < 2 (e.g. only 1 chunk), pad with zeros
        if self.coords_2d.shape[1] < 2:
            padding = np.zeros((self.coords_2d.shape[0], 2 - self.coords_2d.shape[1]))
            self.coords_2d = np.hstack((self.coords_2d, padding))

    def query(self, text, k=3):
        """Retrieves top-k nearest chunks, projects query to 2D, and performs lexical reranking."""
        if not self.chunks:
            return [], [0, 0]

        query_emb = self.get_embedding(text).astype(np.float32)
        
        # Project query to 2D PCA space
        query_coord = self.pca.transform(query_emb.reshape(1, -1))[0]
        if len(query_coord) < 2:
            query_coord = np.append(query_coord, 0.0)

        # Vector search
        if FAISS_AVAILABLE and self.index:
            # Normalize query vector
            q_norm = np.linalg.norm(query_emb)
            if q_norm > 0:
                query_emb = query_emb / q_norm
            scores, indices = self.index.search(query_emb.reshape(1, -1), min(k * 2, len(self.chunks))) # Retrieve double for reranking
            scores = scores[0]
            indices = indices[0]
        else:
            # NumPy cosine similarity search
            norms = np.linalg.norm(self.embeddings, axis=1)
            norms[norms == 0] = 1.0
            q_norm = np.linalg.norm(query_emb)
            if q_norm == 0:
                q_norm = 1.0
            
            cos_sim = np.dot(self.embeddings, query_emb) / (norms * q_norm)
            indices = np.argsort(cos_sim)[::-1][:min(k * 2, len(self.chunks))]
            scores = cos_sim[indices]

        # Map to actual chunks
        retrieved = []
        for rank, (idx, score) in enumerate(zip(indices, scores)):
            if idx < 0 or idx >= len(self.chunks):
                continue
            chunk = self.chunks[idx].copy()
            chunk["vector_score"] = float(score)
            chunk["x"] = float(self.coords_2d[idx][0])
            chunk["y"] = float(self.coords_2d[idx][1])
            retrieved.append(chunk)

        # Lexical Reranking: Calculate token overlap between query and chunk content
        query_words = set(re.findall(r'\w+', text.lower()))
        for chunk in retrieved:
            chunk_words = set(re.findall(r'\w+', chunk["content"].lower()))
            overlap = len(query_words.intersection(chunk_words))
            jaccard = overlap / len(query_words.union(chunk_words)) if query_words else 0
            # Combined score: 70% vector score + 30% jaccard lexical score
            chunk["rerank_score"] = 0.7 * chunk["vector_score"] + 0.3 * jaccard

        # Sort by rerank score and keep top k
        retrieved.sort(key=lambda x: x["rerank_score"], reverse=True)
        final_retrieved = retrieved[:k]

        return final_retrieved, query_coord.tolist()

    def get_all_coordinates(self):
        """Returns coordinates of all indexed chunks for visualizer plotting."""
        nodes = []
        for idx, c in enumerate(self.chunks):
            nodes.append({
                "id": c["id"],
                "title": c["title"],
                "category": c["category"],
                "x": float(self.coords_2d[idx][0]),
                "y": float(self.coords_2d[idx][1])
            })
        return nodes

def get_rag_engine(openai_key=None, gemini_key=None, force_reload=False):
    global _RAG_ENGINE
    if _RAG_ENGINE is None or force_reload:
        _RAG_ENGINE = RAGEngine(openai_key, gemini_key)
    else:
        # Update keys if provided
        if openai_key:
            _RAG_ENGINE.openai_key = openai_key
        if gemini_key:
            _RAG_ENGINE.gemini_key = gemini_key
    return _RAG_ENGINE
