from langchain_ollama import OllamaEmbeddings, ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.documents import Document
from langchain_chroma import Chroma

from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Any, List

from pathlib import Path
import sqlite3

import asyncio

CP_DB_PATH = Path(__file__).resolve().parent.parent / "database" / "checkpoints.sqlite"

@dataclass
class ProcessedChunk:
    url: str
    chunk_number: int
    title: str
    summary: str
    content: str
    metadata: Dict[str, Any]

# --- SEMAPHORE HELPER ---
# Do not initialize it here globally
_ollama_semaphore = None
class VectorDatabase:
    def __init__(self):
        # --- LOCAL DATABASE CONFIGURATION ---
        #TODO : add a yaml config to configure path to config and other
        DB_PATH = "./database/"
        self.embeddings_model = OllamaEmbeddings(
            model="bge-m3",
            base_url="http://jcs-macbook-pro:11434",
        )

        # Initialize ChromaDB
        self.vectorstore = Chroma(
            collection_name="agent_collection",
            embedding_function=self.embeddings_model,
            persist_directory=DB_PATH
        )

    # --- VECTOR DATABASE UTILITIES ---
    def similarity_search(self, query: str, k: int = 5) -> List[Document]:
        """Search the vector database for relevant documents."""
        try:
            results = self.vectorstore.similarity_search(query, k)
            if not results:
                return []
        except Exception as e:
            raise Exception(f"Vector DB Search Error: {e}")
        
    # --- CRAWLER ---
    async def crawl_parallel(self, urls: List[str], max_concurrent: int = 3):
        print(f"\n=== Local Research: Crawling {len(urls)} URLs ===")
        browser_config = BrowserConfig(headless=True, extra_args=["--no-sandbox"])
        crawl_config = CrawlerRunConfig(cache_mode=CacheMode.BYPASS)
        crawler = AsyncWebCrawler(config=browser_config)
        await crawler.start()

        try:
            for i in range(0, len(urls), max_concurrent):
                batch = urls[i : i + max_concurrent]
                print(f"Processing batch {i//max_concurrent + 1}...")
                
                tasks = [crawler.arun(url=url, config=crawl_config) for url in batch]
                results = await asyncio.gather(*tasks, return_exceptions=True)

                for url, result in zip(batch, results):
                    if not isinstance(result, Exception) and result.success:
                        await self.process_and_store_document(url, result.markdown)
                    else:
                        print(f"Failed to crawl: {url}")
        finally:
            await crawler.close()


    # --- SEMAPHORE MANAGEMENT ---

    @staticmethod
    def get_ollama_semaphore():
        """Lazily initializes the semaphore in the current active event loop."""
        global _ollama_semaphore
        if _ollama_semaphore is None:
            _ollama_semaphore = asyncio.Semaphore(2)
        return _ollama_semaphore

    # --- AI UTILITIES (SYNCHRONOUS) ---
    @staticmethod
    def get_title_and_summary(chunk: str, url: str) -> Dict[str, str]:
        llm = ChatOllama(
            model="mistral:v0.3", 
            base_url="http://jcs-macbook-pro:11434",
            temperature=0,
            format="json"
        )
        prompt = ChatPromptTemplate.from_messages([
            ("system", "Extract 'title' and 'summary' from this chunk as JSON."),
            ("user", "URL: {url}\n\nContent:\n{content}")
        ])
        chain = prompt | llm | JsonOutputParser()
        try:
            return chain.invoke({"url": url, "content": chunk[:1000]})
        except Exception as e:
            print(f"LLM Error: {e}")
            return {"title": "Untitled Chunk", "summary": "No summary available"}

    async def process_chunk(self, chunk: str, chunk_number: int, url: str) -> ProcessedChunk:
        # Get the semaphore that is bound to the current loop being run by the tool
        semaphore = self.get_ollama_semaphore()
        
        async with semaphore:
            # Move blocking sync calls to threads
            extracted = await asyncio.to_thread(self.get_title_and_summary, chunk, url)

        metadata = {
            "url": url,
            "chunk_number": chunk_number,
            "title": extracted.get('title', 'Untitled'),
            "summary": extracted.get('summary', 'No summary'),
            "crawled_at": datetime.now(timezone.utc).isoformat(),
            "source": "research_agent"
        }
        return ProcessedChunk(
            url=url,
            chunk_number=chunk_number,
            title=extracted.get('title', 'Untitled'),
            summary=extracted.get('summary', 'No summary'),
            content=chunk,
            metadata=metadata
        )
    
    # --- PROCESSING LOGIC ---

    @staticmethod
    def chunk_text(text: str, chunk_size: int = 5000) -> List[str]:
        # Basic splitting
        return [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]
    

    async def insert_chunks_local(self, chunks: List[ProcessedChunk]):
        """Insert processed chunks into the local ChromaDB."""
        try:
            documents = [
                Document(
                    page_content=c.content,
                    metadata=c.metadata
                ) for c in chunks
            ]
            # ChromaDB handles embeddings internally via the embeddings_model we passed
            await asyncio.to_thread(self.vectorstore.add_documents, documents)
            print(f"✓ Saved {len(chunks)} chunks to local DB from {chunks[0].url if chunks else 'N/A'}")
        except Exception as e:
            print(f"✗ Local DB Error: {e}")

    async def process_and_store_document(self, url: str, markdown: str):
        chunks = self.chunk_text(markdown)
        tasks = [self.process_chunk(c, i, url) for i, c in enumerate(chunks)]
        processed_chunks = await asyncio.gather(*tasks)
        
        # Store all chunks for this document
        await self.insert_chunks_local(processed_chunks)

class Database:
    def connect_sync(self) -> sqlite3.Connection:
        CP_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        return sqlite3.connect(CP_DB_PATH, check_same_thread=False)

class TestDatabase:

    def connect(self):
        ... # Implement connection logic for testing, e.g., using an in-memory SQLite database