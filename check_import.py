# c:\Projects\RIN\check_import.py
print("Attempting to import 'rin'...")
try:
    import rin
    print("Successfully imported 'rin' package.")
    print(f"rin package found at: {rin.__file__}") # See where it's loading from

    # Let's also try to access something from the __init__.py's __all__ list
    # to see if the submodules loaded correctly into the rin namespace
    print(f"Attempting to access rin.RinConfig...")
    from rin import RinConfig
    print(f"Successfully accessed rin.RinConfig: {RinConfig}")

except Exception as e:
    print(f"Failed to import 'rin' or access its members. Error: {e}")
    import traceback
    traceback.print_exc()

print("Script finished.")
