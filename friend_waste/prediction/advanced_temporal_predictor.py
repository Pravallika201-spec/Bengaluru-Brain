"""
=========================================================
Urban Predictive Intelligence System
Advanced Temporal Waste Prediction Engine
=========================================================

Enhanced temporal prediction using:
- Prophet for time-series forecasting
- LSTM for sequence learning
- XGBoost for ensemble predictions
- Statistical seasonal decomposition
- Uncertainty quantification

This replaces the basic day-of-week multiplier approach
with sophisticated time-series modeling.
=========================================================
"""

from pathlib import Path
import json
import warnings
warnings.filterwarnings("ignore")

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional

# Try to import geopandas (optional)
try:
    import geopandas as gpd
    GEOPANDAS_AVAILABLE = True
except ImportError:
    GEOPANDAS_AVAILABLE = False
    print("Geopandas not available - will use pandas only")

# ML and Time Series Libraries
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import TimeSeriesSplit, cross_val_score
from sklearn.metrics import mean_absolute_error, mean_squared_error
import joblib

# Try to import dill (optional)
try:
    import dill
    DILL_AVAILABLE = True
except ImportError:
    DILL_AVAILABLE = False
    print("Dill not available - using joblib only")

# Try to import optional ML libraries
try:
    from prophet import Prophet
    PROPHET_AVAILABLE = True
except ImportError:
    PROPHET_AVAILABLE = False
    print("Prophet not available - will use alternative methods")

try:
    import xgboost as xgb
    XGBOOST_AVAILABLE = True
except ImportError:
    XGBOOST_AVAILABLE = False
    print("XGBoost not available - will use scikit-learn only")

try:
    import lightgbm as lgb
    LIGHTGBM_AVAILABLE = True
except ImportError:
    LIGHTGBM_AVAILABLE = False
    print("LightGBM not available - will use scikit-learn only")

try:
    from statsmodels.tsa.seasonal import seasonal_decompose
    from statsmodels.tsa.statespace.sarimax import SARIMAX
    STATSMODELS_AVAILABLE = True
except ImportError:
    STATSMODELS_AVAILABLE = False
    print("Statsmodels not available - SARIMAX disabled")

try:
    import tensorflow as tf
    from tensorflow import keras
    from tensorflow.keras.models import Sequential
    from tensorflow.keras.layers import LSTM, Dense, Dropout, Bidirectional
    from tensorflow.keras.callbacks import EarlyStopping, ModelCheckpoint
    TENSORFLOW_AVAILABLE = True
except ImportError:
    TENSORFLOW_AVAILABLE = False
    print("TensorFlow not available - LSTM models disabled")

# =========================================================
# PATHS
# =========================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

INPUT_FILE = (
    PROJECT_ROOT
    / "waste_module"
    / "data"
    / "processed"
    / "bengaluru_waste_estimates.gpkg"
)

HISTORICAL_DATA_FILE = (
    PROJECT_ROOT
    / "waste_module"
    / "data"
    / "processed"
    / "bengaluru_historical_waste.csv"
)

OUTPUT_DIR = (
    PROJECT_ROOT
    / "waste_module"
    / "data"
    / "processed"
)

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_FILE = (
    OUTPUT_DIR
    / "bengaluru_advanced_temporal_predictions.gpkg"
)

MODEL_DIR = (
    PROJECT_ROOT
    / "waste_module"
    / "models"
)

MODEL_DIR.mkdir(parents=True, exist_ok=True)

# =========================================================
# CONFIGURATION
# =========================================================

FORECAST_HORIZON_DAYS = 30
CONFIDENCE_INTERVAL = 0.95
ENSEMBLE_WEIGHTS = {
    'prophet': 0.3,
    'lstm': 0.3,
    'xgboost': 0.2,
    'sarimax': 0.2
}

LSTM_CONFIG = {
    'sequence_length': 14,
    'hidden_units': 64,
    'dropout_rate': 0.2,
    'epochs': 100,
    'batch_size': 32
}

PROPHET_CONFIG = {
    'yearly_seasonality': True,
    'weekly_seasonality': True,
    'daily_seasonality': False,
    'seasonality_mode': 'multiplicative',
    'changepoint_prior_scale': 0.05,
    'seasonality_prior_scale': 10.0,
    'holidays_prior_scale': 10.0
}

# =========================================================
# SYNTHETIC BASELINE DATA GENERATOR
# =========================================================

def generate_synthetic_baseline_data(num_grids: int = 100) -> pd.DataFrame:
    """Generate synthetic baseline waste data when geopandas is not available."""
    print("Generating synthetic baseline data...")
    
    data = []
    for i in range(num_grids):
        lat = 12.9 + np.random.uniform(-0.1, 0.1)
        lon = 77.5 + np.random.uniform(-0.1, 0.1)
        
        data.append({
            'Grid_ID': f'BG_{i:06d}',
            'Latitude': lat,
            'Longitude': lon,
            'estimated_daily_waste_kg': np.random.uniform(500, 3000)
        })
    
    return pd.DataFrame(data)

# =========================================================
# SYNTHETIC HISTORICAL DATA GENERATOR
# =========================================================

def generate_synthetic_historical_data(
    baseline_data: gpd.GeoDataFrame,
    start_date: str = "2023-01-01",
    end_date: str = "2024-08-01"
) -> pd.DataFrame:
    """
    Generate synthetic historical waste data for model training.
    In production, this would be replaced with actual historical data.
    """
    print("Generating synthetic historical data for training...")
    
    date_range = pd.date_range(start=start_date, end=end_date, freq='D')
    
    historical_data = []
    
    for grid_idx, grid_row in baseline_data.iterrows():
        grid_id = grid_row['Grid_ID']
        baseline_waste = grid_row['estimated_daily_waste_kg']
        latitude = grid_row['Latitude']
        longitude = grid_row['Longitude']
        
        # Add realistic temporal patterns
        for date in date_range:
            # Day of week effect
            dow_factor = {
                0: 1.0,   # Monday
                1: 1.0,   # Tuesday
                2: 1.02,  # Wednesday
                3: 1.03,  # Thursday
                4: 1.08,  # Friday
                5: 1.15,  # Saturday
                6: 1.10   # Sunday
            }.get(date.dayofweek, 1.0)
            
            # Seasonal effect (stronger in summer)
            month_factor = 1.0 + 0.1 * np.sin(2 * np.pi * date.month / 12)
            
            # Random variation
            random_factor = np.random.normal(1.0, 0.15)
            
            # Special events (occasional spikes)
            event_factor = 1.0
            if np.random.random() < 0.05:  # 5% chance of event
                event_factor = np.random.uniform(1.2, 1.8)
            
            daily_waste = (
                baseline_waste * 
                dow_factor * 
                month_factor * 
                random_factor * 
                event_factor
            )
            
            historical_data.append({
                'Grid_ID': grid_id,
                'date': date,
                'daily_waste_kg': max(daily_waste, baseline_waste * 0.5),
                'Latitude': latitude,
                'Longitude': longitude,
                'day_of_week': date.dayofweek,
                'month': date.month,
                'is_weekend': int(date.dayofweek >= 5),
                'event_indicator': int(event_factor > 1.0)
            })
    
    df = pd.DataFrame(historical_data)
    
    # Save synthetic data
    df.to_csv(HISTORICAL_DATA_FILE, index=False)
    print(f"Generated {len(df)} historical records")
    print(f"Saved to: {HISTORICAL_DATA_FILE}")
    
    return df

# =========================================================
# FEATURE ENGINEERING
# =========================================================

def create_temporal_features(df: pd.DataFrame) -> pd.DataFrame:
    """Create advanced temporal features for ML models."""
    df = df.copy()
    df['date'] = pd.to_datetime(df['date'])
    
    # Basic temporal features
    df['day_of_week'] = df['date'].dt.dayofweek
    df['day_of_month'] = df['date'].dt.day
    df['month'] = df['date'].dt.month
    df['quarter'] = df['date'].dt.quarter
    df['year'] = df['date'].dt.year
    df['is_weekend'] = (df['day_of_week'] >= 5).astype(int)
    df['is_month_start'] = df['date'].dt.is_month_start.astype(int)
    df['is_month_end'] = df['date'].dt.is_month_end.astype(int)
    
    # Seasonal features
    df['day_of_year'] = df['date'].dt.dayofyear
    df['week_of_year'] = df['date'].dt.isocalendar().week.astype(int)
    
    # Cyclical encoding for periodic features
    df['day_of_week_sin'] = np.sin(2 * np.pi * df['day_of_week'] / 7)
    df['day_of_week_cos'] = np.cos(2 * np.pi * df['day_of_week'] / 7)
    df['month_sin'] = np.sin(2 * np.pi * df['month'] / 12)
    df['month_cos'] = np.cos(2 * np.pi * df['month'] / 12)
    df['day_of_year_sin'] = np.sin(2 * np.pi * df['day_of_year'] / 365)
    df['day_of_year_cos'] = np.cos(2 * np.pi * df['day_of_year'] / 365)
    
    # Lag features
    df = df.sort_values(['Grid_ID', 'date'])
    for lag in [1, 7, 14, 30]:
        df[f'waste_lag_{lag}'] = df.groupby('Grid_ID')['daily_waste_kg'].shift(lag)
    
    # Rolling statistics
    for window in [7, 14, 30]:
        df[f'waste_rolling_mean_{window}'] = (
            df.groupby('Grid_ID')['daily_waste_kg']
            .transform(lambda x: x.rolling(window=window, min_periods=1).mean())
        )
        df[f'waste_rolling_std_{window}'] = (
            df.groupby('Grid_ID')['daily_waste_kg']
            .transform(lambda x: x.rolling(window=window, min_periods=1).std())
        )
    
    return df

# =========================================================
# PROPHET MODEL
# =========================================================

class ProphetPredictor:
    """Prophet time-series predictor for each grid."""
    
    def __init__(self, config: Dict = None):
        self.config = config or PROPHET_CONFIG
        self.models = {}
        self.predictions = {}
        self.available = PROPHET_AVAILABLE
    
    def train_grid_model(self, grid_data: pd.DataFrame, grid_id: str):
        """Train Prophet model for a specific grid."""
        if not self.available:
            return None
            
        # Prepare data for Prophet
        prophet_data = grid_data[['date', 'daily_waste_kg']].copy()
        prophet_data.columns = ['ds', 'y']
        
        # Create and fit model
        model = Prophet(**self.config)
        
        # Add custom seasonality if needed
        model.add_seasonality(name='monthly', period=30.5, fourier_order=5)
        
        model.fit(prophet_data)
        
        return model
    
    def predict_grid(self, model: Prophet, forecast_days: int = FORECAST_HORIZON_DAYS) -> pd.DataFrame:
        """Generate predictions for a grid."""
        future = model.make_future_dataframe(periods=forecast_days)
        forecast = model.predict(future)
        
        # Extract prediction intervals
        result = forecast[['ds', 'yhat', 'yhat_lower', 'yhat_upper']].tail(forecast_days)
        result.columns = ['date', 'predicted_waste', 'lower_bound', 'upper_bound']
        
        return result
    
    def train_all_grids(self, historical_data: pd.DataFrame) -> None:
        """Train Prophet models for all grids."""
        print("Training Prophet models for all grids...")
        
        grid_ids = historical_data['Grid_ID'].unique()
        total_grids = len(grid_ids)
        
        for idx, grid_id in enumerate(grid_ids):
            if idx % 100 == 0:
                print(f"Progress: {idx}/{total_grids} grids")
            
            grid_data = historical_data[historical_data['Grid_ID'] == grid_id].copy()
            
            if len(grid_data) < 30:  # Need minimum data
                continue
            
            try:
                model = self.train_grid_model(grid_data, grid_id)
                self.models[grid_id] = model
            except Exception as e:
                print(f"Error training Prophet for grid {grid_id}: {e}")
                continue
        
        print(f"Trained {len(self.models)} Prophet models")
    
    def predict_all_grids(self) -> Dict[str, pd.DataFrame]:
        """Generate predictions for all grids."""
        print("Generating Prophet predictions...")
        
        for grid_id, model in self.models.items():
            try:
                prediction = self.predict_grid(model)
                prediction['Grid_ID'] = grid_id
                self.predictions[grid_id] = prediction
            except Exception as e:
                print(f"Error predicting for grid {grid_id}: {e}")
                continue
        
        return self.predictions

# =========================================================
# LSTM MODEL
# =========================================================

class LSTMPredictor:
    """LSTM-based sequence predictor for temporal patterns."""
    
    def __init__(self, config: Dict = None):
        self.config = config or LSTM_CONFIG
        self.models = {}
        self.scalers = {}
        self.sequence_length = self.config['sequence_length']
        self.available = TENSORFLOW_AVAILABLE
    
    def prepare_sequences(self, data: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """Prepare sequences for LSTM training."""
        X, y = [], []
        
        for i in range(len(data) - self.sequence_length):
            X.append(data[i:i + self.sequence_length])
            y.append(data[i + self.sequence_length])
        
        return np.array(X), np.array(y)
    
    def create_lstm_model(self, input_shape: Tuple) -> Sequential:
        """Create LSTM model architecture."""
        model = Sequential([
            Bidirectional(LSTM(self.config['hidden_units'], 
                              return_sequences=True,
                              input_shape=input_shape)),
            Dropout(self.config['dropout_rate']),
            Bidirectional(LSTM(self.config['hidden_units'])),
            Dropout(self.config['dropout_rate']),
            Dense(32, activation='relu'),
            Dense(1)
        ])
        
        model.compile(optimizer='adam', loss='mse', metrics=['mae'])
        return model
    
    def train_grid_model(self, grid_data: pd.DataFrame, grid_id: str) -> Tuple[Sequential, StandardScaler]:
        """Train LSTM model for a specific grid."""
        # Scale data
        scaler = StandardScaler()
        waste_values = scaler.fit_transform(grid_data['daily_waste_kg'].values.reshape(-1, 1))
        
        # Prepare sequences
        if len(waste_values) < self.sequence_length + 1:
            return None, None
        
        X, y = self.prepare_sequences(waste_values)
        
        if len(X) < 10:  # Need minimum sequences
            return None, None
        
        # Create model
        model = self.create_lstm_model((self.sequence_length, 1))
        
        # Callbacks
        early_stopping = EarlyStopping(patience=10, restore_best_weights=True)
        
        # Train
        history = model.fit(
            X, y,
            epochs=self.config['epochs'],
            batch_size=self.config['batch_size'],
            validation_split=0.2,
            callbacks=[early_stopping],
            verbose=0
        )
        
        return model, scaler
    
    def predict_grid(self, model: Sequential, scaler: StandardScaler, 
                    last_sequence: np.ndarray, forecast_days: int) -> np.ndarray:
        """Generate predictions using LSTM."""
        predictions = []
        current_sequence = last_sequence.copy()
        
        for _ in range(forecast_days):
            # Predict next value
            next_pred = model.predict(current_sequence.reshape(1, self.sequence_length, 1), verbose=0)
            predictions.append(next_pred[0, 0])
            
            # Update sequence
            current_sequence = np.roll(current_sequence, -1)
            current_sequence[-1] = next_pred[0, 0]
        
        # Inverse transform
        predictions = scaler.inverse_transform(np.array(predictions).reshape(-1, 1))
        return predictions.flatten()
    
    def train_all_grids(self, historical_data: pd.DataFrame) -> None:
        """Train LSTM models for all grids."""
        print("Training LSTM models for all grids...")
        
        grid_ids = historical_data['Grid_ID'].unique()
        total_grids = len(grid_ids)
        
        for idx, grid_id in enumerate(grid_ids):
            if idx % 100 == 0:
                print(f"Progress: {idx}/{total_grids} grids")
            
            grid_data = historical_data[historical_data['Grid_ID'] == grid_id].copy()
            grid_data = grid_data.sort_values('date')
            
            if len(grid_data) < self.sequence_length + 10:
                continue
            
            try:
                model, scaler = self.train_grid_model(grid_data, grid_id)
                if model is not None:
                    self.models[grid_id] = model
                    self.scalers[grid_id] = scaler
            except Exception as e:
                print(f"Error training LSTM for grid {grid_id}: {e}")
                continue
        
        print(f"Trained {len(self.models)} LSTM models")
    
    def predict_all_grids(self, historical_data: pd.DataFrame) -> Dict[str, np.ndarray]:
        """Generate predictions for all grids."""
        print("Generating LSTM predictions...")
        
        predictions = {}
        
        for grid_id, model in self.models.items():
            try:
                grid_data = historical_data[historical_data['Grid_ID'] == grid_id].copy()
                grid_data = grid_data.sort_values('date')
                
                scaler = self.scalers[grid_id]
                last_sequence = scaler.transform(
                    grid_data['daily_waste_kg'].tail(self.sequence_length).values.reshape(-1, 1)
                ).flatten()
                
                grid_predictions = self.predict_grid(model, scaler, last_sequence, FORECAST_HORIZON_DAYS)
                predictions[grid_id] = grid_predictions
                
            except Exception as e:
                print(f"Error predicting LSTM for grid {grid_id}: {e}")
                continue
        
        return predictions

# =========================================================
# XGBOOST PREDICTOR
# =========================================================

class XGBoostPredictor:
    """XGBoost-based predictor with temporal features."""
    
    def __init__(self):
        self.models = {}
        self.feature_importance = {}
    
    def train_grid_model(self, grid_data: pd.DataFrame, grid_id: str) -> xgb.XGBRegressor:
        """Train XGBoost model for a specific grid."""
        # Create features
        grid_data = create_temporal_features(grid_data)
        
        # Remove rows with NaN (from lag features)
        grid_data = grid_data.dropna()
        
        if len(grid_data) < 30:
            return None
        
        # Feature columns
        feature_cols = [col for col in grid_data.columns 
                       if col not in ['Grid_ID', 'date', 'daily_waste_kg']]
        
        X = grid_data[feature_cols]
        y = grid_data['daily_waste_kg']
        
        # Train model
        model = xgb.XGBRegressor(
            n_estimators=200,
            max_depth=6,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42
        )
        
        model.fit(X, y)
        
        return model
    
    def predict_grid(self, model: xgb.XGBRegressor, last_features: pd.DataFrame) -> np.ndarray:
        """Generate predictions using XGBoost."""
        predictions = []
        
        for day_ahead in range(1, FORECAST_HORIZON_DAYS + 1):
            future_date = pd.Timestamp.now() + timedelta(days=day_ahead)
            
            # Create future features
            future_features = last_features.copy()
            future_features['date'] = future_date
            future_features = create_temporal_features(future_features)
            
            # Select feature columns
            feature_cols = [col for col in future_features.columns 
                           if col not in ['Grid_ID', 'date', 'daily_waste_kg']]
            
            X_future = future_features[feature_cols].iloc[[-1]]
            prediction = model.predict(X_future)[0]
            predictions.append(prediction)
        
        return np.array(predictions)
    
    def train_all_grids(self, historical_data: pd.DataFrame) -> None:
        """Train XGBoost models for all grids."""
        print("Training XGBoost models for all grids...")
        
        grid_ids = historical_data['Grid_ID'].unique()
        total_grids = len(grid_ids)
        
        for idx, grid_id in enumerate(grid_ids):
            if idx % 100 == 0:
                print(f"Progress: {idx}/{total_grids} grids")
            
            grid_data = historical_data[historical_data['Grid_ID'] == grid_id].copy()
            
            try:
                model = self.train_grid_model(grid_data, grid_id)
                if model is not None:
                    self.models[grid_id] = model
            except Exception as e:
                print(f"Error training XGBoost for grid {grid_id}: {e}")
                continue
        
        print(f"Trained {len(self.models)} XGBoost models")
    
    def predict_all_grids(self, historical_data: pd.DataFrame) -> Dict[str, np.ndarray]:
        """Generate predictions for all grids."""
        print("Generating XGBoost predictions...")
        
        predictions = {}
        
        for grid_id, model in self.models.items():
            try:
                grid_data = historical_data[historical_data['Grid_ID'] == grid_id].copy()
                grid_data = grid_data.sort_values('date').tail(30)
                grid_data = create_temporal_features(grid_data)
                
                grid_predictions = self.predict_grid(model, grid_data)
                predictions[grid_id] = grid_predictions
                
            except Exception as e:
                print(f"Error predicting XGBoost for grid {grid_id}: {e}")
                continue
        
        return predictions

# =========================================================
# ENSEMBLE PREDICTOR
# =========================================================

class EnsemblePredictor:
    """Ensemble predictor combining multiple models."""
    
    def __init__(self, weights: Dict[str, float] = None):
        self.weights = weights or ENSEMBLE_WEIGHTS
        self.prophet_predictor = ProphetPredictor()
        self.lstm_predictor = LSTMPredictor()
        self.xgboost_predictor = XGBoostPredictor()
    
    def train_all_models(self, historical_data: pd.DataFrame) -> None:
        """Train all ensemble models."""
        print("=" * 70)
        print("TRAINING ENSEMBLE MODELS")
        print("=" * 70)
        
        # Train Prophet
        self.prophet_predictor.train_all_grids(historical_data)
        
        # Train LSTM
        self.lstm_predictor.train_all_grids(historical_data)
        
        # Train XGBoost
        self.xgboost_predictor.train_all_grids(historical_data)
    
    def generate_ensemble_predictions(self, historical_data: pd.DataFrame) -> pd.DataFrame:
        """Generate ensemble predictions with uncertainty."""
        print("=" * 70)
        print("GENERATING ENSEMBLE PREDICTIONS")
        print("=" * 70)
        
        # Get predictions from all models
        prophet_preds = self.prophet_predictor.predict_all_grids()
        lstm_preds = self.lstm_predictor.predict_all_grids(historical_data)
        xgb_preds = self.xgboost_predictor.predict_all_grids(historical_data)
        
        # Combine predictions
        ensemble_predictions = []
        
        # Get all grid IDs from baseline data
        baseline_data = gpd.read_file(INPUT_FILE, layer="waste_estimates")
        all_grid_ids = baseline_data['Grid_ID'].unique()
        
        for grid_id in all_grid_ids:
            grid_info = baseline_data[baseline_data['Grid_ID'] == grid_id].iloc[0]
            
            for day_ahead in range(FORECAST_HORIZON_DAYS):
                forecast_date = pd.Timestamp.now() + timedelta(days=day_ahead)
                
                # Collect predictions from available models
                predictions = []
                model_names = []
                
                if grid_id in prophet_preds and day_ahead < len(prophet_preds[grid_id]):
                    prophet_pred = prophet_preds[grid_id].iloc[day_ahead]
                    predictions.append(prophet_pred['predicted_waste'])
                    model_names.append('prophet')
                
                if grid_id in lstm_preds and day_ahead < len(lstm_preds[grid_id]):
                    lstm_pred = lstm_preds[grid_id][day_ahead]
                    predictions.append(lstm_pred)
                    model_names.append('lstm')
                
                if grid_id in xgb_preds and day_ahead < len(xgb_preds[grid_id]):
                    xgb_pred = xgb_preds[grid_id][day_ahead]
                    predictions.append(xgb_pred)
                    model_names.append('xgboost')
                
                if predictions:
                    # Weighted ensemble
                    weights = [self.weights.get(name, 0) for name in model_names]
                    total_weight = sum(weights)
                    
                    if total_weight > 0:
                        normalized_weights = [w / total_weight for w in weights]
                        ensemble_pred = sum(p * w for p, w in zip(predictions, normalized_weights))
                    else:
                        ensemble_pred = np.mean(predictions)
                    
                    # Calculate uncertainty (standard deviation of predictions)
                    uncertainty = np.std(predictions) if len(predictions) > 1 else 0
                    
                    ensemble_predictions.append({
                        'Grid_ID': grid_id,
                        'Latitude': grid_info['Latitude'],
                        'Longitude': grid_info['Longitude'],
                        'forecast_date': forecast_date,
                        'forecast_day': day_ahead + 1,
                        'ensemble_prediction': ensemble_pred,
                        'prediction_lower': ensemble_pred - 1.96 * uncertainty,
                        'prediction_upper': ensemble_pred + 1.96 * uncertainty,
                        'uncertainty': uncertainty,
                        'models_used': ','.join(model_names),
                        'confidence_score': len(predictions) / 3.0  # More models = higher confidence
                    })
                else:
                    # Fallback to baseline
                    ensemble_predictions.append({
                        'Grid_ID': grid_id,
                        'Latitude': grid_info['Latitude'],
                        'Longitude': grid_info['Longitude'],
                        'forecast_date': forecast_date,
                        'forecast_day': day_ahead + 1,
                        'ensemble_prediction': grid_info['estimated_daily_waste_kg'],
                        'prediction_lower': grid_info['estimated_daily_waste_kg'] * 0.8,
                        'prediction_upper': grid_info['estimated_daily_waste_kg'] * 1.2,
                        'uncertainty': grid_info['estimated_daily_waste_kg'] * 0.2,
                        'models_used': 'baseline',
                        'confidence_score': 0.3
                    })
        
        return pd.DataFrame(ensemble_predictions)

# =========================================================
# MAIN EXECUTION
# =========================================================

def main():
    print("=" * 70)
    print("ADVANCED TEMPORAL WASTE PREDICTION ENGINE")
    print("=" * 70)
    
    # Load baseline data
    print("\nLoading baseline waste estimates...")
    if GEOPANDAS_AVAILABLE:
        baseline_data = gpd.read_file(INPUT_FILE, layer="waste_estimates")
    else:
        # Try to load as CSV if geopandas not available
        csv_file = INPUT_FILE.parent / INPUT_FILE.stem.replace('.gpkg', '') / 'waste_estimates.csv'
        if csv_file.exists():
            baseline_data = pd.read_csv(csv_file)
        else:
            print("No baseline data available - generating synthetic data")
            baseline_data = generate_synthetic_baseline_data()
    print(f"Loaded {len(baseline_data)} grid cells")
    
    # Generate or load historical data
    if HISTORICAL_DATA_FILE.exists():
        print(f"\nLoading existing historical data from {HISTORICAL_DATA_FILE}")
        historical_data = pd.read_csv(HISTORICAL_DATA_FILE)
    else:
        print("\nGenerating synthetic historical data...")
        historical_data = generate_synthetic_historical_data(baseline_data)
    
    print(f"Historical data: {len(historical_data)} records")
    print(f"Date range: {historical_data['date'].min()} to {historical_data['date'].max()}")
    
    # Initialize ensemble predictor
    ensemble = EnsemblePredictor()
    
    # Train all models
    ensemble.train_all_models(historical_data)
    
    # Generate ensemble predictions
    predictions_df = ensemble.generate_ensemble_predictions(historical_data)
    
    print(f"\nGenerated {len(predictions_df)} forecast records")
    print(f"Forecast horizon: {FORECAST_HORIZON_DAYS} days")
    
    # Calculate advanced risk classifications
    print("\nCalculating advanced risk classifications...")
    
    # Risk based on prediction percentiles with uncertainty consideration
    predictions_df['risk_percentile'] = predictions_df.groupby('forecast_day')['ensemble_prediction'].transform(
        lambda x: x.rank(pct=True) * 100
    )
    
    def advanced_risk_classification(row):
        uncertainty_factor = min(row['uncertainty'] / (row['ensemble_prediction'] + 1e-6), 0.5)
        adjusted_percentile = row['risk_percentile'] * (1 + uncertainty_factor)
        
        if adjusted_percentile >= 90:
            return "CRITICAL"
        elif adjusted_percentile >= 75:
            return "HIGH"
        elif adjusted_percentile >= 50:
            return "MEDIUM"
        else:
            return "LOW"
    
    predictions_df['advanced_risk'] = predictions_df.apply(advanced_risk_classification, axis=1)
    
    # Collection priority based on risk and confidence
    def advanced_priority(row):
        risk_priority = {'CRITICAL': 1, 'HIGH': 2, 'MEDIUM': 3, 'LOW': 4}
        base_priority = risk_priority.get(row['advanced_risk'], 4)
        
        # Adjust based on confidence
        if row['confidence_score'] < 0.5:
            base_priority = min(base_priority + 1, 4)
        
        return base_priority
    
    predictions_df['collection_priority'] = predictions_df.apply(advanced_priority, axis=1)
    
    # Save predictions
    print("\nSaving advanced temporal predictions...")
    
    # Convert to GeoDataFrame for spatial output
    geometry_gdf = baseline_data[['Grid_ID', 'geometry']].copy()
    predictions_gdf = predictions_df.merge(geometry_gdf, on='Grid_ID', how='left')
    predictions_gdf = gpd.GeoDataFrame(predictions_gdf, geometry='geometry', crs=baseline_data.crs)
    
    predictions_gdf.to_file(OUTPUT_FILE, layer="advanced_temporal_predictions", driver="GPKG")
    print(f"Saved to: {OUTPUT_FILE}")
    
    # Save models
    print("\nSaving trained models...")
    joblib.dump(ensemble.prophet_predictor.models, MODEL_DIR / "prophet_models.joblib")
    joblib.dump(ensemble.lstm_predictor.models, MODEL_DIR / "lstm_models.joblib")
    joblib.dump(ensemble.xgboost_predictor.models, MODEL_DIR / "xgboost_models.joblib")
    
    # Print summary
    print("\n" + "=" * 70)
    print("ADVANCED TEMPORAL PREDICTION SUMMARY")
    print("=" * 70)
    
    print(f"\nTotal forecast records: {len(predictions_df)}")
    print(f"Forecast days: {FORECAST_HORIZON_DAYS}")
    print(f"Grid cells: {predictions_df['Grid_ID'].nunique()}")
    
    print("\nRisk distribution:")
    print(predictions_df['advanced_risk'].value_counts())
    
    print("\nCollection priority distribution:")
    print(predictions_df['collection_priority'].value_counts().sort_index())
    
    print("\nConfidence score distribution:")
    print(predictions_df['confidence_score'].describe())
    
    print("\nUncertainty statistics:")
    print(predictions_df['uncertainty'].describe())
    
    print("\nAverage predictions by forecast day:")
    daily_summary = predictions_df.groupby('forecast_day')['ensemble_prediction'].agg(['mean', 'std', 'min', 'max'])
    print(daily_summary)
    
    print("\n" + "=" * 70)
    print("ADVANCED TEMPORAL PREDICTION COMPLETED")
    print("=" * 70)

if __name__ == "__main__":
    main()