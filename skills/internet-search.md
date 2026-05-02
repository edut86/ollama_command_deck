# Internet Search Skill

Deploy note: internet search is disabled by default in deploy mode until explicitly enabled and configured. It can contact external services.

Search works out of the box. News/headline queries use the Google News RSS fallback,
and other queries use the DuckDuckGo HTML fallback.

Configured providers are preferred when available.

For SearxNG:

```bash
export SEARXNG_URL="http://localhost:8080"
```

For Brave Search:

```bash
export BRAVE_SEARCH_API_KEY="..."
```

To require a configured provider and disable the fallback:

```bash
export DISABLE_DUCKDUCKGO_FALLBACK=1
```

Then run:

```bash
python3 -m ollama_tools.cli search "query text"
python3 hooks/search_web.py "query text"
```
