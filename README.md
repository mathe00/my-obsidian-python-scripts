# 🐍 My Obsidian Python Bridge Scripts

Yo! Welcome to my stash of Python scripts built to supercharge Obsidian! 🚀

These scripts leverage the power of the **[Obsidian Python Bridge V2 plugin](https://github.com/mathe00/obsidian-plugin-python-bridge)**. If you haven't checked out the bridge yet, it's the thing that finally lets us Python folks automate and extend Obsidian without touching JavaScript/TypeScript. V2 is a massive upgrade, making these kinds of scripts actually practical and powerful (cross-platform, UI settings for scripts, full vault access, event listening... the works!).

Here you'll find various scripts I've cooked up – some simple, some maybe a bit more niche – designed to automate tasks, mess with metadata, or just make my (and hopefully your) Obsidian life easier. Feel free to grab, modify, and get inspired!

## ▶️ Usage

1.  Make sure you have the **[Obsidian Python Bridge V2 plugin](https://github.com/mathe00/obsidian-plugin-python-bridge)** installed and enabled in Obsidian. Follow the setup instructions in its [README](https://github.com/mathe00/obsidian-plugin-python-bridge#readme).
2.  Configure the Python Bridge plugin settings in Obsidian to point to the folder where you've placed these scripts (or your own).
3.  Ensure you have Python 3.x and `requests` installed (`pip install requests`). (Some scripts might require `PyYAML` too).
4.  Run the scripts via Obsidian's command palette! (Check the Python Bridge settings to see available script commands and configure script-specific settings if available).
5.  **Important Note:** For scripts to work reliably with plugin features like **Settings Discovery**, it's highly recommended they include the `define_settings([])` and `_handle_cli_args()` boilerplate, even if empty. See the [Python Bridge Library Docs](https://github.com/mathe00/obsidian-plugin-python-bridge/blob/main/PythonClientLibrary.md#important-script-structure-for-settings-discovery) for details. Some minimal examples here might omit this for brevity, but be aware they might cause errors during settings refresh.

## ✨ Available Scripts

Here's what's currently in the collection:

1.  **[`define_word_en_concise.py`](./define_word_en_concise.py)**
    *   **Purpose:** A **super concise example** (around 9 lines!) showing the power of the bridge. Select an English word in Obsidian, run the script, and get its definition from an online dictionary API in a notification.
    *   **Highlights:** Demonstrates `get_selected_text()`, `show_notification()`, and easy integration with external APIs via `requests`.
    *   **Note:** This script prioritizes extreme brevity over robustness. It lacks error handling and the recommended `define_settings`/`_handle_cli_args` structure (which might cause errors during plugin settings discovery/refresh but works for manual execution). It's primarily for demonstrating how few lines are needed for a useful interaction.

2.  **[`script-auto-linker.py`](./script-auto-linker.py)** (V2.3 - Robust Matching)
    *   **Purpose:** An advanced auto-linker that scans the active note for text matching other note titles in your vault and automatically creates links.
    *   **Features:**
        *   Configurable link type via plugin settings: Piped Wikilink, Simple Wikilink, or Markdown Link.
        *   Configurable options (via plugin settings) for case preservation, accent ignorance, and punctuation handling.
        *   Avoids linking inside existing links or code blocks.
        *   Handles multi-word titles accurately, even mid-sentence.
        *   Preserves frontmatter.
    *   **Requires:** Obsidian Python Bridge V2. Uses script-specific settings and the recommended structure.

3.  **[`convert_all_basic_obsidian_links_into_wikilinks.py`](./convert_all_basic_obsidian_links_into_wikilinks.py)**
    *   **Purpose:** A simple utility script (updated for V2 compatibility) that finds basic links like `[[My Note]]` and converts them to piped wikilinks like `[[My Note|My Note]]`.
    *   **Features:** Preserves frontmatter. Uses the recommended structure.
    *   **Configurable:** No specific UI settings for this one.

*(More scripts might be added over time!)*

## 💡 Contributions & Ideas

Got ideas for improvements, new scripts, or found a bug in one of these? Feel free to open an issue or PR here!

For questions about the **Obsidian Python Bridge plugin itself**, please head over to its main repository: [mathe00/obsidian-plugin-python-bridge](https://github.com/mathe00/obsidian-plugin-python-bridge).

Happy scripting! 🤘
