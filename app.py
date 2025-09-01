#!/usr/bin/env python3
"""
YAML Config Diff Viewer
A web-based tool to visualize differences between YAML configuration files.
"""

import os
import json
import yaml
import threading
import subprocess
import tempfile
import getpass
from pathlib import Path
import time
from pathlib import Path
from typing import Dict, Any, List, Optional, Set
from collections import defaultdict
from dataclasses import dataclass
from flask import Flask, render_template, jsonify, request
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Load configuration
def load_config():
    """Load configuration from config.json"""
    config_path = Path(__file__).parent / 'config.json'
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    
    with open(config_path, 'r') as f:
        return json.load(f)

# Global configuration
CONFIG = load_config()

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
analyzer = YAMLDiffAnalyzer(CONFIG['paths']['configs_directory'])

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

@app.route('/api/submit-slurm', methods=['POST'])
def submit_slurm_job():
    """Create sbatch file and submit SLURM job."""
    data = request.get_json()
    job_name = data.get('jobName', '').strip()
    use_gpu = data.get('useGpu', False)
    memory = data.get('memory', '64G')
    config_path = data.get('configPath', '').strip()
    
    if not job_name:
        return jsonify({'error': 'Job name is required'}), 400
    
    if not config_path:
        return jsonify({'error': 'Config path is required'}), 400
    
    try:
        # Create sbatch file content
        sbatch_content = create_sbatch_content(job_name, use_gpu, memory, config_path)
        
        # Create temporary sbatch file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False) as f:
            f.write(sbatch_content)
            sbatch_file_path = f.name
        
        try:
            # Submit job via SSH
            job_result = submit_job_via_ssh(sbatch_file_path, job_name)
            
            if job_result.get('manual_submission'):
                return jsonify({
                    'status': 'ready_for_manual_submission',
                    'jobName': job_name,
                    'manual_submission': True,
                    'sbatch_file': os.path.basename(job_result.get('sbatch_file', '')),
                    'message': job_result.get('message', 'Sbatch file created for manual submission'),
                    'instructions': job_result.get('instructions', ''),
                    'error': job_result.get('error')
                })
            else:
                return jsonify({
                    'status': 'submitted',
                    'jobId': job_result.get('job_id'),
                    'sbatchFile': os.path.basename(sbatch_file_path),
                    'message': job_result.get('message', 'Job submitted successfully')
                })
            
        finally:
            # Clean up temporary file
            try:
                os.unlink(sbatch_file_path)
            except:
                pass
                
    except Exception as e:
        return jsonify({'error': f'Failed to submit job: {str(e)}'}), 500

def create_sbatch_content(job_name, use_gpu, memory, config_path):
    """Create sbatch file content based on the template."""
    slurm_config = CONFIG['slurm']
    
    # Try to read from template file first
    template_file = Path(CONFIG['paths']['slurm_template_file'])
    if template_file.exists():
        try:
            with open(template_file, 'r') as f:
                template_content = f.read()
            
            # Replace placeholders in the template
            content = template_content.format(
                job_name=job_name,
                memory=memory,
                config_path=config_path,
                gpu_line="#SBATCH --gres=gpu:1               # Request 1 GPU" if use_gpu else "",
                partition=slurm_config.get('default_partition', 'general'),
                time=slurm_config.get('default_time', '12:00:00'),
                nodes=slurm_config.get('default_nodes', 1),
                output_pattern=slurm_config.get('output_pattern', 'slurm-%j.out'),
                error_pattern=slurm_config.get('error_pattern', 'slurm-%j.err')
            )
            return content
        except Exception as e:
            print(f"Warning: Could not read template file {template_file}: {e}")
            # Fall back to hardcoded template
    
    # Fallback hardcoded template
    gpu_line = "#SBATCH --gres=gpu:1               # Request 1 GPU" if use_gpu else ""
    
    return f"""#!/bin/sh
#SBATCH --job-name={job_name}
#SBATCH --account=ewi-st-dis
#SBATCH --qos=medium 
#SBATCH --partition={slurm_config.get('default_partition', 'general')}        # Request partition.
#SBATCH --exclude=influ[1-6],insy[15-16],awi[01-02]
#SBATCH --time={slurm_config.get('default_time', '12:00:00')}            # Request run time (wall-clock). Default is 1 minute
#SBATCH --nodes={slurm_config.get('default_nodes', 1)}                  # Request 1 node
#SBATCH --tasks-per-node=1         # Set one task per node
{gpu_line}
#SBATCH --mem={memory}
#SBATCH --mail-type=END            # Set mail type to 'END' to receive a mail when the job finishes. %j is the Slurm jobId
#SBATCH --output=./output/{slurm_config.get('output_pattern', 'slurm-%j.out')}
#SBATCH --error=./output/{slurm_config.get('error_pattern', 'slurm-%j.err')}

# Increase file descriptor limit
ulimit -n 65536

# Assuming you have a dedicated directory for *.sif files
export APPTAINER_ROOT="/tudelft.net/staff-umbrella/ScalableGraphLearning/apptainer"
export APPTAINER_NAME="pytorch2.2.2-cuda11.8-ubuntu22.04-Federated.sif"

nvidia-smi

srun apptainer exec \\
  --nv \\
  -B /home/nfs/letouwen/megagnn_graphgym:/home/$USER/megagnn_graphgym \\
  -B /tudelft.net/staff-umbrella/ScalableGraphLearning/lourens/data:/mnt/lourens/data \\
  -B /tudelft.net/staff-umbrella/ScalableGraphLearning/lourens/exps/:/mnt/lourens/exps/results \\
  $APPTAINER_ROOT/$APPTAINER_NAME \\
  python -m MegaGNN.main --cfg {config_path}
"""

def submit_job_via_ssh(sbatch_file_path, job_name):
    """Submit job via SSH to login node."""
    import os
    import pexpect
    from pathlib import Path
    
    try:
        ssh_config = CONFIG['ssh']
        slurm_config = CONFIG['slurm']
        working_dir = CONFIG['paths']['working_directory']
        
        # Check if credentials file exists
        creds_file = Path(working_dir) / ssh_config.get('credentials_file', 'secret.txt')
        if not creds_file.exists():
            # Fall back to manual submission if no credentials
            return manual_submission_fallback(sbatch_file_path, job_name, f"Credentials file not found: {creds_file}. Create this file with username on first line and password on second line for automated submission.")
        
        # Read credentials
        try:
            with open(creds_file) as f:
                lines = f.read().strip().splitlines()
                if len(lines) >= 2:
                    username, password = lines[0], lines[1]
                else:
                    raise ValueError("Invalid credentials file format")
        except Exception as e:
            print(f"Error reading credentials: {e}")
            return manual_submission_fallback(sbatch_file_path, job_name, f"Could not read credentials file: {e}")
        
        ssh_host = slurm_config['ssh_host']
        full_ssh_host = f"login3.daic.tudelft.nl" if ssh_host == "daic" else ssh_host
        
        print(f"Attempting automated SSH submission to {full_ssh_host}...")
        
        # Read the sbatch file content
        with open(sbatch_file_path, 'r') as f:
            sbatch_content = f.read()
        
        # Create a local copy with a proper name
        local_sbatch_name = f"run_{job_name}.sh"
        local_sbatch_path = os.path.join(working_dir, local_sbatch_name)
        
        with open(local_sbatch_path, 'w') as f:
            f.write(sbatch_content)
        
        # Make it executable
        os.chmod(local_sbatch_path, 0o755)
        
        print(f"Created sbatch file: {local_sbatch_path}")
        
        # Submit job via SSH with pexpect
        usr = slurm_config.get('ssh_user', 'username')
        rel_path = local_sbatch_path.split(usr)[1][1:]
        ssh_cmd = f"sbatch {rel_path}"
        timeout = ssh_config.get('command_timeout', 30)
        
        try:
            child = pexpect.spawn(f"ssh {username}@{full_ssh_host} '{ssh_cmd}'", timeout=timeout)
            child.expect("password:")
            child.sendline(password)
            
            # Wait for either the command to complete or timeout
            index = child.expect([pexpect.EOF, pexpect.TIMEOUT])
            
            if index == 0:  # EOF - command completed
                output = child.before.decode().strip()
                print(f"SSH command output: {output}")
                child.close()
                
                # Parse SLURM output to extract job ID
                job_id = None
                for line in output.split('\n'):
                    if 'Submitted batch job' in line:
                        try:
                            job_id = line.split()[-1]
                        except:
                            pass
                
                if job_id:
                    print(f"Job submitted successfully with ID: {job_id}")
                    return {
                        'job_id': job_id,
                        'message': f'Job submitted successfully with ID: {job_id}',
                        'sbatch_file': local_sbatch_path,
                        'manual_submission': False,
                        'ssh_output': output
                    }
                else:
                    print(f"Job submission unclear. Output: {output}")
                    return {
                        'job_id': None,
                        'message': f'Job submission status unclear. Output: {output}',
                        'sbatch_file': local_sbatch_path,
                        'manual_submission': False,
                        'ssh_output': output
                    }
            else:  # Timeout
                child.close(force=True)
                print(f"SSH command timed out after {timeout} seconds")
                return manual_submission_fallback(sbatch_file_path, job_name, 
                                                f"SSH command timed out after {timeout} seconds")
                
        except pexpect.exceptions.ExceptionPexpect as e:
            print(f"SSH connection failed: {e}")
            return manual_submission_fallback(sbatch_file_path, job_name, f"SSH connection failed: {e}")
        
    except Exception as e:
        print(f"Automated submission failed: {e}")
        return manual_submission_fallback(sbatch_file_path, job_name, f"Automated submission failed: {e}")

def manual_submission_fallback(sbatch_file_path, job_name, error_msg=None):
    """Fallback to manual submission instructions."""
    import os
    
    ssh_config = CONFIG['ssh']
    slurm_config = CONFIG['slurm']
    working_dir = CONFIG['paths']['working_directory']
    ssh_host = slurm_config['ssh_host']
    
    print("Falling back to manual submission...")
    
    # Read the sbatch file content
    with open(sbatch_file_path, 'r') as f:
        sbatch_content = f.read()
    
    # Create a local copy with a proper name
    local_sbatch_name = f"run_{job_name}.sh"
    local_sbatch_path = os.path.join(working_dir, local_sbatch_name)
    
    with open(local_sbatch_path, 'w') as f:
        f.write(sbatch_content)
    
    # Make it executable
    os.chmod(local_sbatch_path, 0o755)
    
    print(f"Created sbatch file: {local_sbatch_path}")
    
    # Create manual instructions (without error section since it's shown separately in UI)
    instructions = f"""
MANUAL SUBMISSION REQUIRED:

Copy and paste these commands in your terminal:

ssh {ssh_host}
cd {working_dir}
sbatch {local_sbatch_path}
squeue -u $USER
exit

After the job completes, check the output:

ssh {ssh_host}
cat slurm-*.out
exit

The sbatch file has been created at: {local_sbatch_path}
"""
    
    return {
        'job_id': None,
        'message': 'Sbatch file created for manual submission',
        'instructions': instructions,
        'sbatch_file': local_sbatch_path,
        'manual_submission': True,
        'error': error_msg
    }

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
    file_watching_config = CONFIG.get('file_watching', {})
    if file_watching_config.get('enabled', True):
        try:
            print("Setting up file watcher...")
            observer = setup_file_watcher()
            print("File watcher started successfully")
        except Exception as e:
            print(f"Warning: Could not start file watcher: {e}")
            print("Manual refresh will be required for file changes")
    else:
        print("File watching disabled in configuration")
    
    try:
        app_config = CONFIG['app']
        host = app_config.get('host', '0.0.0.0')
        port = app_config.get('port', 5000)
        debug = app_config.get('debug', True)
        
        print("Starting web server...")
        print(f"Access the application at: http://localhost:{port}")
        print(f"For SSH access, use port forwarding: ssh -L {port}:localhost:{port} user@host")
        app.run(debug=debug, host=host, port=port, use_reloader=False)
    except KeyboardInterrupt:
        if observer:
            observer.stop()
    
    if observer:
        observer.join()
