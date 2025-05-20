# c:\Projects\RIN\conftest.py
import sys
import os

# Calculate the absolute path to the project root directory (where this conftest.py is)
project_root = os.path.dirname(os.path.abspath(__file__))
# Calculate the absolute path to the 'src' directory
src_path = os.path.join(project_root, "src")

# Add the 'src' directory to the beginning of sys.path if it's not already there
if src_path not in sys.path:
    sys.path.insert(0, src_path)
    print(f"\n[conftest.py] Added to sys.path: {src_path}")
else:
    print(f"\n[conftest.py] '{src_path}' already in sys.path.")

# Optional: Print sys.path as seen by conftest.py for debugging
# print(f"[conftest.py] Current sys.path (after potential modification):")
# for p_idx, p_val in enumerate(sys.path):
#     print(f"  {p_idx}: {p_val}")
# print("-" * 30)