# YAML Config Tool

Tool to visualize differences between YAML configuration files, create new configurations, and submit SLURM jobs.

# Setup and Run

One-time setup
1. Clone repository `git clone https://github.com/LourensT/yamltool.git`
2. go into the directory `cd yamltool`
3. Edit `config.json` to match your paths and settings
  * Most important are the paths. 
    * `configs_directory`: Directory containing your YAML config files
    * `working_directory`: Directory for temporary files (can be the yamltool directory)
    * `slurm_template_file`: Path to your SLURM job submission example. **The tool assumes that the location of this file is from where slurmjobs should be submitted!**
4. Create a `secret.txt` file with two lines: one with your username and one with your netid pwd. 
5. Make a virtualenv (python 3.10 or above)
  * When using venv: 
  ```bash
  python -m venv venv
  source venv/bin/activate
  ```
  * when using conda: 
  ```bash
  conda create --name yamltool python=3.10
  conda activate yamltool
  ```
6. While in active virtual environment
```bash
pip install flask pyyaml watchdog pexpect
```
Run

7. Run `python app.py`
8. Open http://localhost:5000 or as specified in config
      - if yamltool is running on your workstation, do `ssh -L 5000:localhost:5000 user@remote_host` 
      - if using VPN, use the VS Code Simple Browser! (Cmd + Shift + P, search "Simple Browser")

## Configuration

The tool is configured via `config.json`:

### App Settings
```json
{
  "app": {
    "host": "0.0.0.0",     // Server host
    "port": 5000,          // Server port
    "debug": true          // Debug mode
  }
}
```

### Paths
```json
{
  "paths": {
    "configs_directory": "/path/to/configs",     // Directory containing YAML files
    "slurm_template_file": "/path/to/run.sh",   // SLURM example file, this filepath is also where new slurmjobs will be submitted from!
    "working_directory": "/path/to/work"       // Working directory for tool (temps and secret.txt)
  }
}
```

### SLURM Settings
```json
{
  "slurm": {
    "default_partition": "general",
    "default_time": "12:00:00",
    "default_mem": "8G",
    "ssh_host": "daic",                          // SSH hostname for cluster, probably login3.daic.tudelft.nl
    "ssh_user": "username",             
    "output_pattern": "slurm-%j.out",
    "error_pattern": "slurm-%j.err"
  }
}
```

### SSH & Authentication
```json
{
  "ssh": {
    "connection_timeout": 10,
    "command_timeout": 30,
    "requires_password": true,
    "credentials_file": "secret.txt"           // Filename in working_dir containing username and password (one per line)
  }
}
```

**Credentials File Format (`secret.txt`)**:
```
username
password
```

### File Watching
```json
{
  "file_watching": {
    "enabled": true,                             // Enable automatic file watching
    "recursive": true,                           // Watch subdirectories
    "patterns": ["*.yaml", "*.yml"]              // File patterns to watch
  }
}
```

## SLURM Template

If you provide a `slurm_template_file` in your configuration, the tool will use it as a template for job submissions. The template can include placeholders:

- `{job_name}` - Job name
- `{memory}` - Memory allocation
- `{config_path}` - Path to config file
- `{gpu_line}` - GPU allocation line (if GPU requested)
- `{partition}` - SLURM partition
- `{time}` - Time limit
- `{nodes}` - Number of nodes
- `{output_pattern}` - Output file pattern
- `{error_pattern}` - Error file pattern

Example template:
```bash
#!/bin/sh
#SBATCH --job-name={job_name}
#SBATCH --partition={partition}
#SBATCH --time={time}
#SBATCH --nodes={nodes}
#SBATCH --mem={memory}
{gpu_line}
#SBATCH --output={output_pattern}
#SBATCH --error={error_pattern}

# Your job commands here
python your_script.py --config {config_path}
```
