from models.predict_route_v2 import RoutePredictorV2

predictor = RoutePredictorV2(
    model_path='models/traffic_model_v2.pth',
    graph_path='backend/data/bengaluru_graph.pkl',
    traffic_dataset_path='data/traffic_gnn_dataset.csv'
)

result = predictor.predict_route('Hebbal', 'Silk Board')

print('=== PREDICTION RESULT ===')
print(f'Source: {result["source"]}')
print(f'Destination: {result["destination"]}')
print(f'Distance: {result["distance_km"]} km')
print(f'Predicted time: {result["predicted_mins"]} mins')
print(f'Free flow time: {result["free_flow_mins"]} mins')
print(f'Delay: {result["delay_mins"]} mins ({result["delay_percentage"]}%)')
print(f'Average speed: {result["avg_speed_kmh"]} km/h')
print(f'Status: {result["status"]}')
print(f'Number of segments: {result["num_segments"]}')
print(f'Model info: {result["model_info"]}')
print(f'Temporal limitation: {result["temporal_limitation"]}')
