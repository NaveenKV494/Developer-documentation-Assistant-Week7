import os
import requests

# Official Microsoft MAUI documentation raw URLs
doc_urls = [
    "https://raw.githubusercontent.com/dotnet/docs-maui/main/docs/what-is.md",
    "https://raw.githubusercontent.com/dotnet/docs-maui/main/docs/fundamentals/app-lifecycle.md",
    "https://raw.githubusercontent.com/dotnet/docs-maui/main/docs/fundamentals/dependency-injection.md",
    "https://raw.githubusercontent.com/dotnet/docs-maui/main/docs/xaml/fundamentals/get-started.md",
    "https://raw.githubusercontent.com/dotnet/docs-maui/main/docs/user-interface/layouts/grid.md",
    "https://raw.githubusercontent.com/dotnet/docs-maui/main/docs/macios/deployment/overview.md"
]

# Clean out the old fake documents
folder = "documents"
for file in os.listdir(folder):
    os.remove(os.path.join(folder, file))
print("Cleared old documents.")

# Download the new ones
for url in doc_urls:
    # Generate a readable filename from the URL
    filename = url.split("/")[-1]
    if filename in ["index.md", "overview.md", "get-started.md"]:
        filename = f"{url.split('/')[-2]}-{filename}"
        
    print(f"Downloading: {filename}...")
    response = requests.get(url)
    
    if response.status_code == 200:
        with open(os.path.join(folder, filename), "w", encoding="utf-8") as f:
            f.write(response.text)
    else:
        print(f"Failed to fetch {url}")

print("\nSuccess! Real Microsoft documentation is ready.")