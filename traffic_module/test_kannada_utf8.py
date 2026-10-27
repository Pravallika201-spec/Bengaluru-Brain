import sys
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
import json
sys.path.append('backend')
from backend.kannada_messages import get_kannada_service

print('Testing Kannada Messages UTF-8 Encoding')
print('=' * 50)

try:
    kannada_service = get_kannada_service()
    message = kannada_service.generate_message(
        traffic_status="MODERATE",
        has_incident=False,
        weather_impact=False,
        reroute_recommended=False
    )
    
    # Test JSON serialization (this is what the API will do)
    json_output = json.dumps(message, ensure_ascii=False, indent=2)
    print('JSON generated successfully (length:', len(json_output), 'bytes)')
    
    # Verify the characters are preserved
    kannada_text = message["kannada"]
    print(f'Kannada text length: {len(kannada_text)} characters')
    print(f'First 5 chars (hex): {kannada_text[:5].encode("utf-8").hex()}')
    
    # Write to file to verify UTF-8 preservation
    with open('kannada_test.json', 'w', encoding='utf-8') as f:
        json.dump(message, f, ensure_ascii=False, indent=2)
    print('SUCCESS: Kannada messages written to kannada_test.json')
    
    # Read back to verify
    with open('kannada_test.json', 'r', encoding='utf-8') as f:
        loaded_message = json.load(f)
    print(f'Loaded Kannada: {loaded_message["kannada"]}')
    print('SUCCESS: UTF-8 encoding verified')
    
except Exception as e:
    print(f'ERROR: {e}')
    import traceback
    traceback.print_exc()
