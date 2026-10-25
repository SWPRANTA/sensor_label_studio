"""Run tests; optionally verify real project recordings without writing any CSV."""
import os,sys,tempfile,io,json,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
task_tmp=ROOT/".runtime/test-temp"
task_tmp.mkdir(parents=True,exist_ok=True)
os.environ["TEMP"]=os.environ["TMP"]=str(task_tmp)
tempfile.tempdir=str(task_tmp)
sys.dont_write_bytecode=True

if __name__=="__main__":
    suite=unittest.defaultTestLoader.discover(str(ROOT/"tests"))
    log=io.StringIO()
    result=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
    print(log.getvalue())
    folder=ROOT/".runtime/reports";folder.mkdir(parents=True,exist_ok=True)
    (folder/"tests.txt").write_text(log.getvalue(),encoding="utf-8")
    (folder/"tests.json").write_text(json.dumps(dict(tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),passed=result.wasSuccessful()),indent=2),encoding="utf-8")
    raise SystemExit(0 if result.wasSuccessful() else 1)
