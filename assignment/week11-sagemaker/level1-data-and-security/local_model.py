"""Local baseline/model comparison. This file never calls AWS."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data'
OUT = ROOT / 'outputs'
FEATURES = json.loads((DATA / 'metadata.json').read_text(encoding='utf-8'))['feature_order']

def evaluate(frame, predicted_returns):
    predicted_returns = np.asarray(predicted_returns, dtype=float)
    if len(predicted_returns) != len(frame) or not np.isfinite(predicted_returns).all():
        raise ValueError('Invalid prediction length or values')
    predicted_prices = frame['close'].to_numpy() * (1 + predicted_returns)
    error = predicted_prices - frame['next_close'].to_numpy()
    actual = frame['target_return'].to_numpy()
    # Exact zero is a flat forecast, not an upward/downward forecast.
    direction = float(np.mean(np.sign(predicted_returns) == np.sign(actual)))
    return dict(mae_price=float(np.mean(np.abs(error))),
                rmse_price=float(np.sqrt(np.mean(error**2))),
                rmse_return=float(np.sqrt(np.mean((predicted_returns-actual)**2))),
                direction_accuracy=direction)

def compare(frame, predicted_returns):
    rows = []
    for model, pred in [('no_change', np.zeros(len(frame))), ('model', np.asarray(predicted_returns))]:
        rows.append(dict(scope='ALL', model=model, **evaluate(frame, pred)))
        for ticker in sorted(frame.ticker.unique()):
            mask = (frame.ticker == ticker).to_numpy()
            rows.append(dict(scope=ticker, model=model, **evaluate(frame.loc[mask], pred[mask])))
    return pd.DataFrame(rows)

def main():
    OUT.mkdir(exist_ok=True)
    df = pd.read_csv(DATA / 'examples.csv')
    train, valid, test = [df[df.split == s].copy() for s in ['train', 'validation', 'test']]
    # Fixed parameters; chronological validation is explicit, no random early-stopping split.
    model = HistGradientBoostingRegressor(max_iter=80, max_leaf_nodes=7,
                                         learning_rate=0.05, early_stopping=False, random_state=11)
    model.fit(train[FEATURES], train.target_return)
    print('Validation:', evaluate(valid, model.predict(valid[FEATURES])))
    pred = model.predict(test[FEATURES])
    metrics = compare(test, pred)
    metrics.to_csv(OUT / 'local_metrics.csv', index=False)
    test['predicted_close'] = test.close * (1 + pred)
    test.to_csv(OUT / 'local_predictions.csv', index=False)
    latest = pd.read_csv(DATA / 'latest.csv')
    latest['predicted_day'] = latest.day + 1
    latest['predicted_close'] = latest.close * (1 + model.predict(latest[FEATURES]))
    latest[['ticker', 'company', 'day', 'close', 'predicted_day', 'predicted_close']].to_csv(
        OUT / 'local_latest.csv', index=False, encoding='utf-8-sig')
    print(metrics.to_string(index=False))
    print('Saved outputs/local_metrics.csv, local_predictions.csv, local_latest.csv')

if __name__ == '__main__':
    main()
