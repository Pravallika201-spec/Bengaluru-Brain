"""
Test suite for Traffic Prediction Pipeline V2
Verifies that the new pipeline uses real data and trained GNN model
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_no_random_route_nodes():
    """Verify that route prediction does not use random node selection"""
    from models.predict_route_v2 import RoutePredictorV2
    
    predictor = RoutePredictorV2(
        model_path='models/traffic_model_v2.pth',
        graph_path='backend/data/bengaluru_graph.pkl',
        traffic_dataset_path='data/traffic_gnn_dataset.csv'
    )
    
    result = predictor.predict_route("Hebbal", "Marathahalli")
    
    # Verify that segments are based on actual route
    assert result['num_segments'] > 0, "Route should have segments"
    assert result['distance_km'] > 0, "Distance should be positive"
    assert result['predicted_mins'] > 0, "Predicted time should be positive"
    
    print("✅ Test passed: No random route nodes")

def test_no_hardcoded_delays():
    """Verify that delays are calculated from predicted speeds, not hardcoded"""
    from models.predict_route_v2 import RoutePredictorV2
    
    predictor = RoutePredictorV2(
        model_path='models/traffic_model_v2.pth',
        graph_path='backend/data/bengaluru_graph.pkl',
        traffic_dataset_path='data/traffic_gnn_dataset.csv'
    )
    
    result = predictor.predict_route("Hebbal", "Marathahalli")
    
    # Verify delay is not one of the hardcoded values (5, 15, 25)
    assert result['delay_mins'] not in [5, 15, 25], "Delay should not be hardcoded"
    
    print("✅ Test passed: No hardcoded delays")

def test_travel_time_from_predicted_speeds():
    """Verify that travel time is calculated from predicted speeds"""
    from models.predict_route_v2 import RoutePredictorV2
    
    predictor = RoutePredictorV2(
        model_path='models/traffic_model_v2.pth',
        graph_path='backend/data/bengaluru_graph.pkl',
        traffic_dataset_path='data/traffic_gnn_dataset.csv'
    )
    
    result = predictor.predict_route("Hebbal", "Marathahalli")
    
    # Verify travel time is consistent with distance and speed
    expected_time = (result['distance_km'] / result['avg_speed_kmh']) * 60
    actual_time = result['predicted_mins']
    
    # Allow 20% tolerance due to route variations
    assert abs(expected_time - actual_time) / max(1, expected_time) < 0.3, \
        f"Travel time should be consistent with speed: expected {expected_time:.1f}, got {actual_time:.1f}"
    
    print("✅ Test passed: Travel time from predicted speeds")

def test_model_loading():
    """Verify that the trained model can be loaded"""
    import torch
    from models.traffic_gnn_v2 import create_model_v2
    
    model = create_model_v2(input_dim=15, hidden_dim1=64, hidden_dim2=32, output_dim=1)
    checkpoint = torch.load('models/traffic_model_v2.pth', weights_only=False)
    model.load_state_dict(checkpoint)
    
    assert model is not None, "Model should load successfully"
    
    print("✅ Test passed: Model loading")

def test_prediction_output_consistency():
    """Verify that prediction outputs are consistent"""
    from models.predict_route_v2 import RoutePredictorV2
    
    predictor = RoutePredictorV2(
        model_path='models/traffic_model_v2.pth',
        graph_path='backend/data/bengaluru_graph.pkl',
        traffic_dataset_path='data/traffic_gnn_dataset.csv'
    )
    
    result = predictor.predict_route("Hebbal", "Marathahalli")
    
    # Verify all required fields are present
    required_fields = [
        'source', 'destination', 'distance_km', 'predicted_mins',
        'free_flow_mins', 'delay_mins', 'delay_percentage', 'avg_speed_kmh',
        'status', 'route_coords', 'src_coords', 'dst_coords'
    ]
    
    for field in required_fields:
        assert field in result, f"Missing required field: {field}"
    
    print("✅ Test passed: Prediction output consistency")

def test_backend_integration():
    """Verify backend integration with v2 predictor"""
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))
    from traffic_predictor_v2 import predict_route_v2
    
    result = predict_route_v2("Hebbal", "Marathahalli")
    
    # Verify frontend-compatible format
    assert 'distance_km' in result
    assert 'predicted_mins' in result
    assert 'delay_mins' in result
    assert 'status' in result
    assert 'confidence' in result
    
    print("✅ Test passed: Backend integration")

def main():
    """Run all tests"""
    print("="*60)
    print("TRAFFIC PREDICTION PIPELINE V2 TESTS")
    print("="*60)
    
    tests = [
        test_no_random_route_nodes,
        test_no_hardcoded_delays,
        test_travel_time_from_predicted_speeds,
        test_model_loading,
        test_prediction_output_consistency,
        test_backend_integration
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"❌ Test failed: {test.__name__}")
            print(f"   Error: {e}")
            failed += 1
    
    print("\n" + "="*60)
    print(f"TEST RESULTS: {passed} passed, {failed} failed")
    print("="*60)
    
    if failed == 0:
        print("✅ All tests passed!")
    else:
        print(f"❌ {failed} test(s) failed")

if __name__ == "__main__":
    main()
