# Command Deck Mail Finder

Read-only Thunderbird MailExtension proof of concept for Ollama Command Deck.

## Permissions

This add-on asks for:

- `messagesRead`: read selected/search-result messages.
- `accountsRead`: include folder/account metadata in results.
- `storage`: save the local Command Deck URL, token, and optional model.
- `http://localhost:8765/*` and `http://127.0.0.1:8765/*`: call the local Command Deck bridge.

It does not request compose, send, delete, move, or message modification permissions.

## Setup

1. In Command Deck setup, enable **Read-only Thunderbird bridge** and save.
2. Copy the generated Thunderbird bridge token.
3. In Thunderbird, load this folder as a temporary add-on during development.
4. Open the add-on popup, paste the token, and save.
5. Open an email and click **Analyze Current**, or enter a search query and click **Search and Analyze**.

The add-on sends only the selected/search-result message snippets to:

```text
POST http://localhost:8765/api/thunderbird/analyze
```

Command Deck returns an analysis using only the snippets supplied in the request.
