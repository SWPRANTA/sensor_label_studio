"""Every rendered sensor group and subplot must show the same label intervals."""
import json, sys, unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from csv_document import Recording, EditSession
from plotting_loader import load_plotting
p=load_plotting(Path(__file__).resolve().parents[1])


def shaded(figure):
    return [shape for shape in figure.layout.shapes
            if str(shape.name or "").startswith("road-label:")]


class AllPlotShadingTests(unittest.TestCase):
    def setUp(self):
        self.rec=Recording.load(p.synthetic_demo())
        self.clock=self.rec.clock("elapsed_time_ms")
        self.doc=EditSession(self.rec)
        self.ids=self.clock.rows(0,8)
        self.regions=p.label_intervals(self.clock.values,self.doc.labels,0,8,self.clock.exclusive_end)

    def test_every_raw_and_derived_sensor_group(self):
        arrays={name:self.rec.numbers(name) for name in self.rec.numeric_columns()}
        arrays.update(p.derived_signals(self.rec,self.clock))
        for title,names,unit in p.GROUPS:
            columns=[name for name in names if name in arrays]
            if not columns:
                continue
            with self.subTest(group=title):
                fig=p.sensor_figure(self.clock.values,self.ids,columns,arrays,unit,
                                    label_regions=self.regions)
                self.assertEqual([(s.x0,s.x1) for s in shaded(fig)],[(a,b) for a,b,_ in self.regions])
                self.assertEqual([s.fillcolor for s in shaded(fig)],[p.label_color(label) for _,_,label in self.regions])
                self.assertTrue(all(s.layer=="above" and s.yref=="paper" and s.editable is False
                                    for s in shaded(fig)))
                self.assertEqual(fig.layout.hovermode,"x unified")
                self.assertEqual(fig.layout.hoverdistance,-1)
                self.assertTrue(all("%{text}" in trace.hovertemplate for trace in fig.data))

    def test_label_and_motion_subplots_both_shaded(self):
        fig=p.label_figure(self.rec,self.doc.labels,self.clock,self.ids,label_regions=self.regions)
        for xref,yaxis in [("x","yaxis"),("x2","yaxis2")]:
            with self.subTest(axis=xref):
                spans=[s for s in shaded(fig) if s.xref==xref]
                self.assertEqual(len(spans),len(self.regions))
                domain=fig.layout[yaxis].domain
                self.assertTrue(all(s.yref=="paper" and s.y0==domain[0] and s.y1==domain[1]
                                    and s.layer=="above" for s in spans))

    def test_common_render_step_does_not_double_shade(self):
        arrays={"acc_x":self.rec.numbers("acc_x")}
        fig=p.sensor_figure(self.clock.values,self.ids,["acc_x"],arrays,"m/s²",
                            edit_span=(1,3),label_regions=self.regions)
        p.add_label_shading(fig,self.regions)
        self.assertEqual(len(shaded(fig)),len(self.regions))
        self.assertEqual(len(fig.layout.shapes)-len(shaded(fig)),2)

    def test_changed_labels_update_each_group(self):
        self.doc.apply(self.clock,3,4,"Utility Cut")
        regions=p.label_intervals(self.clock.values,self.doc.labels,0,8,self.clock.exclusive_end)
        arrays={name:self.rec.numbers(name) for name in ["acc_x","gyro_x","speed","orient_roll","rot_x"]}
        for name in arrays:
            fig=p.sensor_figure(self.clock.values,self.ids,[name],arrays,"source units",label_regions=regions)
            self.assertTrue(any(s.fillcolor==p.LABEL_COLORS["Utility Cut"] and s.x0==3 and s.x1==4 for s in shaded(fig)))
        fig=p.overview(self.rec,self.clock,0,8,labels=self.doc.labels)
        self.assertTrue(any(s.fillcolor==p.LABEL_COLORS["Utility Cut"] for s in shaded(fig)))

    def test_hover_preserves_original_csv_numeric_spellings(self):
        raw=self.rec.raw.replace(b"21.00",b"21.000000000000000123")
        rec=Recording.load(raw)
        clock=rec.clock("elapsed_time_ms")
        ids=clock.rows(0,8)
        fig=p.sensor_figure(clock.values,ids,["mag_x"],{"mag_x":rec.numbers("mag_x")},"uT",
                            raw_values={"mag_x":rec.frame.mag_x.to_numpy()},label_regions=self.regions)
        self.assertTrue(all(value=="21.000000000000000123" for value in fig.data[0].text))
        self.assertIn("%{text}",fig.data[0].hovertemplate)

    def test_overview_and_custom_channel_have_hover_and_colors(self):
        fig=p.overview(self.rec,self.clock,0,8)
        self.assertTrue(shaded(fig))
        self.assertTrue(all(s.layer=="above" and s.yref=="paper" for s in shaded(fig)))
        self.assertIn("%{text}",fig.data[0].hovertemplate)
        self.assertEqual(len(fig.layout.shapes)-len(shaded(fig)),2)
        custom=p.sensor_figure(self.clock.values,self.ids,["custom_sensor"],
                               {"custom_sensor":np.arange(len(self.rec.frame),dtype=float)},
                               "source units",label_regions=self.regions)
        self.assertEqual(len(shaded(custom)),len(self.regions))
        self.assertIn("%{text}",custom.data[0].hovertemplate)

    def test_decoration_is_mouse_transparent(self):
        css=(Path(__file__).resolve().parents[1]/"assets/studio.css").read_text()
        self.assertIn('[data-testid="stPlotlyChart"] .shapelayer path',css)
        self.assertIn("pointer-events:none!important",css)

    def test_streamlit_payloads_keep_colors_hover_and_editor_data(self):
        import runpy
        from unittest.mock import patch
        root=Path(__file__).resolve().parents[1]
        # Exercise the real Streamlit serialization path without starting a
        # browser or AppTest's ScriptRunner/component-discovery background work.
        namespace=runpy.run_path(str(root/"app.py"))
        render=namespace["render_labeled_plot"]
        arrays={name:self.rec.numbers(name) for name in self.rec.numeric_columns()}
        arrays.update(p.derived_signals(self.rec,self.clock))
        raw={name:self.rec.frame[name].to_numpy() for name in self.rec.numeric_columns()}
        figures=[p.overview(self.rec,self.clock,0,8),
                 p.label_figure(self.rec,self.doc.labels,self.clock,self.ids,self.regions)]
        for _,names,unit in p.GROUPS:
            columns=[name for name in names if name in arrays]
            if columns:
                figures.append(p.sensor_figure(self.clock.values,self.ids,columns,arrays,unit,
                                               label_regions=self.regions,raw_values=raw))
        for index,figure in enumerate(figures):
            with patch("streamlit.delta_generator.DeltaGenerator._enqueue") as enqueue:
                render(figure,self.regions,theme=None,key=f"payload_test_{index}")
            proto=enqueue.call_args.args[1]
            spec=json.loads(proto.spec)
            config=json.loads(proto.config)
            bands=[s for s in spec["layout"]["shapes"] if s.get("name","").startswith("road-label:")]
            self.assertTrue(bands)
            self.assertTrue(any(s["fillcolor"]==p.LABEL_COLORS["Pothole"] for s in bands))
            self.assertTrue(all(s["layer"]=="above" and s["yref"]=="paper" for s in bands))
            self.assertEqual(spec["layout"]["hovermode"],"x unified")
            self.assertTrue(all(trace.get("hovertemplate") for trace in spec["data"]))
            self.assertIs(config["staticPlot"],False)
            self.assertIs(config["editable"],False)
        self.doc.apply(self.clock,4.1,4.5,"Utility Cut")
        original_labels=self.doc.labels
        regions=p.label_intervals(self.clock.values,self.doc.labels,0,8,self.clock.exclusive_end)
        figure=p.label_figure(self.rec,self.doc.labels,self.clock,self.ids,regions)
        with patch("streamlit.delta_generator.DeltaGenerator._enqueue"):
            render(figure,regions,theme=None,key="edited_payload")
        self.assertIs(self.doc.labels,original_labels)
        self.assertEqual(len(self.doc.changed),40)
        self.assertTrue(self.doc.export()[1]["nonlabel_bytes_identical"])


if __name__=="__main__":
    unittest.main()
