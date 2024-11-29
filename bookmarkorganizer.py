#!./venv/bin/python

import json
import sys
from fuzzywuzzy import fuzz  # Ensure this library is installed (`pip install fuzzywuzzy`)
from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup
import os
import hashlib


# Path to your bookmarks JSON file
BOOKMARKS_FILE = "/Users/edmundsitumorang/Library/CloudStorage/OneDrive-Personal/Applications/Bookmark Organizer/bookmarks.json"
CACHE_DIR = "cover_image_cache"

# Create cache directory if it doesn't exist
if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)

def get_cover_image(url):
    # Generate a unique filename based on URL hash
    url_hash = hashlib.md5(url.encode()).hexdigest()
    local_image_path = os.path.join(CACHE_DIR, f"{url_hash}.webp")

    # Check if the image is already cached locally
    if os.path.exists(local_image_path):
        return local_image_path

    # Fetch cover image if not found locally
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, 'html.parser')
        og_image = soup.find('meta', property='og:image')
        if og_image and og_image['content']:
            image_url = og_image['content']
            # Download and save the image locally
            image_response = requests.get(image_url, stream=True)
            if image_response.status_code == 200:
                with open(local_image_path, 'wb') as f:
                    for chunk in image_response.iter_content(1024):
                        f.write(chunk)
                return local_image_path
    except Exception as e:
        print(f"Error fetching cover image for {url}: {e}")

    # Fallback to default icon if no cover image found
    return "/System/Library/CoreServices/CoreTypes.bundle/Contents/Resources/BookmarkIcon.icns"

# Load bookmarks from the JSON file
def load_bookmarks():
    with open(BOOKMARKS_FILE, "r") as file:
        return json.load(file)["bookmarks"]

# Save updated bookmarks to the JSON file
def save_bookmarks(bookmarks):
    with open(BOOKMARKS_FILE, "w") as file:
        json.dump({"bookmarks": bookmarks}, file, indent=4)

# Update usage count for a bookmark
def update_usage_count(selected_url, bookmarks):
    for bookmark in bookmarks:
        if bookmark["url"] == selected_url:
            bookmark["usage_count"] += 1
            break
    save_bookmarks(bookmarks)

# Search bookmarks with fuzzy matching and tag-specific searches
def search_bookmarks(query, bookmarks):
    # If no query is provided, return all bookmarks
    if not query:
        return bookmarks

    # Split query into parts
    query_parts = query.strip().split()

    # Extract collections, OR tags, and AND tags
    collections = [part[1:].lower() for part in query_parts if part.startswith("@")]
    or_tags = [part[1:].lower() for part in query_parts if part.startswith("#") and not part.startswith("##")]
    and_tags = [part[2:].lower() for part in query_parts if part.startswith("##")]

    # Filter by collections (support partial matches)
    if collections:
        bookmarks = [
            bookmark for bookmark in bookmarks
            if any(bookmark["collection"].lower().startswith(collection) for collection in collections)
        ]

    # Apply AND logic (all specified tags must match)
    if and_tags:
        bookmarks = [
            bookmark for bookmark in bookmarks
            if all(
                any(tag.startswith(and_tag) for tag in bookmark["tags"])
                for and_tag in and_tags
            )
        ]

    # Apply OR logic (any specified tags must match)
    if or_tags:
        bookmarks = [
            bookmark for bookmark in bookmarks
            if any(
                any(tag.startswith(or_tag) for tag in bookmark["tags"])
                for or_tag in or_tags
            )
        ]

    # If no collections or tags specified, perform a fuzzy search
    if not collections and not and_tags and not or_tags:
        query = query.lower()
        results = []

        for bookmark in bookmarks:
            # Combine title, tags, and description into a searchable string
            searchable = f"{bookmark['title'].lower()} {' '.join(bookmark['tags']).lower()} {bookmark['description'].lower()}"

            # Fuzzy match score (partial and ratio combined)
            partial_score = fuzz.partial_ratio(query, searchable)
            ratio_score = fuzz.ratio(query, searchable)

            # Higher weight if query matches the start of the title
            if bookmark["title"].lower().startswith(query):
                partial_score += 20  # Boost starting matches

            # Add to results with total score
            total_score = (partial_score + ratio_score) / 2  # Average the scores
            results.append((bookmark, total_score))

        # Sort by score in descending order
        results = sorted(results, key=lambda x: x[1], reverse=True)

        # Return bookmarks that pass the fuzzy search threshold
        return [result[0] for result in results if result[1] > 50]

    return bookmarks






# Format results for Alfred
def format_for_alfred(results):
    alfred_results = {"items": []}
    for result in results:
        # Fetch cover image from cache or download if not available
        cover_image = result.get("cover_image") or get_cover_image(result["url"])
        # Format the subtitle
        collection = f"@{result['collection']}"  # Add collection with '@'
        tags = "".join(f"#{tag}" for tag in result["tags"])  # Concatenate tags with '#'
        description = result["description"]  # Add description
        subtitle = f"{collection} {tags}・{description}"  # Combine all parts

        # Append to Alfred results
        alfred_results["items"].append({
            "title": result["title"],
            "subtitle": subtitle,
            "arg": result["url"],
            "icon": {"path": cover_image}
            # "icon": {"path": "/System/Library/CoreServices/CoreTypes.bundle/Contents/Resources/BookmarkIcon.icns"}
        })
    return json.dumps(alfred_results)


# Main entry point
def main():
    # Combine input arguments into a single query string
    query = " ".join(sys.argv[1:]).strip()

    # Load all bookmarks
    bookmarks = load_bookmarks()

    # If a URL is provided as an argument, update its usage count
    parsed_url = urlparse(query)
    if parsed_url.scheme in ["http", "https"] and parsed_url.netloc:
        update_usage_count(query, bookmarks)
        return

    # Get search results
    results = search_bookmarks(query, bookmarks)

    # Sort by usage count before returning
    results = sorted(results, key=lambda b: b["usage_count"], reverse=True)

    # Format and output results for Alfred
    print(format_for_alfred(results))

if __name__ == "__main__":
    main()
