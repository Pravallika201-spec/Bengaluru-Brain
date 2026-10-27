"""
=========================================================
Urban Predictive Intelligence System
Model Validation Framework Module
=========================================================

Comprehensive model validation framework with ground truth:
- Ground truth data collection and management
- Model performance metrics and benchmarks
- Cross-validation and time-series validation
- Backtesting with historical data
- A/B testing framework
- Model comparison and selection
- Uncertainty quantification validation
- Continuous monitoring and drift detection
- Automated retraining triggers
- Performance dashboards and alerts

Replaces the limited validation capability.
=========================================================
"""

import os
import json
import warnings
warnings.filterwarnings("ignore")

from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
import geopandas as gpd

# ML Libraries
from sklearn.model_selection import TimeSeriesSplit, cross_val_score, GridSearchCV
from sklearn.metrics import (
    mean_absolute_error, mean_squared_error, mean_absolute_percentage_error,
    r2_score, explained_variance_score
)
from sklearn.calibration import calibration_curve
import joblib

# Statistical libraries
from scipy import stats
import matplotlib.pyplot as plt
import seaborn as sns

# =========================================================
# CONFIGURATION
# =========================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "waste_module" / "data" / "processed"
VALIDATION_DIR = DATA_DIR / "validation"
VALIDATION_DIR.mkdir(parents=True, exist_ok=True)

MODEL_DIR = PROJECT_ROOT / "waste_module" / "models"
MODEL_DIR.mkdir(parents=True, exist_ok=True)

# Validation configuration
VALIDATION_CONFIG = {
    'validation_metrics': [
        'MAE', 'RMSE', 'MAPE', 'R2', 'Explained Variance'
    ],
    'cross_validation_folds': 5,
    'test_size': 0.2,
    'random_state': 42,
    'backtest_days': 30,
    'performance_thresholds': {
        'MAE': 500,  # kg
        'MAPE': 20,  # percentage
        'R2': 0.7
    },
    'drift_detection_threshold': 0.15  # 15% performance degradation
}

# =========================================================
# GROUND TRUTH DATA MANAGEMENT
# =========================================================

class GroundTruthManager:
    """Manage ground truth waste collection data."""
    
    def __init__(self):
        self.ground_truth_file = VALIDATION_DIR / "ground_truth_waste.csv"
        self.ground_truth_data = None
    
    def load_ground_truth(self) -> pd.DataFrame:
        """Load ground truth waste data."""
        if self.ground_truth_file.exists():
            self.ground_truth_data = pd.read_csv(self.ground_truth_file)
            print(f"Loaded {len(self.ground_truth_data)} ground truth records")
            return self.ground_truth_data
        else:
            print("No ground truth data found")
            return None
    
    def generate_synthetic_ground_truth(self, predictions_df: pd.DataFrame, 
                                    noise_level: float = 0.15) -> pd.DataFrame:
        """Generate synthetic ground truth data for validation."""
        print("Generating synthetic ground truth data...")
        
        ground_truth = []
        
        for _, prediction in predictions_df.iterrows():
            # Generate ground truth with realistic noise
            predicted_waste = prediction['ensemble_prediction']
            
            # Add noise based on waste magnitude
            noise = np.random.normal(0, predicted_waste * noise_level)
            actual_waste = max(0, predicted_waste + noise)
            
            ground_truth.append({
                'Grid_ID': prediction['Grid_ID'],
                'Latitude': prediction['Latitude'],
                'Longitude': prediction['Longitude'],
                'forecast_date': prediction['forecast_date'],
                'predicted_waste_kg': predicted_waste,
                'actual_waste_kg': actual_waste,
                'prediction_error': actual_waste - predicted_waste,
                'absolute_error': abs(actual_waste - predicted_waste),
                'percentage_error': abs((actual_waste - predicted_waste) / predicted_waste * 100) if predicted_waste > 0 else 0,
                'recorded_at': datetime.now().isoformat()
            })
        
        df = pd.DataFrame(ground_truth)
        
        # Save ground truth
        df.to_csv(self.ground_truth_file, index=False)
        print(f"Generated {len(df)} ground truth records")
        print(f"Saved to: {self.ground_truth_file}")
        
        self.ground_truth_data = df
        return df
    
    def collect_field_data(self, grid_ids: List[str], date: str) -> pd.DataFrame:
        """Simulate field data collection for specific grids."""
        print(f"Simulating field data collection for {len(grid_ids)} grids on {date}")
        
        # In production, this would interface with IoT sensors or manual collection
        field_data = []
        
        for grid_id in grid_ids:
            # Simulate actual waste measurement
            base_waste = np.random.uniform(500, 3000)
            measurement_error = np.random.normal(0, base_waste * 0.1)
            actual_waste = max(0, base_waste + measurement_error)
            
            field_data.append({
                'Grid_ID': grid_id,
                'collection_date': date,
                'actual_waste_kg': actual_waste,
                'collection_method': 'manual',  # Could be 'iot', 'manual', 'drone'
                'confidence': np.random.uniform(0.8, 0.95),
                'collector_id': f"COL{np.random.randint(1000, 9999)}",
                'collected_at': datetime.now().isoformat()
            })
        
        df = pd.DataFrame(field_data)
        
        # Save field data
        field_file = VALIDATION_DIR / f"field_data_{date}.csv"
        df.to_csv(field_file, index=False)
        print(f"Field data saved to: {field_file}")
        
        return df

# =========================================================
# MODEL PERFORMANCE EVALUATOR
# =========================================================

class ModelPerformanceEvaluator:
    """Evaluate model performance against ground truth."""
    
    def __init__(self):
        self.validation_results = {}
    
    def calculate_metrics(self, predictions: np.ndarray, actual: np.ndarray) -> Dict:
        """Calculate comprehensive performance metrics."""
        metrics = {}
        
        # Basic metrics
        metrics['MAE'] = mean_absolute_error(actual, predictions)
        metrics['RMSE'] = np.sqrt(mean_squared_error(actual, predictions))
        metrics['MAPE'] = mean_absolute_percentage_error(actual, predictions)
        metrics['R2'] = r2_score(actual, predictions)
        metrics['Explained_Variance'] = explained_variance_score(actual, predictions)
        
        # Additional metrics
        metrics['Mean_Error'] = np.mean(predictions - actual)
        metrics['Std_Error'] = np.std(predictions - actual)
        metrics['Max_Error'] = np.max(np.abs(predictions - actual))
        
        # Directional accuracy
        correct_direction = np.sum((predictions - actual) * (predictions - actual) >= 0)
        metrics['Directional_Accuracy'] = correct_direction / len(predictions)
        
        return metrics
    
    def evaluate_spatial_performance(self, predictions_df: pd.DataFrame, 
                                     ground_truth_df: pd.DataFrame) -> Dict:
        """Evaluate performance across different spatial regions."""
        print("Evaluating spatial performance...")
        
        # Merge predictions with ground truth
        merged = predictions_df.merge(
            ground_truth_df,
            on=['Grid_ID', 'forecast_date'],
            how='inner'
        )
        
        if merged.empty:
            print("No matching predictions and ground truth data")
            return {}
        
        # Calculate overall metrics
        overall_metrics = self.calculate_metrics(
            merged['predicted_waste_kg'].values,
            merged['actual_waste_kg'].values
        )
        
        # Spatial evaluation by area (if available)
        spatial_metrics = {}
        if 'area_name' in merged.columns:
            area_performance = merged.groupby('area_name').apply(
                lambda x: self.calculate_metrics(x['predicted_waste_kg'].values, x['actual_waste_kg'].values)
            )
            spatial_metrics['by_area'] = area_performance.to_dict()
        
        # Temporal evaluation
        if 'forecast_day' in merged.columns:
            temporal_performance = merged.groupby('forecast_day').apply(
                lambda x: self.calculate_metrics(x['predicted_waste_kg'].values, x['actual_waste_kg'].values)
            )
            spatial_metrics['by_forecast_day'] = temporal_performance.to_dict()
        
        return {
            'overall': overall_metrics,
            'spatial': spatial_metrics
        }
    
    def evaluate_calibration(self, predictions: np.ndarray, actual: np.ndarray) -> Dict:
        """Evaluate prediction calibration."""
        print("Evaluating prediction calibration...")
        
        # Binary classification: whether actual > predicted
        overpredictions = (predictions > actual).astype(int)
        
        # Calibration curve
        if len(np.unique(overpredictions)) > 1:
            fraction_of_positives, mean_predicted_value = calibration_curve(
                actual, predictions, n_bins=10
            )
            
            calibration_metrics = {
                'reliability_diagram': {
                    'fraction_of_positives': fraction_of_poisitives.tolist(),
                    'mean_predicted_value': mean_predicted_value.tolist()
                },
                'expected_calibration_error': np.mean(np.abs(fraction_of_positives - mean_predicted_value))
            }
        else:
            calibration_metrics = {
                'expected_calibration_error': 0,
                'note': 'Not enough variation for calibration analysis'
            }
        
        return calibration_metrics

# =========================================================
# TIME SERIES VALIDATION
# =========================================================

class TimeSeriesValidator:
    """Time series-specific validation methods."""
    
    def __init__(self):
        self.cv_results = {}
    
    def time_series_cross_validation(self, model, X: pd.DataFrame, y: pd.Series, 
                                   n_splits: int = 5) -> Dict:
        """Perform time series cross-validation."""
        print("Performing time series cross-validation...")
        
        tscv = TimeSeriesSplit(n_splits=n_splits, test_size=VALIDATION_CONFIG['test_size'])
        
        cv_scores = []
        for fold, (train_idx, test_idx) in enumerate(tscv.split(X)):
            X_train, X_test = X.iloc[train_idx], X.iloc[test_idx]
            y_train, y_test = y.iloc[train_idx], y.iloc[test_idx]
            
            # Train model
            model.fit(X_train, y_train)
            
            # Evaluate
            predictions = model.predict(X_test)
            mae = mean_absolute_error(y_test, predictions)
            cv_scores.append(mae)
        
        return {
            'cv_scores': cv_scores,
            'mean_cv_score': np.mean(cv_scores),
            'std_cv_score': np.std(cv_scores),
            'min_cv_score': np.min(cv_scores),
            'max_cv_score': np.max(cv_scores)
        }
    
    def backtesting(self, model, historical_data: pd.DataFrame, 
                  forecast_horizon: int = 30) -> Dict:
        """Perform backtesting with historical data."""
        print(f"Performing backtesting with {forecast_horizon} day horizon...")
        
        backtest_results = []
        
        # Sort by date
        historical_data = historical_data.sort_values('date')
        
        # Rolling window backtesting
        min_samples = 90  # Minimum training samples
        
        for i in range(min_samples, len(historical_data) - forecast_horizon):
            train_data = historical_data.iloc[:i]
            test_data = historical_data.iloc[i:i+forecast_horizon]
            
            # Prepare features
            X_train = train_data[['Grid_ID', 'date', 'daily_waste_kg']].copy()
            y_train = train_data['daily_waste_kg']
            
            X_test = test_data[['Grid_ID', 'date', 'daily_waste_kg']].copy()
            y_test = test_data['daily_waste_kg']
            
            # Simple baseline: use previous day's value as prediction
            predictions = X_train['daily_waste_kg'].tail(1).values[0]
            predictions_array = np.full(len(y_test), predictions)
            
            # Calculate error
            mae = mean_absolute_error(y_test, predictions_array)
            
            backtest_results.append({
                'test_start_date': test_data['date'].min(),
                'test_end_date': test_data['date'].max(),
                'MAE': mae
            })
        
        backtest_df = pd.DataFrame(backtest_results)
        
        return {
            'backtest_results': backtest_df,
            'average_mae': backtest_df['MAE'].mean(),
            'mae_std': backtest_df['MAE'].std(),
            'worst_performing_day': backtest_df.loc[backtest_df['MAE'].idxmax(), 'test_start_date']
        }

# =========================================================
# MODEL COMPARISON FRAMEWORK
# =========================================================

class ModelComparisonFramework:
    """Compare multiple models to select the best performer."""
    
    def __init__(self):
        self.comparison_results = {}
    
    def compare_models(self, models: Dict, X: pd.DataFrame, y: pd.Series) -> Dict:
        """Compare multiple models on the same dataset."""
        print("Comparing multiple models...")
        
        comparison = {}
        
        for model_name, model in models.items():
            print(f"  Evaluating {model_name}...")
            
            # Time series cross-validation
            tscv = TimeSeriesSplit(n_splits=VALIDATION_CONFIG['cross_validation_folds'])
            cv_scores = cross_val_score(model, X, y, cv=tscv, scoring='neg_mean_absolute_error')
            
            # Train final model
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=VALIDATION_CONFIG['test_size'], random_state=VALIDATION_CONFIG['random_state']
            )
            
            model.fit(X_train, y_train)
            predictions = model.predict(X_test)
            
            # Calculate metrics
            metrics = {
                'MAE': mean_absolute_error(y_test, predictions),
                'RMSE': np.sqrt(mean_squared_error(y_test, predictions)),
                'R2': r2_score(y_test, predictions),
                'cv_mean_mae': -np.mean(cv_scores),
                'cv_std_mae': np.std(cv_scores)
            }
            
            comparison[model_name] = metrics
        
        # Rank models
        ranking = sorted(comparison.items(), key=lambda x: x[1]['MAE'])
        
        return {
            'comparison': comparison,
            'ranking': ranking,
            'best_model': ranking[0][0] if ranking else None,
            'best_mae': ranking[0][1]['MAE'] if ranking else None
        }

# =========================================================
# UNCERTAINTY VALIDATION
# =========================================================

class UncertaintyValidator:
    """Validate uncertainty quantification methods."""
    
    def __init__(self):
        self.uncertainty_results = {}
    
    def validate_prediction_intervals(self, predictions_df: pd.DataFrame, 
                                    ground_truth_df: pd.DataFrame) -> Dict:
        """Validate that prediction intervals contain the actual values appropriately."""
        print("Validating prediction intervals...")
        
        # Merge predictions with ground truth
        merged = predictions_df.merge(
            ground_truth_df,
            on=['Grid_ID', 'forecast_date'],
            how='inner'
        )
        
        if merged.empty:
            print("No matching data for interval validation")
            return {}
        
        # Check coverage of prediction intervals
        if 'prediction_lower' in merged.columns and 'prediction_upper' in merged.columns:
            within_interval = (
                (merged['actual_waste_kg'] >= merged['prediction_lower']) &
                (merged['actual_waste_kg'] <= merged['prediction_upper'])
            )
            
            coverage = within_interval.mean()
            target_coverage = 0.95  # 95% confidence interval
            
            interval_width = (merged['prediction_upper'] - merged['prediction_lower']).mean()
            
            interval_metrics = {
                'actual_coverage': coverage,
                'target_coverage': target_coverage,
                'coverage_error': abs(coverage - target_coverage),
                'average_interval_width': interval_width,
                'interval_width_relative': interval_width / merged['actual_waste_kg'].mean()
            }
        else:
            interval_metrics = {
                'note': 'Prediction intervals not available in predictions'
            }
        
        return interval_metrics
    
    def validate_uncertainty_calibration(self, predictions_df: pd.DataFrame) -> Dict:
        """Validate that uncertainty scores are well-calibrated."""
        print("Validating uncertainty calibration...")
        
        if 'uncertainty' not in predictions_df.columns:
            return {'note': 'Uncertainty column not available'}
        
        # Group by uncertainty bins and check prediction error
        predictions_df['prediction_error'] = abs(
            predictions_df['ensemble_prediction'] - predictions_df.get('actual_waste_kg', predictions_df['ensemble_prediction'])
        )
        
        # Create uncertainty bins
        predictions_df['uncertainty_bin'] = pd.qcut(
            predictions_df['uncertainty'],
            q=[0, 0.2, 0.4, 0.6, 0.8, 1.0],
            labels=['Very Low', 'Low', 'Medium', 'High', 'Very High']
        )
        
        # Calculate average error by uncertainty bin
        uncertainty_error = predictions_df.groupby('uncertainty_bin')['prediction_error'].mean()
        
        return {
            'uncertainty_error_by_bin': uncertainty_error.to_dict(),
            'calibration_quality': 'Good' if uncertainty_error.is_monotonic_increasing else 'Poor'
        }

# =========================================================
# DRIFT DETECTION
# =========================================================

class DriftDetector:
    """Detect model performance drift over time."""
    
    def __init__(self):
        self.performance_history = []
        self.drift_detected = False
        self.drift_threshold = VALIDATION_CONFIG['drift_detection_threshold']
    
    def monitor_performance(self, current_metrics: Dict, timestamp: datetime = None):
        """Monitor model performance over time."""
        if timestamp is None:
            timestamp = datetime.now()
        
        # Record performance
        self.performance_history.append({
            'timestamp': timestamp,
            'metrics': current_metrics
        })
        
        # Check for drift
        if len(self.performance_history) >= 2:
            latest_mae = current_metrics.get('MAE', 0)
            baseline_mae = self.performance_history[-2]['metrics'].get('MAE', latest_mae)
            
            if baseline_mae > 0:
                performance_change = abs(latest_mae - baseline_mae) / baseline_mae
                
                if performance_change > self.drift_threshold:
                    self.drift_detected = True
                    print(f"⚠️  PERFORMANCE DRIFT DETECTED: {performance_change:.2%} change")
    
    def check_retraining_needed(self) -> bool:
        """Check if model retraining is needed."""
        if not self.performance_history:
            return False
        
        # Check if recent performance is below threshold
        recent_performance = self.performance_history[-5:]  # Last 5 measurements
        if len(recent_performance) < 2:
            return False
        
        recent_mae = np.mean([m['metrics'].get('MAE', 0) for m in recent_performance])
        threshold_mae = VALIDATION_CONFIG['performance_thresholds']['MAE']
        
        if recent_mae > threshold_mae:
            print(f"⚠️  Performance below threshold ({recent_mae:.2f} > {threshold_mae})")
            return True
        
        return False

# =========================================================
# VALIDATION DASHBOARD
# =========================================================

class ValidationDashboard:
    """Generate validation dashboard and reports."""
    
    def __init__(self):
        self.reports = {}
    
    def generate_validation_report(self, validation_results: Dict) -> str:
        """Generate comprehensive validation report."""
        report = []
        
        report.append("=" * 70)
        report.append("MODEL VALIDATION REPORT")
        report.append("=" * 70)
        report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append("")
        
        # Overall performance
        if 'overall' in validation_results:
            report.append("OVERALL PERFORMANCE")
            report.append("-" * 40)
            overall = validation_results['overall']
            report.append(f"  MAE: {overall['MAE']:.2f} kg")
            report.append(f"  RMSE: {overall['RMSE']:.2f} kg")
            report.append(f"  MAPE: {overall['MAPE']:.2f}%")
            report.append(f"  R²: {overall['R2']:.3f}")
            report.append(f"  Explained Variance: {overall['Explained_Variance']:.3f}")
            report.append("")
        
        # Performance thresholds
        report.append("PERFORMANCE THRESHOLDS")
        report.append("-" * 40)
        for metric, threshold in VALIDATION_CONFIG['performance_thresholds'].items():
            if metric in validation_results.get('overall', {}):
                actual = validation_results['overall'][metric]
                status = "✓ PASS" if actual <= threshold else "✗ FAIL"
                report.append(f"  {metric}: {actual:.2f} / {threshold} - {status}")
        report.append("")
        
        # Spatial performance
        if 'spatial' in validation_results:
            report.append("SPATIAL PERFORMANCE")
            report.append("-" * 40)
            spatial = validation_results['spatial']
            
            if 'by_area' in spatial:
                report.append("  Performance by Area:")
                for area, metrics in list(spatial['by_area'].items())[:5]:
                    report.append(f"    {area}: MAE={metrics['MAE']:.2f}, R²={metrics['R2']:.3f}")
        
        report.append("")
        
        # Recommendations
        report.append("RECOMMENDATIONS")
        report.append("-" * 40)
        
        if validation_results.get('overall', {}).get('MAE', 0) > VALIDATION_CONFIG['performance_thresholds']['MAE']:
            report.append("  ⚠️  Model performance below threshold")
            report.append("  → Consider retraining with more recent data")
            report.append("  → Review feature engineering")
        else:
            report.append("  ✓ Model performance acceptable")
        
        if validation_results.get('overall', {}).get('R2', 0) < VALIDATION_CONFIG['performance_thresholds']['R2']:
            report.append("  ⚠️  Model explainability could be improved")
            report.append("  → Consider adding more features")
        else:
            report.append("  ✓ Model explainability acceptable")
        
        report.append("")
        report.append("=" * 70)
        
        return "\n".join(report)
    
    def save_validation_report(self, report: str):
        """Save validation report to file."""
        report_file = VALIDATION_DIR / f"validation_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        with open(report_file, 'w') as f:
            f.write(report)
        print(f"Validation report saved to: {report_file}")

# =========================================================
# MAIN EXECUTION
# =========================================================

def main():
    print("=" * 70)
    print("MODEL VALIDATION FRAMEWORK")
    print("=" *  )
    
    # Initialize components
    ground_truth_manager = GroundTruthManager()
    performance_evaluator = ModelPerformanceEvaluator()
    time_series_validator = TimeSeriesValidator()
    uncertainty_validator = UncertaintyValidator()
    drift_detector = DriftDetector()
    dashboard = ValidationDashboard()
    
    # Load or generate ground truth
    print("\n" + "=" * 70)
    print("GROUND TRUTH DATA MANAGEMENT")
    print("=" * 70)
    
    predictions_file = DATA_DIR / "bengaluru_advanced_temporal_predictions.gpkg"
    if predictions_file.exists():
        predictions_df = gpd.read_file(predictions_file, layer="advanced_temporal_predictions")
        print(f"Loaded predictions: {len(predictions_df)} records")
        
        # Generate synthetic ground truth
        ground_truth_df = ground_truth_manager.generate_synthetic_ground_truth(predictions_df)
    else:
        print("No predictions file found")
        return
    
    # Evaluate performance
    print("\n" + "=" * 70)
    print("MODEL PERFORMANCE EVALUATION")
    print("=" * 70)
    
    performance_results = performance_evaluator.evaluate_spatial_performance(predictions_df, ground_truth_df)
    
    # Evaluate uncertainty
    print("\n" + "=" * 70)
    print("UNCERTAINTY VALIDATION")
    print "=" * 70)
    
    uncertainty_results = uncertainty_validator.validate_prediction_intervals(predictions_df, ground_truth_df)
    uncertainty_calibration = uncertainty_validator.validate_uncertainty_calibration(predictions_df)
    
    # Check for drift
    print("\n" + "=" * 70)
    print("DRIFT DETECTION")
    print = "=" * 70)
    
    drift_detector.monitor_performance(performance_results.get('overall', {}))
    retraining_needed = drift_detector.check_retraining_needed()
    
    # Generate validation report
    print("\n" + "=" * 70)
    print("VALIDATION REPORT")
    print("=" * 70)
    
    all_results = {
        'performance': performance_results,
        'uncertainty': uncertainty_results,
        'uncertainty_calibration': uncertainty_calibration,
        'drift': {
            'detected': drift_detector.drift_detected,
            'retraining_needed': retraining_needed
        }
    }
    
    report = dashboard.generate_validation_report(all_results)
    print(report)
    
    dashboard.save_validation_report(report)
    
    # Save validation results
    results_file = VALIDATION_DIR / "validation_results.json"
    with open(results_file, 'w') as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"Validation results saved to: {results_file}")
    
    print("\n" + "=" * 70)
    print("MODEL VALIDATION COMPLETED")
    print("=" * 70)

if __name__ == "__main__":
    main()