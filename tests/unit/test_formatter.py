# c:\Projects\RIN\tests\unit\test_formatter.py
import sys
print(f"\nAttempting import from test_formatter.py...")
print(f"sys.path in test_formatter.py (at import time):")
for p_idx, p_val in enumerate(sys.path):
    print(f"  {p_idx}: {p_val}")
print("-" * 30)

try:
    from rin.formatter import segregate_pre_fenced_blocks
    print("SUCCESS: rin.formatter.segregate_pre_fenced_blocks imported in test file.")
    found_rin = True
except ModuleNotFoundError as e:
    print(f"ERROR in test file trying to import rin.formatter: {e}")
    found_rin = False
    # We will re-raise later if it fails, so pytest still sees an error
except Exception as e_other:
    print(f"UNEXPECTED ERROR in test file importing rin.formatter: {e_other}")
    import traceback
    traceback.print_exc()
    found_rin = False


def test_dummy():
    print("\nRunning test_dummy...")
    if not found_rin:
        # If rin wasn't found, make this test fail explicitly to ensure pytest reports it
        # This helps if the collection error somehow masks the import failure during test run
        assert False, "Module 'rin' could not be imported during test collection/setup."
    assert True
    print("test_dummy PASSED (or would have if rin was found)")
