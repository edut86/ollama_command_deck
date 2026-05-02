# Third-Party Notices

Ollama Command Deck is a local control surface built around other open-source
and externally maintained projects. This file is an acknowledgement list, not a
complete legal license audit. Before redistributing packaged builds, review the
exact dependency versions you ship and their upstream license files.

## Core Runtime And AI Stack

| Project | Use in this app |
|---|---|
| [Ollama](https://ollama.com/) | Local model server and model API |
| [LangChain](https://www.langchain.com/) | Optional agent/tool orchestration |
| [langchain-ollama](https://python.langchain.com/docs/integrations/chat/ollama/) | LangChain integration for Ollama chat models |
| [Model Context Protocol](https://modelcontextprotocol.io/) | Optional MCP server/client-facing tool surface |

## Voice And Speech

| Project | Use in this app |
|---|---|
| [edge-tts](https://github.com/rany2/edge-tts) | Optional Microsoft Edge online text-to-speech backend |
| [Piper](https://github.com/rhasspy/piper) / `piper-tts` | Optional self-hosted offline text-to-speech backend |
| [espeak-ng](https://github.com/espeak-ng/espeak-ng) | Phoneme generation dependency for Piper |
| [faster-whisper](https://github.com/SYSTRAN/faster-whisper) | Optional local speech-to-text support |
| [CTranslate2](https://github.com/OpenNMT/CTranslate2) | Runtime used by faster-whisper |

Voice model files are not bundled in this repository. Users must download voices
separately and follow the license for each voice model they choose.

## Document And File Handling

| Project | Use in this app |
|---|---|
| [pypdf](https://github.com/py-pdf/pypdf) | Text extraction from PDF files |
| [python-docx](https://github.com/python-openxml/python-docx) | Text extraction from `.docx` files |
| [PyMuPDF](https://github.com/pymupdf/PyMuPDF) | PDF page rendering for scanned/visual PDFs |

Note: PyMuPDF has specific license terms. Confirm they fit your distribution
model before publishing packaged binaries or commercial builds.

## Containers And System Packages

| Project | Use in this app |
|---|---|
| [Docker](https://www.docker.com/) | Containerized deployment |
| [Python Docker images](https://hub.docker.com/_/python) | Base images for the web and Piper containers |
| [tini](https://github.com/krallin/tini) | Container init process |
| [OpenSSH](https://www.openssh.com/) | Optional SSH command tooling inside the container |
| [FFmpeg](https://ffmpeg.org/) | Audio/document media handling support |

## Search And Monitoring Integrations

| Project or service | Use in this app |
|---|---|
| [DuckDuckGo](https://duckduckgo.com/) | Optional fallback web search |
| [Brave Search API](https://brave.com/search/api/) | Optional configured web search provider |
| [SearxNG](https://docs.searxng.org/) | Optional self-hosted metasearch provider |
| [Netdata](https://www.netdata.cloud/) | Optional monitoring integration |
| [Prometheus](https://prometheus.io/) | Optional monitoring integration |
| [Glances](https://nicolargo.github.io/glances/) | Optional monitoring integration |

## Skill/Profile Inspiration

Some profile-scoped context files are inspired by public AI skill patterns and
should be treated as derivative prompt documentation, not bundled executables.
Credits include:

| Source | Use in this app |
|---|---|
| `softaworks/agent-toolkit/humanizer` on skills.sh | Humanizer-style writing guidance |
| `juliusbrussee/caveman/caveman` on skills.sh | Terse/brief response profile inspiration |
| `obra/superpowers/systematic-debugging` on skills.sh | Debugging workflow profile inspiration |
| `anthropics/skills/frontend-design` on skills.sh | Frontend design profile inspiration |
| `anthropics/skills/skill-creator` on skills.sh | Skill creation profile inspiration |

## Models

This repository does not include Ollama models. Model names in examples, such as
`qwen3.5:latest`, `llava:7b`, or `dolphin3`, are examples only. Users are
responsible for downloading models from their chosen source and complying with
those model licenses.
