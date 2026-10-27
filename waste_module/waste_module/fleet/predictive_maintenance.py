"""
=========================================================
Urban Predictive Intelligence System
Predictive Maintenance Module for Fleet Management
=========================================================

Predictive maintenance for waste collection vehicles:
- Vehicle health monitoring and prediction
- Maintenance scheduling optimization
- Route-based maintenance planning
- Fuel consumption prediction
- Tire wear and replacement forecasting
- Engine performance monitoring
- Cost optimization for maintenance
- Integration with route optimization

Replaces the missing fleet management capability.
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

# ML Libraries
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor, RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, mean_squared_error
import joblib

# Try to import XGBoost (optional)
try:
    import xgboost as xgb
    XGBOOST_AVAILABLE = True
except ImportError:
    XGBOOST_AVAILABLE = False
    print("XGBoost not available - using scikit-learn only")

# =========================================================
# CONFIGURATION
# =========================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "waste_module" / "data" / "processed"
FLEET_DIR = DATA_DIR / "fleet"
FLEET_DIR.mkdir(parents=True, exist_ok=True)

MODEL_DIR = PROJECT_ROOT / "waste_module" / "models"
MODEL_DIR.mkdir(parents=True, exist_ok=True)

# Fleet configuration
FLEET_CONFIG = {
    'total_vehicles': 50,
    'vehicle_types': ['compactor', 'tipper', 'container'],
    'maintenance_intervals': {
        'routine': 30,  # days
        'major': 180,  # days
        'tire_replacement': 90,  # days
        'oil_change': 45  # days
    },
    'cost_estimates': {
        'routine_maintenance': 5000,  # INR
        'major_maintenance': 25000,
        'tire_replacement': 15000,
        'oil_change': 3000,
        'breakdown_repair': 50000
    }
}

# =========================================================
# SYNTHETIC FLEET DATA GENERATOR
# =========================================================

def generate_synthetic_fleet_data(num_vehicles: int = 50, days: int = 365) -> pd.DataFrame:
    """Generate synthetic fleet data for predictive maintenance."""
    print("Generating synthetic fleet data...")
    
    vehicle_ids = [f"VH{i:04d}" for i in range(1, num_vehicles + 1)]
    vehicle_types = np.random.choice(FLEET_CONFIG['vehicle_types'], num_vehicles)
    
    data = []
    
    for vehicle_id, vehicle_type in zip(vehicle_ids, vehicle_types):
        # Base vehicle characteristics
        manufacture_year = np.random.randint(2018, 2024)
        mileage = np.random.randint(10000, 150000)
        engine_hours = mileage / 30  # Approximate
        
        for day in range(days):
            date = datetime.now() - timedelta(days=days - day)
            
            # Daily operational data
            daily_mileage = np.random.randint(50, 200)
            daily_fuel_consumption = daily_mileage * np.random.uniform(0.3, 0.5)  # liters per km
            daily_engine_hours = daily_mileage / 30
            
            # Component health (degrading over time)
            degradation_factor = (day / days) * 0.3
            
            engine_health = max(70, 100 - degradation_factor * 30 - np.random.normal(0, 5))
            transmission_health = max(75, 100 - degradation_factor * 25 - np.random.normal(0, 4))
            brake_health = max(65, 100 - degradation_factor * 35 - np.random.normal(0, 6))
            tire_health = max(60, 100 - degradation_factor * 40 - np.random.normal(0, 7))
            
            # Maintenance events
            last_routine_maintenance = np.random.randint(0, 45)
            last_major_maintenance = np.random.randint(0, 180)
            last_tire_replacement = np.random.randint(0, 90)
            
            # Maintenance needed flags
            needs_routine = last_routine_maintenance >= FLEET_CONFIG['maintenance_intervals']['routine'] - 5
            needs_major = last_major_maintenance >= FLEET_CONFIG['maintenance_intervals']['major'] - 10
            needs_tires = last_tire_replacement >= FLEET_CONFIG['maintenance_intervals']['tire_replacement'] - 7
            
            # Failure probability
            failure_probability = (
                (100 - engine_health) / 100 * 0.3 +
                (100 - transmission_health) / 100 * 0.25 +
                (100 - brake_health) / 100 * 0.2 +
                (100 - tire_health) / 100 * 0.25
            )
            
            # Actual failure event
            has_failure = np.random.random() < failure_probability * 0.1  # Low daily probability
            
            data.append({
                'vehicle_id': vehicle_id,
                'vehicle_type': vehicle_type,
                'date': date,
                'mileage': mileage + daily_mileage,
                'engine_hours': engine_hours + daily_engine_hours,
                'daily_mileage': daily_mileage,
                'fuel_consumption_liters': daily_fuel_consumption,
                'engine_health_percent': engine_health,
                'transmission_health_percent': transmission_health,
                'brake_health_percent': brake_health,
                'tire_health_percent': tire_health,
                'days_since_routine_maintenance': last_routine_maintenance,
                'days_since_major_maintenance': last_major_maintenance,
                'days_since_tire_replacement': last_tire_replacement,
                'needs_routine_maintenance': int(needs_routine),
                'needs_major_maintenance': int(needs_major),
                'needs_tire_replacement': int(needs_tires),
                'has_failure': int(has_failure),
                'manufacture_year': manufacture_year,
                'vehicle_age_years': datetime.now().year - manufacture_year
            })
            
            # Update counters
            mileage += daily_mileage
            engine_hours += daily_engine_hours
            last_routine_maintenance += 1
            last_major_maintenance += 1
            last_tire_replacement += 1
    
    df = pd.DataFrame(data)
    
    # Save fleet data
    fleet_file = FLEET_DIR / "fleet_data.csv"
    df.to_csv(fleet_file, index=False)
    print(f"Generated {len(df)} fleet records for {num_vehicles} vehicles")
    print(f"Saved to: {fleet_file}")
    
    return df

# =========================================================
# MAINTENANCE PREDICTOR
# =========================================================

class MaintenancePredictor:
    """Predictive maintenance model for fleet vehicles."""
    
    def __init__(self):
        self.models = {}
        self.scalers = {}
        self.feature_columns = []
    
    def prepare_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Prepare features for maintenance prediction."""
        features = df.copy()
        
        # Ensure date column exists
        if 'date' not in features.columns:
            features['date'] = pd.to_datetime('now')
        
        # Rolling averages for health metrics
        features = features.sort_values(['vehicle_id', 'date'])
        
        for health_col in ['engine_health_percent', 'transmission_health_percent', 
                           'brake_health_percent', 'tire_health_percent']:
            features[f'{health_col}_rolling_7'] = (
                features.groupby('vehicle_id')[health_col]
                .transform(lambda x: x.rolling(7, min_periods=1).mean())
            )
            features[f'{health_col}_rolling_30'] = (
                features.groupby('vehicle_id')[health_col]
                .transform(lambda x: x.rolling(30, min_periods=1).mean())
            )
        
        # Rate of change
        for health_col in ['engine_health_percent', 'transmission_health_percent', 
                           'brake_health_percent', 'tire_health_percent']:
            features[f'{health_col}_rate'] = (
                features.groupby('vehicle_id')[health_col]
                .transform(lambda x: x.diff())
            )
        
        # Interaction features
        features['engine_transmission_combo'] = (
            features['engine_health_percent'] * features['transmission_health_percent'] / 10000
        )
        
        features['brake_tire_combo'] = (
            features['brake_health_percent'] * features['tire_health_percent'] / 10000
        )
        
        # Maintenance urgency scores
        features['routine_urgency'] = (
            features['days_since_routine_maintenance'] / 
            FLEET_CONFIG['maintenance_intervals']['routine']
        )
        
        features['major_urgency'] = (
            features['days_since_major_maintenance'] / 
            FLEET_CONFIG['maintenance_intervals']['major']
        )
        
        features['tire_urgency'] = (
            features['days_since_tire_replacement'] / 
            FLEET_CONFIG['maintenance_intervals']['tire_replacement']
        )
        
        # Vehicle age impact
        features['age_factor'] = features['vehicle_age_years'] / 10.0
        
        # Usage intensity
        features['usage_intensity'] = features['daily_mileage'] / 100.0
        
        return features
    
    def train_failure_predictor(self, df: pd.DataFrame) -> Dict:
        """Train model to predict vehicle failures."""
        print("Training failure prediction model...")
        
        # Prepare features
        features_df = self.prepare_features(df)
        
        # Select feature columns
        feature_cols = [col for col in features_df.columns 
                       if col not in ['vehicle_id', 'vehicle_type', 'date', 'has_failure']]
        
        # Handle missing values
        X = features_df[feature_cols].fillna(0)
        y = features_df['has_failure']
        
        # Scale features
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)
        
        # Train model (use scikit-learn only)
        model = RandomForestClassifier(
            n_estimators=100,
            max_depth=10,
            class_weight='balanced',
            random_state=42
        )
        
        X_train, X_test, y_train, y_test = train_test_split(
            X_scaled, y, test_size=0.2, random_state=42
        )
        
        model.fit(X_train, y_train)
        
        # Evaluate
        train_score = model.score(X_train, y_train)
        test_score = model.score(X_test, y_test)
        
        # Save model and scaler
        self.models['failure'] = model
        self.scalers['failure'] = scaler
        self.feature_columns = feature_cols
        
        return {
            'train_accuracy': train_score,
            'test_accuracy': test_score,
            'n_features': len(feature_cols)
        }
    
    def predict_failure_probability(self, vehicle_data: Dict) -> float:
        """Predict failure probability for a vehicle."""
        if 'failure' not in self.models:
            return 0.0
        
        # Convert to DataFrame
        df = pd.DataFrame([vehicle_data])
        features_df = self.prepare_features(df)
        
        # Select and scale features
        X = features_df[self.feature_columns].fillna(0)
        X_scaled = self.scalers['failure'].transform(X)
        
        # Predict probability
        probability = self.models['failure'].predict_proba(X_scaled)[0, 1]
        
        return probability
    
    def predict_component_health(self, df: pd.DataFrame, component: str) -> Dict:
        """Predict future health of specific component."""
        print(f"Predicting {component} health...")
        
        # Prepare time series data for component
        component_data = df[['vehicle_id', 'date', f'{component}_health_percent']].copy()
        component_data = component_data.sort_values(['vehicle_id', 'date'])
        
        # Simple trend prediction using linear regression
        predictions = {}
        
        for vehicle_id in component_data['vehicle_id'].unique():
            vehicle_data = component_data[component_data['vehicle_id'] == vehicle_id]
            
            if len(vehicle_data) < 10:
                continue
            
            # Calculate trend
            recent_health = vehicle_data.tail(30)[f'{component}_health_percent'].values
            trend = np.polyfit(range(len(recent_health)), recent_health, 1)[0]
            
            # Predict health in 7, 14, 30 days
            current_health = recent_health[-1]
            
            predictions[vehicle_id] = {
                'current_health': current_health,
                'predicted_7_day': max(0, current_health + trend * 7),
                'predicted_14_day': max(0, current_health + trend * 14),
                'predicted_30_day': max(0, current_health + trend * 30),
                'trend_rate': trend,
                'health_declining': trend < -0.1
            }
        
        return predictions

# =========================================================
# MAINTENANCE SCHEDULER
# =========================================================

class MaintenanceScheduler:
    """Optimize maintenance scheduling based on predictions."""
    
    def __init__(self, predictor: MaintenancePredictor):
        self.predictor = predictor
        self.schedule = []
    
    def generate_maintenance_schedule(self, fleet_data: pd.DataFrame, 
                                     horizon_days: int = 30) -> List[Dict]:
        """Generate optimized maintenance schedule."""
        print("Generating maintenance schedule...")
        
        schedule = []
        
        # Get current vehicle status
        current_status = fleet_data.groupby('vehicle_id').last().reset_index()
        
        for _, vehicle in current_status.iterrows():
            vehicle_info = {
                'vehicle_id': vehicle['vehicle_id'],
                'vehicle_type': vehicle['vehicle_type'],
                'current_mileage': vehicle['mileage'],
                'current_engine_health': vehicle['engine_health_percent'],
                'current_transmission_health': vehicle['transmission_health_percent'],
                'current_brake_health': vehicle['brake_health_percent'],
                'current_tire_health': vehicle['tire_health_percent']
            }
            
            # Predict failure probability
            failure_prob = self.predictor.predict_failure_probability(vehicle_info)
            
            # Determine maintenance needs
            maintenance_needs = []
            
            # Routine maintenance
            if vehicle['days_since_routine_maintenance'] >= FLEET_CONFIG['maintenance_intervals']['routine'] - 7:
                urgency = vehicle['days_since_routine_maintenance'] / FLEET_CONFIG['maintenance_intervals']['routine']
                maintenance_needs.append({
                    'type': 'routine',
                    'urgency': urgency,
                    'estimated_cost': FLEET_CONFIG['cost_estimates']['routine_maintenance'],
                    'estimated_duration_hours': 4
                })
            
            # Major maintenance
            if vehicle['days_since_major_maintenance'] >= FLEET_CONFIG['maintenance_intervals']['major'] - 14:
                urgency = vehicle['days_since_major_maintenance'] / FLEET_CONFIG['maintenance_intervals']['major']
                maintenance_needs.append({
                    'type': 'major',
                    'urgency': urgency,
                    'estimated_cost': FLEET_CONFIG['cost_estimates']['major_maintenance'],
                    'estimated_duration_hours': 24
                })
            
            # Tire replacement
            if vehicle['days_since_tire_replacement'] >= FLEET_CONFIG['maintenance_intervals']['tire_replacement'] - 7:
                urgency = vehicle['days_since_tire_replacement'] / FLEET_CONFIG['maintenance_intervals']['tire_replacement']
                maintenance_needs.append({
                    'type': 'tire_replacement',
                    'urgency': urgency,
                    'estimated_cost': FLEET_CONFIG['cost_estimates']['tire_replacement'],
                    'estimated_duration_hours': 8
                })
            
            # Component-based maintenance
            if vehicle['engine_health_percent'] < 80:
                maintenance_needs.append({
                    'type': 'engine_service',
                    'urgency': (100 - vehicle['engine_health_percent']) / 100,
                    'estimated_cost': FLEET_CONFIG['cost_estimates']['routine_maintenance'] * 1.5,
                    'estimated_duration_hours': 6
                })
            
            if vehicle['brake_health_percent'] < 75:
                maintenance_needs.append({
                    'type': 'brake_service',
                    'urgency': (100 - vehicle['brake_health_percent']) / 100,
                    'estimated_cost': FLEET_CONFIG['cost_estimates']['routine_maintenance'] * 1.2,
                    'estimated_duration_hours': 3
                })
            
            if vehicle['tire_health_percent'] < 70:
                maintenance_needs.append({
                    'type': 'tire_replacement',
                    'urgency': (100 - vehicle['tire_health_percent']) / 100,
                    'estimated_cost': FLEET_CONFIG['cost_estimates']['tire_replacement'],
                    'estimated_duration_hours': 8
                })
            
            # Schedule maintenance based on urgency
            for need in maintenance_needs:
                urgency = need['urgency']
                
                if urgency >= 0.9:  # Critical
                    scheduled_date = datetime.now() + timedelta(days=1)
                elif urgency >= 0.7:  # High
                    scheduled_date = datetime.now() + timedelta(days=3)
                elif urgency >= 0.5:  # Medium
                    scheduled_date = datetime.now() + timedelta(days=7)
                else:  # Low
                    scheduled_date = datetime.now() + timedelta(days=14)
                
                schedule.append({
                    'vehicle_id': vehicle['vehicle_id'],
                    'vehicle_type': vehicle['vehicle_type'],
                    'maintenance_type': need['type'],
                    'scheduled_date': scheduled_date,
                    'urgency': urgency,
                    'estimated_cost': need['estimated_cost'],
                    'estimated_duration_hours': need['estimated_duration_hours'],
                    'failure_probability': failure_prob,
                    'current_engine_health': vehicle['engine_health_percent'],
                    'current_transmission_health': vehicle['transmission_health_percent'],
                    'current_brake_health': vehicle['brake_health_percent'],
                    'current_tire_health': vehicle['tire_health_percent']
                })
        
        # Sort schedule by urgency and date
        schedule.sort(key=lambda x: (-x['urgency'], x['scheduled_date']))
        
        return schedule
    
    def optimize_schedule(self, schedule: List[Dict], available_mechanics: int = 5) -> List[Dict]:
        """Optimize schedule considering resource constraints."""
        print("Optimizing maintenance schedule...")
        
        # Group by date
        schedule_by_date = {}
        for item in schedule:
            date_str = item['scheduled_date'].strftime('%Y-%m-%d')
            if date_str not in schedule_by_date:
                schedule_by_date[date_str] = []
            schedule_by_date[date_str].append(item)
        
        # Limit daily capacity
        optimized_schedule = []
        for date_str, items in schedule_by_date.items():
            # Sort by urgency within each day
            items.sort(key=lambda x: -x['urgency'])
            
            # Take top items based on mechanic availability
            daily_items = items[:available_mechanics]
            optimized_schedule.extend(daily_items)
        
        return optimized_schedule

# =========================================================
# COST OPTIMIZER
# =========================================================

class CostOptimizer:
    """Optimize maintenance costs and operational efficiency."""
    
    def __init__(self):
        self.cost_history = []
    
    def calculate_total_maintenance_cost(self, schedule: List[Dict]) -> Dict:
        """Calculate total maintenance costs for a schedule."""
        total_cost = 0
        cost_breakdown = {}
        
        for item in schedule:
            cost = item['estimated_cost']
            maintenance_type = item['maintenance_type']
            
            total_cost += cost
            
            if maintenance_type not in cost_breakdown:
                cost_breakdown[maintenance_type] = 0
            cost_breakdown[maintenance_type] += cost
        
        return {
            'total_cost': total_cost,
            'cost_breakdown': cost_breakdown,
            'average_cost_per_vehicle': total_cost / len(set(item['vehicle_id'] for item in schedule)) if schedule else 0
        }
    
    def predict_breakdown_savings(self, schedule: List[Dict]) -> Dict:
        """Predict cost savings from preventive maintenance."""
        prevented_breakdowns = 0
        savings = 0
        
        for item in schedule:
            # If high urgency maintenance is scheduled, it likely prevents breakdown
            if item['urgency'] >= 0.8:
                prevented_breakdowns += 1
                savings += FLEET_CONFIG['cost_estimates']['breakdown_repair'] - item['estimated_cost']
        
        return {
            'prevented_breakdowns': prevented_breakdowns,
            'estimated_savings': max(0, savings),
            'roi_percentage': (savings / self.calculate_total_maintenance_cost(schedule)['total_cost'] * 100) if schedule else 0
        }
    
    def calculate_downtime_cost(self, schedule: List[Dict], daily_revenue_per_vehicle: float = 5000) -> Dict:
        """Calculate downtime cost for scheduled maintenance."""
        total_downtime_hours = sum(item['estimated_duration_hours'] for item in schedule)
        total_downtime_days = total_downtime_hours / 8  # Assuming 8-hour workday
        
        downtime_cost = total_downtime_days * daily_revenue_per_vehicle
        
        return {
            'total_downtime_hours': total_downtime_hours,
            'total_downtime_days': total_downtime_days,
            'downtime_cost': downtime_cost,
            'average_downtime_per_maintenance': total_downtime_hours / len(schedule) if schedule else 0
        }

# =========================================================
# MAIN EXECUTION
# =========================================================

def main():
    print("=" * 70)
    print("PREDICTIVE MAINTENANCE MODULE")
    print("=" * 70)
    
    # Generate or load fleet data
    fleet_file = FLEET_DIR / "fleet_data.csv"
    if fleet_file.exists():
        print(f"Loading existing fleet data from {fleet_file}")
        fleet_data = pd.read_csv(fleet_file)
    else:
        print("Generating synthetic fleet data...")
        fleet_data = generate_synthetic_fleet_data(num_vehicles=50, days=365)
    
    print(f"Fleet data: {len(fleet_data)} records")
    print(f"Vehicles: {fleet_data['vehicle_id'].nunique()}")
    print(f"Vehicle types: {fleet_data['vehicle_type'].value_counts().to_dict()}")
    
    # Initialize predictor
    predictor = MaintenancePredictor()
    
    # Train failure predictor
    print("\n" + "=" * 70)
    print("TRAINING FAILURE PREDICTION MODEL")
    print("=" * 70)
    
    training_results = predictor.train_failure_predictor(fleet_data)
    
    print(f"Training completed:")
    print(f"  Train Accuracy: {training_results['train_accuracy']:.3f}")
    print(f"  Test Accuracy: {training_results['test_accuracy']:.3f}")
    print(f"  Features: {training_results['n_features']}")
    
    # Generate maintenance schedule
    print("\n" + "=" * 70)
    print("GENERATING MAINTENANCE SCHEDULE")
    print("=" * 70)
    
    scheduler = MaintenanceScheduler(predictor)
    schedule = scheduler.generate_maintenance_schedule(fleet_data, horizon_days=30)
    
    print(f"Generated {len(schedule)} maintenance items")
    
    # Optimize schedule
    optimized_schedule = scheduler.optimize_schedule(schedule, available_mechanics=5)
    print(f"Optimized to {len(optimized_schedule)} maintenance items (resource constrained)")
    
    # Cost analysis
    print("\n" + "=" * 70)
    print("COST ANALYSIS")
    print("=" * 70)
    
    cost_optimizer = CostOptimizer()
    
    cost_analysis = cost_optimizer.calculate_total_maintenance_cost(optimized_schedule)
    print(f"Total Maintenance Cost: INR {cost_analysis['total_cost']:,.2f}")
    print(f"Average Cost per Vehicle: INR {cost_analysis['average_cost_per_vehicle']:,.2f}")
    print("\nCost Breakdown:")
    for maint_type, cost in cost_analysis['cost_breakdown'].items():
        print(f"  {maint_type}: INR {cost:,.2f}")
    
    savings_analysis = cost_optimizer.predict_breakdown_savings(optimized_schedule)
    print(f"\nBreakdown Prevention Analysis:")
    print(f"  Prevented Breakdowns: {savings_analysis['prevented_breakdowns']}")
    print(f"  Estimated Savings: INR {savings_analysis['estimated_savings']:,.2f}")
    print(f"  ROI: {savings_analysis['roi_percentage']:.1f}%")
    
    downtime_analysis = cost_optimizer.calculate_downtime_cost(optimized_schedule)
    print(f"\nDowntime Analysis:")
    print(f"  Total Downtime Hours: {downtime_analysis['total_downtime_hours']:.1f}")
    print(f"  Total Downtime Days: {downtime_analysis['total_downtime_days']:.1f}")
    print(f"  Downtime Cost: INR {downtime_analysis['downtime_cost']:,.2f}")
    
    # Save schedule
    schedule_file = FLEET_DIR / "maintenance_schedule.csv"
    schedule_df = pd.DataFrame(optimized_schedule)
    schedule_df.to_csv(schedule_file, index=False)
    print(f"\nMaintenance schedule saved to: {schedule_file}")
    
    # Save models
    model_file = MODEL_DIR / "maintenance_predictor.joblib"
    joblib.dump(predictor, model_file)
    print(f"Predictive models saved to: {model_file}")
    
    print("\n" + "=" * 70)
    print("PREDICTIVE MAINTENANCE COMPLETED")
    print("=" * 70)

if __name__ == "__main__":
    main()