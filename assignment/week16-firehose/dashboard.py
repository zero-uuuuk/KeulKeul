"""
따릉이 실시간 현황 대시보드 — Firehose 파이프라인 시연용

흐름:  노트북 폴러 → Firehose → Lambda → S3 → Athena → 이 화면
       30초마다 Athena를 다시 조회해 자동 갱신된다.

실행:
  pip install streamlit pandas boto3 pydeck altair
  streamlit run dashboard.py

AWS 없이 화면만 보기 (가짜 데이터):
  set BIKE_DEMO=1          (Windows CMD)
  streamlit run dashboard.py

필요 IAM 권한 (폴러 사용자에 추가): AmazonAthenaFullAccess, AmazonS3FullAccess
"""

import io
import os
import random
import time
from datetime import datetime, timedelta, timezone

import pandas as pd
import streamlit as st

KST = timezone(timedelta(hours=9))
DEMO = os.environ.get("BIKE_DEMO") == "1"
FULL_POLL = 2000  # 이 건수 이상 도착한 폴링만 "완전히 도착"으로 간주

DEFAULTS = dict(
    region="ap-northeast-2",
    database="week16_firehose_db",
    table="bike_status",
    station_id="ST-2327",
    station_label="한양대역 1번출구",
    center_lat=37.55657959,
    center_lon=127.04335785,
    refresh_sec=30,
)

st.set_page_config(page_title="따릉이 실시간 현황", layout="wide",
                   initial_sidebar_state="collapsed")


# ================================================================= Athena
def find_results_bucket(region: str) -> str | None:
    import boto3
    s3 = boto3.client("s3", region_name=region)
    for b in s3.list_buckets().get("Buckets", []):
        if b["Name"].startswith("keulkeul-week16-"):
            return f"s3://{b['Name']}/athena-results/"
    return None


@st.cache_data(ttl=25, show_spinner=False)
def run_athena(sql: str, region: str, database: str, output: str) -> pd.DataFrame:
    import boto3
    athena = boto3.client("athena", region_name=region)
    qid = athena.start_query_execution(
        QueryString=sql,
        QueryExecutionContext={"Database": database},
        ResultConfiguration={"OutputLocation": output},
    )["QueryExecutionId"]
    while True:
        status = athena.get_query_execution(QueryExecutionId=qid)["QueryExecution"]["Status"]
        if status["State"] in ("SUCCEEDED", "FAILED", "CANCELLED"):
            break
        time.sleep(0.5)
    if status["State"] != "SUCCEEDED":
        raise RuntimeError(status.get("StateChangeReason", status["State"]))
    bucket, key = output.replace("s3://", "").split("/", 1)
    body = boto3.client("s3", region_name=region).get_object(Bucket=bucket, Key=f"{key}{qid}.csv")["Body"].read()
    return pd.read_csv(io.BytesIO(body))


def hours_clause(n: int) -> str:
    now = datetime.now(KST)
    return ", ".join(f"'{(now - timedelta(hours=i)).strftime('%H')}'" for i in range(n))


def load_two_polls(cfg) -> tuple[pd.DataFrame, pd.DataFrame]:
    """완전히 도착한 최근 폴링 2회분. (최신, 직전)"""
    t = f"{cfg['database']}.{cfg['table']}"
    sql = f"""
    WITH counts AS (
      SELECT polled_at, COUNT(*) AS c FROM {t}
      WHERE hour IN ({hours_clause(2)}) GROUP BY polled_at
    ),
    picked AS (
      SELECT polled_at FROM counts WHERE c >= {FULL_POLL} ORDER BY polled_at DESC LIMIT 2
    )
    SELECT b.stationId, b.stationName, b.rackTotCnt, b.parkingBikeTotCnt,
           b.empty_racks, b.is_empty, b.is_overflow,
           b.stationLatitude AS lat, b.stationLongitude AS lon, b.polled_at
    FROM {t} b
    WHERE b.hour IN ({hours_clause(2)}) AND b.polled_at IN (SELECT polled_at FROM picked)
    """
    df = run_athena(sql, cfg["region"], cfg["database"], cfg["output"])
    if df.empty:
        return df, df
    times = sorted(df["polled_at"].unique(), reverse=True)
    latest = df[df["polled_at"] == times[0]].copy()
    prev = df[df["polled_at"] == times[1]].copy() if len(times) > 1 else pd.DataFrame()
    return latest, prev


def load_trend(cfg) -> pd.DataFrame:
    """폴링별 서울 전체 집계 — 최근 3시간."""
    t = f"{cfg['database']}.{cfg['table']}"
    sql = f"""
    SELECT polled_at,
           SUM(parkingBikeTotCnt) AS total_bikes,
           SUM(CASE WHEN is_empty THEN 1 ELSE 0 END) AS empty_cnt,
           COUNT(*) AS records
    FROM {t}
    WHERE hour IN ({hours_clause(3)})
    GROUP BY polled_at
    HAVING COUNT(*) >= {FULL_POLL}
    ORDER BY polled_at
    """
    return run_athena(sql, cfg["region"], cfg["database"], cfg["output"])


def load_series(cfg, station_id: str | None = None) -> pd.DataFrame:
    t = f"{cfg['database']}.{cfg['table']}"
    sid = station_id or cfg["station_id"]
    sql = f"""
    SELECT polled_at, parkingBikeTotCnt
    FROM {t}
    WHERE stationId = '{sid}' AND hour IN ({hours_clause(3)})
    ORDER BY polled_at
    """
    return run_athena(sql, cfg["region"], cfg["database"], cfg["output"])


# ================================================================= 데모 데이터
def _demo_snapshot(seed: int, when: datetime) -> pd.DataFrame:
    rnd = random.Random(seed)
    rows = []
    for i in range(2700):
        rack = 5 + (i * 7) % 16
        bikes = max(0, min(rack + 5, int(rnd.gauss(rack * 0.5, rack * 0.35))))
        rows.append(dict(
            stationId=f"ST-{i+1}", stationName=f"{100+i}. 데모 대여소 {i+1}",
            rackTotCnt=rack, parkingBikeTotCnt=bikes, empty_racks=max(rack - bikes, 0),
            is_empty=bikes == 0, is_overflow=bikes > rack,
            lat=37.45 + ((i * 37) % 1000) / 4000, lon=126.80 + ((i * 53) % 1000) / 2857,
            polled_at=when.isoformat(timespec="seconds"),
        ))
    rows[0].update(stationId="ST-2327", stationName="3545.한양대역 1번출구", rackTotCnt=10,
                   lat=37.55657959, lon=127.04335785)
    return pd.DataFrame(rows)


def demo_two_polls():
    now = datetime.now(KST).replace(microsecond=0)
    base = int(time.time() // 30)
    latest = _demo_snapshot(base, now)
    prev = _demo_snapshot(base, now - timedelta(seconds=30))
    rnd = random.Random(base)
    idx = rnd.sample(range(len(latest)), 60)          # 60곳에서 ±1~2 변화
    for i in idx:
        d = rnd.choice([-2, -1, 1, 2])
        latest.loc[i, "parkingBikeTotCnt"] = max(0, latest.loc[i, "parkingBikeTotCnt"] + d)
    latest["empty_racks"] = (latest["rackTotCnt"] - latest["parkingBikeTotCnt"]).clip(lower=0)
    latest["is_empty"] = latest["parkingBikeTotCnt"] == 0
    latest["is_overflow"] = latest["parkingBikeTotCnt"] > latest["rackTotCnt"]
    return latest, prev


def demo_trend():
    now = datetime.now(KST)
    rnd = random.Random(7)
    rows, total, empty = [], 16000, 420
    for i in range(240, 0, -1):
        total += rnd.randint(-40, 40); empty += rnd.randint(-5, 5)
        t = now - timedelta(seconds=30 * i)
        rows.append(dict(polled_at=t.isoformat(timespec="seconds"), total_bikes=total,
                         empty_cnt=max(0, empty), records=2731))
    return pd.DataFrame(rows)


def demo_series(station_id: str = "ST-2327"):
    now = datetime.now(KST)
    rnd = random.Random(sum(map(ord, station_id)))
    pts, v = [], 4
    for i in range(240, 0, -1):
        v = max(0, min(12, v + rnd.choice([-1, 0, 0, 1])))
        pts.append(dict(polled_at=(now - timedelta(seconds=30 * i)).isoformat(timespec="seconds"),
                        parkingBikeTotCnt=v))
    return pd.DataFrame(pts)


# ================================================================= 사이드바
with st.sidebar:
    st.header("설정")
    cfg = dict(DEFAULTS)
    cfg["region"] = st.text_input("리전", cfg["region"])
    cfg["database"] = st.text_input("Athena 데이터베이스", cfg["database"])
    cfg["table"] = st.text_input("테이블", cfg["table"])
    cfg["station_id"] = st.text_input("관심 대여소 ID", cfg["station_id"])
    cfg["station_label"] = st.text_input("관심 대여소 이름", cfg["station_label"])
    cfg["refresh_sec"] = st.slider("갱신 주기(초)", 30, 300, cfg["refresh_sec"], 10)
    if not DEMO:
        auto = find_results_bucket(cfg["region"]) or ""
        cfg["output"] = st.text_input("Athena 결과 위치", auto, help="s3://버킷/athena-results/")
    st.divider()
    st.caption("이 화면은 파이프라인의 **마지막 소비자**입니다. 폴러 30초 → Firehose → Lambda → S3 → Athena → 여기.")
    if DEMO:
        st.warning("데모 모드: AWS 없이 가짜 데이터로 그립니다.")


# ================================================================= 본문
def nz(d):
    """0이면 뱃지를 숨기기 위해 None."""
    return None if d is None or d == 0 else d


def line(df: pd.DataFrame, ycol: str, label: str, height: int = 180):
    """시간축 꺾은선. y축은 데이터 범위에 맞춤(0부터 시작하지 않음)."""
    import altair as alt
    d = df[["polled_at", ycol]].copy()
    d["time"] = pd.to_datetime(d["polled_at"]).dt.tz_convert(KST).dt.tz_localize(None)
    return (alt.Chart(d).mark_line(interpolate="monotone").encode(
        x=alt.X("time:T", title=None, axis=alt.Axis(format="%H:%M")),
        y=alt.Y(f"{ycol}:Q", title=label, scale=alt.Scale(zero=False)),
        tooltip=[alt.Tooltip("time:T", format="%H:%M:%S", title="시각"), alt.Tooltip(f"{ycol}:Q", title=label)],
    ).properties(height=height))


@st.fragment(run_every=f"{cfg['refresh_sec']}s")
def body():
    st.title("따릉이 실시간 현황")

    cols = st.columns(6)
    for i, (col, (title, sub)) in enumerate(zip(cols, [
        ("폴러", "30초마다 API 호출"), ("Firehose", "수신·버퍼"), ("Lambda", "타입 변환·파생 필드"),
        ("S3", "clean/hour=HH/"), ("Athena", "SQL 조회"), ("대시보드", "자동 갱신"),
    ])):
        arrow = "" if i == 5 else "<span style='position:absolute;right:-8px;top:14px;color:#999'>&rarr;</span>"
        col.markdown(f"<div style='position:relative;text-align:center;padding:8px 4px;border:1px solid #ddd;border-radius:8px'>"
                     f"<div style='font-size:16px;font-weight:600'>{title}</div>"
                     f"<div style='font-size:12px;color:#777'>{sub}</div>{arrow}</div>",
                     unsafe_allow_html=True)
    st.divider()

    # ---- 데이터
    try:
        if DEMO:
            latest, prev = demo_two_polls(); trend = demo_trend(); series = demo_series()
        else:
            if not cfg.get("output"):
                st.error("왼쪽 위 » 를 눌러 사이드바를 열고 Athena 결과 위치를 입력하세요.")
                return
            latest, prev = load_two_polls(cfg); trend = load_trend(cfg); series = load_series(cfg)
    except Exception as e:
        st.error(f"Athena 조회 실패: {e}")
        st.info("확인할 것: ① 폴러가 켜져 있는가 ② `MSCK REPAIR TABLE`을 실행했는가 "
                "③ IAM 사용자에 AmazonAthenaFullAccess, AmazonS3FullAccess가 있는가")
        return
    if latest.empty:
        st.warning("최근 2시간 안에 완전히 도착한 폴링이 없습니다. 폴러를 켜고 2분 뒤 `MSCK REPAIR TABLE`을 실행하세요.")
        return

    # ---- 직전 폴링과 비교
    has_prev = not prev.empty
    if has_prev:
        m = latest.merge(prev[["stationId", "parkingBikeTotCnt"]], on="stationId", suffixes=("", "_prev"))
        m["delta"] = m["parkingBikeTotCnt"] - m["parkingBikeTotCnt_prev"]
        changed = m[m["delta"] != 0]
        rentals = int(-changed.loc[changed["delta"] < 0, "delta"].sum())
        returns = int(changed.loc[changed["delta"] > 0, "delta"].sum())
        d_bikes = int(latest["parkingBikeTotCnt"].sum() - prev["parkingBikeTotCnt"].sum())
        d_empty = int(latest["is_empty"].sum() - prev["is_empty"].sum())
        d_over = int(latest["is_overflow"].sum() - prev["is_overflow"].sum())
        changed_ids = set(changed["stationId"])
    else:
        changed = pd.DataFrame(); rentals = returns = 0; d_bikes = d_empty = d_over = None; changed_ids = set()

    # ---- 숫자 카드
    polled = pd.to_datetime(latest["polled_at"].iloc[0]).tz_convert(KST)
    age = int((datetime.now(KST) - polled).total_seconds())
    total_records = int(trend["records"].sum()) if not trend.empty else len(latest)
    c = st.columns(6)
    c[0].metric("대여소 수", f"{len(latest):,}")
    c[1].metric("전체 자전거", f"{int(latest['parkingBikeTotCnt'].sum()):,}대", nz(d_bikes))
    c[2].metric("0대 대여소", f"{int(latest['is_empty'].sum()):,}곳", nz(d_empty), delta_color="inverse")
    c[3].metric("초과 대여소", f"{int(latest['is_overflow'].sum()):,}곳", nz(d_over), delta_color="inverse")
    c[4].metric("누적 레코드 (3h)", f"{total_records:,}")
    c[5].metric("마지막 수집", polled.strftime("%H:%M:%S"), f"{age}초 전", delta_color="off")
    st.caption("화살표는 직전 폴링(30초 전) 대비 변화. 누적 레코드는 갱신할 때마다 약 2,700건씩 늘어난다.")
    st.divider()

    # ---- 30초 사이에 일어난 일
    h1, h2 = st.columns([5, 1])
    h1.subheader("30초 사이에 일어난 일")
    if h2.button("지금 새로고침", use_container_width=True):
        run_athena.clear()
    if has_prev:
        a, b, cc = st.columns([1, 1, 2])
        a.metric("대여 (자전거 빠짐)", f"{rentals}대")
        b.metric("반납 (자전거 들어옴)", f"{returns}대")
        cc.metric("상태가 바뀐 대여소", f"{len(changed):,}곳 / {len(latest):,}곳")
        if not changed.empty:
            feed = (changed.assign(변화=changed["delta"].map(lambda d: f"{'+' if d > 0 else ''}{d}"))
                    .reindex(changed["delta"].abs().sort_values(ascending=False).index)
                    .head(10)[["stationName", "parkingBikeTotCnt_prev", "parkingBikeTotCnt", "변화"]]
                    .rename(columns={"stationName": "대여소", "parkingBikeTotCnt_prev": "30초 전",
                                     "parkingBikeTotCnt": "지금"}))
            st.dataframe(feed, hide_index=True, use_container_width=True)
            st.caption(f"{pd.to_datetime(prev['polled_at'].iloc[0]).tz_convert(KST).strftime('%H:%M:%S')} → "
                       f"{polled.strftime('%H:%M:%S')} 사이 변화가 큰 대여소 10곳. 음수 = 대여(빠짐), 양수 = 반납(들어옴)")
    else:
        st.info("직전 폴링이 아직 없습니다. 다음 갱신부터 변화가 표시됩니다.")
    st.divider()

    # ---- 추이 + 관심 대여소
    l, r = st.columns(2)
    with l:
        st.subheader("서울 전체 추이 (최근 3시간)")
        if not trend.empty:
            st.altair_chart(line(trend, "total_bikes", "전체 자전거"), use_container_width=True)
            st.altair_chart(line(trend, "empty_cnt", "0대 대여소"), use_container_width=True)
            st.caption(f"{len(trend)}회 폴링. 퇴근 시간대엔 전체 자전거 수가 줄고 0대 대여소가 늘어나는 흐름이 보인다.")
    with r:
        st.subheader(f"관심 대여소: {cfg['station_label']}")
        me = latest[latest["stationId"] == cfg["station_id"]]
        if me.empty:
            st.warning(f"{cfg['station_id']} 데이터가 없습니다.")
        else:
            row = me.iloc[0]
            d_me = None
            if has_prev:
                pm = prev[prev["stationId"] == cfg["station_id"]]
                if not pm.empty:
                    d_me = int(row["parkingBikeTotCnt"] - pm.iloc[0]["parkingBikeTotCnt"])
            x, y = st.columns(2)
            x.metric("지금 자전거", f"{int(row['parkingBikeTotCnt'])}대", nz(d_me))
            y.metric("빈 거치대", f"{int(row['empty_racks'])}개")
            st.caption(f"`{cfg['station_id']}` · 거치대 {int(row['rackTotCnt'])}개")
        if not series.empty:
            st.altair_chart(line(series, "parkingBikeTotCnt", "자전거 수", 200), use_container_width=True)
            st.caption(f"최근 3시간 · {len(series)}개 포인트. 폴러가 돌수록 오른쪽으로 자란다.")
    st.divider()

    # ---- 지도
    st.subheader("지도")
    scope = st.radio("범위", ["한양대 주변", "서울 전체"], horizontal=True, label_visibility="collapsed")
    import pydeck as pdk

    pts = latest.copy()
    def color(b):
        return [220, 60, 60, 210] if b == 0 else ([240, 160, 40, 210] if b <= 3 else [50, 170, 90, 190])
    pts["color"] = pts["parkingBikeTotCnt"].map(color)
    pts["radius"] = 50
    pts.loc[pts["stationId"].isin(changed_ids), "radius"] = 120
    pts.loc[pts["stationId"] == cfg["station_id"], "radius"] = 180
    pts["line"] = pts["stationId"].isin(changed_ids).map(lambda x: [255, 255, 255, 230] if x else [0, 0, 0, 0])

    view = (pdk.ViewState(latitude=cfg["center_lat"], longitude=cfg["center_lon"], zoom=13.5)
            if scope == "한양대 주변" else pdk.ViewState(latitude=37.5565, longitude=126.9780, zoom=10.5))
    layer = pdk.Layer("ScatterplotLayer", id="stations", data=pts, get_position="[lon, lat]",
                      get_fill_color="color", get_radius="radius", get_line_color="line",
                      stroked=True, line_width_min_pixels=2, pickable=True,
                      radius_min_pixels=3, radius_max_pixels=20)
    deck = pdk.Deck(layers=[layer], initial_view_state=view, map_style=None,
                    tooltip={"text": "{stationName}\n자전거 {parkingBikeTotCnt}대 / 거치대 {rackTotCnt}개\n클릭하면 아래에 상세"})

    sel_id = st.session_state.get("sel_station", cfg["station_id"])
    clicked = None
    try:
        ev = st.pydeck_chart(deck, on_select="rerun", selection_mode="single-object", key="bike_map")
        objs = (getattr(ev, "selection", None) or {}).get("objects", {}).get("stations", [])
        if objs:
            clicked = objs[0]["stationId"]
        click_ok = True
    except TypeError:
        st.pydeck_chart(deck)
        click_ok = False
    st.caption("빨강 = 0대, 주황 = 1~3대, 초록 = 4대 이상 · 흰 테두리 = 30초 사이 변한 대여소 · 가장 큰 점 = 관심 대여소"
               + (" · **점을 클릭하면 아래에 상세 정보**" if click_ok else ""))

    # 이름으로 찾기 (클릭 대안)
    names = latest.sort_values("stationName")
    options = names["stationId"].tolist()
    labels = dict(zip(names["stationId"], names["stationName"]))
    if clicked:
        sel_id = clicked
    idx = options.index(sel_id) if sel_id in options else 0
    chosen = st.selectbox("대여소 이름으로 찾기", options, index=idx, format_func=lambda i: labels.get(i, i))
    if not clicked and chosen != sel_id:
        sel_id = chosen
    st.session_state["sel_station"] = sel_id
    if not click_ok:
        st.caption("지도 클릭은 Streamlit 1.39 이상에서 동작한다. `pip install -U streamlit` 후 다시 실행하면 된다.")

    # 선택 대여소 상세
    srow = latest[latest["stationId"] == sel_id]
    if not srow.empty:
        r = srow.iloc[0]
        st.markdown(f"#### 선택한 대여소: {r['stationName']}")
        d_sel = None
        if has_prev:
            pm = prev[prev["stationId"] == sel_id]
            if not pm.empty:
                d_sel = int(r["parkingBikeTotCnt"] - pm.iloc[0]["parkingBikeTotCnt"])
        k = st.columns(5)
        k[0].metric("지금 자전거", f"{int(r['parkingBikeTotCnt'])}대", nz(d_sel))
        k[1].metric("거치대", f"{int(r['rackTotCnt'])}개")
        k[2].metric("빈 거치대", f"{int(r['empty_racks'])}개")
        k[3].metric("상태", "비어 있음" if r["is_empty"] else ("거치대 초과" if r["is_overflow"] else "정상"))
        k[4].metric("대여소 ID", r["stationId"])
        try:
            ss = demo_series(sel_id) if DEMO else load_series(cfg, sel_id)
            if not ss.empty:
                st.altair_chart(line(ss, "parkingBikeTotCnt", "자전거 수", 180), use_container_width=True)
                st.caption(f"최근 3시간 · {len(ss)}개 포인트 · 위도 {r['lat']:.5f}, 경도 {r['lon']:.5f}")
        except Exception as e:
            st.caption(f"추이 조회 실패: {e}")

    st.caption(f"갱신 {datetime.now(KST).strftime('%H:%M:%S')} · 다음 갱신까지 {cfg['refresh_sec']}초")


body()
