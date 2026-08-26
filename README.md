# 🐍 My Obsidian Python Bridge Scripts

Yo! Welcome to my stash of Python scripts built to supercharge Obsidian! 🚀

These scripts leverage the power of the **[Obsidian Python Bridge V2 plugin](https://github.com/mathe00/obsidian-plugin-python-bridge)** — the thing that lets Python folks automate and extend Obsidian without touching JavaScript/TypeScript.

This repo is also a **"why Python?" showcase**: half of these scripts do things that would be genuinely painful in TypeScript — hand-rolled TF-IDF and PageRank over your vault, executable code blocks, checksum algorithms, fuzzy diffing — most of it with **zero third-party dependencies**, just the standard library doing what it does best.

Everything is:

- ✅ aligned with the **current V2 API** (verified against the bridge source),
- ✅ following the **recommended script structure** (`define_settings` / `_handle_cli_args`, event guard),
- ✅ covered by a real unit-test suite *plus* integration tests running against the actual bridge library,
- ✅ linted & formatted with **[ruff](https://docs.astral.sh/ruff/)**.

## ▶️ Usage

1. Install & enable the **[Obsidian Python Bridge V2 plugin](https://github.com/mathe00/obsidian-plugin-python-bridge)**.
2. Point its *Python scripts folder* setting at a folder containing these scripts.
3. Ensure Python 3.x + `requests` are available (the plugin checks on startup).
4. Run scripts from the command palette; configure their settings in the plugin tab.

Optional dependencies unlock extra powers:

```bash
pip install pandas matplotlib   # vault-analytics: DataFrame stats + PNG chart
pip install pypdf               # pdf-to-note
pip install qrcode[pil]         # qr-code-generator
pip install pytesseract pillow  # ocr-image-transcriber (+ system tesseract binary)
```

Every optional-dependency script **degrades gracefully**: missing deps produce a friendly notification, never a crash.

## ✨ Core Scripts

### 1. [`script-auto-linker.py`](./script-auto-linker.py) — V2.4, the heavy artillery

Scans the active note for text matching other note titles in your vault and links it automatically.

- Configurable link type: piped wikilink `[[Title|match]]`, simple `[[Title]]`, or markdown `[match](path)`.
- Case-preserving aliases, accent-insensitive matching, punctuation handling — all exposed as UI settings.
- Find-all-then-replace strategy: longest titles win, overlaps resolved deterministically, frontmatter preserved.
- Orchestration in injectable `run(client)`; every pure helper unit-tested.

**Known limitations (pinned by tests, preserved on purpose):**

| Limitation | Detail |
| --- | --- |
| `]` never counts as trailing punctuation | The punctuation class `\[\s.,;!?()]` contains an unescaped `]`, which silently closes the class. A title directly followed by `]` produces no match at all. Side-effect: existing wikilinks/markdown links ending in brackets are naturally protected — fragile, so we pin rather than silently "fix". |
| Conservative fenced-code heuristic | `is_inside_link_or_code` treats everything after a closed ` ``` ` block as still-inside code. One fenced block ⇒ rest of the note is skipped. |
| Midpoint protection check | Matches straddling two structures can slip through the inside-link test. |
| Ligatures are not accents | NFD doesn't decompose ligatures: `cœur` never matches `coeur`. |

### 2. [`convert_all_basic_obsidian_links_into_wikilinks.py`](./convert_all_basic_obsidian_links_into_wikilinks.py)

Finds simple links `[[My Note]]` in the active note and pipes them into `[[My Note|My Note]]`. Frontmatter untouched; pure transform in `process_lines(lines) -> (new_lines, changed)`.

### 3. [`define_word_en_concise.py`](./define_word_en_concise.py) — the minimal demo

Select an English word → definition from [dictionaryapi.dev](https://dictionaryapi.dev) in a notification. Intentionally tiny, but robust: malformed payloads degrade gracefully instead of crashing.

## 🧪 Python-Power POCs

| Script | The flex | Deps |
| --- | --- | --- |
| [`semantic-similar-notes.py`](./semantic-similar-notes.py) | Hand-rolled **TF-IDF + cosine similarity** across the whole vault; suggests related notes you haven't linked yet. Pure stdlib math. | none |
| [`link-graph-insights.py`](./link-graph-insights.py) | Google's **PageRank, implemented by hand** on your vault's link graph + degree centrality + orphan detection → dashboard note. No networkx. | none |
| [`executable-code-blocks.py`](./executable-code-blocks.py) | **Jupyter-lite**: ```python #run fences execute, stdout captured into idempotent result callouts. ⚠️ Runs arbitrary code — same trust model as the bridge. | none |
| [`fuzzy-duplicate-finder.py`](./fuzzy-duplicate-finder.py) | Near-duplicate notes via `difflib.SequenceMatcher` + exact body clones via MD5 fingerprints. | none |
| [`csv-to-markdown-table.py`](./csv-to-markdown-table.py) | Select raw CSV → aligned Markdown table. Delimiter sniffing, quoted fields, pipe escaping — stdlib `csv` flex. | none |
| [`isbn-book-card.py`](./isbn-book-card.py) | ISBN selection → card with cover. **Hand-coded ISBN-10/13 checksum validation** + OpenLibrary/GoogleBooks mashup. | requests |
| [`vault-analytics.py`](./vault-analytics.py) | Word-count analytics dashboard. With pandas/matplotlib: real stats + PNG histogram; without: pure-stdlib fallback report. | optional pandas+matplotlib |
| [`qr-code-generator.py`](./qr-code-generator.py) | Text/link → QR PNG in attachments, embedded in note. Shows bridge FS ops (`check_path_exists`, `create_folder`). | optional qrcode[pil] |
| [`pdf-to-note.py`](./pdf-to-note.py) | PDF embeds in the active note → sibling extracted markdown notes with per-page sections + heading heuristic. | optional pypdf |
| [`ocr-image-transcriber.py`](./ocr-image-transcriber.py) | Image embeds get Tesseract transcriptions injected as idempotent callouts. Engine injectable = fully testable. | optional pytesseract+pillow |

Common pattern across all ten: **pure core functions + injectable `run(client)`** — every script ships with its own test file, heavy engines are injectable seams, optional imports degrade loudly-but-politely.

## 🛠️ Development

Layout:

```
├── *.py                    ← 13 scripts at the root (the bridge discovers .py files)
├── pyproject.toml          # metadata + ruff + pytest config
├── tests/
│   ├── conftest.py         # bridge stub injected before any import + fake client fixtures
│   ├── test_*.py           # one suite per script
│   └── test_bridge_integration.py   # subprocess runs against the REAL bridge library
├── LICENSE
└── README.md
```

Commands ([uv](https://docs.astral.sh/uv/) manages everything):

```bash
uv sync                 # create .venv + dev tools (ruff, pytest)
uv run ruff format .    # format
uv run ruff check .     # lint (zero violations expected)
uv run pytest           # whole suite (~5 s, no Obsidian needed)
```

How tests work without Obsidian running:

- `tests/conftest.py` injects a **stub** of `ObsidianPluginDevPythonToJS` into `sys.modules`
  *before* any script import, then hands out a configurable mock client (`bind_client(mod)` + `fake_bridge`).
- `test_bridge_integration.py` executes scripts in subprocesses against a local clone of the
  [bridge repo](https://github.com/mathe00/obsidian-plugin-python-bridge), verifying the **event guard**
  exits 0 and `--get-settings-json` prints valid definitions using the *real* current library. Self-skips otherwise.

> 💡 Found while testing: some recent bridge builds' shim does not re-export
> `is_handling_event()` even though docs mention it. These scripts therefore use a
> graceful fallback chain (shim → package module → plain env check).

## 🤝 Contributions & Ideas

Issues and PRs welcome! For questions about the **bridge plugin itself**, head to [mathe00/obsidian-plugin-python-bridge](https://github.com/mathe00/obsidian-plugin-python-bridge).

Happy scripting! 🤘
