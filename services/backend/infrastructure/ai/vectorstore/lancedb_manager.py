import os
import json
import numpy as np
from pathlib import Path
from typing import Any, List, Dict
from ....logger import logger
from ....config import settings
from .vector_persistence import VectorPersistence

class LanceDBManager:
    """
    Manages local-first vector persistence and operations.
    Runs a high-performance Cosine Similarity nearest-neighbor index using numpy,
    storing standard metadata shards within the secure sandbox.
    """
    
    def __init__(self):
        self.db_dir = VectorPersistence.get_secure_db_path()
        self.db_file = self.db_dir / "index_shards.json"
        
    def _load_shards(self) -> Dict[str, List[Dict[str, Any]]]:
        if not self.db_file.exists():
            return {}
        try:
            return json.loads(self.db_file.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"Failed to read local vector index file: {str(e)}. Initializing empty database.")
            return {}

    def _save_shards(self, shards: Dict[str, List[Dict[str, Any]]]) -> None:
        try:
            self.db_file.write_text(json.dumps(shards, indent=2, ensure_ascii=False), encoding="utf-8")
        except FileNotFoundError:
            # Handle mock testing environments where directories are bypassed
            self.db_dir.mkdir(parents=True, exist_ok=True)
            self.db_file.write_text(json.dumps(shards, indent=2, ensure_ascii=False), encoding="utf-8")

    def write_embeddings(self, collection_name: str, records: List[Dict[str, Any]]) -> bool:
        """
        Safely commits embedding vectors and metadata keys to a local collection.
        """
        logger.info(f"Writing {len(records)} vector entries to collection '{collection_name}'")
        
        # Enforce sandbox writing
        if not VectorPersistence.validate_sandbox_path(str(self.db_file)):
            raise PermissionError("Access to directory outside storage root is prohibited.")
            
        shards = self._load_shards()
        if collection_name not in shards:
            shards[collection_name] = []
            
        # Standardize records
        for rec in records:
            shards[collection_name].append({
                "vector": rec["vector"],
                "text": rec.get("text", ""),
                "metadata": rec.get("metadata", {})
            })
            
        self._save_shards(shards)
        return True

    def query_similarity(self, collection_name: str, query_vector: List[float], top_k: int = 5) -> List[Dict[str, Any]]:
        """
        Executes an in-memory matrix-multiplication nearest neighbor index search.
        Calculates Cosine Similarity across dense 384-dimensional floating point vectors.
        """
        logger.debug(f"Querying vector collection '{collection_name}' for structural similarity.")
        
        shards = self._load_shards()
        records = shards.get(collection_name, [])
        if not records:
            logger.warning(f"No records found in vector collection: {collection_name}")
            return []
            
        # 1. Convert lists to numpy arrays for accelerated matrix math
        matrix = np.array([r["vector"] for r in records], dtype=np.float32)
        query = np.array(query_vector, dtype=np.float32)
        
        # 2. Compute cosine similarity: A . B / (||A|| * ||B||)
        dot_products = np.dot(matrix, query)
        matrix_norms = np.linalg.norm(matrix, axis=1)
        query_norm = np.linalg.norm(query)
        
        # Prevent division by zero
        matrix_norms[matrix_norms == 0] = 1e-9
        if query_norm == 0:
            query_norm = 1.0
            
        similarities = dot_products / (matrix_norms * query_norm)
        
        # 3. Sort indices in descending order of similarity
        sorted_indices = np.argsort(similarities)[::-1]
        
        # 4. Formulate top K results
        results = []
        for idx in sorted_indices[:top_k]:
            sim = float(similarities[idx])
            # Convert similarity score to a standardized distance metric
            distance = 1.0 - sim
            
            results.append({
                "text": records[idx]["text"],
                "distance": distance,
                "metadata": records[idx]["metadata"]
            })
            
        return results
