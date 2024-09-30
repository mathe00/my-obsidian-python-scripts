import re
from ObsidianPluginDevPythonToJS import ObsidianPluginDevPythonToJS
import os

# Create an instance of the class
obsidian = ObsidianPluginDevPythonToJS()

# Get the absolute path of the active note
absolute_path_response = obsidian.get_active_note_absolute_path()
note_path = absolute_path_response.get('absolutePath')

if not note_path:
    obsidian.send_notification(content="Error: Unable to retrieve the note path.", duration=5000)
    exit()

# Check if the file exists and is accessible
if not os.path.isfile(note_path):
    obsidian.send_notification(content="Error: The note file does not exist or is not accessible.", duration=5000)
    exit()

# Function to replace simple links with wikilinks
def replace_simple_links_with_wikilinks(content):
    # Regex to capture [[simple link]] that does not already contain a '|' for wikilinks
    pattern = r"\[\[([^\|\]]+)\]\]"
    
    # Replacement function that adds the '|' and duplicates the link
    def replacer(match):
        link = match.group(1)
        return f"[[{link}|{link}]]"
    
    # Apply the transformation to all content
    return re.sub(pattern, replacer, content)

# Read the file content, ignoring the frontmatter
try:
    with open(note_path, 'r', encoding='utf-8') as note_file:
        lines = note_file.readlines()
except Exception as e:
    obsidian.send_notification(content=f"Error while opening the file: {str(e)}", duration=5000)
    exit()

# Identify the start of the content by ignoring the frontmatter
is_frontmatter_ended = False
new_content = []
for line in lines:
    # Ignore the frontmatter (between "---" that delimit the start and end)
    if line.strip() == "---":
        if is_frontmatter_ended:
            # Exit the frontmatter
            is_frontmatter_ended = False
        else:
            # Enter the frontmatter
            is_frontmatter_ended = True
        new_content.append(line)
        continue
    
    # If we are outside the frontmatter, perform the transformation
    if not is_frontmatter_ended:
        transformed_line = replace_simple_links_with_wikilinks(line)
        new_content.append(transformed_line)
    else:
        new_content.append(line)

# Try to rewrite the modified content into the note
try:
    with open(note_path, 'w', encoding='utf-8') as note_file:
        note_file.writelines(new_content)
except Exception as e:
    obsidian.send_notification(content=f"Error while writing to the file: {str(e)}", duration=5000)
    exit()

# Notify the user that the operation is complete
obsidian.send_notification(content="Conversion of simple links to wikilinks completed!", duration=5000)
