#!/usr/bin/env python3
"""
Test path conversion function
"""

def convert_path_for_wsl(windows_path):
    """Convert Windows path to WSL-accessible path"""
    # Normalize path separators to forward slashes
    normalized_path = windows_path.replace('\\', '/')
    
    # Convert E:/path to /mnt/e/path
    if normalized_path.startswith('E:/'):
        wsl_path = normalized_path.replace('E:/', '/mnt/e/')
        return wsl_path
    # Convert C:/path to /mnt/c/path  
    elif normalized_path.startswith('C:/'):
        wsl_path = normalized_path.replace('C:/', '/mnt/c/')
        return wsl_path
    # For other drives, follow same pattern
    elif ':' in normalized_path:
        drive_letter = normalized_path[0].lower()
        path_part = normalized_path[2:]
        return f'/mnt/{drive_letter}{path_part}'
    return windows_path

# Test with the actual database paths
test_paths = [
    "E:/01_INCOMING\\Jane\\20220112_043621.jpg",
    "E:/01_INCOMING\\Jane\\20220112_043706.jpg",
    "C:\\Users\\yanbo\\test.jpg"
]

for path in test_paths:
    converted = convert_path_for_wsl(path)
    print(f"Windows: {path}")
    print(f"WSL:     {converted}")
    print()
