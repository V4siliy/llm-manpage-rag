import os
import uuid
from typing import List, Dict, Any, Optional
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue
from qdrant_client.http.exceptions import UnexpectedResponse
from transformers import AutoModel
import torch
from django.conf import settings


class QdrantService:
    """Service for managing vector operations with Qdrant."""
    
    def __init__(self):
        self.client = QdrantClient(
            host=os.getenv('QDRANT_HOST', 'localhost'),
            port=int(os.getenv('QDRANT_PORT', '6333')),
        )
        self.collection_name = os.getenv('QDRANT_COLLECTION', 'manpages')
        self.embedding_model_name = os.getenv('EMBEDDING_MODEL', 'jinaai/jina-embeddings-v2-small-en')
        
        # Initialize local embedding model
        self.embedding_model = AutoModel.from_pretrained(
            self.embedding_model_name, 
            trust_remote_code=True
        )
        
        # Ensure collection exists
        self._ensure_collection_exists()
    
    def _ensure_collection_exists(self):
        """Create collection if it doesn't exist or recreate if dimensions don't match."""
        try:
            collection_info = self.client.get_collection(self.collection_name)
            existing_dimension = collection_info.config.params.vectors.size
            expected_dimension = 512  # Jina embeddings v2 small dimension
            
            if existing_dimension != expected_dimension:
                print(f"Collection exists with {existing_dimension} dimensions, but need {expected_dimension}")
                print("Recreating collection with correct dimensions...")
                
                # Delete existing collection
                self.client.delete_collection(self.collection_name)
                
                # Create new collection with correct dimensions
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(
                        size=expected_dimension,  # Jina embeddings v2 small dimension
                        distance=Distance.COSINE
                    )
                )
                print(f"✓ Collection recreated with {expected_dimension} dimensions")
            else:
                print(f"✓ Collection exists with correct dimensions ({existing_dimension})")
                
        except UnexpectedResponse:
            # Collection doesn't exist, create it
            print(f"Creating new collection with {512} dimensions...")
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(
                    size=512,  # Jina embeddings v2 small dimension
                    distance=Distance.COSINE
                )
            )
            print("✓ Collection created successfully")
    
    def get_embedding(self, text: str) -> List[float]:
        """Get embedding for text using Jina embeddings model."""
        try:
            # Tokenize and encode the input text
            inputs = self.embedding_model.tokenizer(text, return_tensors='pt', padding=True, truncation=True, max_length=8192)
            
            with torch.no_grad():
                # Generate embeddings
                outputs = self.embedding_model(**inputs)
                # Extract the embeddings from the model output
                embeddings = outputs.last_hidden_state.mean(dim=1)
            
            return embeddings.squeeze().tolist()
        except Exception as e:
            raise Exception(f"Failed to get embedding: {e}")
    
    def add_chunk(self, chunk_id: str, text: str, metadata: Dict[str, Any]) -> str:
        """Add a chunk to Qdrant."""
        embedding = self.get_embedding(text)
        
        # Generate a unique point ID
        point_id = str(uuid.uuid4())
        
        point = PointStruct(
            id=point_id,
            vector=embedding,
            payload={
                'chunk_id': chunk_id,
                'text': text,
                **metadata
            }
        )
        
        self.client.upsert(
            collection_name=self.collection_name,
            points=[point]
        )
        
        return point_id
    
    def search_similar(self, query: str, limit: int = 20, score_threshold: float = 0.7) -> List[Dict[str, Any]]:
        """Search for similar chunks using vector similarity."""
        query_embedding = self.get_embedding(query)
        
        search_results = self.client.search(
            collection_name=self.collection_name,
            query_vector=query_embedding,
            limit=limit,
            score_threshold=score_threshold
        )
        
        results = []
        for result in search_results:
            results.append({
                'chunk_id': result.payload['chunk_id'],
                'text': result.payload['text'],
                'score': result.score,
                'metadata': {k: v for k, v in result.payload.items() if k not in ['chunk_id', 'text']}
            })
        
        return results
    
    def search_with_filters(self, query: str, filters: Dict[str, Any], limit: int = 20) -> List[Dict[str, Any]]:
        """Search with additional filters."""
        query_embedding = self.get_embedding(query)
        
        # Build filter conditions
        filter_conditions = []
        for key, value in filters.items():
            filter_conditions.append(
                FieldCondition(key=key, match=MatchValue(value=value))
            )
        
        search_filter = Filter(must=filter_conditions) if filter_conditions else None
        
        search_results = self.client.search(
            collection_name=self.collection_name,
            query_vector=query_embedding,
            query_filter=search_filter,
            limit=limit
        )
        
        results = []
        for result in search_results:
            results.append({
                'chunk_id': result.payload['chunk_id'],
                'text': result.payload['text'],
                'score': result.score,
                'metadata': {k: v for k, v in result.payload.items() if k not in ['chunk_id', 'text']}
            })
        
        return results
    
    def delete_chunk(self, qdrant_id: str):
        """Delete a chunk from Qdrant."""
        self.client.delete(
            collection_name=self.collection_name,
            points_selector=[qdrant_id]
        )
    
    def recreate_collection(self):
        """Manually recreate the collection with correct dimensions."""
        try:
            # Delete existing collection if it exists
            try:
                self.client.delete_collection(self.collection_name)
                print(f"✓ Deleted existing collection '{self.collection_name}'")
            except UnexpectedResponse:
                print(f"Collection '{self.collection_name}' doesn't exist")
            
            # Create new collection
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(
                    size=512,  # Jina embeddings v2 small dimension
                    distance=Distance.COSINE
                )
            )
            print(f"✓ Created new collection '{self.collection_name}' with 512 dimensions")
            return True
            
        except Exception as e:
            print(f"❌ Failed to recreate collection: {e}")
            return False
    
    def get_collection_info(self) -> Dict[str, Any]:
        """Get information about the collection."""
        try:
            collection_info = self.client.get_collection(self.collection_name)
            return {
                'name': self.collection_name,
                'embedding_model': self.embedding_model_name,
                'vector_size': collection_info.config.params.vectors.size,
                'vectors_count': collection_info.vectors_count,
                'status': collection_info.status
            }
        except Exception as e:
            return {'error': str(e)}
