"""Use the SageMaker-trained model locally and write a standalone HTML report.

No training or endpoint creation. Default: download this lab's completed S3 model.
With --model-file, all inference/report generation runs without AWS access.
"""
import argparse
from datetime import datetime
import hashlib
import html
import json
from pathlib import Path, PurePosixPath
import sys
import tarfile
from urllib.parse import urlparse
import webbrowser

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data'
OUT = ROOT / 'outputs'
MAX_MODEL_BYTES = 128 * 1024 * 1024


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def acquire_model(local_file):
    if local_file:
        path = Path(local_file).expanduser().resolve()
        if not path.is_file():
            raise ValueError(f'모델 압축 파일을 찾을 수 없습니다: {path}')
        return path, '직접 지정한 모델 파일'

    import boto3
    cfg = read_json(ROOT / 'config.json')
    handoff = OUT / 'training-result.json'
    state_path = ROOT / 'lab_state.json'
    if handoff.exists():
        result = read_json(handoff)
    elif state_path.exists():
        result = read_json(state_path)
    else:
        raise ValueError('학습 결과 정보가 없습니다. 실습1의 학습을 완료하거나 --model-file로 내려받은 model.tar.gz를 지정하세요.')
    for key in ('account_id', 'region', 'bucket'):
        if result.get(key) != cfg.get(key):
            raise ValueError('학습 결과와 config.json의 계정·리전·버킷이 다릅니다.')
    session = boto3.Session(profile_name=cfg['profile'], region_name=cfg['region'])
    if session.client('sts').get_caller_identity()['Account'] != cfg['account_id']:
        raise ValueError('AWS CLI 계정과 config.json의 계정이 다릅니다.')
    uri = result.get('model_data')
    if not uri:
        job = session.client('sagemaker').describe_training_job(TrainingJobName=result['training'])
        if job['TrainingJobStatus'] != 'Completed':
            raise ValueError('학습 상태가 Completed가 된 후 실행하세요.')
        uri = job['ModelArtifacts']['S3ModelArtifacts']
    parsed = urlparse(uri)
    key = parsed.path.lstrip('/')
    if (parsed.scheme != 's3' or parsed.netloc != cfg['bucket']
            or not key.startswith('week11/output/') or not key.endswith('/model.tar.gz')
            or parsed.query or parsed.fragment):
        raise ValueError('실습 버킷의 week11/output/ 아래 model.tar.gz만 사용할 수 있습니다.')
    path = OUT / 'model.tar.gz'
    pending = OUT / 'model.tar.gz.download'
    print('S3에서 학습된 model.tar.gz를 다운로드합니다.')
    session.client('s3').download_file(parsed.netloc, key, str(pending))
    pending.replace(path)
    return path, result.get('training', 'SageMaker 학습 모델')


def load_booster(archive, xgb):
    # Read only the expected model member; never extract paths or execute pickle.
    with tarfile.open(archive, 'r:gz') as bundle:
        members = [m for m in bundle.getmembers()
                   if m.isfile() and PurePosixPath(m.name).name == 'xgboost-model']
        if len(members) != 1:
            raise ValueError('압축 파일에 xgboost-model이 하나 있어야 합니다. 이 실습의 XGBoost 1.7-1 결과를 선택하세요.')
        member = members[0]
        if not 0 < member.size <= MAX_MODEL_BYTES:
            raise ValueError('모델 파일 크기가 실습 범위를 벗어났습니다.')
        with bundle.extractfile(member) as stream:
            payload = stream.read(MAX_MODEL_BYTES + 1)
    model = xgb.Booster()
    model.load_model(bytearray(payload))
    model.set_param({'nthread': 2})
    return model, hashlib.sha256(payload).hexdigest()


def predict(model, frame, features, xgb, np):
    missing = set(features) - set(frame.columns)
    if missing:
        raise ValueError(f'입력 특성이 없습니다: {sorted(missing)}')
    values = frame[features].to_numpy(dtype=np.float32)
    if not np.isfinite(values).all():
        raise ValueError('입력 데이터에 숫자가 아닌 값 또는 결측값이 있습니다.')
    matrix = xgb.DMatrix(values, feature_names=model.feature_names)
    predicted = np.asarray(model.predict(matrix), dtype=float)
    if predicted.shape != (len(frame),) or not np.isfinite(predicted).all():
        raise ValueError('회귀 모델의 예측 결과 형식이 올바르지 않습니다.')
    return predicted


def style_chart(fig, height=400):
    fig.update_layout(template='plotly_dark', height=height,
                      font=dict(family='Malgun Gothic, Apple SD Gothic Neo, sans-serif', color='#eeeeee'),
                      margin=dict(l=65, r=35, t=35, b=60), paper_bgcolor='#111111',
                      plot_bgcolor='#111111', hovermode='closest', hoverlabel=dict(bgcolor='#202020', bordercolor='#444444', font_color='#eeeeee'))
    fig.update_xaxes(gridcolor='#292929', zerolinecolor='#686868')
    fig.update_yaxes(gridcolor='#292929')
    return fig


def make_report(latest, test, prices, metrics, provenance, go, pio):
    ranking = style_chart(go.Figure(), 480)
    ranking.add_trace(go.Bar(
        x=latest.predicted_return_pct, y=latest.company, orientation='h',
        marker_color=['#69d6a2' if v > 0 else '#f08b93' if v < 0 else '#999999'
                      for v in latest.predicted_return_pct],
        text=[f'{v:+.2f}%' for v in latest.predicted_return_pct], textposition='auto',
        customdata=latest[['close', 'predicted_close']].to_numpy(),
        hovertemplate='%{y}<br>예상 수익률 %{x:+.3f}%<br>현재 %{customdata[0]:,.2f}'
                      '<br>예상 %{customdata[1]:,.2f}<extra></extra>'))
    ranking.update_layout(xaxis_title='다음 1개 시점 예상 수익률 (%)')
    ranking.update_yaxes(autorange='reversed')
    ranking.add_vline(x=0, line_color='#686868', line_width=1)

    companies = latest.to_dict('records')
    top = latest.iloc[0]
    above_zero = int((latest.predicted_return > 0).sum())
    highest = float(top.predicted_return_pct)
    lead = ('다음 시점 예상 수익률 기준' if highest > 0
            else '상승 예측 종목 없음')
    table_rows = []
    for row in companies:
        cls = 'positive' if row['predicted_return'] > 0 else 'negative' if row['predicted_return'] < 0 else ''
        table_rows.append(f"<tr><td>{row['rank']}</td><td><strong>{html.escape(row['company'])}</strong></td>"
                          f"<td>{row['close']:,.2f}</td><td>{row['predicted_close']:,.2f}</td>"
                          f"<td class='{cls}'>{row['predicted_return_pct']:+.3f}%</td></tr>")
    config = dict(responsive=True, displaylogo=False,
                  toImageButtonOptions=dict(format='png', scale=2))
    charts = [pio.to_html(fig, full_html=False, include_plotlyjs=(i == 0),
                          config=config, div_id=f'chart-{i}')
              for i, fig in enumerate([ranking])]
    created = html.escape(provenance['created_at'])
    job = html.escape(provenance['training'])
    scope = f"{int(top.day)} → {int(top.predicted_day)}"
    return f'''<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>KeulKeul AWS Sagemaker AI 활용 주가 분석기</title>
<style>
*{{box-sizing:border-box}}:root{{color-scheme:dark}}body{{margin:0;background:#080808;color:#eeeeee;font-family:"Malgun Gothic","Apple SD Gothic Neo",sans-serif;line-height:1.65}}
main{{max-width:1200px;margin:auto;padding:44px 28px}}header{{padding-bottom:24px;border-bottom:1px solid #292929;margin-bottom:24px}}
h1{{font-size:29px;font-weight:650;letter-spacing:-1px;margin:0 0 12px;line-height:1.5}}h2{{font-size:20px;font-weight:600;margin:0 0 10px}}p{{margin:6px 0 14px}}.muted{{color:#a5a5a5;font-size:13px}}.caption{{color:#858585;font-size:12px;margin:8px 0 0}}
.cards{{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin:24px 0}}.card,section{{background:#111111;border:1px solid #292929;border-radius:8px;padding:24px}}section{{margin:20px 0;overflow:hidden}}.card label{{font-size:12px;color:#a5a5a5}}.card p{{font-size:13px;color:#a5a5a5}}
.value{{font-size:30px;font-weight:650;letter-spacing:-1px;margin:8px 0;font-variant-numeric:tabular-nums}}.positive{{color:#69d6a2}}.negative{{color:#f08b93}}.scroll{{overflow-x:auto}}
table{{width:100%;border-collapse:collapse;font-size:13px;font-variant-numeric:tabular-nums}}th,td{{padding:13px 12px;border-bottom:1px solid #292929;text-align:right;white-space:nowrap}}th{{color:#a5a5a5;font-weight:500}}td:nth-child(2),th:nth-child(2){{text-align:left}}tbody tr:hover{{background:#191919}}
.metrics{{margin:20px 0}}footer{{font-size:12px;color:#858585;padding:12px 0;overflow-wrap:anywhere}}details{{margin-top:10px}}summary{{cursor:pointer}}a{{color:#b5c1ee}}
.js-plotly-plot .plotly .modebar{{background:#111111!important}}.js-plotly-plot .plotly .modebar-btn path{{fill:#999999!important}}.js-plotly-plot .plotly .modebar-btn:hover path{{fill:#eeeeee!important}}
.js-plotly-plot .updatemenu-item-rect{{fill:#202020!important;stroke:#444444!important}}.js-plotly-plot .updatemenu-item-text{{fill:#eeeeee!important}}.js-plotly-plot .updatemenu-item-rect:hover{{fill:#333333!important}}
@media(max-width:700px){{.cards{{grid-template-columns:1fr}}main{{padding:24px 12px}}h1{{font-size:23px}}section{{padding:16px}}}}
</style></head><body><main>
<header><h1>KeulKeul AWS Sagemaker AI 활용 주가 분석기</h1>
<p class="muted">가상 기업 {len(latest)}개 · XGBoost · day {scope}</p>
<p class="caption">가상 데이터의 다음 시점 예상 수익률입니다. 상승 확률을 나타내지는 않습니다.</p></header>
<div class="cards"><div class="card"><label>예상 수익률 1위</label><div class="value">{html.escape(top.company)}</div><p>{lead}</p></div>
<div class="card"><label>1위 예상 수익률</label><div class="value {'positive' if highest > 0 else 'negative' if highest < 0 else ''}">{highest:+.3f}%</div><p class="muted">{top.close:,.2f} → {top.predicted_close:,.2f}</p></div>
<div class="card"><label>상승 예상 종목</label><div class="value">{above_zero} / {len(latest)}</div><p class="muted">예상 수익률 0% 초과</p></div></div>
<section><h2>예상 수익률 순위</h2><p class="muted">다음 시점 예상 수익률 내림차순 · 녹색은 상승, 분홍색은 하락</p>{charts[0]}
<div class="scroll"><table><thead><tr><th>순위</th><th>기업</th><th>현재 가격</th><th>다음 시점 예상 가격</th><th>예상 수익률</th></tr></thead><tbody>{''.join(table_rows)}</tbody></table></div>
<p class="muted">예상 가격 = 현재 가격 × (1 + 예상 수익률) · 동일 수익률은 같은 순위</p></section>
<footer>업데이트 {created}<details><summary>학습 정보</summary><p>{job}<br>XGBoost · 학습 {provenance['boosting_rounds']}회 · 입력 특성 {provenance['feature_count']}개</p></details></footer>
</main></body></html>'''


def main():
    parser = argparse.ArgumentParser(description='SageMaker 학습 모델로 기업별 예상 수익률 HTML 만들기')
    parser.add_argument('--model-file', help='이미 내려받은 model.tar.gz 경로. 지정하면 AWS에 접속하지 않습니다.')
    parser.add_argument('--no-open', action='store_true', help='완료 후 브라우저 자동 열기 생략')
    args = parser.parse_args()
    try:
        import numpy as np
        import pandas as pd
        import xgboost as xgb
        import plotly.graph_objects as go
        import plotly.io as pio
        from local_model import FEATURES, compare
    except ImportError as exc:
        raise RuntimeError('가상환경을 활성화하고 python -m pip install -r requirements.txt를 실행하세요.') from exc

    OUT.mkdir(exist_ok=True)
    archive, training = acquire_model(args.model_file)
    model, checksum = load_booster(archive, xgb)
    if model.num_features() != len(FEATURES):
        raise ValueError('모델의 입력 특성 수와 data/metadata.json이 다릅니다.')
    objective = read_model_objective(model)
    if objective != 'reg:squarederror':
        raise ValueError('이 실습에서 학습한 reg:squarederror 회귀 모델이 필요합니다.')
    latest = pd.read_csv(DATA / 'latest.csv')
    prices = pd.read_csv(DATA / 'prices.csv')
    examples = pd.read_csv(DATA / 'examples.csv')
    test = examples[examples.split == 'test'].copy()
    if len(latest) != 12 or latest.ticker.nunique() != 12 or latest.day.nunique() != 1 or test.empty:
        raise ValueError('제공 데이터의 최신 12개 기업 행과 테스트 구간을 확인하세요.')
    print('다운로드한 학습 모델로 PC에서 예측합니다.')
    latest['predicted_return'] = predict(model, latest, FEATURES, xgb, np)
    latest['predicted_return_pct'] = latest.predicted_return * 100
    latest['predicted_close'] = latest.close * (1 + latest.predicted_return)
    latest['predicted_day'] = latest.day + 1
    latest['rank'] = latest.predicted_return.rank(method='min', ascending=False).astype(int)
    latest = latest.sort_values(['predicted_return', 'ticker'], ascending=[False, True]).reset_index(drop=True)
    test_pred = predict(model, test, FEATURES, xgb, np)
    metrics = compare(test, test_pred)
    test['predicted_return'] = test_pred
    test['predicted_day'] = test.day + 1
    test['predicted_close'] = test.close * (1 + test_pred)
    columns = ['rank', 'ticker', 'company', 'day', 'close', 'predicted_day',
               'predicted_return', 'predicted_return_pct', 'predicted_close']
    latest[columns].to_csv(OUT / 'sagemaker_latest.csv', index=False, encoding='utf-8-sig')
    metrics.to_csv(OUT / 'sagemaker_metrics.csv', index=False, encoding='utf-8-sig')
    test[['ticker', 'company', 'day', 'close', 'predicted_day', 'next_close', 'target_return',
          'predicted_return', 'predicted_close']].to_csv(OUT / 'sagemaker_test_predictions.csv', index=False, encoding='utf-8-sig')
    provenance = dict(training=training, model_sha256=checksum, feature_count=len(FEATURES),
                      boosting_rounds=model.num_boosted_rounds(), objective=objective,
                      created_at=datetime.now().astimezone().isoformat(timespec='seconds'))
    (OUT / 'model-report.json').write_text(json.dumps(provenance, ensure_ascii=False, indent=2), encoding='utf-8')
    report = OUT / 'model_report.html'
    report.write_text(make_report(latest, test, prices, metrics, provenance, go, pio), encoding='utf-8')
    print(latest[['rank', 'company', 'predicted_return_pct', 'predicted_close']].to_string(index=False))
    print(f'시각화 완료: {report}')
    print('예상 상승률이며 상승 확률은 아닙니다. 가상 데이터의 다음 1개 시점 예측입니다.')
    if not args.no_open:
        try:
            webbrowser.open(report.resolve().as_uri())
        except webbrowser.Error:
            print('브라우저가 열리지 않으면 outputs/model_report.html을 직접 여세요.')


def read_model_objective(model):
    return json.loads(model.save_config())['learner']['objective']['name']


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'실행 중단: {exc}', file=sys.stderr)
        sys.exit(1)
