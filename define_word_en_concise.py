import sys, os, requests, json
from ObsidianPluginDevPythonToJS import ObsidianPluginDevPythonToJS
obsidian = ObsidianPluginDevPythonToJS()
word = obsidian.get_selected_text().strip()
if not word: sys.exit(0)
response = requests.get(f"https://api.dictionaryapi.dev/api/v2/entries/en/{word.lower()}", timeout=5)
definition = f"'{word}' not found or API error."
if response.status_code == 200: definition = response.json()[0].get("meanings", [{}])[0].get("definitions", [{}])[0].get("definition", "Definition format unclear.")
obsidian.show_notification(f"**{word}:**\n{definition[:400]}{'...' if len(definition)>400 else ''}", 10000)

