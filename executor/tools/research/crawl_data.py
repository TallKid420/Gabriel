from daemon.database import VectorDatabase
from langchain_core.tools import tool
from ddgs import DDGS
import asyncio

database = VectorDatabase()  # Initialize the shared vector database instance

@tool(description="Pull Data in .md files from the internet for research.")
def crawl_data(query: str, max_results: int = 10):
    urls = []
    with DDGS() as ddgs:
        for r in ddgs.text(query, max_results=max_results):
            urls.append(r["href"])

    print(f"Found {len(urls)} URLs. Starting local crawl...")
    import nest_asyncio
    nest_asyncio.apply()
    
    loop = asyncio.get_event_loop()
    output = loop.run_until_complete(database.crawl_parallel(urls, max_concurrent=3))
    return output