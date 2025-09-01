#!/usr/bin/env python3
"""
YAML Config Diff Viewer
A web-based tool to visualize differences between YAML configuration files.
"""

import os
import json
import yaml
import threading
import time
from pathlib import Path
from typing import Dict, Any, List, Optional, Set
from collections import defaultdict
from dataclasses import dataclass
from flask import Flask, render_template, jsonify, request
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

app = Flask(__name__)

@dataclass
class DiffInfo:
    """Information about differences at a specific path."""
    values: Dict[str, Any]  # filename -> value
    is_different: bool

class YAMLDiffAnalyzer:
    """Analyzes YAML files to find differences between configurations."""
    
    def __init__(self, configs_dir: str):
        self.configs_dir = Path(configs_dir)
        self.file_data: Dict[str, Dict] = {}
        self.tree_structure: Dict = {}
        self.differences: Dict[str, DiffInfo] = {}
        self.lock = threading.Lock()
        
    def load_yaml_files(self) -> None:
        """Load all YAML files from the configs directory."""
        with self.lock:
            self.file_data.clear()
            
            for yaml_path in self.configs_dir.rglob("*.yaml"):
                try:
                    with open(yaml_path, 'r') as f:
                        data = yaml.safe_load(f)
                    
                    # Store relative path as key
                    rel_path = yaml_path.relative_to(self.configs_dir)
                    self.file_data[str(rel_path)] = data or {}
                    
                except Exception as e:
                    print(f"Error loading {yaml_path}: {e}")
    
    def _flatten_dict(self, d: Dict, parent_key: str = '', sep: str = '.') -> Dict[str, Any]:
        """Flatten a nested dictionary."""
        items = []
        for k, v in d.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else k
            if isinstance(v, dict):
                items.extend(self._flatten_dict(v, new_key, sep=sep).items())
            else:
                items.append((new_key, v))
        return dict(items)
    
    def _group_files_by_directory(self) -> Dict[str, List[str]]:
        """Group files by their directory level."""
        groups = defaultdict(list)
        
        for file_path in self.file_data.keys():
            path_parts = Path(file_path).parts
            if len(path_parts) == 1:  # Root level files
                groups[''].append(file_path)
            else:
                # Group by directory
                dir_path = str(Path(*path_parts[:-1]))
                groups[dir_path].append(file_path)
        
        return groups
    
    def _find_differences_in_group(self, file_paths: List[str]) -> Dict[str, DiffInfo]:
        """Find differences between files in the same group."""
        if len(file_paths) <= 1:
            return {}
        
        differences = {}
        
        # Get all flattened configs for this group
        flat_configs = {}
        for file_path in file_paths:
            if file_path in self.file_data:
                flat_configs[file_path] = self._flatten_dict(self.file_data[file_path])
        
        # Find all possible keys across all files
        all_keys = set()
        for config in flat_configs.values():
            all_keys.update(config.keys())
        
        # Check each key for differences
        for key in all_keys:
            values = {}
            for file_path in file_paths:
                if file_path in flat_configs:
                    values[file_path] = flat_configs[file_path].get(key, "<missing>")
            
            # Check if values are different
            unique_values = set(str(v) for v in values.values() if v != "<missing>")
            is_different = len(unique_values) > 1 or "<missing>" in values.values()
            
            if is_different:
                # Convert full paths to just filenames for display
                filename_values = {}
                for file_path, value in values.items():
                    filename = Path(file_path).name
                    filename_values[filename] = value
                differences[key] = DiffInfo(values=filename_values, is_different=True)
        
        return differences
    
    def analyze_differences(self) -> None:
        """Analyze differences between YAML files."""
        with self.lock:
            self.differences.clear()
            
            # Group files by directory
            file_groups = self._group_files_by_directory()
            
            # Find differences within each group
            for group_dir, file_paths in file_groups.items():
                group_diffs = self._find_differences_in_group(file_paths)
                
                # Store with group prefix
                for key, diff_info in group_diffs.items():
                    full_key = f"{group_dir}/{key}" if group_dir else key
                    self.differences[full_key] = diff_info
    
    def build_tree_structure(self) -> Dict:
        """Build a hierarchical tree structure of the configs."""
        with self.lock:
            tree = {}
            
            for file_path in self.file_data.keys():
                parts = Path(file_path).parts
                current = tree
                
                # Build directory structure
                for part in parts[:-1]:
                    if part not in current:
                        current[part] = {'type': 'directory', 'children': {}}
                    current = current[part]['children']
                
                # Add file
                filename = parts[-1]
                current[filename] = {
                    'type': 'file',
                    'path': file_path,
                    'data': self.file_data[file_path]
                }
            
            self.tree_structure = tree
            return tree
    
    def get_differences_for_path(self, path: str) -> List[Dict]:
        """Get differences for a specific path or directory."""
        with self.lock:
            matching_diffs = []
            
            for diff_key, diff_info in self.differences.items():
                if diff_key.startswith(path) or path == '':
                    matching_diffs.append({
                        'key': diff_key,
                        'values': diff_info.values,
                        'is_different': diff_info.is_different
                    })
            
            return matching_diffs
    
    def refresh(self) -> None:
        """Refresh all data."""
        self.load_yaml_files()
        self.analyze_differences()
        self.build_tree_structure()
    
    def _get_base_config_for_directory(self, directory: str) -> Optional[Dict]:
        """Get the first file's config in a directory as base template."""
        with self.lock:
            # Find files in the specified directory
            target_files = []
            for file_path in self.file_data.keys():
                path_parts = Path(file_path).parts
                file_dir = str(Path(*path_parts[:-1])) if len(path_parts) > 1 else ''
                
                if file_dir == directory:
                    target_files.append(file_path)
            
            if not target_files:
                return None
            
            # Sort to get consistent "first" file
            target_files.sort()
            first_file = target_files[0]
            
            return self.file_data.get(first_file, {})
    
    def _apply_overrides_to_config(self, base_config: Dict, overrides: Dict[str, Any]) -> Dict:
        """Apply flat overrides to a nested config, maintaining structure."""
        import copy
        
        # Deep copy the base config
        new_config = copy.deepcopy(base_config)
        
        # Apply each override
        for flat_key, value in overrides.items():
            if value is None or value == "":
                continue
            
            # Strip directory prefix from the key if present
            # Keys might come in as "directory/actual.config.key"
            if '/' in flat_key:
                # Find the last '/' that separates directory from config key
                key_parts = flat_key.split('/')
                # Take everything after the directory part
                clean_key = key_parts[-1] if len(key_parts) > 1 else flat_key
                # If there are multiple slashes, we need to handle nested directory structures
                # Look for the pattern where we have a dot after a slash (config.key pattern)
                config_key_start = -1
                for i, part in enumerate(key_parts):
                    if '.' in part:
                        config_key_start = i
                        break
                if config_key_start >= 0:
                    clean_key = '.'.join(key_parts[config_key_start:])
                else:
                    clean_key = key_parts[-1]
            else:
                clean_key = flat_key
                
            # Convert clean key to nested path
            keys = clean_key.split('.')
            current = new_config
            
            # Navigate to the parent of the target key
            for key in keys[:-1]:
                if key not in current:
                    current[key] = {}
                current = current[key]
            
            # Set the final value, converting string representations back to proper types
            final_key = keys[-1]
            try:
                # Try to parse as JSON for proper type conversion
                if isinstance(value, str):
                    if value.lower() == 'true':
                        current[final_key] = True
                    elif value.lower() == 'false':
                        current[final_key] = False
                    elif value.lower() == 'null':
                        current[final_key] = None
                    else:
                        try:
                            # Try to parse as number or JSON
                            import json
                            current[final_key] = json.loads(value)
                        except:
                            # Keep as string
                            current[final_key] = value
                else:
                    current[final_key] = value
            except:
                current[final_key] = value
        
        return new_config

class ConfigFileHandler(FileSystemEventHandler):
    """Handle file system events for YAML config files."""
    
    def __init__(self, analyzer: YAMLDiffAnalyzer):
        self.analyzer = analyzer
        self.last_refresh = 0
        self.refresh_delay = 1  # seconds
    
    def on_modified(self, event):
        if not event.is_directory and event.src_path.endswith('.yaml'):
            self._schedule_refresh()
    
    def on_created(self, event):
        if not event.is_directory and event.src_path.endswith('.yaml'):
            self._schedule_refresh()
    
    def on_deleted(self, event):
        if not event.is_directory and event.src_path.endswith('.yaml'):
            self._schedule_refresh()
    
    def _schedule_refresh(self):
        """Schedule a refresh with debouncing."""
        current_time = time.time()
        if current_time - self.last_refresh > self.refresh_delay:
            self.last_refresh = current_time
            threading.Timer(self.refresh_delay, self.analyzer.refresh).start()

# Global analyzer instance
analyzer = YAMLDiffAnalyzer('/home/letouwen/yamltool/configs')

@app.route('/')
def index():
    """Main page."""
    return render_template('index.html')

@app.route('/api/tree')
def get_tree():
    """Get the tree structure."""
    tree = analyzer.build_tree_structure()
    return jsonify(tree)

@app.route('/api/differences')
@app.route('/api/differences/<path:config_path>')
def get_differences(config_path=''):
    """Get differences for a specific path."""
    differences = analyzer.get_differences_for_path(config_path)
    return jsonify(differences)

@app.route('/api/refresh')
def refresh():
    """Manually refresh the data."""
    analyzer.refresh()
    return jsonify({'status': 'refreshed'})

@app.route('/api/create-config', methods=['POST'])
def create_config():
    """Create a new configuration file."""
    from flask import request
    import json
    
    data = request.get_json()
    filename = data.get('filename', '').strip()
    directory = data.get('directory', '').strip()
    selected_overrides = data.get('overrides', {})
    
    if not filename:
        return jsonify({'error': 'Filename is required'}), 400
    
    if not filename.endswith('.yaml'):
        filename += '.yaml'
    
    # Determine the target directory
    if directory:
        target_dir = analyzer.configs_dir / directory
    else:
        target_dir = analyzer.configs_dir
    
    target_path = target_dir / filename
    
    # Check if file already exists
    if target_path.exists():
        return jsonify({'error': f'File {filename} already exists in {directory or "root"}'}), 400
    
    try:
        # Get the first file in the directory as base template
        base_config = analyzer._get_base_config_for_directory(directory)
        if not base_config:
            return jsonify({'error': 'No base configuration found for directory'}), 400
        
        # Apply selected overrides
        new_config = analyzer._apply_overrides_to_config(base_config, selected_overrides)
        
        # Ensure target directory exists
        target_dir.mkdir(parents=True, exist_ok=True)
        
        # Write the new configuration
        with open(target_path, 'w') as f:
            yaml.dump(new_config, f, default_flow_style=False, indent=2)
        
        # Refresh the analyzer
        analyzer.refresh()
        
        return jsonify({
            'status': 'created',
            'filename': filename,
            'path': str(target_path.relative_to(analyzer.configs_dir))
        })
        
    except Exception as e:
        return jsonify({'error': f'Failed to create config: {str(e)}'}), 500

def setup_file_watcher():
    """Set up file system watcher."""
    event_handler = ConfigFileHandler(analyzer)
    observer = Observer()
    observer.schedule(event_handler, analyzer.configs_dir, recursive=True)
    observer.start()
    return observer

if __name__ == '__main__':
    # Initial load
    print("Loading YAML configurations...")
    analyzer.refresh()
    print(f"Loaded {len(analyzer.file_data)} YAML files")
    
    # Start file watcher (optional)
    observer = None
    try:
        print("Setting up file watcher...")
        observer = setup_file_watcher()
        print("File watcher started successfully")
    except Exception as e:
        print(f"Warning: Could not start file watcher: {e}")
        print("Manual refresh will be required for file changes")
    
    try:
        print("Starting web server...")
        print("Access the application at: http://localhost:5000")
        print("For SSH access, use port forwarding: ssh -L 5000:localhost:5000 user@host")
        app.run(debug=True, host='0.0.0.0', port=5000, use_reloader=False)
    except KeyboardInterrupt:
        if observer:
            observer.stop()
    
    if observer:
        observer.join()
