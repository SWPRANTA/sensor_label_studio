"""Read all 21 source hashes and test one whole original CSV per phone in memory."""
from pathlib import Path
import gc,json,time
from csv_document import Recording,EditSession,sha
ROOT=Path(__file__).resolve().parent

if __name__=="__main__":
    project=ROOT.parent
    audit=json.loads((project/"outputs/reports/raw_audit.json").read_text(encoding="utf-8"))
    selected={}
    for meta in audit["recordings"]:
        path=project/"Road_Anomalies_Detection_Raw_Datasets"/meta["relative_path"]
        assert sha(path.read_bytes())==meta["sha256"],"Source changed: "+meta["recording_id"]
        selected.setdefault(meta["device"],meta)
    rows=[]
    for device,meta in selected.items():
        path=project/"Road_Anomalies_Detection_Raw_Datasets"/meta["relative_path"]
        start=time.perf_counter()
        rec=Recording.load(path.read_bytes(),path.name)
        c=rec.clock("elapsed_time_ms")
        doc=EditSession(rec)
        doc.apply(c,c.minimum,min(c.minimum+8,c.exclusive_end),"review_test")
        data,report=doc.export()
        assert sha(path.read_bytes())==meta["sha256"]
        assert report["nonlabel_bytes_identical"] and report["unrelated_fields_equal"]
        rows.append(dict(device=device,file=path.name,rows=len(rec.frame),numeric_features=len(rec.numeric_columns()),
                         changed_rows=report["changed_label_rows"],source_sha256=rec.source_sha256,
                         nonlabel_bytes_identical=True,seconds=round(time.perf_counter()-start,2)))
        print(rows[-1],flush=True)
        del rec,doc,data;gc.collect()
    folder=ROOT/".runtime/reports";folder.mkdir(parents=True,exist_ok=True)
    (folder/"real_recordings.json").write_text(json.dumps(dict(source_hashes_unchanged=len(audit["recordings"]),recordings=rows),indent=2),encoding="utf-8")
