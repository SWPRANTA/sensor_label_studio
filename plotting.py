"""Scientific plotting views; downsampling never selects the rows to relabel."""
import csv, io, hashlib, html
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

BLUE, INK, GRAY = "#1d5fbf", "#222222", "#7b8793"
PALETTE = [BLUE, INK, GRAY, "#a5b3c2"]
GROUPS = [
    ("Accelerometer", ["acc_x","acc_y","acc_z"], "m/s²"),
    ("Gyroscope", ["gyro_x","gyro_y","gyro_z"], "rad/s"),
    ("Gravity", ["grav_x","grav_y","grav_z"], "m/s²"),
    ("Magnetic field", ["mag_x","mag_y","mag_z"], "µT"),
    ("Device motion angles", ["dm_alpha","dm_beta","dm_gamma"], "source units"),
    ("Orientation", ["orient_azimuth","orient_pitch","orient_roll"], "source units"),
    ("Rotation vector", ["rot_x","rot_y","rot_z","rot_scalar"], "source units"),
    ("GPS speed", ["speed"], "m/s"),
    ("GPS coordinates", ["latitude","longitude"], "degrees"),
    ("GPS altitude", ["altitude"], "m"),
    ("Pressure", ["pressure"], "source units"),
    ("Illuminance", ["illuminance"], "source units"),
    ("Step count", ["step_count"], "steps"),
    ("Derived acceleration", ["derived_acc_norm","derived_linear_norm","derived_vertical_linear","derived_horizontal_linear"], "m/s²"),
    ("Derived gyro", ["derived_gyro_norm"], "rad/s"),
    ("Derived jerk", ["derived_jerk_norm"], "m/s³"),
]
MOTION = {"acc_x","acc_y","acc_z","gyro_x","gyro_y","gyro_z","grav_x","grav_y","grav_z"}


# Same road-label palette as 05_Nothing3a_Route_Anomaly_Sensor_Visualisation.ipynb.
LABEL_COLORS = {"normal": "#ccd5dc", "Pothole": "#d95f02", "Speed Breaker": "#1b9e77",
                "Utility Cut": "#7570b3", "Uneven Manhole": "#e7298a", "Raveling": "#b59b00",
                "uncertain": "#8e8e93"}


def label_color(label):
    """Known labels match the notebook; custom labels keep a stable color."""
    text = str(label)
    for name, color in LABEL_COLORS.items():
        if text.strip().casefold() == name.casefold():
            return color
    return "#" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:6]


def label_intervals(times, labels, start, end, recording_end):
    """Contiguous full-resolution current labels, clipped to the visible window.

    A row's label lasts until the next time-stamped row changes it. The last
    label ends at the recording's exclusive end, not an arbitrary plot boundary.
    No sensor downsampling or label editing happens here.
    """
    times = np.asarray(times, dtype=float)
    labels = np.asarray(labels, dtype=object)
    valid = np.flatnonzero(np.isfinite(times))
    if not len(valid) or end <= start:
        return []
    tt, yy = times[valid], labels[valid]
    cuts = np.r_[0, np.flatnonzero(yy[1:] != yy[:-1]) + 1, len(valid)]
    spans = []
    for left, right in zip(cuts[:-1], cuts[1:]):
        a = max(float(start), float(tt[left]))
        b = min(float(end), float(tt[right]) if right < len(tt) else float(recording_end))
        if b > a:
            spans.append((a, b, str(yy[left])))
    return spans


def add_label_shading(fig, regions):
    """Visible, non-editable label bands on every panel, without double fills.

    The bundled Plotly.js cannot resolve layer='between' with 'y domain':
    its subplot lookup uses 'xy domain', then tries to append to an undefined
    layer. Use the upper layer with explicit paper-domain bounds instead.
    studio.css makes these decorative paths pointer-transparent for hover/zoom.
    """
    # Safe to call once when building a figure and again at its rendering boundary.
    # Keep selection boundaries and any unrelated shapes unchanged.
    fig.layout.shapes = tuple(
        shape for shape in (fig.layout.shapes or ())
        if not str(shape.name or "").startswith("road-label:")
    )
    axes = fig.layout.to_plotly_json()
    xaxes = [key for key in axes
             if key == "xaxis" or (key.startswith("xaxis") and key[5:].isdigit())]
    for key in xaxes or ["xaxis"]:
        suffix = key[5:]
        xref = "x" + suffix
        anchor = axes.get(key, {}).get("anchor", "y" + suffix)
        yref = anchor if str(anchor).startswith("y") else "y" + suffix
        bottom, top = axes.get("yaxis" + yref[1:], {}).get("domain", [0, 1])
        for a, b, label in regions or []:
            fig.add_shape(type="rect", name="road-label:" + str(label),
                          x0=a, x1=b, y0=bottom, y1=top, xref=xref, yref="paper",
                          fillcolor=label_color(label), opacity=.24, line_width=0,
                          layer="above", editable=False)
    return fig


def preview_indices(y, limit=2000):
    """Retain local extrema and missing-value markers, not just every nth sample."""
    n = len(y)
    if n <= limit:
        return np.arange(n)
    selected = [0, n-1]
    for block in np.array_split(np.arange(1, n-1), max(1, (limit-2)//3)):
        good = block[np.isfinite(y[block])]
        if len(good):
            selected.extend([int(good[np.argmin(y[good])]), int(good[np.argmax(y[good])])])
        bad = block[~np.isfinite(y[block])]
        if len(bad):
            selected.append(int(bad[0]))
    return np.unique(selected)


def derived_signals(rec, clock):
    result = {}
    def matrix(names):
        return np.column_stack([rec.numbers(c) for c in names]) if all(c in rec.frame for c in names) else None
    acc = matrix(["acc_x","acc_y","acc_z"])
    gyro = matrix(["gyro_x","gyro_y","gyro_z"])
    grav = matrix(["grav_x","grav_y","grav_z"])
    if acc is not None:
        result["derived_acc_norm"] = np.linalg.norm(acc, axis=1)
    if gyro is not None:
        result["derived_gyro_norm"] = np.linalg.norm(gyro, axis=1)
    if acc is not None and grav is not None:
        norm = np.linalg.norm(grav, axis=1)
        valid = np.isfinite(acc).all(axis=1) & np.isfinite(grav).all(axis=1) & (norm >= 6) & (norm <= 13)
        linear = acc-grav
        linear[~valid] = np.nan
        unit = grav/np.where(valid, norm, np.nan)[:, None]
        vertical = np.sum(linear*unit, axis=1)
        total = np.linalg.norm(linear, axis=1)
        result.update(derived_linear_norm=total, derived_vertical_linear=vertical,
                      derived_horizontal_linear=np.sqrt(np.maximum(total**2-vertical**2, 0)))
        dt = np.diff(clock.values)
        jerk = np.full(len(total), np.nan)
        good = valid[1:] & valid[:-1] & np.isfinite(dt) & (dt > 0) & (dt <= .1)
        derivative = np.diff(linear, axis=0)[good]/dt[good, None]
        jerk[np.flatnonzero(good)+1] = np.linalg.norm(derivative, axis=1)
        result["derived_jerk_norm"] = jerk
    return result


def layout(fig, height=190):
    fig.update_layout(height=height, paper_bgcolor="white", plot_bgcolor="white",
                      margin=dict(l=52,r=12,t=30,b=32),
                      font=dict(family="Geist, sans-serif",size=12,color=INK),
                      legend=dict(orientation="h",x=0,y=1.23,font=dict(size=11)),
                      hovermode="x unified", hoverdistance=-1, dragmode="zoom")
    fig.update_xaxes(title_text="Elapsed time (s)", showgrid=False, zeroline=False, nticks=6)
    fig.update_yaxes(showgrid=True, gridcolor="#eeeeee", nticks=5, zeroline=False)
    return fig


def sensor_figure(times, row_ids, columns, arrays, unit, limit=2000, edit_span=None,
                  label_regions=None, raw_values=None):
    fig = go.Figure()
    for i, col in enumerate(columns):
        y = arrays[col][row_ids]
        ii = preview_indices(y, limit)
        # Raw CSV spellings retain precision in the tooltip. Numeric copies are
        # only for the curve; neither view is ever used to export the recording.
        values = (raw_values[col][row_ids][ii] if raw_values is not None and col in raw_values
                  else [format(float(value), ".17g") for value in y[ii]])
        fig.add_trace(go.Scatter(x=times[row_ids][ii],y=y[ii],mode="lines",name=col,
                                text=[html.escape(str(value)) for value in values],
                                hovertemplate="Time: %{x:.6f} s<br>Value: %{text}<extra>%{fullData.name}</extra>",
                                line=dict(color=PALETTE[i % len(PALETTE)],width=1.3),connectgaps=False))
    layout(fig)
    fig.update_yaxes(title_text=unit)
    add_label_shading(fig, label_regions)
    if edit_span:
        # Neutral boundaries keep the edit selection distinct from road-label fills.
        for boundary in edit_span:
            fig.add_vline(x=boundary,line_color=INK,line_width=1,line_dash="dash")
    return fig


def overview(rec, clock, start, end, labels=None):
    column = next((c for c in ["acc_z","speed","acc_x"] if c in rec.frame), rec.numeric_columns()[0])
    y = rec.numbers(column)
    ii = preview_indices(y, 1600)
    fig = go.Figure(go.Scatter(x=clock.values[ii],y=y[ii],mode="lines",name=column,
                              text=[html.escape(str(value)) for value in rec.frame[column].to_numpy()[ii]],
                              hovertemplate="Time: %{x:.6f} s<br>Value: %{text}<extra>%{fullData.name}</extra>",
                              line=dict(color=GRAY,width=1),connectgaps=False))
    layout(fig,110)
    fig.update_layout(margin=dict(l=52,r=12,t=4,b=28),showlegend=False)
    fig.update_yaxes(title_text=column,nticks=3)
    current = rec.frame[rec.label_column].to_numpy() if labels is None else labels
    add_label_shading(fig, label_intervals(clock.values,current,clock.minimum,
                                         clock.exclusive_end,clock.exclusive_end))
    # Two boundary lines, not a full-panel transparent overlay over the data.
    for boundary in (start, end):
        fig.add_vline(x=boundary,line_color=INK,line_width=1,line_dash="dash")
    return fig


def label_figure(rec, labels, clock, ids, label_regions=None):
    has_motion = "motion_state" in rec.frame
    fig = make_subplots(rows=2 if has_motion else 1,cols=1,shared_xaxes=True,
                        row_heights=[.68,.32] if has_motion else [1],vertical_spacing=.18 if has_motion else .1)
    original = rec.frame[rec.label_column].to_numpy()
    names = list(dict.fromkeys(list(original[ids])+list(labels[ids])))
    mapping = {v:i for i,v in enumerate(names)}
    for values, name, color in [(original,"Original label",GRAY),(labels,"Current label",BLUE)]:
        v = values[ids]
        keep = np.unique(np.r_[0,np.flatnonzero(v[1:] != v[:-1])+1,len(v)-1])
        fig.add_trace(go.Scatter(x=clock.values[ids][keep],y=[mapping[s] for s in v[keep]],mode="lines",
                                line=dict(color=color,width=2,shape="hv"),name=name,text=v[keep],
                                hovertemplate="%{x:.4f} s: %{text}<extra>"+name+"</extra>"),row=1,col=1)
    fig.update_yaxes(tickvals=list(mapping.values()),ticktext=names,row=1,col=1)
    if has_motion:
        v = rec.frame.motion_state.to_numpy()[ids]
        kinds = list(dict.fromkeys(v));codes = {v:i for i,v in enumerate(kinds)}
        keep = np.unique(np.r_[0,np.flatnonzero(v[1:] != v[:-1])+1,len(v)-1])
        fig.add_trace(go.Scatter(x=clock.values[ids][keep],y=[codes[s] for s in v[keep]],mode="lines",
                                line=dict(color=INK,width=1.5,shape="hv"),name="Motion state",text=v[keep],
                                hovertemplate="%{x:.4f} s: %{text}<extra>Motion state</extra>"),row=2,col=1)
        fig.update_yaxes(tickvals=list(codes.values()),ticktext=kinds,row=2,col=1)
    layout(fig,190 if has_motion else 145)
    fig.update_layout(margin=dict(l=104,r=12,t=32,b=30))
    fig.update_xaxes(title_text="",row=1,col=1)
    if label_regions is not None:
        add_label_shading(fig,label_regions)
    elif len(ids):
        right = int(ids[-1])+1
        end = float(clock.values[right]) if right < len(clock.values) and np.isfinite(clock.values[right]) else clock.exclusive_end
        add_label_shading(fig,label_intervals(clock.values,labels,float(clock.values[ids[0]]),
                                             end,clock.exclusive_end))
    return fig


def synthetic_demo():
    """Clearly identified synthetic recording for trying controls without user files."""
    rng = np.random.default_rng(42)
    out = io.StringIO(newline="")
    names = ["timestamp","elapsed_time_ms","acc_x","acc_y","acc_z","gyro_x","gyro_y","gyro_z",
             "mag_x","mag_y","mag_z","pressure","illuminance","dm_alpha","dm_beta","dm_gamma",
             "step_count","latitude","longitude","speed","altitude","orient_azimuth","orient_pitch",
             "orient_roll","grav_x","grav_y","grav_z","rot_x","rot_y","rot_z","rot_scalar","label","motion_state"]
    writer = csv.writer(out,lineterminator="\r\n")
    writer.writerow(names)
    for i in range(3201):
        t = i/100
        pulse = 5*np.exp(-((t-4.2)/.1)**2)-3*np.exp(-((t-4.4)/.15)**2)
        pulse += 3*np.exp(-((t-17.5)/.4)**2)
        row = [str(1792640000000+i*10),str(i*10),f"{.15*np.sin(t*3)+rng.normal(0,.07):.8f}",
               f"{.2*np.cos(t*2)+rng.normal(0,.06):.8f}",f"{9.81+pulse+rng.normal(0,.12):.8f}",
               f"{.03*np.sin(t*5):.7f}",f"{.04*np.cos(t*3):.7f}",f"{.02*np.sin(t):.7f}",
               "21.00","-7.00","32.00","1013.250","215.0",f"{t:.3f}","0.0","0.0","0",
               f"{22.82+t*.00001:.8f}","89.54",f"{4+.7*np.sin(t/5):.6f}","-40.00",
               f"{t:.3f}","0.0","0.0","0.0","0.0","9.81","0.0","0.0","0.0","1.0",
               "Pothole" if 2 <= t < 6 else ("Speed Breaker" if 15 <= t < 20 else "normal"),"moving"]
        writer.writerow(row)
    return out.getvalue().encode("utf-8")
