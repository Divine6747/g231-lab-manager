import requests
from requests.auth import HTTPBasicAuth

# Test data
test_data = {
    'id': '1',
    'zone': 'TEST',
    'item_name': 'Test Update',
    'identifier': 'TEST-123',
    'notes': 'Testing update endpoint',
    'power_draw_amps': '1.5'
}

# Make request
response = requests.post(
    'https://imarinventory.pythonanywhere.com/update',
    data=test_data,
    auth=HTTPBasicAuth('admin', 'G231_An_Cuan'),
    headers={'X-Requested-With': 'XMLHttpRequest'}
)

print(f"Status: {response.status_code}")
print(f"Response: {response.text}")
