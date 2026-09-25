"""Create a reproducible teaching dataset. No network or AWS calls."""
import csv
import json
import math
import random
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent
COMPANIES = [('YWEL', '영욱전자', 50000), ('YJBK', '유진문고', 18000), ('HDMT', '현도자동차', 70000), ('JHFD', '주현식품', 24000), ('THCT', '태호건설', 32000), ('MHCH', '문호화학', 45000), ('SHEN', '수하에너지', 60000), ('THTC', '태환통신', 38000), ('HRBI', '현려바이오', 55000), ('SYTR', '성윤물산', 28000), ('JCSC', '지찬반도체', 80000), ('HLPM', '혜린제약', 42000)]
# Deliberately constructed classroom scenario, not observed market data.
# Repeated cycles expose the same momentum patterns in every chronological split.
# Values are input-series returns at day 1000, not model outputs or probabilities.
SCENARIO_RETURN = {
    'YWEL': 0.030, 'YJBK': 0.022, 'HDMT': 0.014, 'HRBI': 0.006,
    'JHFD': -0.002, 'THCT': -0.006, 'MHCH': -0.010, 'SHEN': -0.014,
    'THTC': -0.018, 'SYTR': -0.022, 'JCSC': -0.026, 'HLPM': -0.030,
}
SCENARIO_TOP_FOUR = ['YWEL', 'YJBK', 'HDMT', 'HRBI']

FEATURES = ['return_1', 'return_5', 'ma5_gap', 'ma20_gap',
            'volatility_5', 'volume_ratio_5'] + ['company_' + c[0] for c in COMPANIES]

def write_csv(name, rows, columns, header=True):
    with (ROOT / name).open('w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        if header:
            writer.writerow(columns)
        writer.writerows([[r[k] for k in columns] for r in rows])

def main():
    rng = random.Random(110925)
    raw, examples, latest = [], [], []
    for number, (ticker, company, start) in enumerate(COMPANIES):
        prices, volumes, returns = [], [], []
        p = start
        for day in range(1, 1001):
            # Shift each company's cycle so the final observed momentum follows
            # the teaching scenario. Noise stays small relative to the rank gaps.
            phase = math.asin(SCENARIO_RETURN[ticker] / 0.04)
            r = (0.04 * math.sin(2 * math.pi * (day - 1000) / 100 + phase)
                 + rng.gauss(0, 0.0001))
            p = round(p * (1 + r), 2)
            actual = 0.0 if not prices else p / prices[-1] - 1
            v = int((100000 + number * 20000) * (1 + abs(actual) * 12)
                    * rng.uniform(0.75, 1.25))
            prices.append(p); volumes.append(v); returns.append(actual)
            raw.append(dict(ticker=ticker, company=company, day=day, close=p, volume=v))
        for idx in range(20, 1000):
            day = idx + 1
            row = dict(ticker=ticker, company=company, day=day, close=prices[idx],
                       return_1=returns[idx], return_5=prices[idx] / prices[idx-5] - 1,
                       ma5_gap=prices[idx] / statistics.mean(prices[idx-4:idx+1]) - 1,
                       ma20_gap=prices[idx] / statistics.mean(prices[idx-19:idx+1]) - 1,
                       volatility_5=statistics.pstdev(returns[idx-4:idx+1]),
                       volume_ratio_5=volumes[idx] / statistics.mean(volumes[idx-4:idx+1]))
            row.update({'company_' + c[0]: int(ticker == c[0]) for c in COMPANIES})
            if day == 1000:
                latest.append(row)
                continue
            row.update(target_day=day+1, next_close=prices[idx+1],
                       target_return=prices[idx+1] / prices[idx] - 1)
            # Drop boundary rows: their target belongs to the next split.
            if day <= 699: row['split'] = 'train'
            elif 701 <= day <= 849: row['split'] = 'validation'
            elif 851 <= day <= 999: row['split'] = 'test'
            else: continue
            examples.append(row)
    examples.sort(key=lambda x: (x['day'], x['ticker']))
    raw.sort(key=lambda x: (x['day'], x['ticker']))
    write_csv('prices.csv', raw, ['ticker', 'company', 'day', 'close', 'volume'])
    columns = ['ticker', 'company', 'day', 'target_day', 'close', 'next_close', 'split', 'target_return'] + FEATURES
    write_csv('examples.csv', examples, columns)
    for split in ['train', 'validation', 'test']:
        selected = [r for r in examples if r['split'] == split]
        write_csv(split + '.csv', selected, ['target_return'] + FEATURES, header=False)
    write_csv('latest.csv', latest, ['ticker', 'company', 'day', 'close'] + FEATURES)
    metadata = dict(seed=110925, synthetic=True, real_trading_calendar=False,
                    dataset_version='classroom-ranking-v2',
                    scenario='Constructed periodic momentum with small noise; not market observations.',
                    intended_latest_top_four=SCENARIO_TOP_FOUR,
                    scenario_return_at_day_1000=SCENARIO_RETURN,
                    ranking_note='Intended scenario order; actual model ranking requires retraining and evaluation.', 
                    raw_rows=len(raw), feature_order=FEATURES,
                    target='next_close / close - 1', prediction_time='after current close',
                    dropped_boundary_days=[700, 850],
                    counts={s: sum(r['split'] == s for r in examples)
                            for s in ['train', 'validation', 'test']},
                    companies=[dict(ticker=c[0], name=c[1]) for c in COMPANIES])
    (ROOT / 'metadata.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(metadata['counts']))

if __name__ == '__main__':
    main()
