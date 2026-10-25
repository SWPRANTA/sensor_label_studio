import sys, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from streamlit.testing.v1 import AppTest
from csv_document import Recording
from plotting import synthetic_demo

ROOT=Path(__file__).resolve().parents[1]


class AppWorkflowTests(unittest.TestCase):
    def start(self):
        app=AppTest.from_file(str(ROOT/"app.py"),default_timeout=90).run()
        self.assertFalse(list(app.exception))
        app.button(key="load_demo").click().run()
        self.assertFalse(list(app.exception))
        return app

    def document(self,app):
        return app.session_state["documents"][app.session_state["document_choice"]]

    def test_empty_and_loaded_views(self):
        app=self.start()
        self.assertEqual(len(self.document(app).recording.frame),3201)
        self.assertGreater(len(app.get("plotly_chart")),10)

    def test_edit_undo_redo_and_verified_export(self):
        app=self.start()
        app.text_input(key="edit_start").set_value("4.1")
        app.text_input(key="edit_end").set_value("4.5")
        app.selectbox(key="label_choice").select("Utility Cut")
        app.button(key="FormSubmitter:apply_label_form-Apply label").click().run()
        self.assertFalse(list(app.exception))
        doc=self.document(app)
        self.assertEqual(len(doc.changed),40)
        app.button(key="prepare_export").click().run()
        self.assertTrue(doc.prepared[1]["nonlabel_bytes_identical"])
        app.button(key="undo").click().run()
        self.assertEqual(len(doc.changed),0)
        app.button(key="redo").click().run()
        self.assertEqual(len(doc.changed),40)
        self.assertIsNone(doc.prepared)

    def test_next_previous_and_duration(self):
        app=self.start()
        app.button(key="next").click().run()
        self.assertEqual(float(app.text_input(key="plot_start").value),8)
        self.assertEqual(float(app.text_input(key="edit_start").value),8)
        app.button(key="previous").click().run()
        self.assertEqual(float(app.text_input(key="plot_start").value),0)
        app.text_input(key="plot_duration").set_value("2.5").run()
        self.assertEqual(float(app.text_input(key="edit_end").value),2.5)
        self.assertFalse(list(app.exception))

    def test_full_file_requires_bulk_confirmation(self):
        app=self.start()
        app.checkbox(key="full_file").check().run()
        self.assertTrue(app.button(key="FormSubmitter:apply_label_form-Apply label").disabled)
        app.checkbox(key="allow_bulk").check().run()
        app.selectbox(key="label_choice").select("Raveling")
        app.button(key="FormSubmitter:apply_label_form-Apply label").click().run()
        self.assertFalse(list(app.exception))
        self.assertEqual(len(self.document(app).changed),3201)

    def test_bad_duration_never_edits(self):
        app=self.start()
        app.text_input(key="plot_duration").set_value("NaN").run()
        self.assertTrue(list(app.error));self.assertFalse(list(app.exception))
        self.assertEqual(len(self.document(app).changed),0)

    def test_clock_switch_resets_window(self):
        app=self.start()
        app.selectbox(key="time_column").select("timestamp").run()
        self.assertFalse(list(app.exception))
        self.assertTrue(app.checkbox(key="relative_clock").value)
        self.assertEqual(float(app.text_input(key="plot_start").value),0)

    def test_uploaded_bytes_path(self):
        class Upload:
            name="uploaded sensors.csv"
            def getvalue(self):return synthetic_demo()
        def uploader(*args,**kwargs):return Upload()
        with patch("streamlit.file_uploader",uploader):
            app=AppTest.from_file(str(ROOT/"app.py"),default_timeout=90).run()
            self.assertFalse(list(app.exception))
            self.assertEqual(self.document(app).recording.filename,"uploaded sensors.csv")


if __name__=="__main__":unittest.main()
