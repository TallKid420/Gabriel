from langchain_core.tools import tool
from daemon.database import VectorDatabase

database = VectorDatabase()  # Initialize the shared vector database instance

def graph_search(query: str) -> str:
    # Placeholder for graph search logic
    return "Graph search results for query: " + query

@tool(description="""Retrieve relevant documentation chunks based on the query with RAG. Use this to find factual information from crawled sites. Result: formatted string.""")
def vector_search(query: str, limit: int = 10) -> str:
    # Logic remains the same, accessing your shared vectorstore
    try:
        # Chroma/LangChain search logic
        results = database.similarity_search(query, k=limit)
        
        if not results:
            return "No relevant documentation chunks found in the local database."
            
        formatted_results = []
        for i, doc in enumerate(results, 1):
            source = doc.metadata.get("url", "Unknown Source")
            title = doc.metadata.get("title", "Untitled")
            
            formatted_results.append(
                f"--- Result {i} ---\n"
                f"Source: {source}\n"
                f"Title: {title}\n"
                f"Content: {doc.page_content}\n"
            )
            
        return "\n".join(formatted_results)
        
    except Exception as e:
        return f"Error retrieving documentation: {str(e)}"