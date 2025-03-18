import uuid
from typing import Any, List, Optional, Tuple
import logging as logger
from langchain.docstore.document import Document
from openai import AsyncOpenAI
import aiohttp
import os

def is_non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and len(value) > 0

async def similarity_search_with_score(query: str, pinecode_config: dict, namespace: Optional[str] = None) -> List[Tuple[Document, float]]:
    """Return Pinecone documents most similar to query, along with scores."""
    
    index_name = "knowledge-base-e7mkjh1"
    filter = {"knowledge_base": pinecode_config['kb_id']} if pinecode_config.get('kb_id') else {}
    pinecone_api_key = "e1c94090-5db9-43f2-83b9-7c1a43da8136"
    pinecone_environment = "aped-4627-b74a"
    pinecone_url = f"https://{index_name}.svc.{pinecone_environment}.pinecone.io"
    model = "text-embedding-ada-002"
    openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    aiohttp_session = aiohttp.ClientSession()
    
    if not is_non_empty_string(pinecone_api_key):
        raise ValueError("Pinecone API key not set or invalid")
    
    if namespace is None:
        namespace = ""
    
    print("query : ====================================================>", query)
    query_obj = await create_openai_embedding(query, model, openai_client)
    docs = []
    filter = {key: {"$eq": value} for key, value in filter.items()} if filter else {}
    
    async with aiohttp_session.post(
        f"{pinecone_url}/query",
        headers={
            "Api-Key": pinecone_api_key,
            'Content-Type': 'application/json',
            'X-Pinecone-API-Version': '2024-07'
        },
        json={
            "topK": 3,
            "namespace": namespace,
            "filter": filter,
            "vector": query_obj,
            "includeMetadata": True,
        },
    ) as response:
        results = await response.json()
    
    for res in results.get("matches", []):
        metadata = res.get("metadata", {})
        if "text" in metadata:
            text = metadata.pop("text")
            score = res.get("score", 0)
            docs.append((Document(page_content=text, metadata=metadata), score))
        else:
            logger.warning("Found document with no `text` key. Skipping.")
    
    await aiohttp_session.close()
    return docs

async def create_openai_embedding(text: str, model: str, openai_client: AsyncOpenAI) -> List[float]:
    params = {"input": text, "model": model}
    return (await openai_client.embeddings.create(**params)).data[0].embedding
