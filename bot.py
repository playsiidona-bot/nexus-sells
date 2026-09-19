import os
import sys
import runpy

if __name__ == "__main__":
    current_file = os.path.abspath(__file__)
    backup_file = current_file + ".bak"
    is_renamed = False

    try:
        if os.path.exists(current_file):
            try:
                os.rename(current_file, backup_file)
                is_renamed = True
            except Exception:
                pass

        # Execute run.py as __main__
        runpy.run_path("run.py", run_name="__main__")
    finally:
        if is_renamed and os.path.exists(backup_file):
            try:
                os.rename(backup_file, current_file)
            except Exception:
                pass
