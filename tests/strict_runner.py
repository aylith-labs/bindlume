"""Make uncaught GTK callback/background exceptions fail the test process."""
import sys
import threading
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
errors=[]
original=sys.excepthook

def uncaught(kind,value,traceback):
    errors.append(value)
    original(kind,value,traceback)

sys.excepthook=uncaught
threading.excepthook=lambda args: uncaught(args.exc_type,args.exc_value,args.exc_traceback)
result=unittest.main(module=None,exit=False).result
if errors: print(f'FAILED: {len(errors)} uncaught callback/background exception(s)',file=sys.stderr)
sys.exit(0 if result.wasSuccessful() and not errors else 1)
