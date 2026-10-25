import csv, io, json, sys, unittest
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from csv_document import Recording, EditSession, CsvError, label_spans, encoded_label
from plotting import synthetic_demo, preview_indices, derived_signals


def recording(raw=None, **kwargs):
    return Recording.load(raw if raw is not None else b"elapsed_time_ms,x,label,other\r\n0,1.000,normal,NaN\r\n10,-0.00,normal,001\r\n20,1e-9,Pothole,\r\n30,,normal,42\r\n", **kwargs)


class CsvPreservationTests(unittest.TestCase):
    def test_no_changes_byte_identical(self):
        r=recording();self.assertEqual(EditSession(r).export()[0],r.raw)
    def test_single_label_only(self):
        r=recording();s=EditSession(r);s.apply(r.clock("elapsed_time_ms"),.01,.02,"Utility Cut")
        data,report=s.export();self.assertEqual(data,r.raw.replace(b"10,-0.00,normal",b"10,-0.00,Utility Cut"))
        self.assertTrue(report["nonlabel_bytes_identical"])
    def test_original_frame_not_mutated(self):
        r=recording();copy=r.frame.copy(deep=True);s=EditSession(r);s.apply(r.clock("elapsed_time_ms"),0,.03,"Raveling")
        pd.testing.assert_frame_equal(r.frame,copy,check_exact=True)
    def test_bom_blank_lines_and_lf_preserved(self):
        raw=b'\xef\xbb\xbfelapsed_time_ms,label,x\n\n0,"normal",001\n10,normal,1.000\n\n'
        r=recording(raw);s=EditSession(r);s.apply(r.clock("elapsed_time_ms"),0,.01,"Pothole")
        self.assertEqual(s.export()[0],raw.replace(b'0,"normal",',b'0,Pothole,'))
    def test_quoted_comma_and_embedded_newline_elsewhere(self):
        raw=b'elapsed_time_ms,other,label\r\n0,"a,b\r\nc",normal\r\n10,"a ""quote""",normal'
        r=recording(raw);s=EditSession(r);s.apply(r.clock("elapsed_time_ms"),0,.02,'custom, "review"')
        data,_=s.export();self.assertIn(b'"a,b\r\nc"',data);self.assertIn(b'"a ""quote"""',data)
    def test_no_final_newline(self):
        r=recording(b"elapsed_time_ms,label\n0,normal");s=EditSession(r);s.apply(r.clock("elapsed_time_ms"),0,1,"Pothole")
        self.assertEqual(s.export()[0],b"elapsed_time_ms,label\n0,Pothole")
    def test_cr_line_endings(self):
        r=recording(b"elapsed_time_ms,label\r0,normal\r10,normal\r");s=EditSession(r)
        s.apply(r.clock("elapsed_time_ms"),0,.01,"Pothole");self.assertEqual(s.export()[0].count(b"\r"),3)
    def test_semicolon(self):
        r=recording(b"elapsed_time_ms;label;x\n0;normal;1.000\n",delimiter=";");s=EditSession(r)
        s.apply(r.clock("elapsed_time_ms"),0,1,"rough; reviewed");self.assertIn(b'"rough; reviewed"',s.export()[0])
    def test_tab(self):
        r=recording(b"elapsed_time_ms\tlabel\tx\n0\tnormal\t1.000\n",delimiter="\t")
        self.assertEqual(EditSession(r).export()[0],r.raw)
    def test_unicode_labels(self):
        r=recording();s=EditSession(r);s.apply(r.clock("elapsed_time_ms"),0,.01,"পর্যালোচিত")
        self.assertIn("পর্যালোচিত".encode(),s.export()[0])
    def test_legacy_encoding(self):
        r=recording('elapsed_time_ms,label,note\r\n0,normal,café\r\n'.encode("cp1252"),encoding="cp1252")
        s=EditSession(r);s.apply(r.clock("elapsed_time_ms"),0,1,"révisé");self.assertIn(b"caf\xe9",s.export()[0])
    def test_legacy_encoding_rejects_unrepresentable_label(self):
        r=recording(b"elapsed_time_ms,label\n0,normal\n",encoding="cp1252");s=EditSession(r)
        with self.assertRaises(CsvError):s.apply(r.clock("elapsed_time_ms"),0,1,"বাংলা")
    def test_duplicate_or_empty_columns_rejected(self):
        for raw in [b"elapsed_time_ms,label,label\n0,a,b",b"elapsed_time_ms,label,\n0,a,b"]:
            with self.assertRaises(CsvError):recording(raw)
    def test_malformed_or_ragged_rejected(self):
        for raw in [b'elapsed_time_ms,label\n0,"normal',b"elapsed_time_ms,label\n0,a,b",b"elapsed_time_ms,label\n0"]:
            with self.assertRaises(CsvError):recording(raw)
    def test_no_label_column_rejected(self):
        with self.assertRaises(CsvError):recording(b"time,x\n0,1")
    def test_utf16_rejected(self):
        with self.assertRaises(CsvError):recording("elapsed_time_ms,label\n0,normal".encode("utf-16"))
    def test_blank_and_formula_labels_rejected(self):
        for text in [""," ","a\nb","a\x00b","=1+1"," +SUM(A1)"]:
            with self.assertRaises(CsvError):encoded_label(text,"utf-8",",")
    def test_empty_file_rejected(self):
        with self.assertRaises(CsvError):recording(b"")


class ClockAndHistoryTests(unittest.TestCase):
    def test_half_open_interval(self):
        r=recording();np.testing.assert_array_equal(r.clock("elapsed_time_ms").rows(.01,.02),[1])
    def test_inclusive_end_explicit(self):
        r=recording();np.testing.assert_array_equal(r.clock("elapsed_time_ms").rows(.01,.02,True),[1,2])
    def test_duplicate_timestamps_keep_all_rows(self):
        r=recording(b"elapsed_time_ms,label\n0,a\n0,b\n10,c")
        np.testing.assert_array_equal(r.clock("elapsed_time_ms").rows(0,.01),[0,1])
    def test_bad_time_rows_preserved(self):
        r=recording(b"elapsed_time_ms,label\n0,normal\n,normal\n10,normal")
        c=r.clock("elapsed_time_ms");self.assertEqual(c.missing,1);s=EditSession(r)
        s.apply(c,0,.02,"Pothole");self.assertIn(b"\n,normal\n",s.export()[0])
    def test_no_backwards_sort_or_drop(self):
        r=recording(b"elapsed_time_ms,label\n10,a\n0,b")
        with self.assertRaises(CsvError):r.clock("elapsed_time_ms")
    def test_large_epoch_subtract_before_float(self):
        r=recording(b"timestamp,label\n9007199254740993000,normal\n9007199254740993001,normal")
        c=r.clock("timestamp","nanoseconds",True);self.assertEqual(c.values[1],1e-9)
    def test_elapsed_clock_matches_notebook_without_rezero(self):
        r=recording(b"elapsed_time_ms,label\n107,normal\n117,normal")
        self.assertEqual(r.clock("elapsed_time_ms").minimum,.107)
    def test_undo_redo_and_original_token_restoration(self):
        r=recording(b'elapsed_time_ms,label\n0,"normal"\n10,normal\n')
        s=EditSession(r);s.apply(r.clock("elapsed_time_ms"),0,.01,"Pothole")
        changed=s.export()[0];s.undo();self.assertEqual(s.export()[0],r.raw);s.redo();self.assertEqual(s.export()[0],changed)
    def test_redo_cleared_after_new_edit(self):
        r=recording();s=EditSession(r);c=r.clock("elapsed_time_ms");s.apply(c,0,.01,"Pothole");s.undo()
        s.apply(c,0,.01,"Raveling");self.assertFalse(s.redo_stack)
    def test_overlapping_edits_undo_correctly(self):
        r=recording();s=EditSession(r);c=r.clock("elapsed_time_ms");s.apply(c,0,.03,"Raveling")
        first=s.labels.copy();s.apply(c,.01,.04,"Utility Cut");s.undo();np.testing.assert_array_equal(s.labels,first)
    def test_empty_or_inverted_range_rejected(self):
        r=recording();s=EditSession(r);c=r.clock("elapsed_time_ms")
        for a,b in [(1,2),(0,0),(.1,0),(float("nan"),1)]:
            with self.assertRaises(CsvError):s.apply(c,a,b,"normal")
    def test_reset_byte_identical(self):
        r=recording();s=EditSession(r);s.apply(r.clock("elapsed_time_ms"),0,.03,"Raveling");s.reset()
        self.assertEqual(s.export()[0],r.raw)
    def test_prepared_download_invalidated(self):
        r=recording();s=EditSession(r);s.export();s.apply(r.clock("elapsed_time_ms"),0,.01,"Pothole")
        self.assertIsNone(s.prepared)
    def test_numeric_view_not_exported(self):
        r=recording();r.numbers("x")[:]=999
        self.assertEqual(EditSession(r).export()[0],r.raw)
    def test_immutable_numeric_view_is_safe(self):
        self.assertTrue(np.isfinite(recording().numbers("elapsed_time_ms")).all())


class PreviewTests(unittest.TestCase):
    def test_preview_keeps_impulse(self):
        y=np.zeros(100000);y[55555]=100;y[70001]=-100
        ii=preview_indices(y,1000);self.assertIn(55555,ii);self.assertIn(70001,ii);self.assertLessEqual(len(ii),1000)
    def test_preview_does_not_influence_edit_selection(self):
        r=Recording.load(synthetic_demo());c=r.clock("elapsed_time_ms");s=EditSession(r)
        self.assertEqual(s.apply(c,0,8,"Raveling"),800)
    def test_missing_values_stay_missing_in_preview(self):
        y=np.zeros(10000);y[4000:4500]=np.nan;ii=preview_indices(y,500)
        self.assertTrue(np.isnan(y[ii]).any())
    def test_derived_traces_not_source_columns(self):
        r=Recording.load(synthetic_demo());before=r.frame.copy();a=derived_signals(r,r.clock("elapsed_time_ms"))
        self.assertIn("derived_vertical_linear",a);pd.testing.assert_frame_equal(r.frame,before)
    def test_jerk_does_not_use_future_samples(self):
        r=Recording.load(synthetic_demo());c=r.clock("elapsed_time_ms");a=derived_signals(r,c)
        r.numeric["acc_z"][101:]+=100
        b=derived_signals(r,c);np.testing.assert_array_equal(a["derived_jerk_norm"][:101],b["derived_jerk_norm"][:101])


if __name__=="__main__":unittest.main()
