#!/usr/bin/env python3

def parse_key(flat_key):
    """Test the key parsing logic."""
    print(f"Original key: {flat_key}")
    
    if '/' in flat_key:
        # Find the last '/' that separates directory from config key
        key_parts = flat_key.split('/')
        print(f"Key parts: {key_parts}")
        
        # Take everything after the directory part
        clean_key = key_parts[-1] if len(key_parts) > 1 else flat_key
        print(f"Initial clean_key: {clean_key}")
        
        # If there are multiple slashes, we need to handle nested directory structures
        # Look for the pattern where we have a dot after a slash (config.key pattern)
        config_key_start = -1
        for i, part in enumerate(key_parts):
            if '.' in part:
                config_key_start = i
                break
        
        print(f"Config key start index: {config_key_start}")
        
        if config_key_start >= 0:
            clean_key = '.'.join(key_parts[config_key_start:])
        else:
            clean_key = key_parts[-1]
            
        print(f"Final clean_key: {clean_key}")
    else:
        clean_key = flat_key
        print(f"No slash, using original: {clean_key}")
    
    return clean_key

# Test cases
test_keys = [
    "FedAML-Large-HI/fedsize/federation.number_of_clients",
    "FedAML-Large-HI/fedsize/federation.tau", 
    "federation.epochs_per_round",
    "dataset.dir",
    "gnn.act"
]

print("Testing key parsing logic:")
print("=" * 50)

for key in test_keys:
    result = parse_key(key)
    print(f"Result: {result}")
    print("-" * 30)
