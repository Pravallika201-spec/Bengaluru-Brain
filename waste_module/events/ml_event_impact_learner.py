"""
=========================================================
Urban Predictive Intelligence System
ML-based Event Impact Learning Module
=========================================================

Machine learning approach to learn event impacts on waste generation:
- Historical event-waste correlation analysis
- Feature engineering for event characteristics
- ML model training for impact prediction
- Dynamic impact factor calculation
- Event type clustering and similarity analysis
- Transfer learning for new event types
- Continuous learning from new data

Replaces the rule-based event impact system with data-driven learning.
=========================================================
"""

import os
import json
import warnings
warnings.filterwarnings("ignore")

from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
import numpy as np
import pandas as pd
import geopandas as gpd

# ML Libraries
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.model_selection import train_test_split, cross_val_score, GridSearchCV
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.feature_extraction.text import TfidfVectorizer
import xgboost as xgb
import lightgbm as lgb
import joblib

# Text processing
from textblob import TextBlob
import re

# =========================================================
# CONFIGURATION
# =========================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "waste_module" / "data" / "processed"
MODEL_DIR = PROJECT_ROOT / "waste_module" / "models"
MODEL_DIR.mkdir(parents=True, exist_ok=True)

# Historical data files
HISTORICAL_EVENTS_FILE = DATA_DIR / "historical_event_waste_data.csv"
SOCIAL_EVENTS_FILE = DATA_DIR / "social_media_events.csv"
WASTE_PREDICTIONS_FILE = DATA_DIR / "bengaluru_advanced_temporal_predictions.gpkg"

# Model configuration
ML_CONFIG = {
    'random_forest': {
        'n_estimators': 200,
        'max_depth': 10,
        'min_samples_split': 5,
        'min_samples_leaf': 2,
        'random_state': 42
    },
    'xgboost': {
        'n_estimators': 200,
        'max_depth': 6,
        'learning_rate': 0.05,
        'subsample': 0.8,
        'colsample_bytree': 0.8,
        'random_state': 42
    },
    'lightgbm': {
        'n_estimators': 200,
        'max_depth': 6,
        'learning_rate': 0.05,
        'subsample': 0.8,
        'colsample_bytree': 0.8,
        'random_state': 42
    }
}

# =========================================================
# SYNTHETIC HISTORICAL EVENT-WASTE DATA GENERATOR
# =========================================================

def generate_synthetic_event_waste_data(num_samples: int = 1000) -> pd.DataFrame:
    """
    Generate synthetic historical data for event-waste impact learning.
    In production, this would be replaced with actual historical data.
    """
    print("Generating synthetic historical event-waste data...")
    
    # Event types and their base characteristics
    event_types = [
        'festival', 'concert', 'sports', 'conference', 'market',
        'religious', 'protest', 'political', 'cultural', 'exhibition'
    ]
    
    data = []
    
    for i in range(num_samples):
        # Random event characteristics
        event_type = np.random.choice(event_types)
        duration_days = np.random.randint(1, 8)
        expected_attendance = np.random.randint(100, 50000)
        intensity = np.random.randint(1, 4)
        
        # Location characteristics
        area_type = np.random.choice(['residential', 'commercial', 'mixed', 'industrial'])
        population_density = np.random.randint(1000, 20000)
        
        # Temporal characteristics
        day_of_week = np.random.randint(0, 7)
        is_weekend = day_of_week >= 5
        month = np.random.randint(1, 13)
        is_holiday_season = month in [11, 12, 1]  # Nov, Dec, Jan
        
        # Baseline waste for the area (kg)
        baseline_waste = np.random.uniform(500, 5000)
        
        # Generate actual waste with event impact
        # Base impact factors by event type
        type_impact = {
            'festival': 2.5, 'concert': 1.8, 'sports': 1.6, 'conference': 1.3,
            'market': 1.4, 'religious': 2.0, 'protest': 1.2, 'political': 1.1,
            'cultural': 1.5, 'exhibition': 1.3
        }
        
        base_impact = type_impact.get(event_type, 1.3)
        
        # Attendance impact (logarithmic scaling)
        attendance_factor = 1 + np.log10(expected_attendance / 1000 + 1) * 0.3
        
        # Duration impact
        duration_factor = 1 + (duration_days - 1) * 0.1
        
        # Intensity impact
        intensity_factor = 1 + (intensity - 1) * 0.2
        
        # Temporal factors
        weekend_factor = 1.15 if is_weekend else 1.0
        holiday_factor = 1.2 if is_holiday_season else 1.0
        
        # Combined impact
        total_impact = (
            base_impact * 
            attendance_factor * 
            duration_factor * 
            intensity_factor * 
            weekend_factor * 
            holiday_factor
        )
        
        # Add some randomness
        total_impact *= np.random.uniform(0.8, 1.2)
        
        # Calculate actual waste
        actual_waste = baseline_waste * total_impact
        
        # Calculate waste increase
        waste_increase = actual_waste - baseline_waste
        waste_increase_percentage = (waste_increase / baseline_waste) * 100
        
        data.append({
            'event_id': f"EVT_{i:06d}",
            'event_type': event_type,
            'duration_days': duration_days,
            'expected_attendance': expected_attendance,
            'intensity': intensity,
            'area_type': area_type,
            'population_density': population_density,
            'day_of_week': day_of_week,
            'is_weekend': int(is_weekend),
            'month': month,
            'is_holiday_season': int(is_holiday_season),
            'baseline_waste_kg': baseline_waste,
            'actual_waste_kg': actual_waste,
            'waste_increase_kg': waste_increase,
            'waste_increase_percentage': waste_increase_percentage,
            'event_date': datetime.now() - timedelta(days=np.random.randint(0, 365))
        })
    
    df = pd.DataFrame(data)
    
    # Save synthetic data
    df.to_csv(HISTORICAL_EVENTS_FILE, index=False)
    print(f"Generated {len(df)} historical event-waste records")
    print(f"Saved to: {HISTORICAL_EVENTS_FILE}")
    
    return df

# =========================================================
# FEATURE ENGINEERING
# =========================================================

class EventFeatureEngineer:
    """Engineer features for event impact prediction."""
    
    def __init__(self):
        self.label_encoders = {}
        self.scalers = {}
        self.text_vectorizer = None
    
    def create_basic_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Create basic numerical features from event data."""
        features = df.copy()
        
        # Log transformations for skewed variables
        features['log_attendance'] = np.log1p(features['expected_attendance'])
        features['log_baseline_waste'] = np.log1p(features['baseline_waste_kg'])
        
        # Interaction features
        features['attendance_intensity'] = features['expected_attendance'] * features['intensity']
        features['duration_intensity'] = features['duration_days'] * features['intensity']
        
        # Area-type specific features
        features['residential_flag'] = (features['area_type'] == 'residential').astype(int)
        features['commercial_flag'] = (features['area_type'] == 'commercial').astype(int)
        features['mixed_flag'] = (features['area_type'] == 'mixed').astype(int)
        features['industrial_flag'] = (features['area_type'] == 'industrial').astype(int)
        
        # Temporal features
        features['weekend_event'] = features['is_weekend'].astype(int)
        features['holiday_event'] = features['is_holiday_season'].astype(int)
        
        # Cyclical encoding for temporal features
        features['day_of_week_sin'] = np.sin(2 * np.pi * features['day_of_week'] / 7)
        features['day_of_week_cos'] = np.cos(2 * np.pi * features['day_of_week'] / 7)
        features['month_sin'] = np.sin(2 * np.pi * features['month'] / 12)
        features['month_cos'] = np.cos(2 * np.pi * features['month'] / 12)
        
        return features
    
    def encode_categorical_features(self, df: pd.DataFrame, fit: bool = True) -> pd.DataFrame:
        """Encode categorical features."""
        categorical_cols = ['event_type', 'area_type']
        
        for col in categorical_cols:
            if col not in df.columns:
                continue
            
            if fit:
                if col not in self.label_encoders:
                    self.label_encoders[col] = LabelEncoder()
                    df[f'{col}_encoded'] = self.label_encoders[col].fit_transform(df[col].astype(str))
                else:
                    df[f'{col}_encoded'] = self.label_encoders[col].transform(df[col].astype(str))
            else:
                if col in self.label_encoders:
                    # Handle unseen categories
                    df[f'{col}_encoded'] = df[col].astype(str).apply(
                        lambda x: self.label_encoders[col].transform([x])[0] 
                        if x in self.label_encoders[col].classes_ else -1
                    )
        
        return df
    
    def scale_numerical_features(self, df: pd.DataFrame, fit: bool = True) -> pd.DataFrame:
        """Scale numerical features."""
        numerical_cols = [
            'duration_days', 'expected_attendance', 'intensity',
            'population_density', 'baseline_waste_kg',
            'log_attendance', 'log_baseline_waste',
            'attendance_intensity', 'duration_intensity'
        ]
        
        available_cols = [col for col in numerical_cols if col in df.columns]
        
        for col in available_cols:
            if fit:
                if col not in self.scalers:
                    self.scalers[col] = StandardScaler()
                    df[f'{col}_scaled'] = self.scalers[col].fit_transform(df[[col]]).flatten()
                else:
                    df[f'{col}_scaled'] = self.scalers[col].transform(df[[col]]).flatten()
            else:
                if col in self.scalers:
                    df[f'{col}_scaled'] = self.scalers[col].transform(df[[col]]).flatten()
        
        return df
    
    def create_text_features(self, df: pd.DataFrame, text_col: str = 'event_description', fit: bool = True) -> pd.DataFrame:
        """Create text features from event descriptions."""
        if text_col not in df.columns:
            return df
        
        if fit:
            if self.text_vectorizer is None:
                self.text_vectorizer = TfidfVectorizer(max_features=50, stop_words='english')
                text_features = self.text_vectorizer.fit_transform(df[text_col].fillna(''))
                
                # Add TF-IDF features as columns
                feature_names = [f'text_{i}' for i in range(text_features.shape[1])]
                for i, name in enumerate(feature_names):
                    df[name] = text_features[:, i].toarray().flatten()
            else:
                text_features = self.text_vectorizer.transform(df[text_col].fillna(''))
                feature_names = [f'text_{i}' for i in range(text_features.shape[1])]
                for i, name in enumerate(feature_names):
                    df[name] = text_features[:, i].toarray().flatten()
        
        return df
    
    def extract_sentiment_features(self, df: pd.DataFrame, text_col: str = 'event_description') -> pd.DataFrame:
        """Extract sentiment features from text."""
        if text_col not in df.columns:
            df['sentiment_polarity'] = 0
            df['sentiment_subjectivity'] = 0
            return df
        
        sentiments = []
        subjectivities = []
        
        for text in df[text_col].fillna(''):
            try:
                blob = TextBlob(str(text))
                sentiments.append(blob.sentiment.polarity)
                subjectivities.append(blob.sentiment.subjectivity)
            except:
                sentiments.append(0)
                subjectivities.append(0)
        
        df['sentiment_polarity'] = sentiments
        df['sentiment_subjectivity'] = subjectivities
        
        return df
    
    def engineer_all_features(self, df: pd.DataFrame, fit: bool = True) -> pd.DataFrame:
        """Apply all feature engineering steps."""
        print("Engineering features...")
        
        # Basic features
        df = self.create_basic_features(df)
        
        # Categorical encoding
        df = self.encode_categorical_features(df, fit=fit)
        
        # Numerical scaling
        df = self.scale_numerical_features(df, fit=fit)
        
        # Text features (if available)
        if 'event_description' in df.columns:
            df = self.create_text_features(df, fit=fit)
            df = self.extract_sentiment_features(df)
        
        return df

# =========================================================
# EVENT IMPACT PREDICTOR
# =========================================================

class EventImpactPredictor:
    """ML-based event impact predictor."""
    
    def __init__(self, model_type: str = 'random_forest'):
        self.model_type = model_type
        self.model = None
        self.feature_engineer = EventFeatureEngineer()
        self.feature_importance = None
        self.model_config = ML_CONFIG.get(model_type, ML_CONFIG['random_forest'])
    
    def create_model(self):
        """Create the ML model based on configuration."""
        if self.model_type == 'random_forest':
            self.model = RandomForestRegressor(**self.model_config)
        elif self.model_type == 'xgboost':
            self.model = xgb.XGBRegressor(**self.model_config)
        elif self.model_type == 'lightgbm':
            self.model = lgb.LGBMRegressor(**self.model_config)
        elif self.model_type == 'gradient_boosting':
            self.model = GradientBoostingRegressor(**self.model_config)
        else:
            self.model = RandomForestRegressor(**self.model_config)
    
    def prepare_training_data(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.Series]:
        """Prepare features and target for training."""
        # Engineer features
        df = self.feature_engineer.engineer_all_features(df, fit=True)
        
        # Select feature columns
        feature_cols = [col for col in df.columns 
                       if col not in ['event_id', 'event_type', 'area_type', 'event_date',
                                   'baseline_waste_kg', 'actual_waste_kg', 
                                   'waste_increase_kg', 'waste_increase_percentage']]
        
        # Remove non-numeric columns
        numeric_feature_cols = []
        for col in feature_cols:
            try:
                pd.to_numeric(df[col])
                numeric_feature_cols.append(col)
            except:
                continue
        
        X = df[numeric_feature_cols].copy()
        
        # Handle missing values
        X = X.fillna(X.median())
        
        # Target: waste increase percentage
        y = df['waste_increase_percentage']
        
        return X, y
    
    def train(self, df: pd.DataFrame) -> Dict:
        """Train the event impact prediction model."""
        print(f"Training {self.model_type} model...")
        
        # Prepare data
        X, y = self.prepare_training_data(df)
        
        # Split data
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42
        )
        
        # Create and train model
        self.create_model()
        self.model.fit(X_train, y_train)
        
        # Evaluate
        train_predictions = self.model.predict(X_train)
        test_predictions = self.model.predict(X_test)
        
        train_mae = mean_absolute_error(y_train, train_predictions)
        test_mae = mean_absolute_error(y_test, test_predictions)
        train_r2 = r2_score(y_train, train_predictions)
        test_r2 = r2_score(y_test, test_predictions)
        
        # Feature importance
        if hasattr(self.model, 'feature_importances_'):
            self.feature_importance = dict(zip(X.columns, self.model.feature_importances_))
        
        results = {
            'train_mae': train_mae,
            'test_mae': test_mae,
            'train_r2': train_r2,
            'test_r2': test_r2,
            'feature_importance': self.feature_importance,
            'n_features': len(X.columns),
            'n_samples': len(df)
        }
        
        print(f"Training completed. Test MAE: {test_mae:.2f}%, Test R²: {test_r2:.3f}")
        
        return results
    
    def predict_impact(self, event_data: Dict) -> Dict:
        """Predict waste impact for a new event."""
        if self.model is None:
            print("Model not trained. Please train the model first.")
            return None
        
        # Convert to DataFrame
        df = pd.DataFrame([event_data])
        
        # Engineer features (without fitting)
        df = self.feature_engineer.engineer_all_features(df, fit=False)
        
        # Select feature columns (same as training)
        feature_cols = [col for col in df.columns 
                       if col not in ['event_id', 'event_type', 'area_type', 'event_date',
                                   'baseline_waste_kg', 'actual_waste_kg', 
                                   'waste_increase_kg', 'waste_increase_percentage']]
        
        numeric_feature_cols = []
        for col in feature_cols:
            try:
                pd.to_numeric(df[col])
                numeric_feature_cols.append(col)
            except:
                continue
        
        X = df[numeric_feature_cols].copy()
        X = X.fillna(X.median())
        
        # Ensure we have the same features as training
        missing_features = set(self.feature_importance.keys()) - set(X.columns)
        for feature in missing_features:
            X[feature] = 0  # Fill missing features with 0
        
        extra_features = set(X.columns) - set(self.feature_importance.keys())
        X = X.drop(columns=list(extra_features))
        
        # Reorder columns to match training
        X = X[self.feature_importance.keys()]
        
        # Predict
        predicted_increase = self.model.predict(X)[0]
        
        return {
            'predicted_waste_increase_percentage': predicted_increase,
            'confidence': self._calculate_prediction_confidence(X),
            'feature_contributions': self._get_feature_contributions(X)
        }
    
    def _calculate_prediction_confidence(self, X: pd.DataFrame) -> float:
        """Calculate prediction confidence based on feature similarity."""
        # Simple confidence based on feature ranges
        confidence = 0.7  # Base confidence
        
        # If using tree-based model, can use tree consistency
        if hasattr(self.model, 'estimators_'):
            predictions = []
            for estimator in self.model.estimators_[:10]:  # Sample 10 trees
                predictions.append(estimator.predict(X)[0])
            
            prediction_std = np.std(predictions)
            confidence = max(0.5, min(0.95, 1.0 - prediction_std / 100))
        
        return confidence
    
    def _get_feature_contributions(self, X: pd.DataFrame) -> Dict:
        """Get feature contributions for the prediction."""
        if self.feature_importance is None:
            return {}
        
        contributions = {}
        for feature, importance in self.feature_importance.items():
            if feature in X.columns:
                feature_value = X[feature].values[0]
                contributions[feature] = importance * feature_value
        
        # Normalize
        total = sum(abs(v) for v in contributions.values())
        if total > 0:
            contributions = {k: v/total for k, v in contributions.items()}
        
        return contributions
    
    def save_model(self, model_path: Path = None):
        """Save the trained model and feature engineer."""
        if model_path is None:
            model_path = MODEL_DIR / f"event_impact_{self.model_type}.joblib"
        
        model_data = {
            'model': self.model,
            'feature_engineer': self.feature_engineer,
            'feature_importance': self.feature_importance,
            'model_type': self.model_type,
            'model_config': self.model_config
        }
        
        joblib.dump(model_data, model_path)
        print(f"Model saved to: {model_path}")
    
    def load_model(self, model_path: Path = None):
        """Load a trained model."""
        if model_path is None:
            model_path = MODEL_DIR / f"event_impact_{self.model_type}.joblib"
        
        if not model_path.exists():
            raise FileNotFoundError(f"Model file not found: {model_path}")
        
        model_data = joblib.load(model_path)
        
        self.model = model_data['model']
        self.feature_engineer = model_data['feature_engineer']
        self.feature_importance = model_data['feature_importance']
        self.model_type = model_data['model_type']
        self.model_config = model_data['model_config']
        
        print(f"Model loaded from: {model_path}")

# =========================================================
# EVENT CLUSTERING
# =========================================================

class EventClusterer:
    """Cluster events by similarity for impact estimation."""
    
    def __init__(self, n_clusters: int = 5):
        self.n_clusters = n_clusters
        self.clusterer = None
        self.cluster_centers = None
        self.cluster_impact_profiles = {}
    
    def prepare_clustering_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Prepare features for clustering."""
        feature_cols = [
            'event_type', 'duration_days', 'expected_attendance', 
            'intensity', 'area_type', 'day_of_week', 'month'
        ]
        
        available_cols = [col for col in feature_cols if col in df.columns]
        cluster_df = df[available_cols].copy()
        
        # Encode categorical
        le = LabelEncoder()
        for col in ['event_type', 'area_type']:
            if col in cluster_df.columns:
                cluster_df[f'{col}_encoded'] = le.fit_transform(cluster_df[col].astype(str))
        
        # Select numerical features
        numerical_cols = [col for col in cluster_df.columns 
                        if cluster_df[col].dtype in ['int64', 'float64']]
        
        return cluster_df[numerical_cols]
    
    def fit_clusters(self, df: pd.DataFrame):
        """Fit clustering model to events."""
        print(f"Clustering events into {self.n_clusters} groups...")
        
        X = self.prepare_clustering_features(df)
        
        # Scale features
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)
        
        # Fit K-means
        self.clusterer = KMeans(n_clusters=self.n_clusters, random_state=42)
        clusters = self.clusterer.fit_predict(X_scaled)
        
        # Calculate cluster impact profiles
        df['cluster'] = clusters
        for cluster_id in range(self.n_clusters):
            cluster_data = df[df['cluster'] == cluster_id]
            avg_impact = cluster_data['waste_increase_percentage'].mean()
            self.cluster_impact_profiles[cluster_id] = avg_impact
        
        print(f"Clustering completed. Cluster impact profiles:")
        for cluster_id, impact in self.cluster_impact_profiles.items():
            print(f"  Cluster {cluster_id}: {impact:.2f}% average impact")
        
        return clusters
    
    def predict_cluster_impact(self, event_data: Dict) -> float:
        """Predict impact based on cluster membership."""
        if self.clusterer is None:
            return 100.0  # Default impact
        
        # Prepare features
        df = pd.DataFrame([event_data])
        X = self.prepare_clustering_features(df)
        
        # Scale
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)
        
        # Predict cluster
        cluster = self.clusterer.predict(X_scaled)[0]
        
        # Return cluster impact
        return self.cluster_impact_profiles.get(cluster, 100.0)

# =========================================================
# CONTINUOUS LEARNING SYSTEM
# =========================================================

class ContinuousEventLearner:
    """Continuously learn from new event data."""
    
    def __init__(self, model_type: str = 'random_forest'):
        self.predictor = EventImpactPredictor(model_type)
        self.clusterer = EventClusterer()
        self.min_samples_for_retrain = 50
        self.last_retrain_date = None
    
    def initial_training(self, historical_data: pd.DataFrame):
        """Perform initial training with historical data."""
        print("Performing initial training...")
        
        # Train impact predictor
        training_results = self.predictor.train(historical_data)
        
        # Train clusterer
        self.clusterer.fit_clusters(historical_data)
        
        # Save models
        self.predictor.save_model()
        
        self.last_retrain_date = datetime.now()
        
        return training_results
    
    def update_with_new_data(self, new_events: pd.DataFrame):
        """Update models with new event data."""
        print("Updating models with new event data...")
        
        # Load existing model
        try:
            self.predictor.load_model()
        except:
            print("No existing model found. Performing initial training...")
            return self.initial_training(new_events)
        
        # Combine with existing data (if available)
        if HISTORICAL_EVENTS_FILE.exists():
            existing_data = pd.read_csv(HISTORICAL_EVENTS_FILE)
            combined_data = pd.concat([existing_data, new_events], ignore_index=True)
        else:
            combined_data = new_events
        
        # Retrain if enough new data
        if len(new_events) >= self.min_samples_for_retrain:
            print(f"Retraining with {len(new_events)} new samples...")
            
            # Retrain predictor
            training_results = self.predictor.train(combined_data)
            
            # Retrain clusterer
            self.clusterer.fit_clusters(combined_data)
            
            # Save updated models
            self.predictor.save_model()
            
            # Update historical data
            combined_data.to_csv(HISTORICAL_EVENTS_FILE, index=False)
            
            self.last_retrain_date = datetime.now()
            
            return training_results
        else:
            print(f"Not enough new samples for retraining ({len(new_events)} < {self.min_samples_for_retrain})")
            return None
    
    def predict_event_impact(self, event_data: Dict) -> Dict:
        """Predict impact using ensemble of ML and clustering."""
        # ML prediction
        ml_prediction = self.predictor.predict_impact(event_data)
        
        # Cluster-based prediction
        cluster_prediction = self.clusterer.predict_cluster_impact(event_data)
        
        # Ensemble prediction
        if ml_prediction:
            ml_impact = ml_prediction['predicted_waste_increase_percentage']
            ensemble_impact = 0.7 * ml_impact + 0.3 * cluster_prediction
            
            return {
                'ensemble_impact_percentage': ensemble_impact,
                'ml_impact_percentage': ml_impact,
                'cluster_impact_percentage': cluster_prediction,
                'ml_confidence': ml_prediction.get('confidence', 0.7),
                'feature_contributions': ml_prediction.get('feature_contributions', {})
            }
        else:
            return {
                'ensemble_impact_percentage': cluster_prediction,
                'ml_impact_percentage': None,
                'cluster_impact_percentage': cluster_prediction,
                'ml_confidence': 0.5,
                'feature_contributions': {}
            }

# =========================================================
# MAIN EXECUTION
# =========================================================

def main():
    print("=" * 70)
    print("ML-BASED EVENT IMPACT LEARNING MODULE")
    print("=" * 70)
    
    # Generate or load historical data
    if HISTORICAL_EVENTS_FILE.exists():
        print(f"Loading existing historical data from {HISTORICAL_EVENTS_FILE}")
        historical_data = pd.read_csv(HISTORICAL_EVENTS_FILE)
    else:
        print("Generating synthetic historical data...")
        historical_data = generate_synthetic_event_waste_data(num_samples=1000)
    
    print(f"Historical data: {len(historical_data)} records")
    
    # Initialize continuous learner
    learner = ContinuousEventLearner(model_type='random_forest')
    
    # Perform initial training
    print("\n" + "=" * 70)
    print("INITIAL TRAINING")
    print("=" * 70)
    
    training_results = learner.initial_training(historical_data)
    
    print("\nTraining Results:")
    print(f"  Train MAE: {training_results['train_mae']:.2f}%")
    print(f"  Test MAE: {training_results['test_mae']:.2f}%")
    print(f"  Train R²: {training_results['train_r2']:.3f}")
    print(f"  Test R²: {training_results['test_r2']:.3f}")
    print(f"  Features: {training_results['n_features']}")
    print(f"  Samples: {training_results['n_samples']}")
    
    # Feature importance
    print("\nTop 10 Feature Importances:")
    sorted_importance = sorted(training_results['feature_importance'].items(), 
                              key=lambda x: x[1], reverse=True)
    for feature, importance in sorted_importance[:10]:
        print(f"  {feature}: {importance:.4f}")
    
    # Test prediction on sample events
    print("\n" + "=" * 70)
    print("SAMPLE PREDICTIONS")
    print("=" * 70)
    
    sample_events = [
        {
            'event_type': 'festival',
            'duration_days': 3,
            'expected_attendance': 25000,
            'intensity': 3,
            'area_type': 'commercial',
            'population_density': 12000,
            'day_of_week': 5,
            'is_weekend': 1,
            'month': 12,
            'is_holiday_season': 1,
            'baseline_waste_kg': 2500
        },
        {
            'event_type': 'concert',
            'duration_days': 1,
            'expected_attendance': 5000,
            'intensity': 2,
            'area_type': 'mixed',
            'population_density': 8000,
            'day_of_week': 2,
            'is_weekend': 0,
            'month': 6,
            'is_holiday_season': 0,
            'baseline_waste_kg': 1800
        }
    ]
    
    for i, event in enumerate(sample_events, 1):
        print(f"\nSample Event {i}:")
        print(f"  Type: {event['event_type']}")
        print(f"  Attendance: {event['expected_attendance']}")
        print(f"  Duration: {event['duration_days']} days")
        
        prediction = learner.predict_event_impact(event)
        
        print(f"  Predicted Impact: {prediction['ensemble_impact_percentage']:.2f}%")
        print(f"  ML Impact: {prediction['ml_impact_percentage']:.2f}%")
        print(f"  Cluster Impact: {prediction['cluster_impact_percentage']:.2f}%")
        print(f"  Confidence: {prediction['ml_confidence']:.2f}")
    
    print("\n" + "=" * 70)
    print("ML-BASED EVENT IMPACT LEARNING COMPLETED")
    print("=" * 70)

if __name__ == "__main__":
    main()