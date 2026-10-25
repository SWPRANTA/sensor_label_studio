"""Run: python -m streamlit run app.py (or double-click run_app.cmd)."""
from decimal import Decimal, InvalidOperation
from pathlib import Path
import base64, hashlib, html, json, sys
sys.dont_write_bytecode = True
import numpy as np
import pandas as pd
import streamlit as st
from csv_document import Recording, EditSession, CsvError
from plotting_loader import load_plotting

ROOT = Path(__file__).resolve().parent
_plotting = load_plotting(ROOT)
GROUPS, MOTION = _plotting.GROUPS, _plotting.MOTION
derived_signals, overview = _plotting.derived_signals, _plotting.overview
label_figure, sensor_figure = _plotting.label_figure, _plotting.sensor_figure
synthetic_demo = _plotting.synthetic_demo
LABEL_COLORS = _plotting.LABEL_COLORS
label_color, label_intervals = _plotting.label_color, _plotting.label_intervals
CANONICAL = ["normal","Pothole","Speed Breaker","Utility Cut","Uneven Manhole","Raveling","uncertain"]
st.set_page_config(page_title="Road Sensor Studio",layout="wide",initial_sidebar_state="auto")


def appearance():
    font = ROOT/"assets/Geist.woff2"
    face = ""
    if font.exists():
        raw = font.read_bytes()
        fmt = "woff2" if raw[:4] == b"wOF2" else ("woff" if raw[:4] == b"wOFF" else "truetype")
        face = "@font-face{font-family:Geist;src:url(data:font/"+fmt+";base64,"+base64.b64encode(raw).decode()+") format('"+fmt+"');font-weight:100 900;font-display:swap;}"
    st.markdown("<style>"+face+(ROOT/"assets/studio.css").read_text(encoding="utf-8")+"</style>",unsafe_allow_html=True)


def add_document(data, name, encoding="utf-8", delimiter=","):
    identity = hashlib.sha256(data+encoding.encode()+delimiter.encode()).hexdigest()
    documents = st.session_state.documents
    if identity not in documents:
        documents[identity] = EditSession(Recording.load(data,name,encoding,delimiter))
    st.session_state.document_choice = identity
    return identity


def decimal_number(text, name):
    try:
        value = Decimal(str(text))
        if not value.is_finite():
            raise InvalidOperation
        return value
    except (InvalidOperation,ValueError):
        raise CsvError(name+" must be a finite number")


def move_window(direction, minimum, last):
    try:
        start = decimal_number(st.session_state.plot_start,"Plot start")
        duration = decimal_number(st.session_state.plot_duration,"Window length")
        if duration <= 0:
            return
        st.session_state.plot_start = str(max(Decimal(str(minimum)),
                                              min(start+direction*duration,Decimal(str(last)))))
    except CsvError:
        pass


def clock_changed():
    for key in ["time_unit","relative_clock","clock_configuration"]:
        st.session_state.pop(key,None)


def render_labeled_plot(figure, regions, *, target=None, **options):
    """Every plot passes this final shading step, including custom columns."""
    _plotting.add_label_shading(figure, regions)
    config = dict(options.pop("config", {}))
    config.update(staticPlot=False, editable=False)
    options["config"] = config
    return (st if target is None else target).plotly_chart(figure, **options)


def main():
    appearance()
    if "documents" not in st.session_state:
        st.session_state.documents = {}
    if st.query_params.get("demo") == "1" and not st.session_state.documents:
        add_document(synthetic_demo(),"Synthetic demo.csv")
    with st.sidebar:
        st.markdown('<div class="studio-mark"><svg width="25" height="28" viewBox="0 0 25 28" aria-hidden="true"><path d="M5 27L9 1M20 27L16 1" fill="none" stroke="#1d5fbf" stroke-width="2"/><path d="M12.5 3V8M12.5 12V17M12.5 21V26" stroke="#1d5fbf" stroke-width="2"/></svg>Road Sensor Studio</div>',unsafe_allow_html=True)
        st.caption("Local CSV annotation workspace")
        with st.expander("CSV import settings"):
            encoding = st.selectbox("Character encoding",["utf-8","cp1252","latin-1"],key="encoding")
            delimiter_name = st.selectbox("Delimiter",["Comma","Semicolon","Tab"],key="delimiter")
        delimiter = {"Comma":",","Semicolon":";","Tab":"\t"}[delimiter_name]
        uploaded = st.file_uploader("Upload sensor CSV",type=["csv"],key="csv_upload",
                                   help="A copy stays in this browser session. Source files are never overwritten.")
        if uploaded is not None:
            payload = uploaded.getvalue()
            signature = hashlib.sha256(payload+encoding.encode()+delimiter.encode()).hexdigest()
            if signature != st.session_state.get("last_upload"):
                try:
                    if len(payload) > 128*1024*1024:
                        raise CsvError("The local upload limit is 128 MB")
                    add_document(payload,uploaded.name,encoding,delimiter)
                    st.session_state.last_upload = signature
                except CsvError as error:
                    st.error(str(error))
        if st.button("Try synthetic demo",key="load_demo",width="stretch"):
            add_document(synthetic_demo(),"Synthetic demo.csv")
        docs = st.session_state.documents
        if not docs:
            st.caption("Nothing is uploaded to a cloud service. Keep this app bound to 127.0.0.1.")
    if not st.session_state.documents:
        st.title("Road Sensor Studio")
        st.subheader("Inspect a recording")
        st.write("Upload a CSV in the sidebar, or try the clearly marked synthetic demo.")
        st.markdown("Choose a time window, inspect the sensor channels, then edit only its label cells. Export a verified CSV when you are ready.")
        st.info("Your CSV needs a header, a numeric timestamp column and a label column. Every sensor column is retained.")
        return
    with st.sidebar:
        st.selectbox("Open recording",list(docs),format_func=lambda key:docs[key].recording.filename,key="document_choice")
    identity = st.session_state.document_choice
    doc = docs[identity]
    rec = doc.recording
    if st.session_state.get("active_document") != identity:
        for key in ["time_column","time_unit","relative_clock","plot_start","plot_duration","edit_start","edit_end","scope_signature","full_file","label_choice","custom_label","include_end","allow_bulk"]:
            st.session_state.pop(key,None)
        st.session_state.active_document = identity
    with st.sidebar:
        st.caption(f"{len(rec.frame):,} samples · {len(rec.frame.columns)} columns")
        clock_names = [c for c in ["elapsed_time_ms","timestamp"] if c in rec.frame]
        clock_names += [c for c in rec.frame if c not in clock_names and c != rec.label_column]
        time_column = st.selectbox("Time column",clock_names,key="time_column",on_change=clock_changed)
        default_unit = "milliseconds" if time_column in {"elapsed_time_ms","timestamp"} or time_column.endswith("_ms") else "seconds"
        units = ["milliseconds","seconds","microseconds","nanoseconds"]
        time_unit = st.selectbox("Timestamp unit",units,index=units.index(default_unit),key="time_unit")
        relative = st.checkbox("Subtract first valid timestamp",value=time_column != "elapsed_time_ms",key="relative_clock")
        st.caption("elapsed_time_ms is divided by 1,000 by default, matching the earlier notebook plots. Epoch clocks should be offset.")
        show_derived = st.checkbox("Show derived IMU traces",value=True,key="derived")
        budget = st.selectbox("Preview points per feature",[1000,2000,5000,10000],index=1,key="point_budget")
        st.caption("Long plots keep local minima, maxima and missing-value markers. Label edits always use every original sample.")
    st.title("Road Sensor Studio")
    st.caption(rec.filename+(" · synthetic controls demo" if rec.filename == "Synthetic demo.csv" else ""))
    try:
        clock = rec.clock(time_column,time_unit,relative)
    except (CsvError,KeyError) as error:
        st.error(str(error))
        return
    if clock.missing:
        st.warning(f"{clock.missing:,} rows have no valid time. They remain in the CSV but cannot be selected by a time interval.")
    clock_configuration = identity,time_column,time_unit,relative
    if st.session_state.get("clock_configuration") != clock_configuration:
        st.session_state.plot_start = str(clock.minimum)
        st.session_state.clock_configuration = clock_configuration
    st.session_state.setdefault("plot_start",str(clock.minimum))
    st.session_state.setdefault("plot_duration","8")
    a,b,c = st.columns([1,1,1.2])
    with a:
        st.text_input("Plot start (seconds)",key="plot_start")
    with b:
        st.text_input("Window length (seconds)",key="plot_duration")
    with c:
        st.checkbox("Plot entire recording",key="full_file")
    try:
        start = decimal_number(st.session_state.plot_start,"Plot start")
        length = decimal_number(st.session_state.plot_duration,"Window length")
        if length <= 0:
            raise CsvError("Window length must be greater than zero")
        end = start+length
        if st.session_state.full_file:
            start,end = Decimal(str(clock.minimum)),Decimal(str(clock.exclusive_end))
        start,end = max(float(start),clock.minimum),min(float(end),clock.exclusive_end)
        ids = clock.rows(start,end)
        if not len(ids):
            raise CsvError("No samples in this plot window. Choose a start time within the recording.")
    except CsvError as error:
        st.error(str(error))
        return
    a,b,c = st.columns([1,1,2])
    with a:
        st.button("Previous window",on_click=move_window,args=(-1,clock.minimum,clock.last),disabled=st.session_state.full_file,key="previous",width="stretch")
    with b:
        st.button("Next window",on_click=move_window,args=(1,clock.minimum,clock.last),disabled=st.session_state.full_file,key="next",width="stretch")
    with c:
        st.caption(f"Plot: {start:.4f}–{end:.4f} s · {len(ids):,} samples. Last timestamp: {clock.last:.4f} s.")
    overview_slot = st.empty()
    scope = identity,time_column,time_unit,relative,start,end
    if st.session_state.get("scope_signature") != scope:
        st.session_state.edit_start = str(start)
        st.session_state.edit_end = str(end)
        st.session_state.allow_bulk = False
        st.session_state.include_end = False
        st.session_state.scope_signature = scope
    with st.container(key="workbench"):
        signals,editor = st.columns([3.2,1.25],gap="medium")
        edit_span = None
        with editor:
            st.subheader("Edit labels")
            st.caption("Changes apply only to the explicit interval below, not the chart's zoom or reduced preview.")
            st.text_input("Edit start (seconds)",key="edit_start")
            st.text_input("Edit end (seconds)",key="edit_end")
            include_end = st.checkbox("Include the end timestamp",value=False,key="include_end")
            valid_edit = True
            selected = np.array([],int)
            try:
                edit_start = float(decimal_number(st.session_state.edit_start,"Edit start"))
                edit_end = float(decimal_number(st.session_state.edit_end,"Edit end"))
                if edit_start < start or edit_end > end:
                    raise CsvError("The edit interval must stay inside the displayed window")
                selected = clock.rows(edit_start,edit_end,include_end)
                if not len(selected):
                    raise CsvError("No samples in this edit interval")
                edit_span = edit_start,edit_end
                symbol = "≤" if include_end else "<"
                st.caption(f"{len(selected):,} samples: {edit_start:.4f} ≤ time {symbol} {edit_end:.4f} s")
            except CsvError as error:
                st.error(str(error));valid_edit = False
            options = list(dict.fromkeys(CANONICAL+rec.frame[rec.label_column].unique().tolist()+["Custom label…"]))
            bulk = len(selected) == len(rec.frame) or (edit_span is not None and edit_span[1]-edit_span[0] > 60)
            confirmed = st.checkbox("I intend to change this large / whole-file interval",key="allow_bulk") if bulk else True
            with st.form("apply_label_form",clear_on_submit=False):
                choice = st.selectbox("New label",options,key="label_choice")
                custom = st.text_input("Custom label (used only for Custom label…)",key="custom_label")
                apply = st.form_submit_button("Apply label",type="primary",disabled=not valid_edit or not confirmed,width="stretch")
                if apply:
                    try:
                        count = doc.apply(clock,edit_start,edit_end,custom if choice == "Custom label…" else choice,include_end)
                        st.success(f"Changed {count:,} label cells." if count else "These samples already have that label.")
                    except CsvError as error:
                        st.error(str(error))
            a,b = st.columns(2)
            with a:
                st.button("Undo",on_click=doc.undo,disabled=not doc.undo_stack,key="undo",width="stretch")
            with b:
                st.button("Redo",on_click=doc.redo,disabled=not doc.redo_stack,key="redo",width="stretch")
            st.caption(f"{len(doc.changed):,} labels differ from the uploaded file.")
            st.subheader("Download")
            if st.button("Prepare verified CSV",key="prepare_export",width="stretch"):
                try:
                    with st.spinner("Checking all other bytes and fields…"):
                        doc.export()
                except CsvError as error:
                    st.error(str(error))
            if doc.prepared is not None:
                payload,report = doc.prepared
                stem = Path(rec.filename.replace("\\","/")).stem
                st.caption("Verified: all bytes outside label cells are unchanged.")
                st.download_button("Download relabeled CSV",payload,file_name=stem+"_relabeled.csv",mime="text/csv",
                                   on_click="ignore",key="download_csv",width="stretch")
                st.download_button("Download edit log",json.dumps(doc.audit_document(),indent=2,ensure_ascii=False).encode("utf-8"),
                                   file_name=stem+"_label_edits.json",mime="application/json",on_click="ignore",key="download_log",width="stretch")
                st.download_button("Download verification",json.dumps(report,indent=2).encode("utf-8"),file_name=stem+"_verification.json",
                                   mime="application/json",on_click="ignore",key="download_verification",width="stretch")
            st.caption("Download before closing or refreshing the browser. Edits live only in this session; no source file is overwritten.")
            with st.expander("Discard this recording's edits"):
                discard = st.checkbox("Restore every label to this uploaded file",key="confirm_reset")
                st.button("Discard edits",on_click=doc.reset,disabled=not discard,key="reset")
        with signals:
            # Render the earlier placeholder after Apply has updated current labels.
            overview_regions = label_intervals(clock.values,doc.labels,clock.minimum,
                                               clock.exclusive_end,clock.exclusive_end)
            render_labeled_plot(overview(rec,clock,start,end,labels=doc.labels),overview_regions,
                                        target=overview_slot,width="stretch",
                                        theme=None,key="overview",config={"displayModeBar":False},
                                        alt="Full recording with colored road labels; dashed lines mark the plot window.")
            regions = label_intervals(clock.values,doc.labels,start,end,clock.exclusive_end)
            legend_labels = list(LABEL_COLORS)
            for _,_,name in regions:
                if not any(name.strip().casefold() == known.casefold() for known in legend_labels):
                    legend_labels.append(name)
            swatches = "".join(
                '<span style="display:inline-flex;align-items:center;gap:6px;margin:0 14px 6px 0;">'
                '<span aria-hidden="true" style="display:inline-block;width:13px;height:13px;'
                'border-radius:2px;background:'+label_color(name)+';"></span>'+html.escape(name)+'</span>'
                for name in legend_labels
            )
            st.markdown('<div aria-label="Road label color key" style="font-size:12px;">'+swatches+'</div>',
                        unsafe_allow_html=True)
            st.caption("Background colors show current road labels and update after Apply, Undo or Redo. Dashed lines mark edit bounds.")
            st.caption("Hover over a chart for time and values. Raw-channel tooltips retain the original CSV value; long previews show plotted samples only.")
            st.subheader("Labels and motion")
            render_labeled_plot(label_figure(rec,doc.labels,clock,ids,label_regions=regions),regions,width="stretch",theme=None,key="labels",
                            config={"displaylogo":False},alt="Original and current road labels, plus the manually annotated motion state.")
            st.subheader("Sensor signals")
            view = st.selectbox("Sensor view",["All numeric columns","Motion sensors","Orientation and rotation","GPS and environment","Custom"],key="sensor_view")
            available = [name for name in rec.numeric_columns() if name not in {time_column,"timestamp","elapsed_time_ms"}]
            if view == "Motion sensors":
                available = [name for name in available if name in MOTION]
            elif view == "Orientation and rotation":
                available = [name for name in available if name.startswith(("orient_","rot_","dm_"))]
            elif view == "GPS and environment":
                available = [name for name in available if name in {"latitude","longitude","speed","altitude","pressure","illuminance","mag_x","mag_y","mag_z","step_count"}]
            elif view == "Custom":
                available = st.multiselect("Columns",rec.numeric_columns(),default=available[:3],key="custom_columns")
            arrays = {name:rec.numbers(name) for name in available}
            raw_values = {name:rec.frame[name].to_numpy() for name in available}
            if show_derived and view in {"All numeric columns","Motion sensors"}:
                arrays.update(derived_signals(rec,clock))
            used = set()
            for number,(title,columns,unit) in enumerate(GROUPS):
                columns = [name for name in columns if name in arrays]
                if not columns:
                    continue
                used.update(columns)
                st.caption(title+(" · visual only, never exported" if title.startswith("Derived") else ""))
                render_labeled_plot(sensor_figure(clock.values,ids,columns,arrays,unit,budget,edit_span,regions,
                                                 raw_values=raw_values),regions,
                                width="stretch",theme=None,key=f"signal_{number}",config={"displaylogo":False},
                                alt=title+" sensor values over the selected elapsed-time window.")
            for name in (name for name in arrays if name not in used):
                st.caption(name)
                render_labeled_plot(sensor_figure(clock.values,ids,[name],arrays,"source units",budget,edit_span,regions,
                                                 raw_values=raw_values),regions,
                                width="stretch",theme=None,key="extra_"+name,config={"displaylogo":False})
            if not arrays:
                st.info("No numeric channels in this view. Choose another view or inspect the sample table.")
    with st.expander("Sample preview (read-only)"):
        preview = rec.frame.iloc[ids[:500]].copy()
        preview.insert(0,"sample row (not exported)",ids[:500])
        preview.insert(1,"original label (not exported)",preview[rec.label_column])
        preview[rec.label_column] = doc.labels[ids[:500]]
        st.dataframe(preview,width="stretch",hide_index=True)
        st.caption(f"Showing {len(preview):,} of {len(ids):,} samples in this plot window. Preview columns are not added to downloads.")
    with st.expander("Edit history and source fingerprint"):
        st.code("SHA-256: "+rec.source_sha256,language=None)
        if doc.audit:
            st.dataframe(pd.DataFrame(doc.audit),width="stretch",hide_index=True)
        else:
            st.caption("No label edits in this recording.")
        st.caption("Chart previews can be reduced; no raw sample is discarded. Derived traces are inspection aids, not independent evidence of a road anomaly.")


if __name__ == "__main__":
    main()
