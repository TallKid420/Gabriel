from daemon.database import LinkQueue

q = LinkQueue()
q.add_urls(
    ["https://www.irs.gov/"],
    source_type="direct_url",
    source_value="manual_test",
    content_kind="page",
)
print(q.get_stats())

# from xml.etree import ElementTree
# from urllib.parse import urlparse
# from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
# from ddgs import DDGS
# from typing import List
# import aiohttp, psutil
# import asyncio
# import os
# from daemon.database import VectorDatabase

# HEADERS = {
#     "User-Agent": "Mozilla/5.0"
# }


# async def fetch_text(session, url):
#     try:
#         async with session.get(url, timeout=15) as response:
#             if response.status == 200:
#                 return await response.text()
#     except Exception:
#         pass
#     return None


# async def fetch_bytes(session, url):
#     try:
#         async with session.get(url, timeout=15) as response:
#             if response.status == 200:
#                 return await response.read()
#     except Exception:
#         pass
#     return None


# async def get_sitemap_urls(session, base_url):
#     candidates = []

#     robots = await fetch_text(session, f"{base_url}/robots.txt")

#     if robots:
#         for line in robots.splitlines():
#             if line.lower().startswith("sitemap:"):
#                 candidates.append(
#                     line.split(":", 1)[1].strip()
#                 )

#     candidates.extend([
#         f"{base_url}/sitemap.xml",
#         f"{base_url}/sitemap_index.xml",
#         f"{base_url}/sitemap-index.xml",
#         f"{base_url}/sitemapindex.xml",
#     ])

#     return list(dict.fromkeys(candidates))


# async def parse_sitemap(session, sitemap_url, visited):
#     if sitemap_url in visited:
#         return []

#     visited.add(sitemap_url)

#     xml_data = await fetch_bytes(session, sitemap_url)

#     if not xml_data:
#         return []

#     try:
#         root = ElementTree.fromstring(xml_data)

#         namespace = {
#             "ns": "http://www.sitemaps.org/schemas/sitemap/0.9"
#         }

#         if root.tag.endswith("urlset"):
#             return [
#                 loc.text
#                 for loc in root.findall(".//ns:loc", namespace)
#                 if loc.text
#             ]

#         if root.tag.endswith("sitemapindex"):
#             child_sitemaps = [
#                 loc.text
#                 for loc in root.findall(".//ns:loc", namespace)
#                 if loc.text
#             ]

#             results = await asyncio.gather(
#                 *[
#                     parse_sitemap(
#                         session,
#                         child,
#                         visited
#                     )
#                     for child in child_sitemaps
#                 ]
#             )

#             urls = []

#             for result in results:
#                 urls.extend(result)

#             return urls

#     except Exception:
#         pass

#     return []


# async def get_links_async(
#     query: str = "",
#     max_results: int = 10,
#     deep: bool = False,
#     search_urls: List[str] = []
# ):
#     if not search_urls:

#         if query == "":
#             raise ValueError("Either a query or a list of search URLs must be provided.")

#         with DDGS() as ddgs:
#             for result in ddgs.text(
#                 query,
#                 max_results=max_results
#             ):
#                 href = result.get("href")

#                 if href:
#                     search_urls.append(href)
        
#     print(f"[debug] DDGS returned {len(search_urls)} initial search URLs")

#     if not deep:
#         return search_urls

#     base_urls = list(dict.fromkeys(
#         f"{urlparse(url).scheme}://{urlparse(url).netloc}"
#         for url in search_urls
#     ))

#     print(f"[debug] Derived base URLs: {base_urls}")

#     connector = aiohttp.TCPConnector(
#         limit=100,
#         ssl=False
#     )

#     async with aiohttp.ClientSession(
#         connector=connector,
#         headers=HEADERS
#     ) as session:

#         sitemap_tasks = [
#             get_sitemap_urls(session, base)
#             for base in base_urls
#         ]

#         sitemap_lists = await asyncio.gather(
#             *sitemap_tasks
#         )

#         print(f"[debug] Retrieved sitemap lists for {len(sitemap_lists)} base URLs")

#         sitemap_urls = []

#         print(f"[debug] Candidate sitemap URLs deduplicated: {len(sitemap_urls)}")
#         for lst in sitemap_lists:
#             sitemap_urls.extend(lst)

#         sitemap_urls = list(dict.fromkeys(
#             sitemap_urls
#         ))

#         visited = set()

#         sitemap_results = await asyncio.gather(
#             *[
#                 parse_sitemap(
#                     session,
#                     sitemap,
#                     visited
#                 )
#                 for sitemap in sitemap_urls
#             ]
#         )

#     print(f"[debug] Completed parsing {len(sitemap_results)} sitemaps")

#     urls = []

#     for result in sitemap_results:
#         urls.extend(result)

#     print(f"[debug] Total URLs extracted from sitemaps: {len(urls)}")

#     return list(dict.fromkeys(urls))


# def get_links(
#     query: str,
#     max_results: int = 10,
#     deep: bool = True
# ):
#     return asyncio.run(
#         get_links_async(
#             query,
#             max_results,
#             deep
#         )
#     )


# async def crawl_parallel(urls: List[str], max_concurrent: int = 3):
#     print("\n=== Parallel Crawling with Browser Reuse + Memory Check ===")

#     # We'll keep track of peak memory usage across all tasks
#     peak_memory = 0
#     process = psutil.Process(os.getpid())

#     def log_memory(prefix: str = ""):
#         nonlocal peak_memory
#         current_mem = process.memory_info().rss  # in bytes
#         if current_mem > peak_memory:
#             peak_memory = current_mem
#         print(f"{prefix} Current Memory: {current_mem // (1024 * 1024)} MB, Peak: {peak_memory // (1024 * 1024)} MB")

#     # Minimal browser config
#     browser_config = BrowserConfig(
#         headless=True,
#         verbose=False,   # corrected from 'verbos=False'
#         extra_args=["--disable-gpu", "--disable-dev-shm-usage", "--no-sandbox"],
#     )
#     crawl_config = CrawlerRunConfig(cache_mode=CacheMode.BYPASS)

#     # Create the crawler instance
#     crawler = AsyncWebCrawler(config=browser_config)
#     print("[debug] Starting crawler...")
#     await crawler.start()
#     print("[debug] Crawler started")

#     try:
#         # We'll chunk the URLs in batches of 'max_concurrent'
#         success_count = 0
#         fail_count = 0
#         save_tasks = []
#         for i in range(0, len(urls), max_concurrent):
#             batch = urls[i : i + max_concurrent]
#             tasks = []

#             for j, url in enumerate(batch):
#                 # Unique session_id per concurrent sub-task
#                 session_id = f"parallel_session_{i + j}"
#                 task = crawler.arun(url=url, config=crawl_config, session_id=session_id)
#                 tasks.append(task)

#             # Check memory usage prior to launching tasks
#             log_memory(prefix=f"Before batch {i//max_concurrent + 1}: ")
#             print(f"[debug] Launching batch {i//max_concurrent + 1} with {len(tasks)} tasks: {batch}")

#             # Gather results
#             results = await asyncio.gather(*tasks, return_exceptions=True)

#             # Check memory usage after tasks complete
#             log_memory(prefix=f"After batch {i//max_concurrent + 1}: ")
#             print(f"[debug] Batch {i//max_concurrent + 1} completed, evaluating results")

#             # Evaluate results
#             for url, result in zip(batch, results):
#                 if isinstance(result, Exception):
#                     print(f"Error crawling {url}: {result}")
#                     fail_count += 1
#                 elif result.success:
#                     success_count += 1
#                     print(f"[debug] Successfully crawled: {url}")
#                     # Attempt to persist crawled content asynchronously using VectorDatabase
#                     try:
#                         # Lazy initialize vector DB (may perform network/IO during init)
#                         if 'vector_db' not in locals():
#                             print(f"[debug] Initializing VectorDatabase")
#                             vector_db = VectorDatabase()
#                             print(f"[debug] VectorDatabase initialized")

#                         # Prefer the generated markdown when available, fallback to extracted_content or html
#                         markdown = None
#                         try:
#                             markdown = str(result.markdown) if getattr(result, "markdown", None) else None
#                         except Exception:
#                             markdown = None

#                         if not markdown:
#                             markdown = getattr(result, "extracted_content", None) or getattr(result, "html", None) or ""

#                         # Fire-and-forget storing to avoid blocking crawling; log exceptions inside task
#                         async def _store(url_inner, md_inner):
#                             try:
#                                 await vector_db.process_and_store_document(url_inner, md_inner)
#                             except Exception as e:
#                                 print(f"Error saving document for {url_inner}: {e}")

#                         t = asyncio.create_task(_store(url, markdown))
#                         save_tasks.append(t)
#                         print(f"[debug] Scheduled save task for {url}")
#                     except Exception as e:
#                         print(f"Error initializing/saving to vector DB: {e}")
#                 else:
#                     fail_count += 1

#         # Wait for any scheduled save tasks to finish before summarizing
#         if save_tasks:
#             print(f"[debug] Awaiting {len(save_tasks)} save tasks to complete")
#             try:
#                 results = await asyncio.gather(*save_tasks, return_exceptions=True)
#                 for idx, r in enumerate(results):
#                     if isinstance(r, Exception):
#                         print(f"[debug] Save task {idx} error: {r}")
#             except Exception as e:
#                 print(f"[debug] Error awaiting save tasks: {e}")

#         print(f"\nSummary:")
#         print(f"  - Successfully crawled: {success_count}")
#         print(f"  - Failed: {fail_count}")

#     finally:
#         print("\nClosing crawler...")
#         await crawler.close()
#         # Final memory log
#         log_memory(prefix="Final: ")
#         print(f"\nPeak memory usage (MB): {peak_memory // (1024 * 1024)}")

# async def crawl_data(query: str = "", search_urls: List[str] = [], max_links: int = 10, deep: bool = False):
#     # Use the async version to avoid calling asyncio.run() from a running loop
#     if search_urls:
#         urls = await get_links_async(search_urls=search_urls, deep=deep)
#     else:
#         urls = await get_links_async(query, max_results=max_links, deep=deep)
#     if urls:
#         print(f"Found {len(urls)} URLs to crawl")
#         await crawl_parallel(urls, max_concurrent=10)
#     else:
#         print("No URLs found to crawl")    

# if __name__ == "__main__":
#     asyncio.run(crawl_data(search_urls=["https://www.irs.gov/"], deep=True))