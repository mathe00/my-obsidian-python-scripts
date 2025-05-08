# 🐍 My Obsidian Python Bridge Scripts

Yo! Welcome to my stash of Python scripts built to supercharge Obsidian! 🚀

These scripts leverage the power of the **[Obsidian Python Bridge V2 plugin](https://github.com/mathe00/obsidian-plugin-python-bridge)**. If you haven't checked out the bridge yet, it's the thing that finally lets us Python folks automate and extend Obsidian without touching JavaScript/TypeScript. V2 is a massive upgrade, making these kinds of scripts actually practical and powerful (cross-platform, UI settings for scripts, full vault access, event listening... the works!).

Here you'll find various scripts I've cooked up – some simple, some maybe a bit more niche – designed to automate tasks, mess with metadata, or just make my (and hopefully your) Obsidian life easier. Feel free to grab, modify, and get inspired!

## ▶️ Usage

1.  Make sure you have the **[Obsidian Python Bridge V2 plugin](https://github.com/mathe00/obsidian-plugin-python-bridge)** installed and enabled in Obsidian. Follow the setup instructions in its [README](https://github.com/mathe00/obsidian-plugin-python-bridge#readme).
2.  Configure the Python Bridge plugin settings in Obsidian to point to the folder where you've placed these scripts (or your own).
3.  Ensure you have Python 3.x and `requests` installed (`pip install requests`). (Some scripts might require `PyYAML` too).
4.  Run the scripts via Obsidian's command palette! (Check the Python Bridge settings to see available script commands and configure script-specific settings if available).

## ✨ Available Scripts

Here's what's currently in the collection:

1.  **`convert_all_basic_obsidian_links_into_wikilinks.py`**
    *   **Purpose:** A simple utility script (originally from V1 era, updated for V2 compatibility) that finds basic links like `[[My Note]]` and converts them to piped wikilinks like `[[My Note|My Note]]`.
    *   **Features:** Preserves frontmatter.
    *   **Configurable:** No specific UI settings for this one.

2.  **`script-auto-linker.py`** (V2.3 - Robust Matching)
    *   **Purpose:** An advanced auto-linker that scans the active note for text matching other note titles in your vault and automatically creates links.
    *   **Features:**
        *   Configurable link type via plugin settings:
            *   Piped Wikilink: `[[Note Title|Matched Text]]`
            *   Simple Wikilink: `[[Note Title]]`
            *   Markdown Link: `[Matched Text](Note%20Path.md)`
        *   Configurable options (via plugin settings) for:
            *   Preserving original text case in links.
            *   Ignoring accents when matching text to titles.
            *   Handling punctuation adjacent to matched text.
        *   Avoids linking inside existing links or code blocks.
        *   Handles multi-word titles accurately, even mid-sentence.
        *   Preserves frontmatter.
    *   **Requires:** Obsidian Python Bridge V2. Uses script-specific settings.

*(More scripts might be added over time!)*

## 💡 Contributions & Ideas

Got ideas for improvements, new scripts, or found a bug in one of these? Feel free to open an issue or PR here!

For questions about the **Obsidian Python Bridge plugin itself**, please head over to its main repository: [mathe00/obsidian-plugin-python-bridge](https://github.com/mathe00/obsidian-plugin-python-bridge).

Happy scripting! 🤘
