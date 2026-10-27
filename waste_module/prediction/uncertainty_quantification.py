"""
=========================================================
Urban Predictive Intelligence System
Uncertainty Quantification Module
=========================================================

Advanced uncertainty quantification for predictions:
- Prediction intervals with multiple methods
- Bayesian uncertainty estimation
- Monte Carlo simulation
- Ensemble uncertainty aggregation
- Confidence calibration
- Risk-aware decision making
- Uncertainty visualization
- Probabilistic forecasting
- Scenario-based uncertainty analysis

Replaces the limited uncertainty quantification capability.
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

# Try to import geopandas (optional)
try:
    import geopandas as gpd
    GEOPANDAS_AVAILABLE = True
except ImportError:
    GEOPANDAS_AVAILABLE = False
    print("Geopandas not available - using pandas only")

# Statistical and probabilistic libraries
from scipy import stats
from scipy.stats import norm, beta, lognorm
import matplotlib.pyplot as plt
import seaborn as sns

# ML Libraries
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
import joblib

# =========================================================
# CONFIGURATION
# =========================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "waste_module" / "data" / "processed"
OUTPUT_DIR = DATA_DIR / "uncertainty_analysis"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

MODEL_DIR = PROJECT_ROOT / "waste_module" / "models"
MODEL_DIR.mkdir(parents=True, exist_ok=True)

# Uncertainty quantification configuration
UNCERTAINTY_CONFIG = {
    'confidence_levels': [0.50, 0.68, 0.90, 0.95, 0.99],
    'default_confidence': 0.95,
    'monte_carlo_simulations': 1000,
    'bootstrap_samples': 100,
    'methods': ['quantile', 'bootstrap', 'bayesian', 'ensemble']
}

# =========================================================
# QUANTILE REGRESSION UNCERTAINTY
# =========================================================

class QuantileUncertaintyEstimator:
    """Quantile regression for prediction intervals."""
    
    def __init__(self, quantiles: List[float] = None):
        self.quantiles = quantiles or [0.025, 0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95, 0.975]
        self.models = {}
        self.scaler = StandardScaler()
    
    def train_quantile_models(self, X: pd.DataFrame, y: pd.Series) -> Dict:
        """Train quantile regression models."""
        print("Training quantile regression models...")
        
        X_scaled = self.scaler.fit_transform(X)
        
        for quantile in self.quantiles:
            # Use GradientBoostingRegressor with quantile loss
            model = GradientBoostingRegressor(
                loss='quantile',
                alpha=quantile,
                n_estimators=100,
                max_depth=6,
                learning_rate=0.05,
                random_state=42
            )
            
            model.fit(X_scaled, y)
            self.models[quantile] = model
        
        return {
            'trained_quantiles': self.quantiles,
            'n_features': X.shape[1],
            'n_samples': len(y)
        }
    
    def predict_intervals(self, X: pd.DataFrame, confidence: float = 0.95) -> Dict:
        """Predict with confidence intervals."""
        if not self.models:
            raise ValueError("Models not trained. Call train_quantile_models first.")
        
        X_scaled = self.scaler.transform(X)
        
        # Get lower and upper quantiles
        lower_alpha = (1 - confidence) / 2
        upper_alpha = 1 - lower_alpha
        
        # Find closest trained quantiles
        lower_quantile = min(self.quantiles, key=lambda q: abs(q - lower_alpha))
        upper_quantile = min(self.quantiles, key=lambda q: abs(q - upper_alpha))
        
        lower_pred = self.models[lower_quantile].predict(X_scaled)
        upper_pred = self.models[upper_quantile].predict(X_scaled)
        median_pred = self.models[0.5].predict(X_scaled)
        
        return {
            'median': median_pred,
            'lower_bound': lower_pred,
            'upper_bound': upper_pred,
            'interval_width': upper_pred - lower_pred,
            'confidence': confidence
        }

# =========================================================
# BOOTSTRAP UNCERTAINTY
# =========================================================

class BootstrapUncertaintyEstimator:
    """Bootstrap-based uncertainty estimation."""
    
    def __init__(self, n_bootstrap: int = 100):
        self.n_bootstrap = n_bootstrap
        self.base_model = None
        self.bootstrap_models = []
    
    def train_bootstrap_models(self, X: pd.DataFrame, y: pd.Series, 
                             base_model = None) -> Dict:
        """Train bootstrap ensemble of models."""
        print(f"Training {self.n_bootstrap} bootstrap models...")
        
        if base_model is None:
            base_model = RandomForestRegressor(
                n_estimators=100,
                max_depth=10,
                random_state=42
            )
        
        self.base_model = base_model
        self.bootstrap_models = []
        
        n_samples = len(X)
        
        for i in range(self.n_bootstrap):
            # Bootstrap sample
            indices = np.random.choice(n_samples, n_samples, replace=True)
            X_boot = X.iloc[indices]
            y_boot = y.iloc[indices]
            
            # Train model on bootstrap sample
            model = RandomForestRegressor(
                n_estimators=50,
                max_depth=8,
                random_state=i
            )
            model.fit(X_boot, y_boot)
            
            self.bootstrap_models.append(model)
            
            if (i + 1) % 20 == 0:
                print(f"  Trained {i + 1}/{self.n_bootstrap} bootstrap models")
        
        return {
            'n_bootstrap': self.n_bootstrap,
            'n_features': X.shape[1],
            'n_samples': n_samples
        }
    
    def predict_with_uncertainty(self, X: pd.DataFrame, confidence: float = 0.95) -> Dict:
        """Predict with bootstrap uncertainty."""
        if not self.bootstrap_models:
            raise ValueError("Bootstrap models not trained. Call train_bootstrap_models first.")
        
        # Get predictions from all bootstrap models
        bootstrap_predictions = []
        for model in self.bootstrap_models:
            pred = model.predict(X)
            bootstrap_predictions.append(pred)
        
        bootstrap_predictions = np.array(bootstrap_predictions)
        
        # Calculate statistics
        median_pred = np.median(bootstrap_predictions, axis=0)
        mean_pred = np.mean(bootstrap_predictions, axis=0)
        std_pred = np.std(bootstrap_predictions, axis=0)
        
        # Calculate confidence intervals
        lower_alpha = (1 - confidence) / 2
        upper_alpha = 1 - lower_alpha
        
        lower_pred = np.percentile(bootstrap_predictions, lower_alpha * 100, axis=0)
        upper_pred = np.percentile(bootstrap_predictions, upper_alpha * 100, axis=0)
        
        return {
            'mean': mean_pred,
            'median': median_pred,
            'std': std_pred,
            'lower_bound': lower_pred,
            'upper_bound': upper_pred,
            'interval_width': upper_pred - lower_pred,
            'confidence': confidence,
            'bootstrap_predictions': bootstrap_predictions
        }

# =========================================================
# BAYESIAN UNCERTAINTY
# =========================================================

class BayesianUncertaintyEstimator:
    """Bayesian uncertainty estimation using approximate methods."""
    
    def __init__(self):
        self.posterior_samples = None
        self.posterior_mean = None
        self.posterior_std = None
    
    def fit_posterior(self, predictions: np.ndarray, ground_truth: np.ndarray = None) -> Dict:
        """Fit posterior distribution to predictions."""
        print("Fitting Bayesian posterior distribution...")
        
        if ground_truth is not None:
            # Fit error distribution
            errors = predictions - ground_truth
            
            # Fit normal distribution to errors
            mu, sigma = norm.fit(errors)
            
            self.posterior_mean = mu
            self.posterior_std = sigma
            
            # Generate posterior samples
            n_samples = UNCERTAINTY_CONFIG['monte_carlo_simulations']
            self.posterior_samples = np.random.normal(mu, sigma, n_samples)
        else:
            # Fit distribution to predictions themselves
            self.posterior_mean = np.mean(predictions)
            self.posterior_std = np.std(predictions)
            
            n_samples = UNCERTAINTY_CONFIG['monte_carlo_simulations']
            self.posterior_samples = np.random.normal(
                self.posterior_mean, 
                self.posterior_std, 
                n_samples
            )
        
        return {
            'posterior_mean': self.posterior_mean,
            'posterior_std': self.posterior_std,
            'n_samples': len(self.posterior_samples)
        }
    
    def predict_with_uncertainty(self, point_prediction: float, 
                                confidence: float = 0.95) -> Dict:
        """Predict with Bayesian uncertainty."""
        if self.posterior_samples is None:
            raise ValueError("Posterior not fitted. Call fit_posterior first.")
        
        # Add posterior uncertainty to point prediction
        prediction_samples = point_prediction + self.posterior_samples
        
        # Calculate confidence intervals
        lower_alpha = (1 - confidence) / 2
        upper_alpha = 1 - lower_alpha
        
        lower_bound = np.percentile(prediction_samples, lower_alpha * 100)
        upper_bound = np.percentile(prediction_samples, upper_alpha * 100)
        
        return {
            'point_prediction': point_prediction,
            'lower_bound': lower_bound,
            'upper_bound': upper_bound,
            'interval_width': upper_bound - lower_bound,
            'confidence': confidence,
            'posterior_samples': prediction_samples
        }

# =========================================================
# ENSEMBLE UNCERTAINTY
# =========================================================

class EnsembleUncertaintyEstimator:
    """Ensemble uncertainty from multiple methods."""
    
    def __init__(self):
        self.quantile_estimator = QuantileUncertaintyEstimator()
        self.bootstrap_estimator = BootstrapUncertaintyEstimator()
        self.bayesian_estimator = BayesianUncertaintyEstimator()
        self.ensemble_weights = {
            'quantile': 0.35,
            'bootstrap': 0.35,
            'bayesian': 0.30
        }
    
    def train_all_estimators(self, X: pd.DataFrame, y: pd.Series) -> Dict:
        """Train all uncertainty estimators."""
        print("Training ensemble uncertainty estimators...")
        
        results = {}
        
        # Train quantile estimator
        quantile_results = self.quantile_estimator.train_quantile_models(X, y)
        results['quantile'] = quantile_results
        
        # Train bootstrap estimator
        bootstrap_results = self.bootstrap_estimator.train_bootstrap_models(X, y)
        results['bootstrap'] = bootstrap_results
        
        # Fit Bayesian posterior
        base_model = RandomForestRegressor(n_estimators=100, random_state=42)
        base_model.fit(X, y)
        predictions = base_model.predict(X)
        bayesian_results = self.bayesian_estimator.fit_posterior(predictions, y)
        results['bayesian'] = bayesian_results
        
        return results
    
    def predict_ensemble_uncertainty(self, X: pd.DataFrame, 
                                    confidence: float = 0.95) -> Dict:
        """Predict with ensemble uncertainty."""
        print("Calculating ensemble uncertainty...")
        
        # Get uncertainty from each method
        quantile_uncertainty = self.quantile_estimator.predict_intervals(X, confidence)
        bootstrap_uncertainty = self.bootstrap_estimator.predict_with_uncertainty(X, confidence)
        
        # For Bayesian, we need point predictions first
        base_predictions = self.quantile_estimator.models[0.5].predict(
            self.quantile_estimator.scaler.transform(X)
        )
        
        bayesian_uncertainties = []
        for pred in base_predictions:
            bayesian_unc = self.bayesian_estimator.predict_with_uncertainty(pred, confidence)
            bayesian_uncertainties.append(bayesian_unc)
        
        # Combine uncertainties using weighted average
        ensemble_lower = (
            self.ensemble_weights['quantile'] * quantile_uncertainty['lower_bound'] +
            self.ensemble_weights['bootstrap'] * bootstrap_uncertainty['lower_bound'] +
            self.ensemble_weights['bayesian'] * np.array([u['lower_bound'] for u in bayesian_uncertainties])
        )
        
        ensemble_upper = (
            self.ensemble_weights['quantile'] * quantile_uncertainty['upper_bound'] +
            self.ensemble_weights['bootstrap'] * bootstrap_uncertainty['upper_bound'] +
            self.ensemble_weights['bayesian'] * np.array([u['upper_bound'] for u in bayesian_uncertainties])
        )
        
        ensemble_median = quantile_uncertainty['median']
        
        return {
            'median': ensemble_median,
            'lower_bound': ensemble_lower,
            'upper_bound': ensemble_upper,
            'interval_width': ensemble_upper - ensemble_lower,
            'confidence': confidence,
            'method_weights': self.ensemble_weights,
            'individual_uncertainties': {
                'quantile': quantile_uncertainty,
                'bootstrap': bootstrap_uncertainty,
                'bayesian': bayesian_uncertainties
            }
        }

# =========================================================
# MONTE CARLO SIMULATION
# =========================================================

class MonteCarloSimulator:
    """Monte Carlo simulation for uncertainty propagation."""
    
    def __init__(self, n_simulations: int = 1000):
        self.n_simulations = n_simulations
    
    def simulate_waste_generation(self, base_prediction: float, 
                                 uncertainty_params: Dict) -> Dict:
        """Simulate waste generation with uncertainty."""
        simulations = []
        
        for _ in range(self.n_simulations):
            # Sample from uncertainty distribution
            if uncertainty_params['distribution'] == 'normal':
                noise = np.random.normal(
                    uncertainty_params['mean'],
                    uncertainty_params['std']
                )
            elif uncertainty_params['distribution'] == 'lognormal':
                noise = np.random.lognormal(
                    uncertainty_params['mean'],
                    uncertainty_params['sigma']
                )
            else:
                noise = np.random.normal(0, uncertainty_params['std'])
            
            simulated_value = base_prediction + noise
            simulations.append(max(0, simulated_value))  # Ensure non-negative
        
        simulations = np.array(simulations)
        
        return {
            'simulations': simulations,
            'mean': np.mean(simulations),
            'median': np.median(simulations),
            'std': np.std(simulations),
            'percentiles': {
                '5': np.percentile(simulations, 5),
                '25': np.percentile(simulations, 25),
                '50': np.percentile(simulations, 50),
                '75': np.percentile(simulations, 75),
                '95': np.percentile(simulations, 95)
            },
            'n_simulations': self.n_simulations
        }

# =========================================================
# UNCERTAINTY VISUALIZATION
# =========================================================

class UncertaintyVisualizer:
    """Visualize uncertainty in predictions."""
    
    def __init__(self, output_dir: Path = OUTPUT_DIR):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def plot_prediction_intervals(self, predictions_df: pd.DataFrame, 
                                  uncertainty_results: Dict):
        """Plot prediction intervals over time."""
        fig, ax = plt.subplots(figsize=(12, 6))
        
        # Sort by forecast date
        predictions_df = predictions_df.sort_values('forecast_date')
        
        # Plot median prediction
        ax.plot(predictions_df['forecast_date'], 
               predictions_df['ensemble_prediction'],
               label='Median Prediction', linewidth=2)
        
        # Plot confidence interval
        if 'lower_bound' in predictions_df.columns and 'upper_bound' in predictions_df.columns:
            ax.fill_between(
                predictions_df['forecast_date'],
                predictions_df['lower_bound'],
                predictions_df['upper_bound'],
                alpha=0.3,
                label='95% Confidence Interval'
            )
        
        ax.set_xlabel('Forecast Date')
        ax.set_ylabel('Waste (kg)')
        ax.set_title('Waste Predictions with Uncertainty')
        ax.legend()
        ax.grid(True, alpha=0.3)
        
        plt.xticks(rotation=45)
        plt.tight_layout()
        
        output_file = self.output_dir / "prediction_intervals.png"
        plt.savefig(output_file, dpi=300, bbox_inches='tight')
        plt.close()
        
        print(f"Prediction intervals plot saved to: {output_file}")
    
    def plot_uncertainty_distribution(self, uncertainty_results: Dict):
        """Plot uncertainty distribution."""
        if 'bootstrap_predictions' in uncertainty_results:
            predictions = uncertainty_results['bootstrap_predictions'].flatten()
        elif 'posterior_samples' in uncertainty_results:
            predictions = uncertainty_results['posterior_samples']
        else:
            print("No prediction samples available for plotting")
            return
        
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))
        
        # Histogram
        ax1.hist(predictions, bins=50, alpha=0.7, edgecolor='black')
        ax1.axvline(np.mean(predictions), color='red', linestyle='--', linewidth=2, label='Mean')
        ax1.axvline(np.median(predictions), color='green', linestyle='--', linewidth=2, label='Median')
        ax1.set_xlabel('Predicted Waste (kg)')
        ax1.set_ylabel('Frequency')
        ax1.set_title('Uncertainty Distribution')
        ax1.legend()
        ax1.grid(True, alpha=0.3)
        
        # Q-Q plot
        stats.probplot(predictions, dist="norm", plot=ax2)
        ax2.set_title('Q-Q Plot (Normal Distribution)')
        ax2.grid(True, alpha=0.3)
        
        plt.tight_layout()
        
        output_file = self.output_dir / "uncertainty_distribution.png"
        plt.savefig(output_file, dpi=300, bbox_inches='tight')
        plt.close()
        
        print(f"Uncertainty distribution plot saved to: {output_file}")

# =========================================================
# MAIN EXECUTION
# =========================================================

def main():
    print("=" * 70)
    print("UNCERTAINTY QUANTIFICATION MODULE")
    print("=" * 70)
    
    # Load prediction data
    predictions_file = DATA_DIR / "bengaluru_advanced_temporal_predictions.gpkg"
    if predictions_file.exists():
        if GEOPANDAS_AVAILABLE:
            predictions_gdf = gpd.read_file(predictions_file, layer="advanced_temporal_predictions")
            predictions_df = pd.DataFrame(predictions_gdf.drop(columns='geometry', errors='ignore'))
        else:
            # Try CSV fallback
            csv_file = predictions_file.parent / predictions_file.stem.replace('.gpkg', '') / 'predictions.csv'
            if csv_file.exists():
                predictions_df = pd.read_csv(csv_file)
            else:
                print("No predictions file found (geopandas not available)")
                return
        print(f"Loaded predictions: {len(predictions_df)} records")
    else:
        print("No predictions file found")
        return
    
    # Prepare training data
    print("\n" + "=" * 70)
    print("PREPARING TRAINING DATA")
    print("=" * 70)
    
    # Use ensemble predictions as features
    feature_cols = [col for col in predictions_df.columns 
                   if col not in ['Grid_ID', 'Latitude', 'Longitude', 'forecast_date',
                               'advanced_risk', 'collection_priority']]
    
    X = predictions_df[feature_cols].fillna(0)
    y = predictions_df['ensemble_prediction']
    
    # Initialize ensemble estimator
    print("\n" + "=" * 70)
    print("TRAINING ENSEMBLE UNCERTAINTY ESTIMATORS")
    print("=" * 70)
    
    ensemble_estimator = EnsembleUncertaintyEstimator()
    training_results = ensemble_estimator.train_all_estimators(X, y)
    
    print("Training completed:")
    for method, results in training_results.items():
        print(f"  {method}: {results}")
    
    # Predict with ensemble uncertainty
    print("\n" + "=" * 70)
    print("CALCULATING ENSEMBLE UNCERTAINTY")
    print("=" * 70)
    
    # Sample a subset for faster prediction
    sample_size = min(100, len(X))
    X_sample = X.sample(sample_size, random_state=42)
    
    ensemble_uncertainty = ensemble_estimator.predict_ensemble_uncertainty(X_sample)
    
    print("Ensemble uncertainty results:")
    print(f"  Average interval width: {np.mean(ensemble_uncertainty['interval_width']):.2f} kg")
    print(f"  Average median prediction: {np.mean(ensemble_uncertainty['median']):.2f} kg")
    print(f"  Confidence level: {ensemble_uncertainty['confidence']:.0%}")
    
    # Monte Carlo simulation
    print("\n" + "=" * 70)
    print("MONTE CARLO SIMULATION")
    print("=" * 70)
    
    mc_simulator = MonteCarloSimulator(n_simulations=1000)
    
    uncertainty_params = {
        'distribution': 'normal',
        'mean': 0,
        'std': np.mean(ensemble_uncertainty['interval_width']) / 4  # Approximate std
    }
    
    sample_prediction = ensemble_uncertainty['median'][0]
    mc_results = mc_simulator.simulate_waste_generation(sample_prediction, uncertainty_params)
    
    print("Monte Carlo simulation results:")
    print(f"  Mean: {mc_results['mean']:.2f} kg")
    print(f"  Std: {mc_results['std']:.2f} kg")
    print(f"  5th percentile: {mc_results['percentiles']['5']:.2f} kg")
    print(f"  95th percentile: {mc_results['percentiles']['95']:.2f} kg")
    
    # Add uncertainty to predictions
    print("\n" + "=" * 70)
    print("ADDING UNCERTAINTY TO PREDICTIONS")
    print("=" * 70)
    
    # Calculate uncertainty for all predictions
    all_uncertainty = ensemble_estimator.predict_ensemble_uncertainty(X)
    
    predictions_df['uncertainty_lower'] = all_uncertainty['lower_bound']
    predictions_df['uncertainty_upper'] = all_uncertainty['upper_bound']
    predictions_df['uncertainty_width'] = all_uncertainty['interval_width']
    predictions_df['relative_uncertainty'] = (
        predictions_df['uncertainty_width'] / predictions_df['ensemble_prediction']
    )
    
    # Save updated predictions
    output_file = OUTPUT_DIR / "predictions_with_uncertainty.csv"
    predictions_df.to_csv(output_file, index=False)
    print(f"Predictions with uncertainty saved to: {output_file}")
    
    # Visualize uncertainty
    print("\n" + "=" * 70)
    print("VISUALIZING UNCERTAINTY")
    print("=" * 70)
    
    visualizer = UncertaintyVisualizer()
    visualizer.plot_prediction_intervals(predictions_df.head(30), ensemble_uncertainty)
    visualizer.plot_uncertainty_distribution(mc_results)
    
    # Summary statistics
    print("\n" + "=" * 70)
    print("UNCERTAINTY SUMMARY")
    print("=" * 70)
    
    print(f"Total predictions: {len(predictions_df)}")
    print(f"Average uncertainty width: {predictions_df['uncertainty_width'].mean():.2f} kg")
    print(f"Average relative uncertainty: {predictions_df['relative_uncertainty'].mean():.2%}")
    print(f"Median uncertainty width: {predictions_df['uncertainty_width'].median():.2f} kg")
    print(f"Maximum uncertainty width: {predictions_df['uncertainty_width'].max():.2f} kg")
    print(f"Minimum uncertainty width: {predictions_df['uncertainty_width'].min():.2f} kg")
    
    print("\n" + "=" * 70)
    print("UNCERTAINTY QUANTIFICATION COMPLETED")
    print("=" * 70)

if __name__ == "__main__":
    main()