"""
=========================================================
Urban Predictive Intelligence System
Scenario Analysis and What-If Capabilities Module
=========================================================

Advanced scenario analysis and what-if modeling:
- Scenario definition and management
- Parameter sensitivity analysis
- Multi-variable what-if simulations
- Event impact scenarios
- Weather scenario modeling
- Policy intervention scenarios
- Comparative scenario analysis
- Scenario optimization
- Risk scenario assessment
- Decision support system

Replaces the missing scenario analysis capability.
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

# Optimization and sensitivity analysis
from scipy.optimize import minimize
from scipy.stats import uniform, norm
import matplotlib.pyplot as plt
import seaborn as sns

# =========================================================
# CONFIGURATION
# =========================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "waste_module" / "data" / "processed"
SCENARIO_DIR = DATA_DIR / "scenarios"
SCENARIO_DIR.mkdir(parents=True, exist_ok=True)

# Scenario configuration
SCENARIO_CONFIG = {
    'default_horizon_days': 30,
    'sensitivity_samples': 1000,
    'scenario_types': [
        'baseline', 'optimistic', 'pessimistic', 
        'high_event', 'low_event', 'extreme_weather',
        'policy_intervention', 'capacity_expansion'
    ]
}

# =========================================================
# SCENARIO DEFINITION
# =========================================================

class Scenario:
    """Base class for defining analysis scenarios."""
    
    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description
        self.parameters = {}
        self.results = {}
        self.created_at = datetime.now()
    
    def set_parameter(self, parameter_name: str, value: float, range: Tuple[float, float] = None):
        """Set a scenario parameter."""
        self.parameters[parameter_name] = {
            'value': value,
            'range': range or (value * 0.8, value * 1.2)
        }
    
    def get_parameter(self, parameter_name: str) -> Optional[float]:
        """Get a scenario parameter value."""
        if parameter_name in self.parameters:
            return self.parameters[parameter_name]['value']
        return None
    
    def to_dict(self) -> Dict:
        """Convert scenario to dictionary."""
        return {
            'name': self.name,
            'description': self.description,
            'parameters': self.parameters,
            'results': self.results,
            'created_at': self.created_at.isoformat()
        }

# =========================================================
# SCENARIO MANAGER
# =========================================================

class ScenarioManager:
    """Manage multiple analysis scenarios."""
    
    def __init__(self):
        self.scenarios = {}
        self.scenario_file = SCENARIO_DIR / "scenario_definitions.json"
        self.load_scenarios()
    
    def create_scenario(self, name: str, description: str) -> Scenario:
        """Create a new scenario."""
        scenario = Scenario(name, description)
        self.scenarios[name] = scenario
        self.save_scenarios()
        return scenario
    
    def get_scenario(self, name: str) -> Optional[Scenario]:
        """Get a scenario by name."""
        return self.scenarios.get(name)
    
    def list_scenarios(self) -> List[str]:
        """List all scenario names."""
        return list(self.scenarios.keys())
    
    def delete_scenario(self, name: str) -> bool:
        """Delete a scenario."""
        if name in self.scenarios:
            del self.scenarios[name]
            self.save_scenarios()
            return True
        return False
    
    def save_scenarios(self):
        """Save scenarios to file."""
        scenarios_data = {
            name: scenario.to_dict()
            for name, scenario in self.scenarios.items()
        }
        
        with open(self.scenario_file, 'w') as f:
            json.dump(scenarios_data, f, indent=2, default=str)
    
    def load_scenarios(self):
        """Load scenarios from file."""
        if self.scenario_file.exists():
            with open(self.scenario_file, 'r') as f:
                scenarios_data = json.load(f)
            
            for name, data in scenarios_data.items():
                scenario = Scenario(data['name'], data['description'])
                scenario.parameters = data['parameters']
                scenario.results = data['results']
                scenario.created_at = datetime.fromisoformat(data['created_at'])
                self.scenarios[name] = scenario

# =========================================================
# SENSITIVITY ANALYSIS
# =========================================================

class SensitivityAnalyzer:
    """Perform sensitivity analysis on model parameters."""
    
    def __init__(self):
        self.sensitivity_results = {}
    
    def one_at_a_time_sensitivity(self, base_prediction: float, 
                                 parameters: Dict, 
                                 parameter_ranges: Dict,
                                 n_samples: int = 100) -> Dict:
        """Perform one-at-a-time sensitivity analysis."""
        print("Performing one-at-a-time sensitivity analysis...")
        
        sensitivity_data = {}
        
        for param_name, base_value in parameters.items():
            if param_name not in parameter_ranges:
                continue
            
            min_val, max_val = parameter_ranges[param_name]
            test_values = np.linspace(min_val, max_val, n_samples)
            
            predictions = []
            for test_value in test_values:
                # Copy parameters and modify one
                test_params = parameters.copy()
                test_params[param_name] = test_value
                
                # Calculate prediction (simplified - would use actual model)
                prediction = self._calculate_prediction(base_prediction, test_params)
                predictions.append(prediction)
            
            # Calculate sensitivity metrics
            sensitivity = np.std(predictions) / np.mean(predictions) if np.mean(predictions) > 0 else 0
            
            sensitivity_data[param_name] = {
                'base_value': base_value,
                'test_values': test_values.tolist(),
                'predictions': predictions,
                'sensitivity': sensitivity,
                'min_prediction': min(predictions),
                'max_prediction': max(predictions),
                'prediction_range': max(predictions) - min(predictions)
            }
        
        self.sensitivity_results['one_at_a_time'] = sensitivity_data
        
        return sensitivity_data
    
    def monte_carlo_sensitivity(self, base_prediction: float,
                              parameters: Dict,
                              parameter_distributions: Dict,
                              n_samples: int = 1000) -> Dict:
        """Perform Monte Carlo sensitivity analysis."""
        print(f"Performing Monte Carlo sensitivity analysis ({n_samples} samples)...")
        
        # Generate parameter samples
        parameter_samples = {}
        for param_name, dist_config in parameter_distributions.items():
            dist_type = dist_config['type']
            dist_params = dist_config['params']
            
            if dist_type == 'uniform':
                samples = np.random.uniform(
                    dist_params['min'], 
                    dist_params['max'], 
                    n_samples
                )
            elif dist_type == 'normal':
                samples = np.random.normal(
                    dist_params['mean'], 
                    dist_params['std'], 
                    n_samples
                )
            else:
                samples = np.full(n_samples, parameters.get(param_name, 1.0))
            
            parameter_samples[param_name] = samples
        
        # Calculate predictions for all samples
        predictions = []
        for i in range(n_samples):
            sample_params = {
                param_name: parameter_samples[param_name][i]
                for param_name in parameter_samples
            }
            
            prediction = self._calculate_prediction(base_prediction, sample_params)
            predictions.append(prediction)
        
        predictions = np.array(predictions)
        
        # Calculate sensitivity metrics
        sensitivity_data = {
            'mean_prediction': np.mean(predictions),
            'std_prediction': np.std(predictions),
            'min_prediction': np.min(predictions),
            'max_prediction': np.max(predictions),
            'percentiles': {
                '5': np.percentile(predictions, 5),
                '25': np.percentile(predictions, 25),
                '50': np.percentile(predictions, 50),
                '75': np.percentile(predictions, 75),
                '95': np.percentile(predictions, 95)
            },
            'n_samples': n_samples,
            'parameter_samples': {k: v.tolist() for k, v in parameter_samples.items()},
            'predictions': predictions.tolist()
        }
        
        self.sensitivity_results['monte_carlo'] = sensitivity_data
        
        return sensitivity_data
    
    def _calculate_prediction(self, base_prediction: float, parameters: Dict) -> float:
        """Calculate prediction with modified parameters (simplified)."""
        # This is a simplified calculation - in practice would use the actual model
        # Assume parameters are multipliers
        total_multiplier = 1.0
        
        for param_name, value in parameters.items():
            if isinstance(value, (int, float)):
                total_multiplier *= value
        
        return base_prediction * total_multiplier

# =========================================================
# WHAT-IF SIMULATOR
# =========================================================

class WhatIfSimulator:
    """Perform what-if scenario simulations."""
    
    def __init__(self):
        self.simulation_results = {}
    
    def simulate_event_scenario(self, base_predictions: pd.DataFrame,
                              event_intensity: float,
                              event_duration_days: int,
                              affected_grids: List[str] = None) -> Dict:
        """Simulate event impact scenario."""
        print(f"Simulating event scenario (intensity: {event_intensity}, duration: {event_duration_days} days)")
        
        simulated_predictions = base_predictions.copy()
        
        # Apply event impact
        if affected_grids is None:
            # Apply to all grids
            mask = simulated_predictions['Grid_ID'].isin(simulated_predictions['Grid_ID'])
        else:
            mask = simulated_predictions['Grid_ID'].isin(affected_grids)
        
        # Calculate event impact
        event_multiplier = 1.0 + (event_intensity - 1.0) * 0.5
        
        # Apply to affected days
        simulated_predictions.loc[mask, 'simulated_waste'] = (
            simulated_predictions.loc[mask, 'ensemble_prediction'] * event_multiplier
        )
        
        # Calculate change
        simulated_predictions['waste_change'] = (
            simulated_predictions['simulated_waste'] - simulated_predictions['ensemble_prediction']
        )
        simulated_predictions['waste_change_percentage'] = (
            (simulated_predictions['waste_change'] / simulated_predictions['ensemble_prediction']) * 100
        )
        
        results = {
            'event_intensity': event_intensity,
            'event_duration_days': event_duration_days,
            'affected_grids_count': mask.sum(),
            'total_waste_increase': simulated_predictions['waste_change'].sum(),
            'average_waste_increase_percentage': simulated_predictions['waste_change_percentage'].mean(),
            'simulated_predictions': simulated_predictions
        }
        
        self.simulation_results['event_scenario'] = results
        
        return results
    
    def simulate_weather_scenario(self, base_predictions: pd.DataFrame,
                                weather_condition: str,
                                severity: float) -> Dict:
        """Simulate weather impact scenario."""
        print(f"Simulating weather scenario (condition: {weather_condition}, severity: {severity})")
        
        simulated_predictions = base_predictions.copy()
        
        # Define weather impact factors
        weather_impacts = {
            'extreme_heat': {'multiplier': 1.15, 'severity_sensitivity': 0.1},
            'heavy_rain': {'multiplier': 0.85, 'severity_sensitivity': 0.05},
            'normal': {'multiplier': 1.0, 'severity_sensitivity': 0.0},
            'storm': {'multiplier': 0.9, 'severity_sensitivity': 0.1}
        }
        
        weather_config = weather_impacts.get(weather_condition, weather_impacts['normal'])
        
        # Calculate weather impact
        severity_impact = severity * weather_config['severity_sensitivity']
        weather_multiplier = weather_config['multiplier'] + severity_impact
        
        # Apply weather impact
        simulated_predictions['simulated_waste'] = (
            simulated_predictions['ensemble_prediction'] * weather_multiplier
        )
        
        # Calculate change
        simulated_predictions['waste_change'] = (
            simulated_predictions['simulated_waste'] - simulated_predictions['ensemble_prediction']
        )
        
        results = {
            'weather_condition': weather_condition,
            'severity': severity,
            'weather_multiplier': weather_multiplier,
            'total_waste_change': simulated_predictions['waste_change'].sum(),
            'average_waste_change': simulated_predictions['waste_change'].mean(),
            'simulated_predictions': simulated_predictions
        }
        
        self.simulation_results['weather_scenario'] = results
        
        return results
    
    def simulate_policy_scenario(self, base_predictions: pd.DataFrame,
                                policy_type: str,
                                policy_strength: float) -> Dict:
        """Simulate policy intervention scenario."""
        print(f"Simulating policy scenario (type: {policy_type}, strength: {policy_strength})")
        
        simulated_predictions = base_predictions.copy()
        
        # Define policy impacts
        policy_impacts = {
            'waste_reduction_campaign': {'multiplier': 0.9, 'efficiency': 0.5},
            'improved_collection_frequency': {'multiplier': 0.85, 'efficiency': 0.7},
            'public_awareness_program': {'multiplier': 0.95, 'efficiency': 0.3},
            'recycling_incentive': {'multiplier': 0.92, 'efficiency': 0.4}
        }
        
        policy_config = policy_impacts.get(policy_type, policy_impacts['waste_reduction_campaign'])
        
        # Calculate policy impact
        policy_effectiveness = policy_strength * policy_config['efficiency']
        policy_multiplier = 1.0 - (1.0 - policy_config['multiplier']) * policy_effectiveness
        
        # Apply policy impact
        simulated_predictions['simulated_waste'] = (
            simulated_predictions['ensemble_prediction'] * policy_multiplier
        )
        
        # Calculate change
        simulated_predictions['waste_reduction'] = (
            simulated_predictions['ensemble_prediction'] - simulated_predictions['simulated_waste']
        )
        simulated_predictions['waste_reduction_percentage'] = (
            (simulated_predictions['waste_reduction'] / simulated_predictions['ensemble_prediction']) * 100
        )
        
        results = {
            'policy_type': policy_type,
            'policy_strength': policy_strength,
            'policy_multiplier': policy_multiplier,
            'total_waste_reduction': simulated_predictions['waste_reduction'].sum(),
            'average_waste_reduction_percentage': simulated_predictions['waste_reduction_percentage'].mean(),
            'simulated_predictions': simulated_predictions
        }
        
        self.simulation_results['policy_scenario'] = results
        
        return results

# =========================================================
# COMPARATIVE SCENARIO ANALYSIS
# =========================================================

class ComparativeScenarioAnalyzer:
    """Compare multiple scenarios and provide insights."""
    
    def __init__(self):
        self.comparison_results = {}
    
    def compare_scenarios(self, scenario_results: Dict[str, Dict]) -> Dict:
        """Compare multiple scenario results."""
        print("Comparing scenarios...")
        
        comparison = {
            'scenarios': list(scenario_results.keys()),
            'metrics': {}
        }
        
        # Extract key metrics from each scenario
        for scenario_name, results in scenario_results.items():
            if 'simulated_predictions' in results:
                sim_df = results['simulated_predictions']
                
                comparison['metrics'][scenario_name] = {
                    'total_waste': sim_df['simulated_waste'].sum(),
                    'average_waste': sim_df['simulated_waste'].mean(),
                    'max_waste': sim_df['simulated_waste'].max(),
                    'waste_change': sim_df.get('waste_change', pd.Series([0])).sum(),
                    'waste_change_percentage': sim_df.get('waste_change_percentage', pd.Series([0])).mean()
                }
        
        # Calculate comparative statistics
        if len(comparison['metrics']) > 1:
            total_wastes = [m['total_waste'] for m in comparison['metrics'].values()]
            comparison['comparative_stats'] = {
                'min_total_waste': min(total_wastes),
                'max_total_waste': max(total_wastes),
                'range_total_waste': max(total_wastes) - min(total_wastes),
                'best_scenario': min(comparison['metrics'].items(), key=lambda x: x[1]['total_waste'])[0],
                'worst_scenario': max(comparison['metrics'].items(), key=lambda x: x[1]['total_waste'])[0]
            }
        
        self.comparison_results = comparison
        
        return comparison
    
    def rank_scenarios(self, scenario_results: Dict[str, Dict], 
                     criteria: List[str] = None) -> List[Tuple[str, float]]:
        """Rank scenarios by multiple criteria."""
        if criteria is None:
            criteria = ['total_waste', 'waste_change_percentage']
        
        rankings = []
        
        for scenario_name, results in scenario_results.items():
            score = 0
            
            if 'simulated_predictions' in results:
                sim_df = results['simulated_predictions']
                
                # Lower waste is better
                if 'total_waste' in criteria:
                    normalized_waste = sim_df['simulated_waste'].sum() / 1000000  # Normalize
                    score -= normalized_waste
                
                # Positive waste reduction is better
                if 'waste_reduction_percentage' in criteria and 'waste_reduction_percentage' in sim_df.columns:
                    score += sim_df['waste_reduction_percentage'].mean()
            
            rankings.append((scenario_name, score))
        
        # Sort by score (descending)
        rankings.sort(key=lambda x: x[1], reverse=True)
        
        return rankings

# =========================================================
# DECISION SUPPORT SYSTEM
# =========================================================

class DecisionSupportSystem:
    """Provide decision support based on scenario analysis."""
    
    def __init__(self):
        self.recommendations = []
    
    def generate_recommendations(self, scenario_results: Dict, 
                                baseline_scenario: str = 'baseline') -> List[Dict]:
        """Generate actionable recommendations based on scenario analysis."""
        print("Generating decision support recommendations...")
        
        recommendations = []
        
        baseline = scenario_results.get(baseline_scenario)
        if baseline is None:
            recommendations.append({
                'type': 'warning',
                'message': 'Baseline scenario not found for comparison'
            })
            return recommendations
        
        # Analyze each scenario
        for scenario_name, results in scenario_results.items():
            if scenario_name == baseline_scenario:
                continue
            
            if 'simulated_predictions' in results:
                sim_df = results['simulated_predictions']
                baseline_df = baseline['simulated_predictions']
                
                # Calculate improvement
                total_waste_reduction = baseline_df['ensemble_prediction'].sum() - sim_df['simulated_waste'].sum()
                waste_reduction_percentage = (total_waste_reduction / baseline_df['ensemble_prediction'].sum()) * 100
                
                if waste_reduction_percentage > 5:
                    recommendations.append({
                        'type': 'recommendation',
                        'scenario': scenario_name,
                        'action': f'Implement {scenario_name} scenario',
                        'expected_benefit': f'{waste_reduction_percentage:.1f}% waste reduction',
                        'priority': 'high' if waste_reduction_percentage > 15 else 'medium',
                        'confidence': 0.8
                    })
                elif waste_reduction_percentage < -5:
                    recommendations.append({
                        'type': 'warning',
                        'scenario': scenario_name,
                        'action': f'Avoid {scenario_name} scenario',
                        'expected_impact': f'{abs(waste_reduction_percentage):.1f}% waste increase',
                        'priority': 'high'
                    })
        
        self.recommendations = recommendations
        return recommendations
    
    def optimize_parameters(self, objective_function, 
                          parameter_bounds: Dict,
                          n_iterations: int = 100) -> Dict:
        """Optimize parameters to achieve desired outcome."""
        print("Optimizing parameters...")
        
        # Define bounds
        bounds = list(parameter_bounds.values())
        param_names = list(parameter_bounds.keys())
        
        # Initial guess (middle of bounds)
        x0 = [(b[0] + b[1]) / 2 for b in bounds]
        
        # Optimize
        result = minimize(
            objective_function,
            x0,
            bounds=bounds,
            method='L-BFGS-B',
            options={'maxiter': n_iterations}
        )
        
        optimal_params = {
            param_names[i]: result.x[i]
            for i in range(len(param_names))
        }
        
        return {
            'optimal_parameters': optimal_params,
            'objective_value': result.fun,
            'success': result.success,
            'message': result.message
        }

# =========================================================
# MAIN EXECUTION
# =========================================================

def main():
    print("=" * 70)
    print("SCENARIO ANALYSIS AND WHAT-IF CAPABILITIES")
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
    
    # Initialize scenario manager
    print("\n" + "=" * 70)
    print("SCENARIO MANAGEMENT")
    print("=" * 70)
    
    scenario_manager = ScenarioManager()
    
    # Create predefined scenarios
    baseline_scenario = scenario_manager.create_scenario(
        'baseline',
        'Current operational conditions without changes'
    )
    baseline_scenario.set_parameter('event_intensity', 1.0)
    baseline_scenario.set_parameter('weather_multiplier', 1.0)
    baseline_scenario.set_parameter('collection_efficiency', 1.0)
    
    optimistic_scenario = scenario_manager.create_scenario(
        'optimistic',
        'Best-case scenario with improved conditions'
    )
    optimistic_scenario.set_parameter('event_intensity', 0.8)
    optimistic_scenario.set_parameter('weather_multiplier', 0.95)
    optimistic_scenario.set_parameter('collection_efficiency', 1.15)
    
    pessimistic_scenario = scenario_manager.create_scenario(
        'pessimistic',
        'Worst-case scenario with adverse conditions'
    )
    pessimistic_scenario.set_parameter('event_intensity', 1.3)
    pessimistic_scenario.set_parameter('weather_multiplier', 1.1)
    pessimistic_scenario.set_parameter('collection_efficiency', 0.9)
    
    print(f"Created {len(scenario_manager.list_scenarios())} scenarios")
    
    # Sensitivity analysis
    print("\n" + "=" * 70)
    print("SENSITIVITY ANALYSIS")
    print("=" * 70)
    
    sensitivity_analyzer = SensitivityAnalyzer()
    
    base_prediction = predictions_df['ensemble_prediction'].mean()
    parameters = {
        'event_intensity': 1.0,
        'weather_multiplier': 1.0,
        'collection_efficiency': 1.0
    }
    parameter_ranges = {
        'event_intensity': (0.5, 2.0),
        'weather_multiplier': (0.7, 1.3),
        'collection_efficiency': (0.8, 1.2)
    }
    
    sensitivity_results = sensitivity_analyzer.one_at_a_time_sensitivity(
        base_prediction, parameters, parameter_ranges
    )
    
    print("Sensitivity analysis results:")
    for param_name, results in sensitivity_results.items():
        print(f"  {param_name}:")
        print(f"    Sensitivity: {results['sensitivity']:.4f}")
        print(f"    Prediction range: {results['min_prediction']:.2f} - {results['max_prediction']:.2f} kg")
    
    # What-if simulations
    print("\n" + "=" * 70)
    print("WHAT-IF SIMULATIONS")
    print("=" * 70)
    
    what_if_simulator = WhatIfSimulator()
    
    # Event scenario
    event_results = what_if_simulator.simulate_event_scenario(
        predictions_df.head(100),  # Sample for faster processing
        event_intensity=1.5,
        event_duration_days=3
    )
    print(f"Event scenario: {event_results['total_waste_increase']:.2f} kg increase")
    
    # Weather scenario
    weather_results = what_if_simulator.simulate_weather_scenario(
        predictions_df.head(100),
        weather_condition='extreme_heat',
        severity=0.8
    )
    print(f"Weather scenario: {weather_results['total_waste_change']:.2f} kg change")
    
    # Policy scenario
    policy_results = what_if_simulator.simulate_policy_scenario(
        predictions_df.head(100),
        policy_type='waste_reduction_campaign',
        policy_strength=0.8
    )
    print(f"Policy scenario: {policy_results['total_waste_reduction']:.2f} kg reduction")
    
    # Comparative analysis
    print("\n" + "=" * 70)
    print("COMPARATIVE SCENARIO ANALYSIS")
    print("=" * 70)
    
    comparative_analyzer = ComparativeScenarioAnalyzer()
    
    scenario_results = {
        'baseline': baseline_scenario.to_dict(),
        'optimistic': optimistic_scenario.to_dict(),
        'pessimistic': pessimistic_scenario.to_dict()
    }
    
    comparison = comparative_analyzer.compare_scenarios(scenario_results)
    print("Scenario comparison completed")
    
    # Decision support
    print("\n" + "=" * 70)
    print("DECISION SUPPORT")
    print("=" * 70)
    
    decision_system = DecisionSupportSystem()
    
    what_if_scenario_results = {
        'event_scenario': event_results,
        'weather_scenario': weather_results,
        'policy_scenario': policy_results
    }
    
    recommendations = decision_system.generate_recommendations(what_if_scenario_results)
    
    print("Generated recommendations:")
    for rec in recommendations:
        print(f"  [{rec['type'].upper()}] {rec['message'] if 'message' in rec else rec['action']}")
        if 'expected_benefit' in rec:
            print(f"    Benefit: {rec['expected_benefit']}")
        if 'priority' in rec:
            print(f"    Priority: {rec['priority']}")
    
    # Save scenario results
    results_file = SCENARIO_DIR / "scenario_analysis_results.json"
    all_results = {
        'sensitivity_analysis': sensitivity_results,
        'what_if_simulations': what_if_scenario_results,
        'comparative_analysis': comparison,
        'recommendations': recommendations,
        'generated_at': datetime.now().isoformat()
    }
    
    with open(results_file, 'w') as f:
        json.dump(all_results, f, indent=2, default=str)
    
    print(f"\nScenario analysis results saved to: {results_file}")
    
    print("\n" + "=" * 70)
    print("SCENARIO ANALYSIS COMPLETED")
    print("=" * 70)

if __name__ == "__main__":
    main()